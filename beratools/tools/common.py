"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng, Maverick Fong

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    This file is intended to be hosting common spatial classes/functions for BERA Tools
"""
import geopandas as gpd
import numpy as np
import shapely
import shapely.geometry as sh_geom
import shapely.ops as sh_ops
import xarray as xr
import xrspatial
from scipy import ndimage

import beratools.core.constants as bt_const


def remove_nan_from_array(matrix):
    with np.nditer(matrix, op_flags=["readwrite"]) as it:
        for x in it:
            if np.isnan(x[...]):
                x[...] = bt_const.BT_NODATA_COST
                
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
