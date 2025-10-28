# ---------------------------------------------------------------------------
#    Copyright (C) 2021  Applied Geospatial Research Group
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://gnu.org/licenses/gpl-3.0>.
#
# ---------------------------------------------------------------------------
#
# Refactor to use for produce dynamic footprint from dynamic canopy and cost raster with open source libraries
# Prerequisite:  Line feature class must have the attribute Fields:"CorridorTh" "DynCanTh" "OLnFID"
# line_footprint_function.py
# Maverick Fong
# Date: 2023-Dec
# This script is part of the BERA toolset
# Webpage: https://github.com/
#
# Purpose: Creates dynamic footprint polygons for each input line based on a least
# cost corridor method and individual line thresholds.
#
# ---------------------------------------------------------------------------

import time
from geopandas import GeoDataFrame
from shapely import buffer
from rasterio import features
from rasterio.mask import mask
from xrspatial import convolution

from skimage.graph import MCP_Flexible

from shapely.geometry import shape
from shapely import LineString, Point, MultiPolygon

from beratools.core.constants import *
from beratools.core.algo_centerline import *
from beratools.tools.common import *
from beratools.core.tool_base import *


def dyn_canopy_cost_raster(args):
    # raster_obj = args[0]
    in_chm_raster = args[0]
    DynCanTh = args[1]
    tree_radius = args[2]
    max_line_dist = args[3]
    canopy_avoid = args[4]
    exponent = args[5]
    res = args[6]
    nodata = args[7]
    line_df = args[8]
    out_meta = args[9]
    line_id = args[10]
    Cut_Dist = args[11]
    Side = args[12]
    canopy_thresh_percentage = float(args[13]) / 100
    line_buffer = args[14]

    if Side == "Left":
        canopy_ht_threshold = line_df.CL_CutHt * canopy_thresh_percentage
    elif Side == "Right":
        canopy_ht_threshold = line_df.CR_CutHt * canopy_thresh_percentage
    elif Side == "Center":
        canopy_ht_threshold = DynCanTh * canopy_thresh_percentage
    else:
        canopy_ht_threshold = 0.5

    canopy_ht_threshold = float(canopy_ht_threshold)
    if canopy_ht_threshold <= 0:
        canopy_ht_threshold = 0.5
    tree_radius = float(tree_radius)  # get the round up integer number for tree search radius
    max_line_dist = float(max_line_dist)
    canopy_avoid = float(canopy_avoid)
    cost_raster_exponent = float(exponent)

    try:
        clipped_rasterC, out_meta = clip_raster(in_chm_raster, line_buffer, 0)

        # clipped_rasterC, out_transformC = mask(raster_obj, [line_buffer], crop=True,
        #                                                     filled=False)

        in_chm = np.squeeze(clipped_rasterC, axis=0)

        # # make rasterio meta for saving raster later
        # out_meta = raster_obj.meta.copy()
        # out_meta.update({"driver": "GTiff",
        #                  "height": in_chm.shape[0],
        #                  "width": in_chm.shape[1],
        #                  "nodata": BT_NODATA,
        #                  "transform": out_transformC})

        # print('Loading CHM ...')
        cell_x, cell_y = out_meta["transform"][0], -out_meta["transform"][4]

        # print('Preparing Kernel window ...')
        kernel = convolution.circle_kernel(cell_x, cell_y, int(tree_radius))

        # Generate Canopy Raster and return the Canopy array
        dyn_canopy_ndarray = dyn_np_cc_map(in_chm, canopy_ht_threshold, BT_NODATA)

        # Calculating focal statistic from canopy raster
        cc_std, cc_mean = dyn_fs_raster_stdmean(dyn_canopy_ndarray, kernel, BT_NODATA)

        # Smoothing raster
        cc_smooth = dyn_smooth_cost(dyn_canopy_ndarray, max_line_dist, [cell_x, cell_y])
        avoidance = max(min(float(canopy_avoid), 1), 0)
        cost_clip = dyn_np_cost_raster(
            dyn_canopy_ndarray,
            cc_mean,
            cc_std,
            cc_smooth,
            avoidance,
            cost_raster_exponent,
        )
        negative_cost_clip = np.where(
            np.isnan(cost_clip), -9999, cost_clip
        )  # TODO was nodata, changed to BT_NODATA_COST
        return (
            line_df,
            dyn_canopy_ndarray,
            negative_cost_clip,
            out_meta,
            max_line_dist,
            nodata,
            line_id,
            Cut_Dist,
            line_buffer,
        )

    except Exception as e:
        print("Error in createing (dynamic) cost raster @ {}: {}".format(line_id, e))
        return None


def split_line_fc(line):
    return list(map(LineString, zip(line.coords[:-1], line.coords[1:])))


def split_line_npart(line):
    # Work out n parts for each line (divided by LP_SEGMENT_LENGTH)
    n = int(np.ceil(line.length / LP_SEGMENT_LENGTH))
    if n > 1:
        # divided line into n-1 equal parts;
        distances = np.linspace(0, line.length, n)
        points = [line.interpolate(distance) for distance in distances]
        line = LineString(points)
        mline = split_line_fc(line)
    else:
        mline = line
    return mline


def split_into_segments(df):
    odf = df
    crs = odf.crs
    if "OLnSEG" not in odf.columns.array:
        df["OLnSEG"] = np.nan

    df = odf.assign(geometry=odf.apply(lambda x: split_line_fc(x.geometry), axis=1))
    df = df.explode()

    df["OLnSEG"] = df.groupby("OLnFID").cumcount()
    gdf = GeoDataFrame(df, geometry=df.geometry, crs=crs)
    gdf = gdf.sort_values(by=["OLnFID", "OLnSEG"])
    gdf = gdf.reset_index(drop=True)
    return gdf


def split_into_equal_nth_segments(df):
    odf = df
    crs = odf.crs
    if "OLnSEG" not in odf.columns.array:
        df["OLnSEG"] = np.nan
    df = odf.assign(geometry=odf.apply(lambda x: split_line_npart(x.geometry), axis=1))
    df = df.explode(index_parts=True)

    df["OLnSEG"] = df.groupby("OLnFID").cumcount()
    gdf = GeoDataFrame(df, geometry=df.geometry, crs=crs)
    gdf = gdf.sort_values(by=["OLnFID", "OLnSEG"])
    gdf = gdf.reset_index(drop=True)
    return gdf


def generate_line_args(
    line_seg,
    work_in_bufferL,
    work_in_bufferC,
    raster,
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

        clipped_rasterL, out_transformL = mask(
            raster, [line_bufferL], crop=True, nodata=BT_NODATA, filled=True
        )
        clipped_rasterL = np.squeeze(clipped_rasterL, axis=0)

        clipped_rasterC, out_transformC = mask(
            raster, [line_bufferC], crop=True, nodata=BT_NODATA, filled=True
        )

        clipped_rasterC = np.squeeze(clipped_rasterC, axis=0)

        # make rasterio meta for saving raster later
        out_metaL = raster.meta.copy()
        out_metaL.update(
            {
                "driver": "GTiff",
                "height": clipped_rasterL.shape[0],
                "width": clipped_rasterL.shape[1],
                "nodata": BT_NODATA,
                "transform": out_transformL,
            }
        )

        out_metaC = raster.meta.copy()
        out_metaC.update(
            {
                "driver": "GTiff",
                "height": clipped_rasterC.shape[0],
                "width": clipped_rasterC.shape[1],
                "nodata": BT_NODATA,
                "transform": out_transformC,
            }
        )

        nodata = BT_NODATA
        line_argsL.append(
            [
                clipped_rasterL,
                float(work_in_bufferL.loc[record, "DynCanTh"]),
                float(tree_radius),
                float(max_line_dist),
                float(canopy_avoidance),
                float(exponent),
                raster.res,
                nodata,
                line_seg.iloc[[record]],
                out_metaL,
                line_id,
                LCut,
                "Left",
                canopy_thresh_percentage,
                line_bufferC,
            ]
        )

        line_argsC.append(
            [
                clipped_rasterC,
                float(work_in_bufferC.loc[record, "DynCanTh"]),
                float(tree_radius),
                float(max_line_dist),
                float(canopy_avoidance),
                float(exponent),
                raster.res,
                nodata,
                line_seg.iloc[[record]],
                out_metaC,
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
        clipped_rasterR, out_transformR = mask(
            raster, [line_bufferR], crop=True, nodata=BT_NODATA, filled=True
        )
        clipped_rasterR = np.squeeze(clipped_rasterR, axis=0)

        # make rasterio meta for saving raster later
        out_metaR = raster.meta.copy()
        out_metaR.update(
            {
                "driver": "GTiff",
                "height": clipped_rasterR.shape[0],
                "width": clipped_rasterR.shape[1],
                "nodata": BT_NODATA,
                "transform": out_transformR,
            }
        )
        line_bufferC = work_in_bufferC.loc[record, "geometry"]
        clipped_rasterC, out_transformC = mask(
            raster, [line_bufferC], crop=True, nodata=BT_NODATA, filled=True
        )

        clipped_rasterC = np.squeeze(clipped_rasterC, axis=0)
        out_metaC = raster.meta.copy()
        out_metaC.update(
            {
                "driver": "GTiff",
                "height": clipped_rasterC.shape[0],
                "width": clipped_rasterC.shape[1],
                "nodata": BT_NODATA,
                "transform": out_transformC,
            }
        )

        nodata = BT_NODATA
        # TODO deal with inherited nodata and BT_NODATA_COST
        # TODO convert nodata to BT_NODATA_COST
        line_argsR.append(
            [
                clipped_rasterR,
                float(work_in_bufferR.loc[record, "DynCanTh"]),
                float(tree_radius),
                float(max_line_dist),
                float(canopy_avoidance),
                float(exponent),
                raster.res,
                nodata,
                line_seg.iloc[[record]],
                out_metaR,
                line_id,
                RCut,
                "Right",
                canopy_thresh_percentage,
                line_bufferC,
            ]
        )

        print(
            ' "PROGRESS_LABEL Preparing... {} of {}" '.format(
                line_id + 1 + len(work_in_bufferL),
                len(work_in_bufferL) + len(work_in_bufferR),
            ),
            flush=True,
        )
        print(
            " %{} ".format(
                (line_id + 1 + len(work_in_bufferL)) / (len(work_in_bufferL) + len(work_in_bufferR)) * 100
            ),
            flush=True,
        )

        line_id += 1

    return line_argsL, line_argsR, line_argsC


#
# def find_corridor_threshold_boundary(canopy_clip, least_cost_path, corridor_raster):
#     threshold = -1
#     thresholds = [-1] * 10
#
#     # morphological filters to get polygons from canopy raster
#     canopy_bin = np.where(np.isclose(canopy_clip, 1.0), True, False)
#     clean_holes = remove_small_holes(canopy_bin)
#     clean_obj = remove_small_objects(clean_holes)
#
#     polys = features.shapes(skimage.img_as_ubyte(clean_obj), mask=clean_obj)
#     polys = [shape(poly).segmentize(FP_SEGMENTIZE_LENGTH) for poly, _ in polys]
#
#     # perpendicular segments intersections with polygons
#     size = corridor_raster.shape
#     pts = []
#     for poly in polys:
#         pts.extend(list(poly.exterior.coords))
#
#     index_0 = []
#     index_1 = []
#     for pt in pts:
#         if int(pt[0]) < size[1] and int(pt[1]) < size[0]:
#             index_0.append(int(pt[0]))
#             index_1.append(int(pt[1]))
#
#     try:
#         thresholds = corridor_raster[index_1, index_0]
#     except Exception as e:
#         print(e)
#
#     # trimmed mean of values at intersections
#     threshold = stats.trim_mean(thresholds, 0.3)
#
#     return threshold


def find_corridor_threshold(raster):
    """
    Find the optimal corridor threshold by raster histogram
    Parameters
    ----------
    raster : corridor raster

    Returns
    -------
    corridor_threshold : float

    """
    corridor_threshold = -1.0
    hist, bins = np.histogram(raster.flatten(), bins=100, range=(0, 100))
    CostStd = np.nanstd(raster.flatten())
    half_count = np.sum(hist) / 2
    sub_count = 0

    for count, bin_no in zip(hist, bins):
        sub_count += count
        if sub_count > half_count:
            break

        corridor_threshold = bin_no

    return corridor_threshold


def process_single_line_relative(segment):
    # in_chm = rasterio.open(segment[0])

    # segment[0] = in_chm
    # DynCanTh = segment[1]

    # Segment args from mulitprocessing:
    # [clipped_chm, float(work_in_bufferR.loc[record, 'DynCanTh']), float(tree_radius),
    # float(max_line_dist), float(canopy_avoidance), float(exponent), raster.res, nodata,
    # line_seg.iloc[[record]], out_meta, line_id,RCut,Side,canopy_thresh_percentage,line_buffer]

    # this will change segment content, and parameters will be changed
    segment = dyn_canopy_cost_raster(segment)
    if segment is None:
        return None
    # Segement after Clipped Canopy and Cost Raster
    # line_df, dyn_canopy_ndarray, negative_cost_clip, out_meta, max_line_dist, nodata, line_id,Cut_Dist,line_buffer

    # this function takes single line to work the line footprint
    # (regardless it process the whole line or individual segment)
    df = segment[0]
    in_canopy_r = segment[1]
    in_cost_r = segment[2]
    out_meta = segment[3]

    # in_transform = segment[3]
    if np.isnan(in_canopy_r).all():
        print("Canopy raster empty")

    if np.isnan(in_cost_r).all():
        print("Cost raster empty")

    in_meta = segment[3]
    exp_shk_cell = segment[4]
    no_data = segment[5]
    line_id = segment[6]
    Cut_Dist = segment[7]
    line_bufferR = segment[8]

    shapefile_proj = df.crs
    in_transform = in_meta["transform"]

    FID = df["OLnSEG"]  # segment line feature ID
    OID = df["OLnFID"]  # original line ID for segment line

    segment_list = []

    feat = df.geometry.iloc[0]
    for coord in feat.coords:
        segment_list.append(coord)

    cell_size_x = in_transform[0]
    cell_size_y = -in_transform[4]

    # Work out the corridor from both end of the centerline
    try:
        # TODO: further investigate and submit issue to skimage
        # There is a severe bug in skimage find_costs
        # when nan is present in clip_cost_r, find_costs cause access violation
        # no message/exception will be caught
        # change all nan to BT_NODATA_COST for workaround
        if len(in_cost_r.shape) > 2:
            in_cost_r = np.squeeze(in_cost_r, axis=0)
        remove_nan_from_array(in_cost_r)
        in_cost_r[in_cost_r == no_data] = np.inf

        # generate 1m interval points along line
        distance_delta = 1
        distances = np.arange(0, feat.length, distance_delta)
        multipoint_along_line = [feat.interpolate(distance) for distance in distances]
        multipoint_along_line.append(Point(segment_list[-1]))
        # Rasterize points along line
        rasterized_points_Alongln = features.rasterize(
            multipoint_along_line,
            out_shape=in_cost_r.shape,
            transform=in_transform,
            fill=0,
            all_touched=True,
            default_value=1,
        )
        points_Alongln = np.transpose(np.nonzero(rasterized_points_Alongln))

        # Find minimum cost paths through an N-d costs array.
        mcp_flexible1 = MCP_Flexible(in_cost_r, sampling=(cell_size_x, cell_size_y), fully_connected=True)
        flex_cost_alongLn, flex_back_alongLn = mcp_flexible1.find_costs(starts=points_Alongln)

        # Generate corridor
        # corridor = source_cost_acc + dest_cost_acc
        corridor = flex_cost_alongLn  # +flex_cost_dest #cum_cost_tosource+cum_cost_todestination
        corridor = np.ma.masked_invalid(corridor)

        # Calculate minimum value of corridor raster
        if not np.ma.min(corridor) is None:
            corr_min = float(np.ma.min(corridor))
        else:
            corr_min = 0.5

        # normalize corridor raster by deducting corr_min
        corridor_norm = corridor - corr_min

        # Set minimum as zero and save minimum file
        # corridor_th_value = find_corridor_threshold(corridor_norm)
        corridor_th_value = Cut_Dist / cell_size_x
        if corridor_th_value < 0:  # if no threshold found, use default value
            corridor_th_value = FP_CORRIDOR_THRESHOLD / cell_size_x

        # corridor_th_value = FP_CORRIDOR_THRESHOLD
        corridor_thresh = np.ma.where(corridor_norm >= corridor_th_value, 1.0, 0.0)
        corridor_thresh_cl = np.ma.where(corridor_norm >= (corridor_th_value + (5 / cell_size_x)), 1.0, 0.0)

        # find contiguous corridor polygon for centerline
        corridor_poly_gpd = find_corridor_polygon(corridor_thresh_cl, in_transform, df)

        # Process: Stamp CC and Max Line Width
        # Original code here
        # RasterClass = SetNull(IsNull(CorridorMin),((CorridorMin) + ((Canopy_Raster) >= 1)) > 0)
        temp1 = corridor_thresh + in_canopy_r
        raster_class = np.ma.where(temp1 == 0, 1, 0).data

        # BERA proposed Binary morphology
        # RasterClass_binary=np.where(RasterClass==0,False,True)
        if exp_shk_cell > 0 and cell_size_x < 1:
            # Process: Expand
            # FLM original Expand equivalent
            cell_size = int(exp_shk_cell * 2 + 1)

            expanded = ndimage.grey_dilation(raster_class, size=(cell_size, cell_size))

            # BERA proposed Binary morphology Expand
            # Expanded = ndimage.binary_dilation(RasterClass_binary, iterations=exp_shk_cell,border_value=1)

            # Process: Shrink
            # FLM original Shrink equivalent
            file_shrink = ndimage.grey_erosion(expanded, size=(cell_size, cell_size))

            # BERA proposed Binary morphology Shrink
            # fileShrink = ndimage.binary_erosion((Expanded),iterations=Exp_Shk_cell,border_value=1)
        else:
            print("No Expand And Shrink cell performed.")

            file_shrink = raster_class

        # Process: Boundary Clean
        clean_raster = ndimage.gaussian_filter(file_shrink, sigma=0, mode="nearest")

        # creat mask for non-polygon area
        polygon_mask = np.where(clean_raster == 1, True, False)
        if clean_raster.dtype == np.int64:
            clean_raster = clean_raster.astype(np.int32)

        # Process: ndarray to shapely Polygon
        out_polygon = features.shapes(clean_raster, mask=polygon_mask, transform=in_transform)

        # create a shapely multipolygon
        multi_polygon = []
        for poly, value in out_polygon:
            multi_polygon.append(shape(poly))
        poly = MultiPolygon(multi_polygon)

        # create a pandas dataframe for the FP
        out_data = pd.DataFrame(
            {
                "OLnFID": OID,
                "OLnSEG": FID,
                "CorriThresh": corridor_th_value,
                "geometry": poly,
            }
        )
        out_gdata = GeoDataFrame(out_data, geometry="geometry", crs=shapefile_proj)

        return out_gdata, corridor_poly_gpd

    except Exception as e:
        print("Exception: {}".format(e))


def multiprocessing_footprint_relative(line_args, processes):
    try:
        total_steps = len(line_args)

        feats = []
        # chunksize = math.ceil(total_steps / processes)
        with Pool(processes=processes) as pool:
            step = 0
            # execute tasks in order, process results out of order
            for result in pool.imap_unordered(process_single_line_relative, line_args):
                if BT_DEBUGGING:
                    print("Got result: {}".format(result), flush=True)
                if result != None:
                    feats.append(result)
                step += 1
                print(
                    ' "PROGRESS_LABEL Dynamic Segment Line Footprint {} of {}" '.format(step, total_steps),
                    flush=True,
                )
                print(" %{} ".format(step / total_steps * 100), flush=True)
        return feats
    except OperationCancelledException:
        print("Operation cancelled")
        return None


def main_line_footprint_relative(
    callback,
    in_line,
    in_chm,
    max_ln_width,
    exp_shk_cell,
    out_footprint,
    out_centerline,
    tree_radius,
    max_line_dist,
    canopy_avoidance,
    exponent,
    full_step,
    canopy_thresh_percentage,
    processes,
    verbose,
):
    # use_corridor_th_col = True
    line_seg = GeoDataFrame.from_file(in_line)

    # If Dynamic canopy threshold column not found, create one
    if "DynCanTh" not in line_seg.columns.array:
        print("Please create field {} first".format("DynCanTh"))
        exit()
    if not float(canopy_thresh_percentage):
        canopy_thresh_percentage = 50
    else:
        canopy_thresh_percentage = float(canopy_thresh_percentage)

    if float(canopy_avoidance) <= 0.0:
        canopy_avoidance = 0.0
    if float(exponent) <= 0.0:
        exponent = 1.0
    # If OLnFID column is not found, column will be created
    if "OLnFID" not in line_seg.columns.array:
        print("Created {} column in input line data.".format("OLnFID"))
        line_seg["OLnFID"] = line_seg.index

    if "OLnSEG" not in line_seg.columns.array:
        line_seg["OLnSEG"] = 0

    print("%{}".format(10))

    # check coordinate systems between line and raster features
    with rasterio.open(in_chm) as raster:
        line_args = []

        if compare_crs(vector_crs(in_line), raster_crs(in_chm)):
            proc_segments = False
            if proc_segments:
                print("Splitting lines into segments...")
                line_seg_split = split_into_segments(line_seg)
                print("Splitting lines into segments...Done")
            else:
                if full_step:
                    print("Tool runs on input lines......")
                    line_seg_split = line_seg
                else:
                    print("Tool runs on input segment lines......")
                    line_seg_split = split_into_equal_Nth_segments(line_seg, 250)

            print("%{}".format(20))

            work_in_bufferL1 = GeoDataFrame.copy(line_seg_split)
            work_in_bufferL2 = GeoDataFrame.copy(line_seg_split)
            work_in_bufferR1 = GeoDataFrame.copy(line_seg_split)
            work_in_bufferR2 = GeoDataFrame.copy(line_seg_split)
            work_in_bufferC = GeoDataFrame.copy(line_seg_split)
            work_in_bufferL1["geometry"] = buffer(
                work_in_bufferL1["geometry"],
                distance=float(max_ln_width) + 1,
                cap_style=3,
                single_sided=True,
            )

            work_in_bufferL2["geometry"] = buffer(
                work_in_bufferL2["geometry"],
                distance=-1,
                cap_style=3,
                single_sided=True,
            )

            work_in_bufferL = GeoDataFrame(pd.concat([work_in_bufferL1, work_in_bufferL2]))
            work_in_bufferL = work_in_bufferL.dissolve(by=["OLnFID", "OLnSEG"], as_index=False)

            work_in_bufferR1["geometry"] = buffer(
                work_in_bufferR1["geometry"],
                distance=-float(max_ln_width) - 1,
                cap_style=3,
                single_sided=True,
            )
            work_in_bufferR2["geometry"] = buffer(
                work_in_bufferR2["geometry"], distance=1, cap_style=3, single_sided=True
            )

            work_in_bufferR = GeoDataFrame(pd.concat([work_in_bufferR1, work_in_bufferR2]))
            work_in_bufferR = work_in_bufferR.dissolve(by=["OLnFID", "OLnSEG"], as_index=False)

            work_in_bufferC["geometry"] = buffer(
                work_in_bufferC["geometry"],
                distance=float(max_ln_width),
                cap_style=3,
                single_sided=False,
            )
            print("Prepare arguments for Dynamic FP ...")
            # line_argsL, line_argsR,line_argsC= generate_line_args(line_seg_split, work_in_bufferL,work_in_bufferC,
            #                                                       raster, tree_radius, max_line_dist,
            #                                                       canopy_avoidance, exponent, work_in_bufferR,
            #                                                       canopy_thresh_percentage)

            line_argsL, line_argsR, line_argsC = generate_line_args_DFP_NoClip(
                line_seg_split,
                work_in_bufferL,
                work_in_bufferC,
                raster,
                in_chm,
                tree_radius,
                max_line_dist,
                canopy_avoidance,
                exponent,
                work_in_bufferR,
                canopy_thresh_percentage,
            )

        else:
            print("Line and canopy raster spatial references are not same, please check.")
            exit()
        # pass center lines for footprint
        print("Generating Dynamic footprint ...")

        feat_listL = []
        feat_listR = []
        feat_listC = []
        poly_listL = []
        poly_listR = []
        footprint_listL = []
        footprint_listR = []
        footprint_listC = []
        # PARALLEL_MODE = ParallelMode.SEQUENTIAL
        if PARALLEL_MODE == ParallelMode.MULTIPROCESSING:
            # feat_listC = multiprocessing_footprint_relative(line_argsC, processes)
            feat_listL = multiprocessing_footprint_relative(line_argsL, processes)
            # feat_listL = execute_multiprocessing(process_single_line_relative,'Footprint',line_argsL, processes)
            feat_listR = multiprocessing_footprint_relative(line_argsR, processes)
            # feat_listR = execute_multiprocessing(process_single_line_relative, 'Footprint', line_argsR, processes)

        elif PARALLEL_MODE == ParallelMode.SEQUENTIAL:
            step = 1
            total_steps = len(line_argsL)
            print("There are {} result to process.".format(total_steps))
            for row in line_argsL:
                feat_listL.append(process_single_line_relative(row))
                print("Footprint (left side) for line {} is done".format(step))
                print(
                    ' "PROGRESS_LABEL Dynamic Line Footprint {} of {}" '.format(step, total_steps),
                    flush=True,
                )
                print(" %{} ".format((step / total_steps) * 100))
                step += 1
            step = 1
            total_steps = len(line_argsR)
            for row in line_argsR:
                feat_listR.append(process_single_line_relative(row))
                print("Footprint for (right side) line {} is done".format(step))
                print(
                    ' "PROGRESS_LABEL Dynamic Line Footprint {} of {}" '.format(step, total_steps),
                    flush=True,
                )
                print(" %{} ".format((step / total_steps) * 100))
                step += 1

    print("%{}".format(80))
    print("Task done.")

    for feat in feat_listL:
        if feat:
            footprint_listL.append(feat[0])
            poly_listL.append(feat[1])

    for feat in feat_listR:
        if feat:
            footprint_listR.append(feat[0])
            poly_listR.append(feat[1])

    print("Writing shapefile ...")
    resultsL = GeoDataFrame(pd.concat(footprint_listL))
    resultsL["geometry"] = resultsL["geometry"].buffer(0.005)
    resultsR = GeoDataFrame(pd.concat(footprint_listR))
    resultsR["geometry"] = resultsR["geometry"].buffer(0.005)
    resultsL = resultsL.sort_values(by=["OLnFID", "OLnSEG"])
    resultsR = resultsR.sort_values(by=["OLnFID", "OLnSEG"])
    resultsL = resultsL.reset_index(drop=True)
    resultsR = resultsR.reset_index(drop=True)
    #

    resultsAll = GeoDataFrame(pd.concat([resultsL, resultsR]))
    dissolved_results = resultsAll.dissolve(by="OLnFID", as_index=False)
    dissolved_results["geometry"] = dissolved_results["geometry"].buffer(-0.005)
    print("Saving output ...")
    dissolved_results.to_file(out_footprint)
    print("Footprint file saved")

    # dissolved polygon group by column 'OLnFID'
    print("Generating centerlines from corridor polygons ...")
    resultsCL = GeoDataFrame(pd.concat(poly_listL))
    resultsCL["geometry"] = resultsCL["geometry"].buffer(0.005)
    resultsCR = GeoDataFrame(pd.concat(poly_listR))
    resultsCR["geometry"] = resultsCR["geometry"].buffer(0.005)

    resultsCLR = GeoDataFrame(pd.concat([resultsCL, resultsCR]))
    resultsCLR = resultsCLR.dissolve(by="OLnFID", as_index=False)
    resultsCLR = resultsCLR.sort_values(by=["OLnFID", "OLnSEG"])
    resultsCLR = resultsCLR.reset_index(drop=True)
    resultsCLR["geometry"] = resultsCLR["geometry"].buffer(-0.005)

    # out_centerline=False
    # save lines to file
    if out_centerline:
        poly_centerline_gpd = find_centerlines(resultsCLR, line_seg, processes)
        poly_gpd = poly_centerline_gpd.copy()
        centerline_gpd = poly_centerline_gpd.copy()

        centerline_gpd = centerline_gpd.set_geometry("centerline")
        centerline_gpd = centerline_gpd.drop(columns=["geometry"])
        centerline_gpd.crs = poly_centerline_gpd.crs
        centerline_gpd.to_file(out_centerline)
        print("Centerline file saved")

        # save polygons
        path = Path(out_centerline)
        path = path.with_stem(path.stem + "_poly")
        poly_gpd = poly_gpd.drop(columns=["centerline"])
        poly_gpd.to_file(path)

    print("%{}".format(100))


if __name__ == "__main__":
    start_time = time.time()
    print("Dynamic Footprint processing started")
    print("Current time: {}".format(time.strftime("%d %b %Y %H:%M:%S", time.localtime())))

    in_args, in_verbose = check_arguments()
    main_line_footprint_relative(print, **in_args.input, processes=int(in_args.processes), verbose=in_verbose)

    print("%{}".format(100))
    print("Dynamic Footprint processing finished")
    print("Current time: {}".format(time.strftime("%d %b %Y %H:%M:%S", time.localtime())))
    print("Total processing time (seconds): {}".format(round(time.time() - start_time, 3)))
