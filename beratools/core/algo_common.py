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
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyproj
import rasterio
import shapely
import shapely.affinity as sh_aff
import shapely.geometry as sh_geom
import shapely.ops as sh_ops
import skimage.graph as sk_graph
from osgeo import gdal
from scipy import ndimage

import beratools.core.algo_cost as algo_cost
import beratools.core.constants as bt_const

gpd.options.io_engine = "pyogrio"
DISTANCE_THRESHOLD = 2  # 1 meter for intersection neighborhood


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
        if layer is None:
            # Read the file without specifying a layer
            gdf = gpd.read_file(file_path)
        else:
            # Read the file with the specified layer
            gdf = gpd.read_file(file_path, layer=layer)

        # Clean the geometries in the GeoDataFrame
        gdf = clean_geometries(gdf)
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


def clean_geometries(gdf):
    """
    Remove rows with invalid, None, or empty geometries from the GeoDataFrame.

    Args:
        gdf (GeoDataFrame): The GeoDataFrame to clean.

    Returns:
        GeoDataFrame: The cleaned GeoDataFrame with valid, non-null,
        and non-empty geometries.

    """
    # Remove rows where the geometry is invalid, None, or empty
    gdf = gdf[gdf.geometry.is_valid]  # Only keep valid geometries
    gdf = gdf[~gdf.geometry.isna()]  # Remove rows with None geometries
    gdf = gdf[gdf.geometry.apply(lambda geom: not geom.is_empty)]  # Remove empty geometries
    return gdf


def clean_line_geometries(line_gdf):
    """Clean line geometries in the GeoDataFrame."""
    if line_gdf is None:
        return line_gdf

    if line_gdf.empty:
        return line_gdf

    line_gdf = line_gdf[~line_gdf.geometry.isna() & ~line_gdf.geometry.is_empty]
    line_gdf = line_gdf[line_gdf.geometry.length > bt_const.SMALL_BUFFER]
    return line_gdf


def prepare_lines_gdf(file_path, layer=None, proc_segments=True):
    """
    Split lines at vertices or return original rows.

    It handles for MultiLineString.

    """
    # Check if there are any MultiLineString geometries
    gdf = read_geospatial_file(file_path, layer=layer)

    # Explode MultiLineStrings into individual LineStrings
    if has_multilinestring(gdf):
        gdf = gdf.explode(index_parts=False)

    split_gdf_list = []

    for row in gdf.itertuples(index=False):  # Use itertuples to iterate
        line = row.geometry  # Access geometry directly via the named tuple

        # If proc_segment is True, split the line at vertices
        if proc_segments:
            coords = list(line.coords)  # Extract the list of coordinates (vertices)

            # For each LineString, split the line into segments by the vertices
            for i in range(len(coords) - 1):
                segment = sh_geom.LineString([coords[i], coords[i + 1]])

                # Copy over all non-geometry columns (excluding 'geometry')
                attributes = {col: getattr(row, col) for col in gdf.columns if col != "geometry"}
                single_row_gdf = gpd.GeoDataFrame([attributes], geometry=[segment], crs=gdf.crs)
                split_gdf_list.append(single_row_gdf)

        else:
            # If not proc_segment, add the original row as a single-row GeoDataFrame
            attributes = {col: getattr(row, col) for col in gdf.columns if col != "geometry"}
            single_row_gdf = gpd.GeoDataFrame([attributes], geometry=[line], crs=gdf.crs)
            split_gdf_list.append(single_row_gdf)

    return split_gdf_list


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

    if latlon:
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
