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
from label_centerlines import get_centerline

import beratools.core.algo_common as algo_common
import beratools.core.algo_cost as algo_cost
import beratools.core.algo_dijkstra as bt_dijkstra
import beratools.core.constants as bt_const
import beratools.core.tool_base as bt_base
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


def snap_end_to_end(in_line, line_reference):
    if type(in_line) is sh_geom.MultiLineString:
        in_line = sh_ops.linemerge(in_line)
        if type(in_line) is sh_geom.MultiLineString:
            print(f"algo_centerline: MultiLineString found {in_line.centroid}, pass.")
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

    if in_line.has_z:
        snap_start = shapely.force_3d(snap_start)
        snap_end = shapely.force_3d(snap_end)
    else:
        snap_start = shapely.force_2d(snap_start)
        snap_end = shapely.force_2d(snap_end)

    pts[0] = snap_start.coords[0]
    pts[-1] = snap_end.coords[0]

    return sh_geom.LineString(pts)


def find_centerline(poly, input_line):
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
    if not poly:
        print("find_centerline: No polygon found")
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

    # TODO add more code to filter Voronoi vertices
    src_geom = sh_geom.Point(line_coords[0]).buffer(CenterlineParams.BUFFER_CLIP * 3).intersection(poly)
    dst_geom = sh_geom.Point(line_coords[-1]).buffer(CenterlineParams.BUFFER_CLIP * 3).intersection(poly)
    src_geom = None
    dst_geom = None

    try:
        centerline = get_centerline(
            poly,
            segmentize_maxlen=1,
            max_points=3000,
            simplification=0.05,
            smooth_sigma=CenterlineParams.SMOOTH_SIGMA,
            max_paths=1,
            src_geom=src_geom,
            dst_geom=dst_geom,
        )
    except Exception as e:
        print(f"find_centerline: {e}")
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

    cl_coords = list(centerline.coords)

    # trim centerline at two ends
    head_buffer = sh_geom.Point(cl_coords[0]).buffer(CenterlineParams.BUFFER_CLIP)
    centerline = centerline.difference(head_buffer)

    end_buffer = sh_geom.Point(cl_coords[-1]).buffer(CenterlineParams.BUFFER_CLIP)
    centerline = centerline.difference(end_buffer)

    # No centerline detected, use input line instead.
    if not centerline:
        return default_return
    try:
        # Empty centerline detected, use input line instead.
        if centerline.is_empty:
            return default_return
    except Exception as e:
        print(f"find_centerline: {e}")

    centerline = snap_end_to_end(centerline, input_line)

    # Check centerline. If valid, regenerate by splitting polygon into two halves.
    if not centerline_is_valid(centerline, input_line):
        try:
            print("Regenerating line ...")
            centerline = regenerate_centerline(poly, input_line)
            return centerline, CenterlineStatus.REGENERATE_SUCCESS
        except Exception as e:
            print(f"find_centerline: {e}")
            return input_line, CenterlineStatus.REGENERATE_FAILED

    return centerline, CenterlineStatus.SUCCESS


def find_corridor_polygon(corridor_thresh, in_transform, line_gpd):
    # Threshold corridor raster used for generating centerline
    corridor_thresh_cl = np.ma.where(corridor_thresh == 0.0, 1, 0).data
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
        print("regenerate_centerline: polygon sh_ops.split failed, pass.")
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

    print("Centerline is regenerated.")
    return sh_ops.linemerge(sh_geom.MultiLineString([center_line_1, center_line_2]))


class SeedLine:
    """Class to store seed line and least cost path."""

    def __init__(self, line_gdf, ras_file, proc_segments, line_radius):
        self.line = line_gdf
        self.raster = ras_file
        self.line_radius = line_radius
        self.lc_path = None
        self.centerline = None
        self.corridor_poly_gpd = None

    def compute(self):
        line = self.line.geometry[0]
        line_radius = self.line_radius
        in_raster = self.raster
        seed_line = line  # LineString
        default_return = (seed_line, seed_line, None)

        ras_clip, out_meta = sp_common.clip_raster(in_raster, seed_line, line_radius)
        cost_clip, _ = algo_cost.cost_raster(ras_clip, out_meta)

        lc_path = line
        try:
            if bt_const.CenterlineFlags.USE_SKIMAGE_GRAPH:
                lc_path = bt_dijkstra.find_least_cost_path_skimage(cost_clip, out_meta, seed_line)
            else:
                lc_path = bt_dijkstra.find_least_cost_path(cost_clip, out_meta, seed_line)
        except Exception as e:
            print(e)
            return default_return

        if lc_path:
            lc_path_coords = lc_path.coords
        else:
            lc_path_coords = []

        self.lc_path = lc_path

        # search for centerline
        if len(lc_path_coords) < 2:
            print("No least cost path detected, use input line.")
            self.line["cl_status"] = CenterlineStatus.FAILED.value
            return default_return

        # get corridor raster
        lc_path = sh_geom.LineString(lc_path_coords)
        ras_clip, out_meta = sp_common.clip_raster(in_raster, lc_path, line_radius * 0.9)
        cost_clip, _ = algo_cost.cost_raster(ras_clip, out_meta)

        out_transform = out_meta["transform"]
        transformer = rasterio.transform.AffineTransformer(out_transform)
        cell_size = (out_transform[0], -out_transform[4])

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

        # find contiguous corridor polygon and extract centerline
        df = gpd.GeoDataFrame(geometry=[seed_line], crs=out_meta["crs"])
        corridor_poly_gpd = find_corridor_polygon(corridor_thresh_cl, out_transform, df)
        center_line, status = find_centerline(corridor_poly_gpd.geometry.iloc[0], lc_path)
        self.line["cl_status"] = status.value

        self.lc_path = self.line.copy()
        self.lc_path.geometry = [lc_path]

        self.centerline = self.line.copy()
        self.centerline.geometry = [center_line]

        self.corridor_poly_gpd = corridor_poly_gpd
