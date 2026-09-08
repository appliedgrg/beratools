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
from dataclasses import dataclass
from itertools import compress

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
import shapely.geometry as sh_geom
import shapely.ops as sh_ops
import logging
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
from beratools.core.logger import Logger
LOGGER_NAME = "centerline"
log = Logger(LOGGER_NAME, file_level=logging.WARNING,console_level=logging.INFO)
logger = log.get_logger()
log_print = log.print


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
    GUIDE_SAMPLE_INTERVAL = 10.0
    MIN_GUIDE_LENGTH_RATIO = 0.94
    MAX_SHORTCUT_MEDIAN_DISTANCE = 2.0


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
    CENTERLINE_FAILED_LCP_FALLBACK = 5
    LCP_FAILED_SEED_FALLBACK = 6
    THIN_POLYGON_STABILIZED_SUCCESS = 7
    ABSOLUTE_FOOTPRINT_SUCCESS = 8

@dataclass(frozen=True)
class EndPointAnchorResult:
    anchored: bool
    reversed_match: bool
    start_dist: float
    end_dist: float


def centerline_is_valid(centerline, input_line,cid=None):
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
        if cid:
            logger.info(f"{cid} validation failed: centerline is None")
        return False

    length_check = centerline.length < input_line.length / 2
    anchor_result = _is_endpoint_anchored(
        centerline,
        input_line,
        tol=bt_const.BT_EPSILON,)

    endpoint_check = not anchor_result.anchored

    if length_check or endpoint_check:
        # logger.info(
        #         f"{cid} validation failed:"
        #         f" anchored={anchor_result.anchored}, "
        #         f" reversed={anchor_result.reversed_match}, "
        #         f" start_dist={anchor_result.start_dist:.6f}, "
        #         f" end_dist={anchor_result.end_dist:.6f}")
        return False

    if _looks_like_shortcut(centerline, input_line, cid=cid):
        return False

    return True


def _looks_like_shortcut(centerline, input_line, cid=None):
    if not centerline or not input_line or input_line.length <= 0:
        return False

    length_ratio = centerline.length / input_line.length

    if length_ratio >= CenterlineParams.MIN_GUIDE_LENGTH_RATIO:
        return False

    distances = _sampled_line_distances(
        input_line,
        centerline,
        CenterlineParams.GUIDE_SAMPLE_INTERVAL,
    )

    if not distances:
        return False

    median_distance = float(np.median(distances))

    shortcut = (
        median_distance >
        CenterlineParams.MAX_SHORTCUT_MEDIAN_DISTANCE
    )

    # if cid:
    #     logger.file_only(
    #         f"{cid} shortcut check:"
    #         f" ratio={length_ratio:.3f}, "
    #         f" median_dist={median_distance:.3f}, "
    #         f" threshold_ratio={CenterlineParams.MIN_GUIDE_LENGTH_RATIO.value}, "
    #         f" threshold_dist={CenterlineParams.MAX_SHORTCUT_MEDIAN_DISTANCE.value}, "
    #         f" shortcut={shortcut}"
    #     )

    return shortcut

def _sampled_line_distances(source_line, target_line, interval):
    if interval <= 0:
        interval = 10.0
    sample_count = max(int(np.ceil(source_line.length / interval)), 1)
    distances = []
    for i in range(sample_count + 1):
        distance_along = min(i * interval, source_line.length)
        distances.append(source_line.interpolate(distance_along).distance(target_line))
    return distances


# def snap_end_to_end(in_line, line_reference, max_snap_dist=None,cid=None):
#     if type(in_line) is sh_geom.MultiLineString:
#         in_line = algo_common._safe_linemerge(in_line)
#         if type(in_line) is sh_geom.MultiLineString:
#             logger.file_only(cid+
#                 f"algo_centerline: MultiLineString found {in_line.centroid}, pass.",
#
#             )
#             return None
#
#     pts = list(in_line.coords)
#     if len(pts) < 2:
#         log_print("snap_end_to_end: input line invalid.")
#         return in_line
#
#     line_start = sh_geom.Point(pts[0])
#     line_end = sh_geom.Point(pts[-1])
#     ref_ends = sh_geom.MultiPoint([line_reference.coords[0], line_reference.coords[-1]])
#
#     _, snap_start = sh_ops.nearest_points(line_start, ref_ends)
#     _, snap_end = sh_ops.nearest_points(line_end, ref_ends)
#
#     start_dist = line_start.distance(snap_start)
#     end_dist = line_end.distance(snap_end)
#
#     if in_line.has_z:
#         snap_start = shapely.force_3d(snap_start)
#         snap_end = shapely.force_3d(snap_end)
#     else:
#         snap_start = shapely.force_2d(snap_start)
#         snap_end = shapely.force_2d(snap_end)
#
#     if max_snap_dist is None or start_dist <= max_snap_dist:
#         pts[0] = snap_start.coords[0]
#     if max_snap_dist is None or end_dist <= max_snap_dist:
#         pts[-1] = snap_end.coords[0]
#
#     return sh_geom.LineString(pts)

def snap_end_to_end(in_line, line_reference, max_snap_dist=None,cid=None):
    """
    Snap centerline ends to opposite seedline endpoints.

    Prevents:
        start -> seed_start
        end   -> seed_start

    which creates a ring.
    """

    if in_line is None or in_line.is_empty:
        return line_reference

    coords = list(in_line.coords)

    if len(coords) < 2:
        return line_reference

    cl_start = sh_geom.Point(coords[0])
    cl_end = sh_geom.Point(coords[-1])

    seed_coords = list(line_reference.coords)

    seed_start = sh_geom.Point(seed_coords[0])
    seed_end = sh_geom.Point(seed_coords[-1])

    #
    # Evaluate both possible assignments
    #
    cost_forward = (cl_start.distance(seed_start)
            + cl_end.distance(seed_end))

    cost_reverse = (cl_start.distance(seed_end)
            + cl_end.distance(seed_start))

    if abs(cost_forward - cost_reverse) < 1.0:

        seed_dir = np.array([seed_end.x - seed_start.x,
            seed_end.y - seed_start.y,])

        center_dir = np.array([cl_end.x - cl_start.x,
            cl_end.y - cl_start.y,])

        forward = np.dot(seed_dir, center_dir) >= 0

    elif cost_forward < cost_reverse:

        forward = True

    else:

        forward = False

    if forward:
        coords[0] = seed_start.coords[0]
        coords[-1] = seed_end.coords[0]
    else:
        coords[0] = seed_end.coords[0]
        coords[-1] = seed_start.coords[0]
    #
    # Safety check
    #
    if coords[0] == coords[-1]:
        # keep original geometry rather than
        # creating a ring
        return in_line

    return sh_geom.LineString(coords)

    if max_snap_dist is None or start_dist <= max_snap_dist:
        pts[0] = snap_start.coords[0]
    if max_snap_dist is None or end_dist <= max_snap_dist:
        pts[-1] = snap_end.coords[0]

    return sh_geom.LineString(pts)


def _is_endpoint_anchored(
    centerline,
    seed_line,
    tol=CenterlineParams.ENDPOINT_ANCHOR_TOL,
) -> EndPointAnchorResult:
    """
    Check whether centerline endpoints match seed endpoints.

    Returns
    -------
    EndPointAnchorResult
        anchored       : endpoints match
        reversed_match : centerline orientation is reversed
        start_dist     : endpoint distance used for evaluation
        end_dist       : endpoint distance used for evaluation
    """
    default_return = EndPointAnchorResult(
            False,
            False,
            float("inf"),
            float("inf"),
        )
    if centerline is None or seed_line is None:
        return default_return

    if not isinstance(centerline, sh_geom.LineString):
        return default_return

    if not isinstance(seed_line, sh_geom.LineString):
        return default_return

    cl_coords = list(centerline.coords)
    seed_coords = list(seed_line.coords)

    if len(cl_coords) <=1 or len(seed_coords) <=1:
        return default_return

    cl_start = sh_geom.Point(cl_coords[0])
    cl_end = sh_geom.Point(cl_coords[-1])

    seed_start = sh_geom.Point(seed_coords[0])
    seed_end = sh_geom.Point(seed_coords[-1])

    direct_start = cl_start.distance(seed_start)
    direct_end = cl_end.distance(seed_end)

    reverse_start = cl_start.distance(seed_end)
    reverse_end = cl_end.distance(seed_start)

    direct = (direct_start <= tol and direct_end <= tol)

    reversed_match = (reverse_start <= tol and reverse_end <= tol)

    if direct:
        return EndPointAnchorResult(
            anchored=True,
            reversed_match=False,
            start_dist=direct_start,
            end_dist=direct_end,)

    if reversed_match:
        return EndPointAnchorResult(
            anchored=True,
            reversed_match=True,
            start_dist=reverse_start,
            end_dist=reverse_end,)

    if (direct_start + direct_end) <= (
            reverse_start + reverse_end):
        return EndPointAnchorResult(
            anchored=False,
            reversed_match=False,
            start_dist=direct_start,
            end_dist=direct_end,
        )

    return EndPointAnchorResult(
        anchored=False,
        reversed_match=True,
        start_dist=reverse_start,
        end_dist=reverse_end,
    )


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
        log_print(f"find_centerline: {e}")

    return snap_end_to_end(centerline, input_line, max_snap_dist=max_snap_dist)


def _extract_centerline_from_polygon(
    poly,
    src_geom,
    dst_geom,
    guided_strategy,
    endpoint_mode='strict',
    endpoint_candidate_k=5,
    cell_size=1.0,
    corridor_id="UNKNOWN",
    guide_line=None,
):
    from beratools.external.polygon_centerline import get_centerline
    from beratools.external.polygon_centerline._src import get_last_centerline_info

    _extract_centerline_from_polygon.last_info = {}
    centerline = get_centerline(
        poly,
        segmentize_maxlen=1,
        max_points=3000,
        simplification=0.05,
        smooth_sigma=CenterlineParams.SMOOTH_SIGMA,
        max_paths=1,
        src_geom=src_geom,
        dst_geom=dst_geom,
        guided_strategy=guided_strategy,
        endpoint_mode=endpoint_mode,
        endpoint_candidate_k=endpoint_candidate_k,
        cell_size=cell_size,
        corridor_id=corridor_id,
        input_line=guide_line,
    )
    _extract_centerline_from_polygon.last_info = get_last_centerline_info()
    return centerline


_extract_centerline_from_polygon.last_info = {}


def _last_extraction_used_stabilized_voronoi():
    info = getattr(_extract_centerline_from_polygon, "last_info", {}) or {}
    return info.get("qhull_retry") not in {None, "none"} or bool(info.get("polygon_stabilized"))


def find_centerline(poly, input_line,
                    guided_strategy="main_route",
                    endpoint_mode=None,
                    endpoint_candidate_k=8,
                    allow_regeneration=True,
                    cell_size=1.0,
                    corridor_id="UNKNOWN",
                    ):
    """
    Find centerline from polygon and input line.

    Args:
        poly : sh_geom.Polygon
        input_line ( sh_geom.LineString): Least cost path or seed line

    Returns:
    centerline (sh_geom.LineString): Centerline
    status (CenterlineStatus): Status of centerline generation

    """
    cid = f"[CID={corridor_id}] " if corridor_id else "[CID=UNKNOWN] "
    default_return = input_line, CenterlineStatus.FAILED
    valid_guided_strategies = {"main_route", "pairwise", "virtual_nodes", "direct_insert"}
    ordered_valid_guided_strategies = ["pairwise", "virtual_nodes", "direct_insert", "main_route"]
    if guided_strategy not in valid_guided_strategies:
        raise ValueError("guided_strategy must be one of {}".format(sorted(valid_guided_strategies)))
    effective_strategy = guided_strategy

    if not poly:
        logger.info(cid+
                         f"find_centerline: No polygon found")
        return default_return

    poly = shapely.segmentize(poly, max_segment_length=CenterlineParams.SEGMENTIZE_LENGTH)

    # buffer to reduce MultiPolygons
    poly = poly.buffer(bt_const.SMALL_BUFFER)
    if type(poly) is sh_geom.MultiPolygon:
        log_print("sh_geom.MultiPolygon encountered, skip.")
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
        start_covered = poly.buffer(0.5).covers(src_geom)
        end_covered = poly.buffer(0.5).covers(dst_geom)
        buffer_dist=-0.5
        inner_poly=poly
        # to prevent buffering from shrinking the polygon but use min buffer
        for buffer_dist in np.arange(-0.5,0.00,0.05):
            try_buffer = poly.buffer(buffer_dist)
            if try_buffer.is_empty:
                break
            if try_buffer.area<CenterlineParams.CLEANUP_POLYGON_BY_AREA:
                break
            inner_poly=try_buffer

        src_geom = src_geom if start_covered else sh_ops.nearest_points(src_geom, inner_poly)[1]
        dst_geom = dst_geom if end_covered else sh_ops.nearest_points(dst_geom,inner_poly )[1]

        # if endpoint_mode is None:
        endpoint_mode = ("strict" if start_covered and end_covered else "soft")
        if not (start_covered and end_covered):
            guided_strategy = "main_route"
            effective_strategy = "main_route"

    else:
        if endpoint_mode is None:
            endpoint_mode = "soft"
    try: #first attempt to extract centerline
        centerline = _extract_centerline_from_polygon(
            poly,
            src_geom,
            dst_geom,
            guided_strategy,
            endpoint_mode,
            endpoint_candidate_k,
            cell_size=cell_size,
            corridor_id=corridor_id,
            guide_line=input_line)

    except Exception as e:
        error_msg = str(e)
        logger.warning(cid+f"find_centerline: {error_msg}")
        centerline = None

    if not centerline and guided_strategy in {"pairwise", "virtual_nodes", "direct_insert"}:
        if guided_strategy == "pairwise":
            logger.warning(cid + "find_centerline: pairwise guidance failed, trying fallback strategies", )
        else:
            logger.warning(cid +
                           f"find_centerline: {guided_strategy} guidance failed, trying fallback strategies")
        # Move selected strategy to the front
        execution_order = [guided_strategy] + [s for s in ordered_valid_guided_strategies if s != guided_strategy]
        i = 1
        while i < len(execution_order):
            if execution_order[i] == "main_route":
                in_src_geom = None
                in_dst_geom = None
                if endpoint_mode is None:
                    endpoint_mode = "soft"
            else:
                in_src_geom = src_geom
                in_dst_geom = dst_geom
                if endpoint_mode is None:
                    endpoint_mode = "strict"
            try:

                centerline = _extract_centerline_from_polygon(
                    poly,
                    in_src_geom,
                    in_dst_geom,
                    execution_order[i],
                    endpoint_mode,
                    endpoint_candidate_k,
                    cell_size=cell_size,
                    corridor_id=corridor_id,
                    guide_line=input_line)
            except Exception as e:
                centerline = None
                logger.warning(cid +
                                 f"find_centerline: fallback {execution_order[i]} failed: {e}")
            if centerline is not None and not centerline.is_empty:
                effective_strategy = execution_order[i]
                break
            i += 1

    if not centerline:
        return default_return

    status = CenterlineStatus.SUCCESS
    if _last_extraction_used_stabilized_voronoi():
        status = CenterlineStatus.THIN_POLYGON_STABILIZED_SUCCESS

    if type(centerline) is sh_geom.MultiLineString:
        if len(centerline.geoms) > 1:
            log_print(" Multiple centerline segments detected, no further processing.")
            return centerline, status  # TODO: inspect
        elif len(centerline.geoms) == 1:
            centerline = centerline.geoms[0]
        else:
            return default_return

    needs_trim_snap = effective_strategy == "main_route"
    if effective_strategy in {"pairwise", "virtual_nodes"}:
        result = _is_endpoint_anchored(
            centerline,
            input_line,
            tol=CenterlineParams.ENDPOINT_ANCHOR_TOL,
        )
        needs_trim_snap = not result.anchored
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
    if allow_regeneration and not centerline_is_valid(centerline, input_line,cid=cid):
        if cid == "[CID=174_0] ":
            print("debug start")
        try:
            logger.info(cid+
                             f"Regenerating line ...")
            centerline = regenerate_centerline(poly, input_line,corridor_id)
            if not centerline:
                return input_line, CenterlineStatus.REGENERATE_FAILED
            try:
                if centerline.is_empty:
                    return input_line, CenterlineStatus.REGENERATE_FAILED
            except Exception as e:
                log_print(f"find_centerline: {e}")
                return input_line, CenterlineStatus.REGENERATE_FAILED
            return centerline, CenterlineStatus.REGENERATE_SUCCESS
        except Exception as e:
            log_print(f"find_centerline: {e}")
            return input_line, CenterlineStatus.REGENERATE_FAILED

    return centerline, status


def find_corridor_polygon(corridor_thresh, in_transform, line_gpd,cid, exp_shk_cell=0):
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
        log_print(f"find_corridor_polygon: {e}")

    if corridor_polygon:
        corridor_polygon = sh_ops.unary_union(corridor_polygon)
        if type(corridor_polygon) is sh_geom.MultiPolygon:
            largest_area=max([geom.area for geom in corridor_polygon.geoms])
            parts = [
                p for p in corridor_polygon.geoms
                if p.area >=largest_area*0.01
            ]
            if len(parts)>=1:
            # poly_list = shapely.get_parts(corridor_polygon)
                merge_poly = parts[0]
                for i in range(1, len(parts)):
                    p1, p2 = sh_ops.nearest_points(
                        merge_poly,
                        parts[i])
                    bridge = sh_geom.LineString([p1, p2]).buffer(3 if exp_shk_cell==0 else exp_shk_cell*3)
                    merged = shapely.union(merge_poly, bridge)
                    merge_poly = shapely.union(merged, parts[i])
                corridor_polygon = merge_poly
            elif len(parts) == 1:
                corridor_polygon = sh_ops.unary_union(parts)
            else:
                corridor_polygon = None
            # logger.file_only(
            #     cid +
            #     f" merged_type={corridor_polygon.geom_type}"
            # )
            #
            # logger.file_only(
            #     cid +
            #     f" merged_valid={corridor_polygon.is_valid}"
            # )
            # logger.file_only(
            #     cid +
            #     shapely.validation.explain_validity(
            #         corridor_polygon
            #     )
            # )
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
    corridor_id = f"{row['OLnFID'].iloc[0]}_{row['OLnSEG'].iloc[0]}"

    poly = row.geometry.iloc[0]
    centerline, status = find_centerline(poly, lc_path,
                                         guided_strategy="pairwise",
                                         corridor_id=corridor_id,)
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
        log_print(f"find_centerlines: {e}")

    centerline_gpd = bt_base.execute_multiprocessing(
        process_single_centerline, rows_and_paths, "find_centerlines", processes, 1
    )
    return pd.concat(centerline_gpd)


def regenerate_centerline(poly, input_line,corridor_id="UNKNOWN",
                          cell_size=1.0,
                          guided_strategy="pairwise",
                          endpoint_mode="strict",
                          endpoint_candidate_k=8,
                          ):
    """
    Regenerates centerline when initial poly is not valid.
    Split the corridor polygon, extract each half independently,
        and merge the two centerlines.

    Args:
        input_line (sh_geom.LineString): Seed line or least cost path.
        Only two end points will be used

    Returns:
        sh_geom.MultiLineString

    """
    cid = (f"[CID={corridor_id}] "if corridor_id else "[CID=UNKNOWN] ")
    half_line_length = input_line.length / 2
    split_pt=input_line.interpolate(half_line_length)
    line_1 = sh_ops.substring(input_line, start_dist=0.0, end_dist=half_line_length)
    line_2 = sh_ops.substring(input_line, start_dist=half_line_length, end_dist=input_line.length)

    pts = shapely.force_2d(
        [
            sh_geom.Point(list(input_line.coords)[0]),
            split_pt,
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
            log_print("regenerate_centerline: Multi or none polygon found, pass.")

        poly = sh_geom.Polygon(poly_geoms[0])

    poly_exterior = sh_geom.Polygon(poly.buffer(bt_const.SMALL_BUFFER).exterior)
    poly_split = sh_ops.split(poly_exterior, perp)

    if len(poly_split.geoms) < 2:
        logger.file_only(cid+
            f"regenerate_centerline: polygon sh_ops.split failed, pass.")
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

    # logger.file_only(
    #     cid +
    #     f" poly1 area={poly_1.area:.2f}"
    # )
    #
    # logger.file_only(
    #     cid +
    #     f" poly2 area={poly_2.area:.2f}"
    # )

    center_line_1 = find_centerline(poly_1, pair_line_1,corridor_id=corridor_id,allow_regeneration=False,)
    center_line_2 = find_centerline(poly_2, pair_line_2,corridor_id=corridor_id,allow_regeneration=False,)

    center_line_1 = center_line_1[0]
    center_line_2 = center_line_2[0]

    if not center_line_1 or not center_line_2:
        log_print("Regenerate line: centerline is None")
        return None

    try:
        if center_line_1.is_empty or center_line_2.is_empty:
            log_print("Regenerate line: centerline is empty")
            return None
    except Exception as e:
        log_print(f"regenerate_centerline: {e}")

    center_line_1 = orient_to_split(center_line_1,
                split_pt,want_end_at_split=True)

    center_line_2 = orient_to_split(center_line_2,
        split_pt,want_end_at_split=False)
    # logger.file_only(
    #     cid +
    #     f" cl1 len={center_line_1.length:.2f} "
    #     f"gap={sh_geom.Point(center_line_1.coords[0]).distance(sh_geom.Point(center_line_1.coords[-1])):.2f}"
    # )
    # logger.file_only(
    #     cid +
    #     f" cl1 len={center_line_1.length:.2f} "
    #     f"ring={center_line_1.is_ring}"
    # )
    #
    # logger.file_only(
    #     cid +
    #     f" cl2 len={center_line_2.length:.2f} "
    #     f"ring={center_line_2.is_ring}"
    # )
    result=algo_common._safe_linemerge(sh_geom.MultiLineString([center_line_1, center_line_2]))
    # logger.file_only(
    #     cid +
    #     f" merged_type="
    #     f"{type(result).__name__ if result else 'None'}"
    # )
    #
    # if result:
    #     logger.file_only(
    #         cid +
    #         f" merged_len={result.length:.2f}"
    #     )
    # logger.file_only(cid +
    #                  f"Centerline is regenerated. "
    #                  f" merged_type="
    #                  f"{type(result).__name__}, "
    #                  f" cl1 closed="
    # f"{center_line_1.coords[0] == center_line_1.coords[-1]}, "
    # f" cl2 closed="
    # f"{center_line_2.coords[0] == center_line_2.coords[-1]}")

    if isinstance(result, sh_geom.MultiLineString):
        # logger.file_only(
        #     cid +
        #     " regenerate_centerline: "
        #     "merge remained MultiLineString"
        # )
        return None
    # logger.file_only(
    #     cid +
    #     f" cl1 endpoint gap="
    #     f"{sh_geom.Point(center_line_1.coords[0]).distance(sh_geom.Point(center_line_1.coords[-1])):.2f}"
    # )
    #
    # logger.file_only(
    #     cid +
    #     f" cl2 endpoint gap="
    #     f"{sh_geom.Point(center_line_2.coords[0]).distance(sh_geom.Point(center_line_2.coords[-1])):.2f}"
    # )

    return result



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
        chm_buffer_width=5.0,
        chm_buffer_multiplier=0.5,
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
        self.chm_buffer_width = float(chm_buffer_width)
        self.chm_buffer_multiplier = float(chm_buffer_multiplier)
        if self.chm_buffer_width < 0.0:
            raise ValueError("chm_buffer_width must be greater than or equal to zero")
        if not 0.0 <= self.chm_buffer_multiplier <= 1.0:
            raise ValueError("chm_buffer_multiplier must be between zero and one")
        self.astar_corridor_line_bias_weight = max(float(astar_corridor_line_bias_weight), 0.0)
        self.astar_corridor_distance_penalty_weight = max(float(astar_corridor_distance_penalty_weight), 0.0)
        self.corridor_simplify_polygon = _to_bool(corridor_simplify_polygon)
        self.corridor_simplify_length = max(float(corridor_simplify_length), 0.0)
        self.corridor_smooth_polygon = _to_bool(corridor_smooth_polygon)
        self.corridor_polygon_smooth_iterations = max(int(corridor_polygon_smooth_iterations), 0)
        self.lc_path = None
        self.centerline = None
        self.corridor_poly_gpd = None
        self.endpoint_mode="strict"
        self.endpoint_candidate_k=5
        self.cell_size=1.0
        self.cid = "UNKNOWN"

    def compute(self):
        line = self.line.geometry[0]
        line_radius = self.line_radius
        in_raster = self.raster
        seed_line = line  # LineString
        chm_mode = self.chm_mode
        ## corridor_id is used to identify features in the log file.
        corridor_id = (
            f"{self.line['OLnFID'].iloc[0]}_"
            f"{self.line['OLnSEG'].iloc[0]}"
        )
        cid=f"[CID:{corridor_id}] "
        self.cid=cid
        try:
            ras_clip, out_meta = self._clip_chm(in_raster, seed_line, line_radius)
            if self.chm_mode == bt_const.CenterlineChmMode.BUFFER.value:
                ras_clip = algo_cost.reduce_chm_in_line_buffer(
                    ras_clip,
                    out_meta,
                    seed_line,
                    self.chm_buffer_width,
                    self.chm_buffer_multiplier,
                )
            cost_clip, _ = algo_cost.cost_raster(ras_clip, out_meta)
        except Exception as e:
            log_print(f"{self.cid}:{e}")
            self._set_fallback_outputs(
                seed_line,
                seed_line,
                CenterlineStatus.LCP_FAILED_SEED_FALLBACK,
                corridor_geometry=seed_line.buffer(line_radius),
            )
            return

        lc_path = line
        try:
            if self.centerline_method == bt_const.CenterlineMethod.ASTAR.value:
                lc_path = algo_astar.find_least_cost_path_astar_closest_line(cost_clip, out_meta, seed_line)
            elif bt_const.CenterlineFlags.USE_SKIMAGE_GRAPH:
                lc_path = bt_dijkstra.find_least_cost_path_skimage(cost_clip, out_meta, seed_line)
            else:
                lc_path = bt_dijkstra.find_least_cost_path(cost_clip, out_meta, seed_line)
        except Exception as e:
            log_print(f"{self.cid}:{e}")
            self._set_fallback_outputs(
                seed_line,
                seed_line,
                CenterlineStatus.LCP_FAILED_SEED_FALLBACK,
                corridor_geometry=seed_line.buffer(line_radius),
            )
            return

        if lc_path:
            lc_path_coords = lc_path.coords
        else:
            lc_path_coords = []

        # search for centerline
        if len(lc_path_coords) < 2:
            logger.info(self.cid+"No least cost path detected, use input line.")
            self._set_fallback_outputs(
                seed_line,
                seed_line,
                CenterlineStatus.LCP_FAILED_SEED_FALLBACK,
                corridor_geometry=seed_line.buffer(line_radius),
            )
            return

        # get corridor raster
        lc_path = sh_geom.LineString(lc_path_coords)
        lc_path = self._postprocess_lcp(lc_path, out_meta.get("crs"))
        lc_path_coords = list(lc_path.coords)
        try:
            ras_clip, out_meta = self._clip_chm(in_raster, lc_path, line_radius * 0.9)
            cost_clip, _ = algo_cost.cost_raster(ras_clip, out_meta)

            out_transform = out_meta["transform"]
            transformer = rasterio.transform.AffineTransformer(out_transform)
            cell_size = (out_transform[0], -out_transform[4])

            x1, y1 = lc_path_coords[0]
            x2, y2 = lc_path_coords[-1]
            source = [transformer.rowcol(x1, y1)]
            destination = [transformer.rowcol(x2, y2)]
            if self.centerline_method == bt_const.CenterlineMethod.ASTAR.value:
                corridor_thresh_cl, _details = algo_astar.astar_accumulation_corridor_raster(
                    cost_clip,
                    out_meta,
                    lc_path,
                    corridor_threshold=bt_const.FP_CORRIDOR_THRESHOLD,
                    line_bias_weight=self.astar_corridor_line_bias_weight,
                    distance_penalty_weight=self.astar_corridor_distance_penalty_weight,
                )
            else:
                corridor_thresh_cl = algo_common.corridor_raster(
                    cost_clip,
                    out_meta,
                    source,
                    destination,
                    cell_size,
                    bt_const.FP_CORRIDOR_THRESHOLD,
                )
        except Exception as e:
            log_print(f"Corridor error {cid}:{e}, fall back lcp buffer line_radius")
            self._set_fallback_outputs(
                lc_path,
                lc_path,
                CenterlineStatus.CENTERLINE_FAILED_LCP_FALLBACK,
                corridor_geometry=lc_path.buffer(line_radius),
            )
            return

        # find contiguous corridor polygon and extract centerline
        try:
            df = gpd.GeoDataFrame(geometry=[seed_line], crs=out_meta["crs"])
            corridor_poly_gpd = find_corridor_polygon(corridor_thresh_cl, out_transform, df,cid)
            geom = corridor_poly_gpd.geometry.iloc[0]

            # logger.file_only(
            #     f"{cid} corridor_area={geom.area:.2f} "
            #     f"corridor_perimeter={geom.length:.2f}"
            # )
            #
            # rect = geom.minimum_rotated_rectangle
            # pts = list(rect.exterior.coords)
            #
            # sides = [
            #     sh_geom.Point(pts[i]).distance(
            #         sh_geom.Point(pts[i + 1])
            #     )
            #     for i in range(4)
            # ]

            # logger.file_only(
            #     f"{cid} aspect="
            #     f"{max(sides) / max(min(sides), 1e-9):.2f}"
            # )
            corridor_poly_gpd = self._postprocess_corridor_polygon(corridor_poly_gpd)
            center_line, status = find_centerline(
                corridor_poly_gpd.geometry.iloc[0],
                lc_path,
                guided_strategy=self.guided_strategy,
                corridor_id=corridor_id
            )
        except Exception as e:
            log_print(f"{cid}:{e}")
            corridor_poly_gpd = self.line.copy()
            corridor_poly_gpd.geometry = [lc_path.buffer(line_radius)]
            center_line = lc_path
            status = CenterlineStatus.CENTERLINE_FAILED_LCP_FALLBACK

        status = CenterlineStatus(status)
        if status in {CenterlineStatus.FAILED, CenterlineStatus.REGENERATE_FAILED}:
            corridor_geom = corridor_poly_gpd.geometry.iloc[0]
            if pd.notna(corridor_geom) and not corridor_geom.is_empty:
                estimated_width = corridor_poly_gpd.geometry.iloc[0].area / max(lc_path.length, 1e-6)
            else:
                estimated_width = line_radius/2
            buffer_width = min(line_radius,estimated_width / 2.0)
            absolute_footprint = lc_path.buffer(buffer_width)
            try:
                absolute_centerline, absolute_status = find_centerline(
                    absolute_footprint,
                    lc_path,
                    guided_strategy=self.guided_strategy,
                    corridor_id=corridor_id,
                    allow_regeneration=False,)
                absolute_status = CenterlineStatus(absolute_status)
                if absolute_status not in {CenterlineStatus.FAILED, CenterlineStatus.REGENERATE_FAILED}:
                    center_line = absolute_centerline
                    status = CenterlineStatus.ABSOLUTE_FOOTPRINT_SUCCESS
                    corridor_poly_gpd = self.line.copy()
                    corridor_poly_gpd.geometry = [absolute_footprint]
                else:
                    status = CenterlineStatus.CENTERLINE_FAILED_LCP_FALLBACK
                    center_line = lc_path
            except Exception as e:
                log_print(f"{cid}:{e}")
                status = CenterlineStatus.CENTERLINE_FAILED_LCP_FALLBACK
                center_line = lc_path

        self.line["cl_status"] = status.value
        self.line["cl_status_name"] = status.name

        self.lc_path = self.line.copy()
        self.lc_path.geometry = [lc_path]
        self.lc_path["centerline_method"] = self.centerline_method
        self.lc_path["lcp_simplified"] = bool(self.lcp_simplify_enabled and self.lcp_simplify_diameter > 0)
        self.lc_path["lcp_smoothed"] = bool(self.lcp_smooth_enabled and self.lcp_smooth_iterations > 0)

        self.centerline = self.line.copy()
        self.centerline.geometry = [center_line]
        self.centerline["centerline_method"] = self.centerline_method
        self.centerline["OLnFID"] = self.lc_path["OLnFID"]
        self.centerline["OLnSEG"] = self.lc_path["OLnSEG"]

        self.corridor_poly_gpd = corridor_poly_gpd
        self.corridor_poly_gpd["centerline_method"] = self.centerline_method
        self.corridor_poly_gpd["cl_status"] = status.value
        self.corridor_poly_gpd["cl_status_name"] = status.name
        self.corridor_poly_gpd["OLnFID"] = self.lc_path["OLnFID"]
        self.corridor_poly_gpd["OLnSEG"] = self.lc_path["OLnSEG"]

    def _set_fallback_outputs(self, lc_path, centerline, status, corridor_geometry=None):
        status = CenterlineStatus(status)
        self.line["cl_status"] = status.value
        self.line["cl_status_name"] = status.name

        self.lc_path = self.line.copy()
        self.lc_path.geometry = [lc_path]
        self.lc_path["centerline_method"] = self.centerline_method
        self.lc_path["lcp_simplified"] = False
        self.lc_path["lcp_smoothed"] = False

        self.centerline = self.line.copy()
        self.centerline.geometry = [centerline]
        self.centerline["centerline_method"] = self.centerline_method
        self.centerline["OLnFID"] = self.lc_path["OLnFID"]
        self.centerline["OLnSEG"] = self.lc_path["OLnSEG"]

        self.corridor_poly_gpd = self.line.copy()
        self.corridor_poly_gpd.geometry = [corridor_geometry]
        self.corridor_poly_gpd["centerline_method"] = self.centerline_method
        self.corridor_poly_gpd["OLnFID"] = self.lc_path["OLnFID"]
        self.corridor_poly_gpd["OLnSEG"] = self.lc_path["OLnSEG"]

    def _clip_chm(self, in_raster, clip_geometry, buffer):
        if self.chm_mode == bt_const.CenterlineChmMode.ALT.value:
            ras_clip, out_meta, *_ = alt_sp_common.alt_clip_and_filter_reginal_maxima_wGap(
                {"tree_radius": 2.5},
                in_raster,
                clip_geometry,
                buffer,
            )
            return ras_clip, out_meta
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

def orient_to_split(line, split_pt, want_end_at_split=True):

    start_gap = sh_geom.Point(line.coords[0]).distance(split_pt)

    end_gap = sh_geom.Point(line.coords[-1]).distance(split_pt)

    if want_end_at_split:
        if start_gap < end_gap:
            return algo_common._reverse_line(line)
    else:
        if end_gap < start_gap:
            return algo_common._reverse_line(line)

    return line
