"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide common algorithms
    and utility functions/classes.
"""

import math
import tempfile
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyproj
import rasterio
import shapely, skimage
import shapely.affinity as sh_aff
import shapely.geometry as sh_geom
import shapely.ops as sh_ops
import skimage.graph as sk_graph
import heapq
import keyword
from typing import Iterable
from itertools import count
from osgeo import gdal, ogr
from scipy import ndimage
from shapely import Point, LineString
from rasterio import features
from rasterio.features import geometry_mask
from dataclasses import dataclass

import beratools.core.algo_cost as algo_cost
import beratools.core.constants as bt_const

gpd.options.io_engine = "pyogrio"
DISTANCE_THRESHOLD = 2  # 1 meter for intersection neighborhood
logger = logging.getLogger(__name__)


def log_file_only(message, level=logging.INFO, logger_name=None):
    """Log a message to file handlers only, skipping console/gui handlers."""
    target_logger = logging.getLogger(logger_name) if logger_name else logging.getLogger(__name__)
    record = target_logger.makeRecord(
        name=target_logger.name,
        level=level,
        fn="",
        lno=0,
        msg=message,
        args=(),
        exc_info=None,
    )

    root_logger = logging.getLogger()
    wrote_to_file = False
    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.handle(record)
            wrote_to_file = True

    if not wrote_to_file:
        target_logger.log(level, message)


def process_single_item(cls_obj):
    """
    Process a class object for universal multiprocessing.

    Args:
        cls_obj: Class object to be processed

    Returns:
        cls_obj: Class object after processing

    """
    try:
        cls_obj.compute()
        return cls_obj
    except Exception as e:
        import traceback

        print(f"❌ Exception during compute() for object: {e}")
        traceback.print_exc()
        return None


def read_geospatial_file(file_path, layer=None):
    """
    Read a geospatial file, clean the geometries and return a GeoDataFrame.

    Args:
        file_path (str): The path to the geospatial file (e.g., .shp, .gpkg).
        layer (str, optional): The specific layer to read if the file is
        multi-layered (e.g., GeoPackage).

    Returns:
        GeoDataFrame: The cleaned GeoDataFrame containing the data from the file
        with valid geometries only.
        None: If there is an error reading the file or layer.

    """
    try:
        kwargs = {}
        if layer is not None:
            kwargs["layer"] = layer

        gdf = gpd.read_file(file_path, **kwargs)

        # Rename 'fid' column to avoid conflict with GeoPackage's reserved
        # FID field on write.
        if "fid" in gdf.columns:
            gdf = gdf.rename(columns={"fid": "orig_fid"})

        # Clean the geometries in the GeoDataFrame
        gdf = clean_geometries(gdf, stage="input")
        gdf = gdf.reset_index(drop=True)
        gdf["BT_UID"] = range(len(gdf))  # assign temporary UID
        return gdf

    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return None


def has_multilinestring(gdf):
    """Check if any geometry is a MultiLineString."""
    # Filter out None values (invalid geometries) from the GeoDataFrame
    valid_geometries = gdf.geometry
    return any(isinstance(geom, sh_geom.MultiLineString) for geom in valid_geometries)


def get_aux_path(out_file):
    out_path = Path(out_file)
    return out_path.with_stem(out_path.stem + "_aux").with_suffix(".gpkg").as_posix()


def save_aux_layer(gdf, out_file, layer):
    if gdf is None or gdf.empty or out_file is None or layer is None:
        return

    aux_file = get_aux_path(out_file)
    try:
        gdf.to_file(aux_file, layer=layer)
    except Exception as exc:
        logger.warning("Failed saving aux layer '%s' to %s: %s", layer, aux_file, exc)


def _infer_ogr_field_type(value):
    if isinstance(value, bool):
        return ogr.OFTInteger
    if isinstance(value, int):
        return ogr.OFTInteger64
    if isinstance(value, float):
        return ogr.OFTReal
    return ogr.OFTString


def save_aux_table(rows, out_file, table, overwrite=True):
    if out_file is None or table is None:
        return

    if rows is None:
        rows = []

    if isinstance(rows, dict):
        rows = [rows]

    if not isinstance(rows, list):
        logger.warning("Skipping aux table '%s': rows must be a list of dicts.", table)
        return

    normalized_rows = []
    columns = []
    for row in rows:
        if not isinstance(row, dict):
            logger.warning("Skipping aux table row for '%s': expected dict, got %s.", table, type(row))
            continue
        normalized_rows.append(row)
        for key in row.keys():
            if key not in columns:
                columns.append(key)

    aux_file = get_aux_path(out_file)
    try:
        driver = ogr.GetDriverByName("GPKG")
        if driver is None:
            raise RuntimeError("OGR GeoPackage driver is unavailable.")

        ds = driver.Open(aux_file, 1)
        if ds is None:
            ds = driver.CreateDataSource(aux_file)
        if ds is None:
            raise RuntimeError(f"Unable to open or create GeoPackage: {aux_file}")

        if overwrite:
            layer_index = -1
            for idx in range(ds.GetLayerCount()):
                layer_obj = ds.GetLayer(idx)
                if layer_obj is not None and layer_obj.GetName() == table:
                    layer_index = idx
                    break

            if layer_index >= 0:
                ds.DeleteLayer(layer_index)

        layer = ds.GetLayerByName(table)
        if layer is None:
            layer = ds.CreateLayer(table, geom_type=ogr.wkbNone)

        layer_defn = layer.GetLayerDefn()
        existing_fields = [layer_defn.GetFieldDefn(i).GetName() for i in range(layer_defn.GetFieldCount())]

        for col in columns:
            if col in existing_fields:
                continue

            sample_value = None
            for row in normalized_rows:
                if row.get(col) is not None:
                    sample_value = row[col]
                    break

            field_type = _infer_ogr_field_type(sample_value)
            field_defn = ogr.FieldDefn(col, field_type)
            layer.CreateField(field_defn)

        layer_defn = layer.GetLayerDefn()
        for row in normalized_rows:
            feature = ogr.Feature(layer_defn)
            for col in columns:
                value = row.get(col)
                if isinstance(value, bool):
                    value = int(value)
                if value is None:
                    continue
                feature.SetField(col, value)
            layer.CreateFeature(feature)
            feature = None

        ds = None
    except Exception as exc:
        logger.warning("Failed saving aux table '%s' to %s: %s", table, aux_file, exc)


def clean_geometries(gdf, stage=None, out_file=None, layer=None):
    """
    Remove rows with invalid, None, or empty geometries from the GeoDataFrame.

    Args:
        gdf (GeoDataFrame): The GeoDataFrame to clean.

    Returns:
        GeoDataFrame: The cleaned GeoDataFrame with valid, non-null,
        and non-empty geometries.

    """
    if gdf is None:
        return gdf

    if gdf.empty:
        return gdf

    m_null = gdf.geometry.isna()

    m_empty = m_null.copy()
    m_empty[:] = False
    non_null_mask = ~m_null
    if non_null_mask.any():
        m_empty.loc[non_null_mask] = gdf.geometry.loc[non_null_mask].is_empty

    m_invalid = m_null.copy()
    m_invalid[:] = False
    valid_candidate_mask = non_null_mask & ~m_empty
    if valid_candidate_mask.any():
        m_invalid.loc[valid_candidate_mask] = ~gdf.geometry.loc[valid_candidate_mask].is_valid

    rejected_mask = m_invalid | m_null | m_empty
    if not rejected_mask.any():
        return gdf

    rejected_gdf = gdf[rejected_mask].copy()
    rejected_gdf["BT_REJECT_REASON"] = np.where(
        m_invalid[rejected_mask],
        "invalid",
        np.where(m_null[rejected_mask], "null", "empty"),
    )

    kept_gdf = gdf[~rejected_mask]

    n_invalid = int((rejected_gdf["BT_REJECT_REASON"] == "invalid").sum())
    n_null = int((rejected_gdf["BT_REJECT_REASON"] == "null").sum())
    n_empty = int((rejected_gdf["BT_REJECT_REASON"] == "empty").sum())
    total_removed = int(rejected_mask.sum())
    original_count = len(gdf)

    stage_prefix = f"[{stage}] " if stage else ""
    logger.info(
        "%sRemoved %s invalid, %s null, %s empty geometries (%s of %s rows)",
        stage_prefix,
        n_invalid,
        n_null,
        n_empty,
        total_removed,
        original_count,
    )

    layer_name = layer
    if layer_name is None:
        layer_name = f"rejected_{stage}" if stage else "rejected"

    if out_file is not None:
        save_aux_layer(rejected_gdf, out_file, layer_name)

    return kept_gdf


def clean_line_geometries(line_gdf, min_length=bt_const.SMALL_BUFFER):
    """Clean line geometries in the GeoDataFrame."""
    if line_gdf is None:
        return line_gdf

    if line_gdf.empty:
        return line_gdf

    line_gdf = line_gdf[~line_gdf.geometry.isna() & ~line_gdf.geometry.is_empty]
    line_gdf = line_gdf[line_gdf.geometry.length > float(min_length)]
    return line_gdf


def split_lines_to_segments(gdf):
    """Split input lines to single-segment rows while preserving attributes."""
    if gdf is None:
        return []

    if has_multilinestring(gdf):
        gdf = gdf.explode(index_parts=False)

    split_gdf_list = []
    for row in gdf.itertuples(index=False):
        line = row.geometry
        coords = list(line.coords)

        for i in range(len(coords) - 1):
            segment = sh_geom.LineString([coords[i], coords[i + 1]])
            attributes = {col: getattr(row, col) for col in gdf.columns if col != "geometry"}
            single_row_gdf = gpd.GeoDataFrame([attributes], geometry=[segment], crs=gdf.crs)
            split_gdf_list.append(single_row_gdf)

    return split_gdf_list


def lines_gdf_to_list(gdf):
    """Convert lines GeoDataFrame rows to list of single-row GeoDataFrames."""
    if gdf is None:
        return []

    if has_multilinestring(gdf):
        gdf = gdf.explode(index_parts=False)

    out_list = []
    rename_dict = {
        col: f"{col}_col"
        for col in gdf.columns
        if keyword.iskeyword(col)
    }
    gdf_safe = gdf.rename(columns=rename_dict)
    for row in gdf_safe.itertuples(index=False):
        line = row.geometry
        attributes = {col: getattr(row, col) for col in gdf_safe.columns if col != "geometry"}
        for orig_key,safe_key in rename_dict.items():
            if safe_key in attributes:
                attributes[orig_key] = attributes.pop(safe_key)
        single_row_gdf = gpd.GeoDataFrame([attributes], geometry=[line], crs=gdf.crs)
        out_list.append(single_row_gdf)

    return out_list


def prepare_lines_gdf(file_path, layer=None, proc_segments=True):
    """
    Split lines at vertices or return original rows.

    It handles for MultiLineString.

    """
    gdf = read_geospatial_file(file_path, layer=layer)
    if gdf is None:
        return []

    if proc_segments:
        return split_lines_to_segments(gdf)

    return lines_gdf_to_list(gdf)


# TODO use function from common
def morph_raster(corridor_thresh, canopy_raster, exp_shk_cell, cell_size_x):
    # Process: Stamp CC and Max Line Width
    temp1 = corridor_thresh + canopy_raster
    raster_class = np.ma.where(temp1 == 0, 1, 0).data

    if exp_shk_cell > 0 and cell_size_x < 1:
        # Process: Expand
        # FLM original Expand equivalent
        cell_size = int(exp_shk_cell * 2 + 1)
        expanded = ndimage.grey_dilation(raster_class, size=(cell_size, cell_size))

        # Process: Shrink
        # FLM original Shrink equivalent
        file_shrink = ndimage.grey_erosion(expanded, size=(cell_size, cell_size))

    else:
        if bt_const.BT_DEBUGGING:
            print("No Expand And Shrink cell performed.")
        file_shrink = raster_class

    # Process: Boundary Clean
    clean_raster = ndimage.gaussian_filter(file_shrink, sigma=0, mode="nearest")

    return clean_raster


def closest_point_to_line(point, line):
    if not line:
        return None

    pt = line.interpolate(line.project(sh_geom.Point(point)))
    return pt


def line_coord_list(line):
    point_list = []
    try:
        for point in list(line.coords):  # loops through every point in a line
            # loops through every vertex of every segment
            if point:  # adds all the vertices to segment_list, which creates an array
                point_list.append(sh_geom.Point(point[0], point[1]))
    except Exception as e:
        print(e)

    return point_list


def intersection_of_lines(line_1, line_2):
    """
    Only LINESTRING is dealt with for now.

    Args:
    line_1 :
    line_2 :

    Returns:
    sh_geom.Point: intersection point

    """
    # intersection collection, may contain points and lines
    inter = None
    if line_1 and line_2:
        inter = line_1.intersection(line_2)

    # TODO: intersection may return GeometryCollection, LineString or MultiLineString
    if inter:
        if (
            type(inter) is sh_geom.GeometryCollection
            or type(inter) is sh_geom.LineString
            or type(inter) is sh_geom.MultiLineString
        ):
            return inter.centroid

    return inter


def get_angle(line, vertex_index):
    """
    Calculate the angle of the first or last segment.

    # TODO: use np.arctan2 instead of np.arctan

    Args:
    line: LineString
    end_index: 0 or -1 of the line vertices. Consider the multipart.

    """
    pts = line_coord_list(line)

    if vertex_index == 0:
        pt_1 = pts[0]
        pt_2 = pts[1]
    elif vertex_index == -1:
        pt_1 = pts[-1]
        pt_2 = pts[-2]

    delta_x = pt_2.x - pt_1.x
    delta_y = pt_2.y - pt_1.y
    if np.isclose(pt_1.x, pt_2.x):
        angle = np.pi / 2
        if delta_y > 0:
            angle = np.pi / 2
        elif delta_y < 0:
            angle = -np.pi / 2
    else:
        angle = np.arctan(delta_y / delta_x)

        # arctan is in range [-pi/2, pi/2], regulate all angles to [[-pi/2, 3*pi/2]]
        if delta_x < 0:
            angle += np.pi  # the second or fourth quadrant

    return angle


def points_are_close(pt1, pt2):
    if abs(pt1.x - pt2.x) < DISTANCE_THRESHOLD and abs(pt1.y - pt2.y) < DISTANCE_THRESHOLD:
        return True
    else:
        return False


def generate_raster_footprint(in_raster, latlon=True):
    inter_img = "image_overview.tif"

    src_ds = gdal.Open(in_raster)
    width, height = src_ds.RasterXSize, src_ds.RasterYSize
    src_crs = src_ds.GetSpatialRef().ExportToWkt()

    geom = None
    with tempfile.TemporaryDirectory() as tmp_folder:
        if bt_const.BT_DEBUGGING:
            print("Temporary folder: {}".format(tmp_folder))

        if max(width, height) <= 1024:
            inter_img = in_raster
        else:
            if width >= height:
                options = gdal.TranslateOptions(width=1024, height=0)
            else:
                options = gdal.TranslateOptions(width=0, height=1024)

            inter_img = Path(tmp_folder).joinpath(inter_img).as_posix()
            gdal.Translate(inter_img, src_ds, options=options)

        shapes = gdal.Footprint(None, inter_img, dstSRS=src_crs, format="GeoJSON")
        target_feat = shapes["features"][0]
        geom = sh_geom.shape(target_feat["geometry"])

    if geom is not None and latlon:
        out_crs = pyproj.CRS("EPSG:4326")
        transformer = pyproj.Transformer.from_crs(pyproj.CRS(src_crs), out_crs)

        geom = sh_ops.transform(transformer.transform, geom)

    return geom


def save_raster_to_file(in_raster_mem, in_meta, out_raster_file):
    """
    Save raster matrix in memory to file.

    Args:
        in_raster_mem: numpy raster
        in_meta: input meta
        out_raster_file: output raster file

    """
    with rasterio.open(out_raster_file, "w", **in_meta) as dest:
        dest.write(in_raster_mem, indexes=1)


def generate_perpendicular_line_precise(points, offset=20):
    """
    Generate a perpendicular line to the input line at the given point.

    Args:
        points (list[Point]): The points where to generate the perpendicular lines.
        offset (float): The length of the perpendicular line.

    Returns:
        shapely.geometry.LineString: The generated perpendicular line.

    """
    # Compute the angle of the line
    if len(points) not in [2, 3]:
        return None

    center = points[1]
    perp_line = None

    if len(points) == 2:
        head = points[0]
        tail = points[1]

        delta_x = head.x - tail.x
        delta_y = head.y - tail.y
        angle = 0.0

        if math.isclose(delta_x, 0.0):
            angle = math.pi / 2
        else:
            angle = math.atan(delta_y / delta_x)

        start = [center.x + offset / 2.0, center.y]
        end = [center.x - offset / 2.0, center.y]
        line = sh_geom.LineString([start, end])
        perp_line = sh_aff.rotate(line, angle + math.pi / 2.0, origin=center, use_radians=True)
    elif len(points) == 3:
        head = points[0]
        tail = points[2]

        angle_1 = _line_angle(center, head)
        angle_2 = _line_angle(center, tail)
        angle_diff = (angle_2 - angle_1) / 2.0
        head_new = sh_geom.Point(
            center.x + offset / 2.0 * math.cos(angle_1),
            center.y + offset / 2.0 * math.sin(angle_1),
        )
        if head.has_z:
            head_new = shapely.force_3d(head_new)
        try:
            perp_seg_1 = sh_geom.LineString([center, head_new])
            perp_seg_1 = sh_aff.rotate(perp_seg_1, angle_diff, origin=center, use_radians=True)
            perp_seg_2 = sh_aff.rotate(perp_seg_1, math.pi, origin=center, use_radians=True)
            perp_line = sh_geom.LineString([list(perp_seg_1.coords)[1], list(perp_seg_2.coords)[1]])
        except Exception as e:
            print(e)

    return perp_line


def _line_angle(point_1, point_2):
    """
    Calculate the angle of the line.

    Args:
        point_1, point_2: start and end points of shapely line

    """
    delta_y = point_2.y - point_1.y
    delta_x = point_2.x - point_1.x

    angle = math.atan2(delta_y, delta_x)
    return angle


def corridor_raster(raster_clip, out_meta, source, destination, cell_size, corridor_threshold):
    """
    Calculate corridor raster.

    Args:
        raster_clip (raster):
        out_meta : raster file meta
        source (list of point tuple(s)): start point in row/col
        destination (list of point tuple(s)): end point in row/col
        cell_size (tuple): (cell_size_x, cell_size_y)
        corridor_threshold (double)

    Returns:
    corridor raster

    """
    try:
        # change all nan to BT_NODATA_COST for workaround
        if len(raster_clip.shape) > 2:
            raster_clip = np.squeeze(raster_clip, axis=0)

        algo_cost.remove_nan_from_array_refactor(raster_clip)

        # generate the cost raster to source point
        mcp_source = sk_graph.MCP_Geometric(raster_clip, sampling=cell_size)
        source_cost_acc = mcp_source.find_costs(source)[0]
        del mcp_source

        # # # generate the cost raster to destination point
        mcp_dest = sk_graph.MCP_Geometric(raster_clip, sampling=cell_size)
        dest_cost_acc = mcp_dest.find_costs(destination)[0]

        # Generate corridor
        corridor = source_cost_acc + dest_cost_acc
        corridor = np.ma.masked_invalid(corridor)

        # Calculate minimum value of corridor raster
        if np.ma.min(corridor) is not None:
            corr_min = float(np.ma.min(corridor))
        else:
            corr_min = 0.5

        # normalize corridor raster by deducting corr_min
        corridor_norm = corridor - corr_min
        corridor_thresh_cl = np.ma.where(corridor_norm >= corridor_threshold, 1.0, 0.0)

    except Exception as e:
        print(e)
        print("corridor_raster: Exception occurred.")
        return None

    return corridor_thresh_cl


def remove_holes(geom):
    if geom.geom_type == "Polygon":
        if geom.interiors:
            return sh_geom.Polygon(geom.exterior)
        return geom
    elif geom.geom_type == "MultiPolygon":
        new_polygons = []
        for polygon in geom.geoms:  # Iterate through MultiPolygon
            if polygon.interiors:
                new_polygons.append(sh_geom.Polygon(polygon.exterior))
            else:
                new_polygons.append(polygon)
        return sh_geom.MultiPolygon(new_polygons)
    return geom  # Return other geometry types as is


def alt_MCP_along_corridor_raster(raster_clip, out_meta, lc_path, cell_size, corridor_threshold):
    """
    Calculate corridor raster.

    Args:
        raster_clip (raster):
        out_meta : raster file meta
        lc_path: line geometry
        cell_size (tuple): (cell_size_x, cell_size_y)
        corridor_threshold (double)

    Returns:
    corridor raster

    """
    try:
        # change all nan to BT_NODATA_COST for workaround
        if len(raster_clip.shape) > 2:
            raster_clip = np.squeeze(raster_clip, axis=0)

        algo_cost.remove_nan_from_array_refactor(raster_clip)
        raster_clip_mask=np.ma.masked_invalid(raster_clip)
        segment_list = []
        for coord in lc_path.coords:
            segment_list.append(coord)

        distance_delta = 1
        distances = np.arange(0, lc_path.length, distance_delta)
        multipoint_along_line = [lc_path.interpolate(distance) for distance in distances]
        multipoint_along_line.append(Point(segment_list[-1]))


        rasterized_points_Alongln = features.rasterize(
            multipoint_along_line,
            out_shape=raster_clip.shape,
            transform=out_meta["transform"],
            fill=0,
            all_touched=True,
            default_value=1,
        )
        points_Alongln = np.transpose(np.nonzero(rasterized_points_Alongln))


        mcp_geo_obj = sk_graph.MCP_Geometric(raster_clip, sampling=cell_size, fully_connected=True)
        cost_forward_alongLn,_ = mcp_geo_obj.find_costs(starts=points_Alongln)


        # Generate corridor
        corridor = np.ma.masked_invalid(cost_forward_alongLn)

        # Calculate minimum value of corridor raster
        if np.ma.min(corridor) is not None:
            corr_min = float(np.ma.min(corridor))
        else:
            corr_min = 0.5

        # normalize corridor raster by deducting corr_min
        corridor_norm = corridor - corr_min
        mcorridor_norm=np.ma.filled(corridor_norm, np.nan)
        p_corridor_threshold=np.nanpercentile(mcorridor_norm, min(corridor_threshold*10,70))
        corridor_thresh_cl = np.ma.where(mcorridor_norm >= p_corridor_threshold, 1.0, 0.0)
        corridor_thresh_cl[raster_clip_mask.mask]=np.nan
    except Exception as e:
        print(e)
        print("corridor_raster: Exception occurred.")
        return None

    return corridor_thresh_cl

DEFAULT_LINE_BIAS_WEIGHT = 0.1
DEFAULT_DISTANCE_PENALTY_WEIGHT = 0.5

NEIGHBORS: tuple[tuple[int, int], ...] = (
    (1, 0),
    (0, -1),
    (-1, 0),
    (0, 1),
    (1, -1),
    (1, 1),
    (-1, -1),
    (-1, 1),
)


@dataclass(frozen=True)
class AStarAccumulation:
    path: list[tuple[int, int]]
    best_cost: float
    g_scores: np.ndarray
    closed: np.ndarray


def alt_astar_accumulation_corridor_raster(
    cost_arr,
    meta: dict,
    lc_path: LineString,
    *,
    corridor_threshold: float,
    line_bias_weight: float = DEFAULT_LINE_BIAS_WEIGHT,
    distance_penalty_weight: float = DEFAULT_DISTANCE_PENALTY_WEIGHT,
) -> tuple[np.ma.MaskedArray, dict[str, object]]:
    if lc_path is None or lc_path.is_empty or len(lc_path.coords) < 2:
        raise RuntimeError("A* corridor requires a valid least-cost path")

    cost = _prepare_cost_surface(cost_arr, meta)
    rows, cols = cost.shape
    transform = meta["transform"]
    transformer = rasterio.transform.AffineTransformer(transform)
    segment_list = []
    try:
        for coord in lc_path.coords:
            segment_list.append(coord)
        if lc_path.length >= 10:
            distance_delta = 5
        else:
            distance_delta=2
        distances = np.arange(0, lc_path.length, distance_delta)
        multipoint_along_line = [lc_path.interpolate(distance) for distance in distances]
        multipoint_along_line.append(Point(segment_list[-1]))
    except Exception as e:
        raise RuntimeError("1 A* corridor requires a valid least-cost path")

    forward_list=[]
    reverse_list=[]
    total_forward_path=[]
    dist_to_path_list=[]
    total_score_=np.zeros(cost.shape, dtype=float)
    valid_total=np.zeros(cost.shape, dtype=bool)
    total_score_.fill(np.inf)
    list_forward_best_cost=[]
    forward_closed_list=[]
    reverse_closed_list=[]
    try:
        for i in range(0,len(multipoint_along_line)-1):
            start_xy=multipoint_along_line[i].coords[0]
            end_xy=multipoint_along_line[i+1].coords[0]
            if start_xy == end_xy:
                continue
            source = _clamp_row_col(transformer.rowcol(*start_xy), rows, cols)
            destination = _clamp_row_col(transformer.rowcol(*end_xy), rows, cols)
            if source == destination:
                continue
            sampling = _raster_sampling(transform)
            forward = _astar_mcp_geometric_accumulation(
                cost,
                source,
                destination,
                sampling=sampling,
                line_bias_weight=line_bias_weight,
            )
            forward_list.append(forward)
            reverse =_astar_mcp_geometric_accumulation(
                cost,
                destination,
                source,
                sampling=sampling,
                line_bias_weight=line_bias_weight,
            )
            reverse_list.append(reverse)

            valid = forward.closed | reverse.closed
            local_data = forward.g_scores + reverse.g_scores - forward.best_cost
            total_forward_path = total_forward_path + forward.path
            valid_total[(valid)]=valid[(valid)]
            astar_path = _path_to_linestring(
                    forward.path,
                    transformer,
                    start_xy=source,
                    end_xy=destination,
                )
            dist_to_path_list.append(_distance_raster_to_line(astar_path, meta, cost.shape))
            total_score_[~np.isinf(local_data)] = local_data[~np.isinf(local_data)]

        total_score_[np.isinf(total_score_)] = 0.
        cleaned_arrays = [np.where(np.isinf(arr), np.nan, arr) for arr in dist_to_path_list]
        total_distance_to_path=np.fmin.reduce(cleaned_arrays)

        if distance_penalty_weight > 0.0:
            total_score = total_score_ + total_distance_to_path * distance_penalty_weight
        else:
            total_score = total_score_ + total_distance_to_path

        score = np.ma.masked_invalid(total_score)

        score = np.ma.array(score, mask=np.ma.getmaskarray(score) | ~skimage.morphology.dilation(valid_total, skimage.morphology.disk(int(1/distance_penalty_weight))))
        # score = np.ma.array(score, mask=np.ma.getmaskarray(score) | ~valid_total)

        inside = (~np.ma.getmaskarray(score)) & np.asarray(
            score.filled(np.inf) < corridor_threshold, dtype=bool
        )
        corridor = np.ma.where(inside, 0.0, 1.0)
        corridor = np.ma.array(corridor, mask=np.ma.getmaskarray(score))
        for forward,reverse in zip(forward_list,reverse_list):
            list_forward_best_cost.append(forward.best_cost)
            forward_closed_list.append(forward.closed)
            reverse_closed_list.append(reverse.closed)
        total_forward_closed=np.any(np.array(forward_closed_list), axis=0)
        total_reverse_closed = np.any(np.array(reverse_closed_list), axis=0)

        details = {
            "corridor_threshold": float(corridor_threshold),
            "astar_line_bias_weight": float(line_bias_weight),
            "astar_distance_penalty_weight": float(distance_penalty_weight),
            "astar_best_cost": float( min(list_forward_best_cost)),
            "inside_cells": int(np.count_nonzero(inside)),
            "inside_area": float(np.count_nonzero(inside) * _cell_area(transform)),
            "forward_closed_cells": int(np.count_nonzero(total_forward_closed)),
            "reverse_closed_cells": int(np.count_nonzero(total_reverse_closed)),
            "both_closed_cells": int(np.count_nonzero(valid_total)),
            "astar_path_vertices": int(len(total_forward_path)),
        }
        return corridor, details
    except Exception as e:
        raise RuntimeError("3 A* corridor requires a valid least-cost path")

def _prepare_cost_surface(cost_arr, meta: dict) -> np.ndarray:
    arr = np.ma.asarray(cost_arr)
    if arr.ndim > 2:
        arr = np.ma.squeeze(arr, axis=0)
    cost = np.asarray(arr.filled(np.inf), dtype="float64")
    nodata = meta.get("nodata")
    if nodata is not None:
        cost[cost == float(nodata)] = np.inf
    cost[~np.isfinite(cost)] = np.inf
    cost[cost <= 0.0] = np.inf
    return cost


def _astar_mcp_geometric_accumulation(
    cost: np.ndarray,
    source: tuple[int, int],
    destination: tuple[int, int],
    *,
    sampling: tuple[float, float],
    line_bias_weight: float,
) -> AStarAccumulation:
    if not np.isfinite(cost[source]) or not np.isfinite(cost[destination]):
        raise RuntimeError("A* source or destination is not traversable")

    rows, cols = cost.shape
    walkable = np.isfinite(cost) & (cost > 0.0)
    min_cost = float(cost[walkable].min()) if np.any(walkable) else 0.0
    g_scores = np.full(cost.shape, math.inf, dtype="float64")
    tie_scores = np.full(cost.shape, math.inf, dtype="float64")
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {source: None}
    closed_nodes: set[tuple[int, int]] = set()
    closed = np.zeros(cost.shape, dtype=bool)
    sequence = count()
    heap: list[tuple[float, float, float, int, tuple[int, int]]] = []

    min_costs = {source: 0.0}
    parent_map = {source: None}

    g_scores[source] = 0.0
    tie_scores[source] = 0.0
    heapq.heappush(
        heap,
        _queue_entry(
            source,
            destination,
            source,
            0.0,
            0.0,
            min_cost,
            sampling,
            line_bias_weight,
            next(sequence),
        ),
    )

    while heap:
        current_cost,_,_,_, current = heapq.heappop(heap)
        if current in closed_nodes:
            continue

        if current == destination:
            closed_nodes.add(current)
            closed[current] = True
            return AStarAccumulation(
                path=_reconstruct_path(came_from, destination),
                best_cost=float(g_scores[destination]),
                g_scores=g_scores,
                closed=closed,
            )
        closed_nodes.add(current)
        closed[current] = True

        for neighbor in _neighbors(current, rows, cols, walkable):
            if neighbor in closed_nodes:
                continue
            new_g = g_scores[current] + _geometric_edge_cost(
                cost, current, neighbor, sampling
            )
            new_tie = _line_bias_score(neighbor, source, destination)
            improved = new_g < g_scores[neighbor] - 1e-9
            tied_better = (
                abs(new_g - g_scores[neighbor]) <= 1e-9
                and new_tie < tie_scores[neighbor]
            )
            if not improved and not tied_better:
                continue
            #  Relaxation step
            if new_g < min_costs.get(neighbor, float('inf')):
                min_costs[neighbor] = new_g
                parent_map[neighbor] = current

            g_scores[neighbor] = new_g
            tie_scores[neighbor] = new_tie
            came_from[neighbor] = current
            heapq.heappush(
                heap,
                _queue_entry(
                    neighbor,
                    destination,
                    source,
                    new_g,
                    new_tie,
                    min_cost,
                    sampling,
                    line_bias_weight,
                    next(sequence),
                ),
            )

    raise RuntimeError("A* MCP_Geometric path did not reach destination")


def _queue_entry(
    node: tuple[int, int],
    destination: tuple[int, int],
    source: tuple[int, int],
    g_score: float,
    tie_score: float,
    min_cost: float,
    sampling: tuple[float, float],
    line_bias_weight: float,
    sequence: int,
) -> tuple[float, float, float, int, tuple[int, int]]:
    heuristic = _euclidean_grid_distance(node, destination, sampling) * min_cost
    priority = g_score + heuristic + tie_score * line_bias_weight
    return priority, heuristic, _line_bias_score(node, source, destination), sequence, node


def _neighbors(
    node: tuple[int, int], rows: int, cols: int, walkable: np.ndarray
) -> Iterable[tuple[int, int]]:
    row, col = node
    for dr, dc in NEIGHBORS:
        candidate = row + dr, col + dc
        if 0 <= candidate[0] < rows and 0 <= candidate[1] < cols and walkable[candidate]:
            yield candidate


def _geometric_edge_cost(
    cost: np.ndarray,
    current: tuple[int, int],
    neighbor: tuple[int, int],
    sampling: tuple[float, float],
) -> float:
    dr = neighbor[0] - current[0]
    dc = neighbor[1] - current[1]
    offset_length = math.hypot(dr * sampling[0], dc * sampling[1])
    return offset_length * 0.5 * (float(cost[current]) + float(cost[neighbor]))


def _euclidean_grid_distance(
    a: tuple[int, int], b: tuple[int, int], sampling: tuple[float, float]
) -> float:
    return math.hypot((a[0] - b[0]) * sampling[0], (a[1] - b[1]) * sampling[1])


def _line_bias_score(
    node: tuple[int, int], source: tuple[int, int], destination: tuple[int, int]
) -> float:
    dx1 = node[1] - destination[1]
    dy1 = node[0] - destination[0]
    dx2 = source[1] - destination[1]
    dy2 = source[0] - destination[0]
    return abs(dx1 * dy2 - dx2 * dy1) / max(1.0, math.hypot(dx2, dy2))


def _reconstruct_path(
    came_from: dict[tuple[int, int], tuple[int, int] | None],
    destination: tuple[int, int],
) -> list[tuple[int, int]]:
    path = [destination]
    current = destination
    while came_from[current] is not None:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def _path_to_linestring(
    path: list[tuple[int, int]],
    transformer,
    *,
    start_xy: tuple[float, float],
    end_xy: tuple[float, float],
) -> LineString:
    points = [transformer.xy(row, col) for row, col in path]
    # points[0] = start_xy
    # points[-1] = end_xy
    return LineString(points)


def _distance_raster_to_line(
    line: LineString, meta: dict, shape: tuple[int, int]
) -> np.ndarray:
    transform = meta["transform"]
    cell_size = max(abs(float(transform.a)), abs(float(transform.e)))
    path_mask = geometry_mask(
        [line.buffer(max(cell_size*0.5,5) )],
        out_shape=shape,
        transform=transform,
        invert=True,
        all_touched=True,
    )
    return ndimage.distance_transform_edt(~path_mask, sampling=_raster_sampling(transform))


def _raster_sampling(transform) -> tuple[float, float]:
    return (abs(float(transform.e)), abs(float(transform.a)))


def _cell_area(transform) -> float:
    return abs(float(transform.a) * float(transform.e))


def _clamp_row_col(row_col: tuple[int, int], rows: int, cols: int) -> tuple[int, int]:
    return max(0, min(int(row_col[0]), rows - 1)), max(
        0, min(int(row_col[1]), cols - 1)
    )
