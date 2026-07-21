"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    This file is intended to be hosting algorithms and utility functions/classes
    for centerline tool.
"""

import enum
from itertools import compress

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
import shapely.geometry as sh_geom
import shapely.ops as sh_ops
# Lazy-imported in find_centerline() to avoid ~5s startup cost
# from beratools.external.polygon_centerline import get_centerline

import beratools.core.algo_common as algo_common
import beratools.core.algo_cost as algo_cost
import beratools.core.algo_astar as algo_astar
import beratools.core.algo_geometry as algo_geometry
import beratools.core.alt_spatial_common as alt_sp_common
import beratools.core.algo_dijkstra as bt_dijkstra
import beratools.core.constants as bt_const
import beratools.core.tool_base as bt_base
import beratools.core.tool_geo_simplify as tool_geo_simplify
import beratools.utility.spatial_common as sp_common


class CenterlineParams(float, enum.Enum):
    """
    Parameters for centerline generation.

    These parameters are used to control the behavior of centerline generation
    and should be adjusted based on the specific requirements of the application.
    """

    BUFFER_CLIP = 5.0
    SEGMENTIZE_LENGTH = 1.0
    SIMPLIFY_LENGTH = 0.5
    SMOOTH_SIGMA = 0.8
    CLEANUP_POLYGON_BY_AREA = 1.0
    ENDPOINT_ANCHOR_TOL = 1e-9
    GUIDED_FALLBACK_MAX_SNAP = 2.0


@enum.unique
class CenterlineStatus(enum.IntEnum):
    """
    Status of centerline generation.

    This enum is used to indicate the status of centerline generation.
    It can be used to track the success or failure of the centerline generation process.

    """

    SUCCESS = 1
    FAILED = 2
    REGENERATE_SUCCESS = 3
    REGENERATE_FAILED = 4


def centerline_is_valid(centerline, input_line):
    """
    Check if centerline is valid.

    Args:
        centerline (_type_): _description_
        input_line (sh_geom.LineString): Seed line or least cost path.
        Only two end points are used.

    Returns:
        bool: True if line is valid

    """
    if not centerline:
        return False

    # centerline length less the half of least cost path
    if (
        centerline.length < input_line.length / 2
        or centerline.distance(sh_geom.Point(input_line.coords[0])) > bt_const.BT_EPSILON
        or centerline.distance(sh_geom.Point(input_line.coords[-1])) > bt_const.BT_EPSILON
    ):
        return False

    return True


def snap_end_to_end(in_line, line_reference, max_snap_dist=None):
    if type(in_line) is sh_geom.MultiLineString:
        in_line = sh_ops.linemerge(in_line)
        if type(in_line) is sh_geom.MultiLineString:
            algo_common.log_file_only(
                f"algo_centerline: MultiLineString found {in_line.centroid}, pass.",
                logger_name=__name__,
            )
            return None

    pts = list(in_line.coords)
    if len(pts) < 2:
        print("snap_end_to_end: input line invalid.")
        return in_line

    line_start = sh_geom.Point(pts[0])
    line_end = sh_geom.Point(pts[-1])
    ref_ends = sh_geom.MultiPoint([line_reference.coords[0], line_reference.coords[-1]])

    _, snap_start = sh_ops.nearest_points(line_start, ref_ends)
    _, snap_end = sh_ops.nearest_points(line_end, ref_ends)

    start_dist = line_start.distance(snap_start)
    end_dist = line_end.distance(snap_end)

    if in_line.has_z:
        snap_start = shapely.force_3d(snap_start)
        snap_end = shapely.force_3d(snap_end)
    else:
        snap_start = shapely.force_2d(snap_start)
        snap_end = shapely.force_2d(snap_end)

    if max_snap_dist is None or start_dist <= max_snap_dist:
        pts[0] = snap_start.coords[0]
    if max_snap_dist is None or end_dist <= max_snap_dist:
        pts[-1] = snap_end.coords[0]

    return sh_geom.LineString(pts)


def _is_endpoint_anchored(centerline, seed_line, tol=CenterlineParams.ENDPOINT_ANCHOR_TOL):
    if centerline is None or seed_line is None:
        return False

    if not isinstance(centerline, sh_geom.LineString):
        return False
    if not isinstance(seed_line, sh_geom.LineString):
        return False

    cl_coords = list(centerline.coords)
    seed_coords = list(seed_line.coords)
    if len(cl_coords) < 2 or len(seed_coords) < 2:
        return False

    cl_start = sh_geom.Point(cl_coords[0])
    cl_end = sh_geom.Point(cl_coords[-1])
    seed_start = sh_geom.Point(seed_coords[0])
    seed_end = sh_geom.Point(seed_coords[-1])

    direct = cl_start.distance(seed_start) <= tol and cl_end.distance(seed_end) <= tol
    reversed_match = cl_start.distance(seed_end) <= tol and cl_end.distance(seed_start) <= tol
    return direct or reversed_match


def _trim_and_snap_centerline(centerline, input_line, max_snap_dist=None):
    cl_coords = list(centerline.coords)

    head_buffer = sh_geom.Point(cl_coords[0]).buffer(CenterlineParams.BUFFER_CLIP)
    centerline = centerline.difference(head_buffer)

    end_buffer = sh_geom.Point(cl_coords[-1]).buffer(CenterlineParams.BUFFER_CLIP)
    centerline = centerline.difference(end_buffer)

    if not centerline:
        return None

    try:
        if centerline.is_empty:
            return None
    except Exception as e:
        print(f"find_centerline: {e}")

    return snap_end_to_end(centerline, input_line, max_snap_dist=max_snap_dist)


def _extract_centerline_from_polygon(
    poly,
    src_geom,
    dst_geom,
    guided_strategy,
):
    from beratools.external.polygon_centerline import get_centerline

    return get_centerline(
        poly,
        segmentize_maxlen=1,
        max_points=3000,
        simplification=0.05,
        smooth_sigma=CenterlineParams.SMOOTH_SIGMA,
        max_paths=1,
        src_geom=src_geom,
        dst_geom=dst_geom,
        guided_strategy=guided_strategy,
    )


def find_centerline(poly, input_line, guided_strategy="main_route"):
    """
    Find centerline from polygon and input line.

    Args:
        poly : sh_geom.Polygon
        input_line ( sh_geom.LineString): Least cost path or seed line

    Returns:
    centerline (sh_geom.LineString): Centerline
    status (CenterlineStatus): Status of centerline generation

    """
    default_return = input_line, CenterlineStatus.FAILED
    valid_guided_strategies = {"main_route", "pairwise", "virtual_nodes", "direct_insert"}
    if guided_strategy not in valid_guided_strategies:
        raise ValueError("guided_strategy must be one of {}".format(sorted(valid_guided_strategies)))
    effective_strategy = guided_strategy

    if not poly:
        algo_common.log_file_only("find_centerline: No polygon found")
        return default_return

    poly = shapely.segmentize(poly, max_segment_length=CenterlineParams.SEGMENTIZE_LENGTH)

    # buffer to reduce MultiPolygons
    poly = poly.buffer(bt_const.SMALL_BUFFER)
    if type(poly) is sh_geom.MultiPolygon:
        print("sh_geom.MultiPolygon encountered, skip.")
        return default_return

    exterior_pts = list(poly.exterior.coords)

    if bt_const.CenterlineFlags.DELETE_HOLES:
        poly = sh_geom.Polygon(exterior_pts)
    if bt_const.CenterlineFlags.SIMPLIFY_POLYGON:
        poly = poly.simplify(CenterlineParams.SIMPLIFY_LENGTH)

    line_coords = list(input_line.coords)

    src_geom = None
    dst_geom = None
    if guided_strategy in {"pairwise", "virtual_nodes", "direct_insert"}:
        src_geom = sh_geom.Point(line_coords[0])
        dst_geom = sh_geom.Point(line_coords[-1])

    try:
        centerline = _extract_centerline_from_polygon(
            poly,
            src_geom,
            dst_geom,
            guided_strategy,
        )
    except Exception as e:
        error_msg = str(e)
        if error_msg == "endpoint-guided extraction failed for provided endpoints":
            algo_common.log_file_only(f"find_centerline: {error_msg}")
        else:
            print(f"find_centerline: {e}")
        centerline = None

    if not centerline and guided_strategy in {"pairwise", "virtual_nodes", "direct_insert"}:
        if guided_strategy == "pairwise":
            algo_common.log_file_only("find_centerline: pairwise guidance failed, retrying main_route")
        else:
            print(f"find_centerline: {guided_strategy} guidance failed, retrying main_route")
        try:
            centerline = _extract_centerline_from_polygon(
                poly,
                None,
                None,
                "main_route",
            )
            if centerline:
                effective_strategy = "main_route"
        except Exception as e:
            print(f"find_centerline: main_route retry failed: {e}")
            return default_return

    if not centerline:
        return default_return

    if type(centerline) is sh_geom.MultiLineString:
        if len(centerline.geoms) > 1:
            print(" Multiple centerline segments detected, no further processing.")
            return centerline, CenterlineStatus.SUCCESS  # TODO: inspect
        elif len(centerline.geoms) == 1:
            centerline = centerline.geoms[0]
        else:
            return default_return

    needs_trim_snap = effective_strategy == "main_route"
    if effective_strategy in {"pairwise", "virtual_nodes"}:
        needs_trim_snap = not _is_endpoint_anchored(
            centerline,
            input_line,
            tol=CenterlineParams.ENDPOINT_ANCHOR_TOL,
        )

    if needs_trim_snap:
        max_snap_dist = None
        if effective_strategy in {"pairwise", "virtual_nodes"}:
            max_snap_dist = CenterlineParams.GUIDED_FALLBACK_MAX_SNAP
        centerline = _trim_and_snap_centerline(
            centerline,
            input_line,
            max_snap_dist=max_snap_dist,
        )
        if not centerline:
            return default_return

    # Check centerline. If valid, regenerate by splitting polygon into two halves.
    if not centerline_is_valid(centerline, input_line):
        try:
            algo_common.log_file_only("Regenerating line ...", logger_name=__name__)
            centerline = regenerate_centerline(poly, input_line)
            return centerline, CenterlineStatus.REGENERATE_SUCCESS
        except Exception as e:
            print(f"find_centerline: {e}")
            return input_line, CenterlineStatus.REGENERATE_FAILED

    return centerline, CenterlineStatus.SUCCESS


def find_corridor_polygon(corridor_thresh, in_transform, line_gpd, exp_shk_cell=0):
    # Threshold corridor raster used for generating centerline
    corridor_thresh_cl = algo_common.corridor_threshold_to_mask(corridor_thresh)
    corridor_thresh_cl = algo_common.generalize_binary_mask(corridor_thresh_cl, exp_shk_cell)
    if corridor_thresh_cl.dtype == np.int64:
        corridor_thresh_cl = corridor_thresh_cl.astype(np.int32)

    corridor_mask = np.where(1 == corridor_thresh_cl, True, False)
    poly_generator = rasterio.features.shapes(corridor_thresh_cl, mask=corridor_mask, transform=in_transform)
    corridor_polygon = []

    try:
        for poly, value in poly_generator:
            if sh_geom.shape(poly).area > 1:
                corridor_polygon.append(sh_geom.shape(poly))
    except Exception as e:
        print(f"find_corridor_polygon: {e}")

    if corridor_polygon:
        corridor_polygon = sh_ops.unary_union(corridor_polygon)
        if type(corridor_polygon) is sh_geom.MultiPolygon:
            poly_list = shapely.get_parts(corridor_polygon)
            merge_poly = poly_list[0]
            for i in range(1, len(poly_list)):
                if shapely.intersects(merge_poly, poly_list[i]):
                    merge_poly = shapely.union(merge_poly, poly_list[i])
                else:
                    buffer_dist = poly_list[i].distance(merge_poly) + 0.1
                    buffer_poly = poly_list[i].buffer(buffer_dist)
                    merge_poly = shapely.union(merge_poly, buffer_poly)
            corridor_polygon = merge_poly
    else:
        corridor_polygon = None

    # create GeoDataFrame for centerline
    corridor_poly_gpd = gpd.GeoDataFrame.copy(line_gpd)
    corridor_poly_gpd.geometry = [corridor_polygon]

    return corridor_poly_gpd


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
    return bool(value)


def process_single_centerline(row_and_path):
    """
    Find centerline.

    Args:
    row_and_path (list of row (gdf and lc_path)): and least cost path
    first is GeoPandas row, second is input line, (least cost path)

    Returns:
    row: GeoPandas row with centerline

    """
    row = row_and_path[0]
    lc_path = row_and_path[1]

    poly = row.geometry.iloc[0]
    centerline, status = find_centerline(poly, lc_path)
    row["centerline"] = centerline

    return row


def find_centerlines(poly_gpd, line_seg, processes):
    centerline_gpd = []
    rows_and_paths = []

    try:
        for i in poly_gpd.index:
            row = poly_gpd.loc[[i]]
            if "OLnSEG" in line_seg.columns:
                line_id, Seg_id = row["OLnFID"].iloc[0], row["OLnSEG"].iloc[0]
                lc_path = line_seg.loc[(line_seg.OLnFID == line_id) & (line_seg.OLnSEG == Seg_id)][
                    "geometry"
                ].iloc[0]
            else:
                line_id = row["OLnFID"].iloc[0]
                lc_path = line_seg.loc[(line_seg.OLnFID == line_id)]["geometry"].iloc[0]

            rows_and_paths.append((row, lc_path))
    except Exception as e:
        print(f"find_centerlines: {e}")

    centerline_gpd = bt_base.execute_multiprocessing(
        process_single_centerline, rows_and_paths, "find_centerlines", processes, 1
    )
    return pd.concat(centerline_gpd)


def regenerate_centerline(poly, input_line):
    """
    Regenerates centerline when initial poly is not valid.

    Args:
        input_line (sh_geom.LineString): Seed line or least cost path.
        Only two end points will be used

    Returns:
        sh_geom.MultiLineString

    """
    line_1 = sh_ops.substring(input_line, start_dist=0.0, end_dist=input_line.length / 2)
    line_2 = sh_ops.substring(input_line, start_dist=input_line.length / 2, end_dist=input_line.length)

    pts = shapely.force_2d(
        [
            sh_geom.Point(list(input_line.coords)[0]),
            sh_geom.Point(list(line_1.coords)[-1]),
            sh_geom.Point(list(input_line.coords)[-1]),
        ]
    )
    perp = algo_common.generate_perpendicular_line_precise(pts)

    # sh_geom.MultiPolygon is rare, but need to be dealt with
    # remove polygon of area less than CenterlineParams.CLEANUP_POLYGON_BY_AREA
    poly = poly.buffer(bt_const.SMALL_BUFFER)
    if type(poly) is sh_geom.MultiPolygon:
        poly_geoms = list(poly.geoms)
        poly_valid = [True] * len(poly_geoms)
        for i, item in enumerate(poly_geoms):
            if item.area < CenterlineParams.CLEANUP_POLYGON_BY_AREA:
                poly_valid[i] = False

        poly_geoms = list(compress(poly_geoms, poly_valid))
        if len(poly_geoms) != 1:  # still multi polygon
            print("regenerate_centerline: Multi or none polygon found, pass.")

        poly = sh_geom.Polygon(poly_geoms[0])

    poly_exterior = sh_geom.Polygon(poly.buffer(bt_const.SMALL_BUFFER).exterior)
    poly_split = sh_ops.split(poly_exterior, perp)

    if len(poly_split.geoms) < 2:
        algo_common.log_file_only(
            "regenerate_centerline: polygon sh_ops.split failed, pass.", logger_name=__name__
        )
        return None

    poly_1 = poly_split.geoms[0]
    poly_2 = poly_split.geoms[1]

    # find polygon and line pairs
    pair_line_1 = line_1
    pair_line_2 = line_2
    if not poly_1.intersects(line_1):
        pair_line_1 = line_2
        pair_line_2 = line_1
    elif poly_1.intersection(line_1).length < line_1.length / 3:
        pair_line_1 = line_2
        pair_line_2 = line_1

    center_line_1 = find_centerline(poly_1, pair_line_1)
    center_line_2 = find_centerline(poly_2, pair_line_2)

    center_line_1 = center_line_1[0]
    center_line_2 = center_line_2[0]

    if not center_line_1 or not center_line_2:
        print("Regenerate line: centerline is None")
        return None

    try:
        if center_line_1.is_empty or center_line_2.is_empty:
            print("Regenerate line: centerline is empty")
            return None
    except Exception as e:
        print(f"regenerate_centerline: {e}")

    algo_common.log_file_only("Centerline is regenerated.", logger_name=__name__)
    return sh_ops.linemerge(sh_geom.MultiLineString([center_line_1, center_line_2]))


class SeedLine:
    """Class to store seed line and least cost path."""

    def __init__(
        self,
        line_gdf,
        ras_file,
        proc_segments,
        line_radius,
        guided_strategy="main_route",
        centerline_method=bt_const.CENTERLINE_METHOD.value,
        lcp_simplify_enabled=False,
        lcp_simplify_diameter=10.0,
        lcp_smooth_enabled=False,
        lcp_smooth_iterations=1,
        chm_mode=bt_const.CENTERLINE_CHM_MODE.value,
        astar_corridor_line_bias_weight=0.1,
        astar_corridor_distance_penalty_weight=0.2,
        corridor_simplify_polygon=False,
        corridor_simplify_length=0.5,
        corridor_smooth_polygon=False,
        corridor_polygon_smooth_iterations=1,
    ):
        self.line = line_gdf
        self.raster = ras_file
        self.line_radius = line_radius
        self.tree_radius = 2.5
        self.guided_strategy = guided_strategy
        self.centerline_method = centerline_method
        self.lcp_simplify_enabled = _to_bool(lcp_simplify_enabled)
        self.lcp_simplify_diameter = float(lcp_simplify_diameter)
        self.lcp_smooth_enabled = _to_bool(lcp_smooth_enabled)
        self.lcp_smooth_iterations = max(int(lcp_smooth_iterations), 0)
        if isinstance(chm_mode, bt_const.CenterlineChmMode):
            chm_mode = chm_mode.value
        if chm_mode not in {mode.value for mode in bt_const.CenterlineChmMode}:
            valid_modes = [mode.value for mode in bt_const.CenterlineChmMode]
            raise ValueError("chm_mode must be one of {}".format(valid_modes))
        self.chm_mode = chm_mode
        self.astar_corridor_line_bias_weight = max(float(astar_corridor_line_bias_weight), 0.0)
        self.astar_corridor_distance_penalty_weight = max(float(astar_corridor_distance_penalty_weight), 0.0)
        self.corridor_simplify_polygon = _to_bool(corridor_simplify_polygon)
        self.corridor_simplify_length = max(float(corridor_simplify_length), 0.0)
        self.corridor_smooth_polygon = _to_bool(corridor_smooth_polygon)
        self.corridor_polygon_smooth_iterations = max(int(corridor_polygon_smooth_iterations), 0)
        self.lc_path = None
        self.centerline = None
        self.corridor_poly_gpd = None

    def compute(self):
        line = self.line.geometry[0]
        line_radius = self.line_radius
        in_raster = self.raster
        seed_line = line  # LineString
        chm_mode = self.chm_mode

        # search for lcp
        try:
            if chm_mode in ["current"]:
                ras_clip, out_meta = self._clip_chm(in_raster, seed_line, line_radius)
                cost_clip, _ = algo_cost.cost_raster(ras_clip, out_meta)

            else:# chm_mode in ["alt"]:
                ras_clip, out_meta, tree_gaps = self._clip_chm(in_raster, seed_line, line_radius)
                cost_clip, _ = algo_cost.alt_cost_raster(ras_clip, out_meta, tree_gaps)


            if self.centerline_method == bt_const.CenterlineMethod.ASTAR.value:
                lc_path = algo_astar.find_least_cost_path_astar_closest_line(cost_clip, out_meta, seed_line)
            elif bt_const.CenterlineFlags.USE_SKIMAGE_GRAPH:
                lc_path = bt_dijkstra.alt_find_least_cost_path_skimage(self, cost_clip, out_meta, seed_line,
                                                                       offset_test=True)
            else:
                lc_path = bt_dijkstra.find_least_cost_path(cost_clip, out_meta, seed_line)

            if chm_mode in ["alt"]:
                if algo_common._hausdorff_dist(lc_path, seed_line) > line_radius / 2:
                    lc_path = line

        except Exception as e:
            print(e)
            return

        if lc_path:
            lc_path_coords = lc_path.coords
        else:
            lc_path_coords = []

        # search for centerline
        if len(lc_path_coords) < 2:
            algo_common.log_file_only("No least cost path detected, use input line.", logger_name=__name__)
            self.line["cl_status"] = CenterlineStatus.FAILED.value
            return

        # get corridor raster
        lc_path = sh_geom.LineString(lc_path_coords)
        lc_path = self._postprocess_lcp(lc_path, out_meta.get("crs"))
        lc_path_coords = list(lc_path.coords)

        ras_clip, out_meta, *_ = self._clip_chm(in_raster, lc_path, line_radius * 0.9)
        cost_clip, _ = algo_cost.cost_raster(ras_clip, out_meta)

       
        out_transform = out_meta["transform"]
        transformer = rasterio.transform.AffineTransformer(out_transform)
        cell_size = (out_transform[0], -out_transform[4])
        if self.centerline_method == bt_const.CenterlineMethod.BERA.value:
            x1, y1 = lc_path_coords[0]
            x2, y2 = lc_path_coords[-1]
            source = [transformer.rowcol(x1, y1)]
            destination = [transformer.rowcol(x2, y2)]
            corridor_thresh_cl = algo_common.corridor_raster(
                cost_clip,
                out_meta,
                source,
                destination,
                cell_size,
                bt_const.FP_CORRIDOR_THRESHOLD,
            )
        elif self.centerline_method == bt_const.CenterlineMethod.BERA_ALONG.value:
            corridor_thresh_cl = algo_common.alt_MCP_along_corridor_raster(
                cost_clip,
                out_meta,
                lc_path,
                cell_size,
                corridor_threshold=bt_const.FP_CORRIDOR_THRESHOLD,
            )

        elif self.centerline_method == bt_const.CenterlineMethod.ASTAR_ALONG.value:
            corridor_thresh_cl,_ = algo_astar.alt_astar_accumulation_corridor_raster(
                cost_clip,
                out_meta,
                lc_path,
                corridor_threshold=bt_const.FP_CORRIDOR_THRESHOLD,
                line_bias_weight=self.astar_corridor_line_bias_weight,
                distance_penalty_weight=self.astar_corridor_distance_penalty_weight,
            )


        elif self.centerline_method == bt_const.CenterlineMethod.ASTAR.value:
            corridor_thresh_cl, _details = algo_astar.astar_accumulation_corridor_raster(
                cost_clip,
                out_meta,
                lc_path,
                corridor_threshold=bt_const.FP_CORRIDOR_THRESHOLD,
                line_bias_weight=self.astar_corridor_line_bias_weight,
                distance_penalty_weight=self.astar_corridor_distance_penalty_weight,
            )

        # find contiguous corridor polygon and extract centerline
        df = gpd.GeoDataFrame(geometry=[seed_line], crs=out_meta["crs"])
        corridor_poly_gpd = find_corridor_polygon(corridor_thresh_cl, out_transform, df)
        corridor_poly_gpd = self._postprocess_corridor_polygon(corridor_poly_gpd)
        center_line, status = find_centerline(
            corridor_poly_gpd.geometry.iloc[0],
            lc_path,
            guided_strategy=self.guided_strategy,
        )
        self.line["cl_status"] = status.value

        self.lc_path = self.line.copy()
        self.lc_path.geometry = [lc_path]
        self.lc_path["centerline_method"] = self.centerline_method
        self.lc_path["lcp_simplified"] = bool(self.lcp_simplify_enabled and self.lcp_simplify_diameter > 0)
        self.lc_path["lcp_smoothed"] = bool(self.lcp_smooth_enabled and self.lcp_smooth_iterations > 0)

        self.centerline = self.line.copy()
        self.centerline.geometry = [center_line]
        self.centerline["centerline_method"] = self.centerline_method

        self.corridor_poly_gpd = corridor_poly_gpd
        self.corridor_poly_gpd["centerline_method"] = self.centerline_method

    def _clip_chm(self, in_raster, clip_geometry, buffer):
        if self.chm_mode == bt_const.CenterlineChmMode.ALT.value:
            ras_clip, out_meta,_,_,_,tree_gaps = alt_sp_common.alt_clip_and_filter_regional_maxima_wgap(
                self, #{"tree_radius": 2.5},
                in_raster,
                clip_geometry,
                buffer,
            )
            return ras_clip, out_meta,tree_gaps
        return sp_common.clip_raster(in_raster, clip_geometry, buffer)

    def _postprocess_lcp(self, lc_path, crs):
        processed = lc_path
        if self.lcp_simplify_enabled and self.lcp_simplify_diameter > 0:
            processed = tool_geo_simplify.simplify_line_reduce_bend(
                processed,
                crs=crs,
                diameter=self.lcp_simplify_diameter,
                smooth_line=True,
            )
        if self.lcp_smooth_enabled and self.lcp_smooth_iterations > 0:
            processed = algo_geometry.chaikin_smooth_line(
                processed,
                iterations=self.lcp_smooth_iterations,
            )
        return processed

    def _postprocess_corridor_polygon(self, corridor_poly_gpd):
        polygon = corridor_poly_gpd.geometry.iloc[0]
        processed = algo_geometry.process_corridor_polygon(
            polygon,
            delete_holes=bool(bt_const.CenterlineFlags.DELETE_HOLES),
            simplify=self.corridor_simplify_polygon,
            simplify_length=self.corridor_simplify_length,
            smooth=self.corridor_smooth_polygon,
            smooth_iterations=self.corridor_polygon_smooth_iterations,
        )
        corridor_poly_gpd = corridor_poly_gpd.copy()
        corridor_poly_gpd.geometry = [processed]
        return corridor_poly_gpd
