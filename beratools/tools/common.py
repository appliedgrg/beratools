"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng, Maverick Fong

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    This file is intended to be hosting common classes/functions for BERA Tools
"""

import argparse
import json
import shlex
import warnings

import geopandas as gpd
import numpy as np
import osgeo
import pyogrio
import pyproj
import rasterio
import shapely
import shapely.geometry as sh_geom
import shapely.ops as sh_ops
import xarray as xr
import xrspatial

from osgeo import gdal,osr
from rasterio import mask
from scipy import ndimage
from pathlib import Path

import beratools.core.constants as bt_const
from beratools.core.algo_merge_lines import custom_line_merge
from beratools.core.algo_split_with_lines import LineSplitter

# suppress pandas UserWarning: Geometry column contains no geometry when splitting lines
warnings.simplefilter(action="ignore", category=UserWarning)

# restore .shx for shapefile for using GDAL or pyogrio
gdal.SetConfigOption("SHAPE_RESTORE_SHX", "YES")
pyogrio.set_gdal_config_options({"SHAPE_RESTORE_SHX": "YES"})

# suppress all kinds of warnings
if not bt_const.BT_DEBUGGING:
    gdal.SetConfigOption("CPL_LOG", "NUL")  # GDAL warning
    warnings.filterwarnings("ignore")  # suppress warnings
    warnings.simplefilter(action="ignore", category=UserWarning)  # suppress Pandas UserWarning

def qc_merge_multilinestring(gdf):
    """
    QC step: Merge MultiLineStrings if possible, else split into LineStrings.

    Args:
        gdf (GeoDataFrame): Input GeoDataFrame.

    Returns:
        GeoDataFrame: Cleaned GeoDataFrame with only LineStrings.
    """
    records = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        # Try to merge MultiLineString
        if geom.geom_type == "MultiLineString":
            merged = custom_line_merge(geom)
            if merged.geom_type == "MultiLineString":
                # Could not merge, split into LineStrings
                for part in merged.geoms:
                    new_row = row.copy()
                    new_row.geometry = part
                    records.append(new_row)
            elif merged.geom_type == "LineString":
                new_row = row.copy()
                new_row.geometry = merged
                records.append(new_row)
            else:
                # Unexpected geometry, keep as is
                new_row = row.copy()
                new_row.geometry = merged
                records.append(new_row)
        elif geom.geom_type == "LineString":
            records.append(row)
        else:
            # Keep other geometry types unchanged
            records.append(row)
    # Build new GeoDataFrame
    out_gdf = gpd.GeoDataFrame(records, columns=gdf.columns, crs=gdf.crs)
    out_gdf = out_gdf[out_gdf.geometry.type == "LineString"].reset_index(drop=True)
    return out_gdf

def qc_split_lines_at_intersections(gdf):
    """
    QC step: Split lines at intersections so each segment becomes a separate line object.

    Args:
        gdf (GeoDataFrame): Input GeoDataFrame of LineStrings.

    Returns:
        GeoDataFrame: New GeoDataFrame with lines split at all intersection points.
    """
    splitter = LineSplitter(gdf)
    splitter.process()
    if splitter.split_lines_gdf is not None:
        return splitter.split_lines_gdf.reset_index(drop=True)
    else:
        return gdf.reset_index(drop=True)

def clip_raster(
    in_raster_file,
    clip_geom,
    buffer=0.0,
    out_raster_file=None,
    default_nodata=bt_const.BT_NODATA,
):
    out_meta = None
    with rasterio.open(in_raster_file) as raster_file:
        out_meta = raster_file.meta
        ras_nodata = out_meta["nodata"]
        if ras_nodata is None:
            ras_nodata = default_nodata

        clip_geo_buffer = [clip_geom.buffer(buffer)]
        out_image: np.ndarray
        out_image, out_transform = mask.mask(
            raster_file, clip_geo_buffer, crop=True, nodata=ras_nodata, filled=True
        )
        if np.isnan(ras_nodata):
            out_image[np.isnan(out_image)] = default_nodata

        elif np.isinf(ras_nodata):
            out_image[np.isinf(out_image)] = default_nodata
        else:
            out_image[out_image == ras_nodata] = default_nodata

        out_image = np.ma.masked_where(out_image == default_nodata, out_image)
        out_image.fill_value = default_nodata
        ras_nodata = default_nodata

        height, width = out_image.shape[1:]

        out_meta.update(
            {
                "driver": "GTiff",
                "height": height,
                "width": width,
                "transform": out_transform,
                "nodata": ras_nodata,
            }
        )

    if out_raster_file:
        with rasterio.open(out_raster_file, "w", **out_meta) as dest:
            dest.write(out_image)
            print("[Clip raster]: data saved to {}.".format(out_raster_file))

    return out_image, out_meta

def remove_nan_from_array(matrix):
    with np.nditer(matrix, op_flags=["readwrite"]) as it:
        for x in it:
            if np.isnan(x[...]):
                x[...] = bt_const.BT_NODATA_COST

def extract_string_from_printout(str_print, str_extract):
    str_array = shlex.split(str_print)  # keep string in double quotes
    str_array_enum = enumerate(str_array)
    index = 0
    for item in str_array_enum:
        if str_extract in item[1]:
            index = item[0]
            break
    str_out = str_array[index]
    return str_out.strip()

def check_arguments():
    # Get tool arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", type=json.loads)
    parser.add_argument("-p", "--processes")
    parser.add_argument("-v", "--verbose")
    args = parser.parse_args()

    verbose = True if args.verbose == "True" else False
    for item in args.input:
        if args.input[item].lower() == "false":
            args.input[item] = False
        elif args.input[item].lower() == "true":
            args.input[item] = True

    return args, verbose


def vector_crs(in_vector):
    osr_crs = osgeo.osr.SpatialReference()
    from pyproj.enums import WktVersion

    vec_crs = None
    # open input vector data as GeoDataFrame
    gpd_vector = gpd.GeoDataFrame.from_file(in_vector)
    try:
        if gpd_vector.crs is not None:
            vec_crs = gpd_vector.crs
            if osgeo.version_info.major < 3:
                osr_crs.ImportFromWkt(vec_crs.to_wkt(WktVersion.WKT1_GDAL))
            else:
                osr_crs.ImportFromEPSG(vec_crs.to_epsg())
            return osr_crs
        else:
            print("No CRS found in the input feature, please check!")
            exit()
    except Exception as e:
        print(e)
        exit()


def raster_crs(in_raster):
    osr_crs = osgeo.osr.SpatialReference()
    with rasterio.open(in_raster) as raster_file:
        from pyproj.enums import WktVersion

        try:
            if raster_file.crs is not None:
                vec_crs = raster_file.crs
                if osgeo.version_info.major < 3:
                    osr_crs.ImportFromWkt(vec_crs.to_wkt(WktVersion.WKT1_GDAL))
                else:
                    osr_crs.ImportFromEPSG(vec_crs.to_epsg())
                return osr_crs
            else:
                print("No Coordinate Reference System (CRS) find in the input feature, please check!")
                exit()
        except Exception as e:
            print(e)
            exit()


def compare_crs(crs_org, crs_dst):
    if crs_org and crs_dst:
        if crs_org.IsSameGeogCS(crs_dst):
            print("Check: Input file Spatial Reference are the same, continue.")
            return True
        else:
            crs_org_norm = pyproj.CRS(crs_org.ExportToWkt())
            crs_dst_norm = pyproj.CRS(crs_dst.ExportToWkt())
            if crs_org_norm.is_compound:
                crs_org_proj = crs_org_norm.sub_crs_list[0].coordinate_operation.name
            elif crs_org_norm.name == "unnamed":
                return False
            else:
                crs_org_proj = crs_org_norm.coordinate_operation.name

            if crs_dst_norm.is_compound:
                crs_dst_proj = crs_dst_norm.sub_crs_list[0].coordinate_operation.name
            elif crs_org_norm.name == "unnamed":
                return False
            else:
                crs_dst_proj = crs_dst_norm.coordinate_operation.name

            if crs_org_proj == crs_dst_proj:
                if crs_org_norm.name == crs_dst_norm.name:
                    print("Input files Spatial Reference are the same, continue.")
                    return True
                else:
                    print(
                        """Checked: Data are on the same projected Zone but using 
                        different Spatial Reference. \n Consider to re-project 
                        all data onto same spatial reference system.\n Process Stop."""
                    )
                    exit()
            else:
                return False

    return False


def identity_polygon(line_args):
    """
    Return polygon of line segment.

    Args:
        line_args : list[GeoDataFrame]
            0 : GeoDataFrame line segment, one item
            1 : GeoDataFrame line buffer, one item
            2 : GeoDataFrame polygons returned by spatial search

    Returns:
        line, identity :  tuple of line and associated footprint

    """
    line = line_args[0]
    in_cl_buffer = line_args[1][["geometry", "OLnFID"]]
    in_fp_polygon = line_args[2]

    identity = None
    try:
        # drop polygons not intersecting with line segment
        line_geom = line.iloc[0].geometry
        drop_list = []
        for i in in_fp_polygon.index:
            if not in_fp_polygon.loc[i].geometry.intersects(line_geom):
                drop_list.append(i)
            elif line_geom.intersection(in_fp_polygon.loc[i].geometry).length / line_geom.length < 0.30:
                drop_list.append(i)  # if less the 1/5 of line is inside of polygon, ignore

        # drop all polygons not used
        in_fp_polygon = in_fp_polygon.drop(index=drop_list)

        if not in_fp_polygon.empty:
            identity = in_fp_polygon.overlay(in_cl_buffer, how="intersection")
    except Exception as e:
        print(e)

    return line, identity


def line_split2(in_ln_shp, seg_length):
    # Check the OLnFID column in data. If it is not, column will be created
    if "OLnFID" not in in_ln_shp.columns.array:
        if bt_const.BT_DEBUGGING:
            print("Cannot find {} column in input line data")

        print(f"New column created: {'OLnFID'}, {'OLnFID'}")
        in_ln_shp["OLnFID"] = in_ln_shp.index
    line_seg = split_into_equal_Nth_segments(in_ln_shp, seg_length)

    return line_seg


def split_into_equal_Nth_segments(df, seg_length):
    odf = df
    crs = odf.crs
    if "OLnSEG" not in odf.columns.array:
        df["OLnSEG"] = np.nan
    df = odf.assign(geometry=odf.apply(lambda x: cut_line_by_length(x.geometry, seg_length), axis=1))
    df = df.explode()

    df["OLnSEG"] = df.groupby("OLnFID").cumcount()
    gdf = gpd.GeoDataFrame(df, geometry=df.geometry, crs=crs)
    gdf = gdf.sort_values(by=["OLnFID", "OLnSEG"])
    gdf = gdf.reset_index(drop=True)

    if "shape_leng" in gdf.columns.array:
        gdf["shape_leng"] = gdf.geometry.length
    elif "LENGTH" in gdf.columns.array:
        gdf["LENGTH"] = gdf.geometry.length
    else:
        gdf["shape_leng"] = gdf.geometry.length
    return gdf


def split_line_nPart(line, seg_length):
    seg_line = shapely.segmentize(line, seg_length)
    distances = np.arange(seg_length, line.length, seg_length)

    if len(distances) > 0:
        points = [shapely.line_interpolate_point(seg_line, distance) for distance in distances]

        split_points = shapely.multipoints(points)
        mline = sh_ops.split(seg_line, split_points)
    else:
        mline = seg_line

    return mline


def cut_line_by_length(line, length, merge_threshold=0.5):
    """
    Split line into segments of equal length.

    Merge the last segment with the second-to-last if its length
    is smaller than the given threshold.

    Args:
        line : LineString
            Line to be split by distance along the line.
        length : float
            Length of each segment to cut.
        merge_threshold : float, optional
            Threshold below which the last segment is merged with the previous one. Default is 0.5.

    Returns:
        List of LineString objects
            A list containing the resulting line segments.

    Example:
        ">>> from shapely.geometry import LineString
        ">>> line = LineString([(0, 0), (10, 0)])
        ">>> segments = cut_line_by_length(line, 3, merge_threshold=1)
        ">>> for segment in segments:
        ">>>     print(f"Segment: {segment}, Length: {segment.length}")

        Output:
        Segment: LINESTRING (0 0, 3 0), Length: 3.0
        Segment: LINESTRING (3 0, 6 0), Length: 3.0
        Segment: LINESTRING (6 0, 9 0), Length: 3.0
        Segment: LINESTRING (9 0, 10 0), Length: 1.0

        After merging the last segment with the second-to-last segment:

        Output:
        Segment: LINESTRING (0 0, 3 0), Length: 3.0
        Segment: LINESTRING (3 0, 6 0), Length: 3.0
        Segment: LINESTRING (6 0, 10 0), Length: 4.0

    """
    if line.has_z:
        # Remove the Z component of the line if it exists
        line = sh_ops.transform(lambda x, y, z=None: (x, y), line)

    if shapely.is_empty(line):
        return []

    # Segment the line based on the specified distance
    line = shapely.segmentize(line, length)
    lines = []
    end_pt = None

    while line.length > length:
        coords = list(line.coords)

        for i, p in enumerate(coords):
            p_dist = line.project(sh_geom.Point(p))

            # Check if the distance matches closely and split the line
            if abs(p_dist - length) < 1e-9:  # Use a small epsilon value
                lines.append(sh_geom.LineString(coords[: i + 1]))
                line = sh_geom.LineString(coords[i:])
                end_pt = None
                break
            elif p_dist > length:
                end_pt = line.interpolate(length)
                lines.append(sh_geom.LineString(coords[:i] + list(end_pt.coords)))
                line = sh_geom.LineString(list(end_pt.coords) + coords[i:])
                break

    if end_pt:
        lines.append(line)

    # Handle the threshold condition: merge the last segment if its length is below the threshold
    if len(lines) > 1:
        if lines[-1].length < merge_threshold:
            # Merge the last segment with the second-to-last one
            lines[-2] = sh_geom.LineString(list(lines[-2].coords) + list(lines[-1].coords))
            lines.pop()  # Remove the last segment after merging

    return lines

def chk_df_multipart(df, chk_shp_in_string):
    try:
        found = False
        if str.upper(chk_shp_in_string) in [x.upper() for x in df.geom_type.values]:
            found = True
            df = df.explode()
            if type(df) is gpd.geodataframe.GeoDataFrame:
                df["OLnSEG"] = df.groupby("OLnFID").cumcount()
                df = df.sort_values(by=["OLnFID", "OLnSEG"])
                df = df.reset_index(drop=True)
        else:
            found = False
        return df, found
    except Exception as e:
        print(e)
        return df, True


def dyn_fs_raster_stdmean(canopy_ndarray, kernel, nodata):
    # This function uses xrspatial which can handle large data but slow
    mask = canopy_ndarray.mask
    in_ndarray = np.ma.where(mask == True, np.nan, canopy_ndarray)
    result_ndarray = xrspatial.focal.focal_stats(
        xr.DataArray(in_ndarray.data), kernel, stats_funcs=["std", "mean"]
    )

    # Assign std and mean ndarray (return array contain nan value)
    reshape_std_ndarray = result_ndarray[0].data
    reshape_mean_ndarray = result_ndarray[1].data

    return reshape_std_ndarray, reshape_mean_ndarray


def dyn_smooth_cost(canopy_ndarray, max_line_dist, sampling):
    mask = canopy_ndarray.mask
    in_ndarray = np.ma.where(mask == True, np.nan, canopy_ndarray)
    # scipy way to do Euclidean distance transform
    euc_dist_array = ndimage.distance_transform_edt(
        np.logical_not(np.isnan(in_ndarray.data)), sampling=sampling
    )
    euc_dist_array[mask == True] = np.nan
    smooth1 = float(max_line_dist) - euc_dist_array
    smooth1[smooth1 <= 0.0] = 0.0
    smooth_cost_array = smooth1 / float(max_line_dist)

    return smooth_cost_array


def dyn_np_cost_raster(canopy_ndarray, cc_mean, cc_std, cc_smooth, avoidance, cost_raster_exponent):
    aM1a = cc_mean - cc_std
    aM1b = cc_mean + cc_std
    aM1 = np.divide(aM1a, aM1b, where=aM1b != 0, out=np.zeros(aM1a.shape, dtype=float))
    aM = (1 + aM1) / 2
    aaM = cc_mean + cc_std
    bM = np.where(aaM <= 0, 0, aM)
    cM = bM * (1 - avoidance) + (cc_smooth * avoidance)
    dM = np.where(canopy_ndarray.data == 1, 1, cM)
    eM = np.exp(dM)
    result = np.power(eM, float(cost_raster_exponent))

    return result


def dyn_np_cc_map(in_chm, canopy_ht_threshold, nodata):
    canopy_ndarray = np.ma.where(in_chm >= canopy_ht_threshold, 1.0, 0.0).astype(float)
    canopy_ndarray.fill_value = nodata

    return canopy_ndarray


def generate_line_args_DFP_NoClip(
    line_seg,
    work_in_bufferL,
    work_in_bufferC,
    in_chm_obj,
    in_chm,
    tree_radius,
    max_line_dist,
    canopy_avoidance,
    exponent,
    work_in_bufferR,
    canopy_thresh_percentage,
):
    line_argsL = []
    line_argsR = []
    line_argsC = []
    line_id = 0
    for record in range(0, len(work_in_bufferL)):
        line_bufferL = work_in_bufferL.loc[record, "geometry"]
        line_bufferC = work_in_bufferC.loc[record, "geometry"]
        LCut = work_in_bufferL.loc[record, "LDist_Cut"]

        nodata = bt_const.BT_NODATA
        line_argsL.append(
            [
                in_chm,
                float(work_in_bufferL.loc[record, "DynCanTh"]),
                float(tree_radius),
                float(max_line_dist),
                float(canopy_avoidance),
                float(exponent),
                in_chm_obj.res,
                nodata,
                line_seg.iloc[[record]],
                in_chm_obj.meta.copy(),
                line_id,
                LCut,
                "Left",
                canopy_thresh_percentage,
                line_bufferL,
            ]
        )

        line_argsC.append(
            [
                in_chm,
                float(work_in_bufferC.loc[record, "DynCanTh"]),
                float(tree_radius),
                float(max_line_dist),
                float(canopy_avoidance),
                float(exponent),
                in_chm_obj.res,
                nodata,
                line_seg.iloc[[record]],
                in_chm_obj.meta.copy(),
                line_id,
                10,
                "Center",
                canopy_thresh_percentage,
                line_bufferC,
            ]
        )

        line_id += 1

    line_id = 0
    for record in range(0, len(work_in_bufferR)):
        line_bufferR = work_in_bufferR.loc[record, "geometry"]
        RCut = work_in_bufferR.loc[record, "RDist_Cut"]
        line_bufferC = work_in_bufferC.loc[record, "geometry"]

        nodata = bt_const.BT_NODATA
        # TODO deal with inherited nodata and BT_NODATA_COST
        # TODO convert nodata to BT_NODATA_COST
        line_argsR.append(
            [
                in_chm,
                float(work_in_bufferR.loc[record, "DynCanTh"]),
                float(tree_radius),
                float(max_line_dist),
                float(canopy_avoidance),
                float(exponent),
                in_chm_obj.res,
                nodata,
                line_seg.iloc[[record]],
                in_chm_obj.meta.copy(),
                line_id,
                RCut,
                "Right",
                canopy_thresh_percentage,
                line_bufferR,
            ]
        )

        step = line_id + 1 + len(work_in_bufferL)
        total = len(work_in_bufferL) + len(work_in_bufferR)
        print(f' "PROGRESS_LABEL Preparing... {step} of {total}" ', flush=True)
        print(f" %{step / total * 100} ", flush=True)

        line_id += 1

    return line_argsL, line_argsR, line_argsC
