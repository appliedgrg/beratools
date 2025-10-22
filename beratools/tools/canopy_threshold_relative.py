import os.path
from multiprocessing.pool import Pool
import geopandas as gpd
import json
import argparse
import time
import pandas as pd
import numpy as np
import shapely
from beratools.core.constants import *
from beratools.tools.common import *
import sys
import math


class OperationCancelledException(Exception):
    pass


def main_canopy_threshold_relative(
    callback,
    in_line,
    in_chm,
    off_ln_dist,
    canopy_percentile,
    canopy_thresh_percentage,
    tree_radius,
    max_line_dist,
    canopy_avoidance,
    exponent,
    full_step,
    processes,
    verbose,
):
    file_path, in_file_name = os.path.split(Path(in_line))
    out_file = os.path.join(Path(file_path), "DynCanTh_" + in_file_name)
    line_seg = gpd.GeoDataFrame.from_file(in_line)

    # check coordinate systems between line and raster features
    # with rasterio.open(in_chm) as in_raster:
    if compare_crs(vector_crs(in_line), raster_crs(in_chm)):
        pass
    else:
        print("Line and raster spatial references are not same, please check.")
        exit()

    # Check the canopy threshold percent in 0-100 range.  If it is not, 50% will be applied
    if not 100 >= int(canopy_percentile) > 0:
        canopy_percentile = 50

    # Check the Dynamic Canopy threshold column in data. If it is not, new column will be created
    if "DynCanTh" not in line_seg.columns.array:
        if BT_DEBUGGING:
            print("{} column not found in input line".format("DynCanTh"))
        print("New column created: {}".format("DynCanTh"))
        line_seg["DynCanTh"] = np.nan

    # Check the OLnFID column in data. If it is not, column will be created
    if "OLnFID" not in line_seg.columns.array:
        if BT_DEBUGGING:
            print("{} column not found in input line".format("OLnFID"))

        print("New column created: {}".format("OLnFID"))
        line_seg["OLnFID"] = line_seg.index

    # Check the OLnSEG column in data. If it is not, column will be created
    if "OLnSEG" not in line_seg.columns.array:
        if BT_DEBUGGING:
            print("{} column not found in input line".format("OLnSEG"))

        print("New column created: {}".format("OLnSEG"))
        line_seg["OLnSEG"] = 0

    line_seg = chk_df_multipart(line_seg, "LineString")[0]

    proc_segments = False
    if proc_segments:
        line_seg = split_into_segments(line_seg)
    else:
        pass

    # copy original line input to another GeoDataframe
    workln_dfC = gpd.GeoDataFrame.copy((line_seg),deep=True)
    workln_dfC.geometry = workln_dfC.geometry.simplify(tolerance=0.5, preserve_topology=True)

    print("%{}".format(5))

    worklnbuffer_dfLRing = gpd.GeoDataFrame.copy((workln_dfC),deep=True)
    worklnbuffer_dfRRing = gpd.GeoDataFrame.copy((workln_dfC),deep=True)

    print("Create ring buffer for input line to find the forest edge....")

    def multiringbuffer(df, nrings, ringdist):
        """
        Buffers an input dataframes geometry nring (number of rings) times, with a distance between
        rings of ringdist and returns a list of non overlapping buffers
        """

        rings = []  # A list to hold the individual buffers
        for ring in np.arange(0, ringdist, nrings):  # For each ring (1, 2, 3, ..., nrings)
            big_ring = df["geometry"].buffer(
                nrings + ring, single_sided=True, cap_style="flat"
            )  # Create one big buffer
            small_ring = df["geometry"].buffer(
                ring, single_sided=True, cap_style="flat"
            )  # Create one smaller one
            the_ring = big_ring.difference(small_ring)  # Difference the big with the small to create a ring
            if (
                ~shapely.is_empty(the_ring)
                or ~shapely.is_missing(the_ring)
                or not None
                or ~the_ring.area == 0
            ):
                if isinstance(the_ring, shapely.MultiPolygon) or isinstance(the_ring, shapely.Polygon):
                    rings.append(the_ring)  # Append the ring to the rings list
                else:
                    if isinstance(the_ring, shapely.GeometryCollection):
                        for i in range(0, len(the_ring.geoms)):
                            if not isinstance(the_ring.geoms[i], shapely.LineString):
                                rings.append(the_ring.geoms[i])
            print(" %{} ".format((ring / ringdist) * 100))

        return rings  # return the list

    # Create a column with the rings as a list

    worklnbuffer_dfLRing["mgeometry"] = worklnbuffer_dfLRing.apply(
        lambda x: multiringbuffer(df=x, nrings=1, ringdist=15), axis=1
    )

    worklnbuffer_dfLRing = worklnbuffer_dfLRing.explode("mgeometry")  # Explode to create a row for each ring
    worklnbuffer_dfLRing = worklnbuffer_dfLRing.set_geometry("mgeometry")
    worklnbuffer_dfLRing = (
        worklnbuffer_dfLRing.drop(columns=["geometry"]).rename_geometry("geometry").set_crs(workln_dfC.crs)
    )
    worklnbuffer_dfLRing["iRing"] = worklnbuffer_dfLRing.groupby(["OLnFID", "OLnSEG"]).cumcount()
    worklnbuffer_dfLRing = worklnbuffer_dfLRing.sort_values(by=["OLnFID", "OLnSEG", "iRing"])
    worklnbuffer_dfLRing = worklnbuffer_dfLRing.reset_index(drop=True)

    worklnbuffer_dfRRing["mgeometry"] = worklnbuffer_dfRRing.apply(
        lambda x: multiringbuffer(df=x, nrings=-1, ringdist=-15), axis=1
    )

    worklnbuffer_dfRRing = worklnbuffer_dfRRing.explode("mgeometry")  # Explode to create a row for each ring
    worklnbuffer_dfRRing = worklnbuffer_dfRRing.set_geometry("mgeometry")
    worklnbuffer_dfRRing = (
        worklnbuffer_dfRRing.drop(columns=["geometry"]).rename_geometry("geometry").set_crs(workln_dfC.crs)
    )
    worklnbuffer_dfRRing["iRing"] = worklnbuffer_dfRRing.groupby(["OLnFID", "OLnSEG"]).cumcount()
    worklnbuffer_dfRRing = worklnbuffer_dfRRing.sort_values(by=["OLnFID", "OLnSEG", "iRing"])
    worklnbuffer_dfRRing = worklnbuffer_dfRRing.reset_index(drop=True)

    print("Task done.")
    print("%{}".format(20))

    worklnbuffer_dfRRing["Percentile_RRing"] = np.nan
    worklnbuffer_dfLRing["Percentile_LRing"] = np.nan
    line_seg["CL_CutHt"] = np.nan
    line_seg["CR_CutHt"] = np.nan
    line_seg["RDist_Cut"] = np.nan
    line_seg["LDist_Cut"] = np.nan
    print("%{}".format(80))

    # calculate the Height percentile for each parallel area using CHM
    worklnbuffer_dfLRing = multiprocessing_Percentile(
        worklnbuffer_dfLRing,
        int(canopy_percentile),
        float(canopy_thresh_percentage),
        in_chm,
        processes,
        side="LRing",
    )

    worklnbuffer_dfLRing = worklnbuffer_dfLRing.sort_values(by=["OLnFID", "OLnSEG", "iRing"])
    worklnbuffer_dfLRing = worklnbuffer_dfLRing.reset_index(drop=True)

    worklnbuffer_dfRRing = multiprocessing_Percentile(
        worklnbuffer_dfRRing,
        int(canopy_percentile),
        float(canopy_thresh_percentage),
        in_chm,
        processes,
        side="RRing",
    )

    worklnbuffer_dfRRing = worklnbuffer_dfRRing.sort_values(by=["OLnFID", "OLnSEG", "iRing"])
    worklnbuffer_dfRRing = worklnbuffer_dfRRing.reset_index(drop=True)

    result = multiprocessing_RofC(line_seg, worklnbuffer_dfLRing, worklnbuffer_dfRRing, processes)
    print("%{}".format(40))
    print("Task done.")

    print("Saving percentile information to input line ...")
    gpd.GeoDataFrame.to_file(result, out_file)
    print("Saving percentile information to input line ...done.")

    if full_step:
        return out_file

    print("%{}".format(100))


def rate_of_change(in_arg):  # ,max_chmht):
    x = in_arg[0]
    Olnfid = in_arg[1]
    Olnseg = in_arg[2]
    side = in_arg[3]
    df = in_arg[4]
    index = in_arg[5]

    # Since the x interval is 1 unit, the array 'diff' is the rate of change (slope)
    diff = np.ediff1d(x)
    cut_dist = len(x) / 5

    median_percentile = np.nanmedian(x)
    if not np.isnan(median_percentile):
        cut_percentile = math.floor(median_percentile)
    else:
        cut_percentile = 0.5
    found = False
    changes = 1.50
    Change = np.insert(diff, 0, 0)
    scale_down = 1

    # test the rate of change is > than 150% (1.5), if it is
    # no result found then lower to 140% (1.4) until 110% (1.1)
    try:
        while not found and changes >= 1.1:
            for ii in range(0, len(Change) - 1):
                if x[ii] >= 0.5:
                    if (Change[ii]) >= changes:
                        cut_dist = (ii + 1) * scale_down
                        cut_percentile = math.floor(x[ii])
                        # median_diff=(cut_percentile-median_percentile)
                        if 0.5 >= cut_percentile:
                            if cut_dist > 5:
                                cut_percentile = 2
                                cut_dist = cut_dist * scale_down**3
                                print(
                                    "{}: OLnFID:{}, OLnSEG: {} @<0.5  found and modified".format(
                                        side, Olnfid, Olnseg
                                    ),
                                    flush=True,
                                )
                        elif 0.5 < cut_percentile <= 5.0:
                            if cut_dist > 6:
                                cut_dist = cut_dist * scale_down**3  # 4.0
                                print(
                                    "{}: OLnFID:{}, OLnSEG: {} @0.5-5.0  found and modified".format(
                                        side, Olnfid, Olnseg
                                    ),
                                    flush=True,
                                )
                        elif 5.0 < cut_percentile <= 10.0:
                            if cut_dist > 8:  # 5
                                cut_dist = cut_dist * scale_down**3
                                print(
                                    "{}: OLnFID:{}, OLnSEG: {} @5-10  found and modified".format(
                                        side, Olnfid, Olnseg
                                    ),
                                    flush=True,
                                )
                        elif 10.0 < cut_percentile <= 15:
                            if cut_dist > 5:
                                cut_dist = cut_dist * scale_down**3  # 5.5
                                print(
                                    "{}: OLnFID:{}, OLnSEG: {} @10-15  found and modified".format(
                                        side, Olnfid, Olnseg
                                    ),
                                    flush=True,
                                )
                        elif 15 < cut_percentile:
                            if cut_dist > 4:
                                cut_dist = cut_dist * scale_down**2
                                cut_percentile = 15.5
                                print(
                                    "{}: OLnFID:{}, OLnSEG: {} @>15  found and modified".format(
                                        side, Olnfid, Olnseg
                                    ),
                                    flush=True,
                                )
                        found = True
                        print(
                            "{}: OLnFID:{}, OLnSEG: {} rate of change found".format(side, Olnfid, Olnseg),
                            flush=True,
                        )
                        break
            changes = changes - 0.1

    except IndexError:
        pass

    # if still is no result found, lower to 10% (1.1), if no result found then default is used
    if not found:
        if 0.5 >= median_percentile:
            cut_dist = 4 * scale_down  # 3
            cut_percentile = 0.5
        elif 0.5 < median_percentile <= 5.0:
            cut_dist = 4.5 * scale_down  # 4.0
            cut_percentile = math.floor(median_percentile)
        elif 5.0 < median_percentile <= 10.0:
            cut_dist = 5.5 * scale_down  # 5
            cut_percentile = math.floor(median_percentile)
        elif 10.0 < median_percentile <= 15:
            cut_dist = 6 * scale_down  # 5.5
            cut_percentile = math.floor(median_percentile)
        elif 15 < median_percentile:
            cut_dist = 5 * scale_down  # 5
            cut_percentile = 15.5
        print(
            "{}: OLnFID:{}, OLnSEG: {} Estimated".format(side, Olnfid, Olnseg),
            flush=True,
        )
    if side == "Right":
        df["RDist_Cut"] = cut_dist
        df["CR_CutHt"] = cut_percentile
    elif side == "Left":
        df["LDist_Cut"] = cut_dist
        df["CL_CutHt"] = cut_percentile

    return df


def multiprocessing_RofC(line_seg, worklnbuffer_dfLRing, worklnbuffer_dfRRing, processes):
    in_argsL = []
    in_argsR = []

    for index in line_seg.index:
        resultsL = []
        resultsR = []
        Olnfid = int(line_seg.OLnFID.iloc[index])
        Olnseg = int(line_seg.OLnSEG.iloc[index])
        sql_dfL = worklnbuffer_dfLRing.loc[
            (worklnbuffer_dfLRing["OLnFID"] == Olnfid) & (worklnbuffer_dfLRing["OLnSEG"] == Olnseg)
        ].sort_values(by=["iRing"])
        PLRing = list(sql_dfL["Percentile_LRing"])
        sql_dfR = worklnbuffer_dfRRing.loc[
            (worklnbuffer_dfRRing["OLnFID"] == Olnfid) & (worklnbuffer_dfRRing["OLnSEG"] == Olnseg)
        ].sort_values(by=["iRing"])
        PRRing = list(sql_dfR["Percentile_RRing"])
        in_argsL.append([PLRing, Olnfid, Olnseg, "Left", line_seg.loc[index], index])
        in_argsR.append([PRRing, Olnfid, Olnseg, "Right", line_seg.loc[index], index])
        print(' "PROGRESS_LABEL Preparing grouped buffer areas...." ', flush=True)
        print(" %{} ".format((index + 1 / len(line_seg)) * 100))

    total_steps = len(in_argsL) + len(in_argsR)
    featuresL = []
    featuresR = []

    if PARALLEL_MODE == ParallelMode.MULTIPROCESSING:
        with Pool(processes=int(processes)) as pool:
            step = 0
            # execute tasks in order, process results out of order
            try:
                for resultL in pool.imap_unordered(rate_of_change, in_argsL):
                    if BT_DEBUGGING:
                        print("Got result: {}".format(resultL), flush=True)
                    featuresL.append(resultL)
                    step += 1
                    print(
                        ' "PROGRESS_LABEL Calculate Rate of Change In Buffer Area {} of {}" '.format(
                            step, total_steps
                        ),
                        flush=True,
                    )
                    print("%{}".format(step / total_steps * 100), flush=True)
            except Exception:
                print(Exception)
                raise

            gpdL = gpd.GeoDataFrame(pd.concat(featuresL, axis=1).T)
        with Pool(processes=int(processes)) as pool:
            try:
                for resultR in pool.imap_unordered(rate_of_change, in_argsR):
                    if BT_DEBUGGING:
                        print("Got result: {}".format(resultR), flush=True)
                    featuresR.append(resultR)
                    step += 1
                    print(
                        ' "PROGRESS_LABEL Calculate Rate of Change Area {} of {}" '.format(
                            step + len(in_argsL), total_steps
                        ),
                        flush=True,
                    )
                    print(
                        "%{}".format((step + len(in_argsL)) / total_steps * 100),
                        flush=True,
                    )
            except Exception:
                print(Exception)
                raise
            gpdR = gpd.GeoDataFrame(pd.concat(featuresR, axis=1).T)
    else:
        for rowL in in_argsL:
            featuresL.append(rate_of_change(rowL))

        for rowR in in_argsR:
            featuresR.append(rate_of_change(rowR))

        gpdL = gpd.GeoDataFrame(pd.concat(featuresL, axis=1).T)
        gpdR = gpd.GeoDataFrame(pd.concat(featuresR, axis=1).T)

    for index in line_seg.index:
        lnfid = line_seg.OLnFID.iloc[index]
        Olnseg = line_seg.OLnSEG.iloc[index]
        line_seg.loc[index, "RDist_Cut"] = float(
            gpdR.loc[(gpdR.OLnFID == lnfid) & (gpdR.OLnSEG == Olnseg)]["RDist_Cut"]
        )
        line_seg.loc[index, "LDist_Cut"] = float(
            gpdL.loc[(gpdL.OLnFID == lnfid) & (gpdL.OLnSEG == Olnseg)]["LDist_Cut"]
        )
        line_seg.loc[index, "CL_CutHt"] = float(
            gpdL.loc[(gpdL.OLnFID == lnfid) & (gpdL.OLnSEG == Olnseg)]["CL_CutHt"]
        )
        line_seg.loc[index, "CR_CutHt"] = float(
            gpdR.loc[(gpdR.OLnFID == lnfid) & (gpdR.OLnSEG == Olnseg)]["CR_CutHt"]
        )
        line_seg.loc[index, "DynCanTh"] = (
            line_seg.loc[index, "CL_CutHt"] + line_seg.loc[index, "CR_CutHt"]
        ) / 2
        print(
            ' "PROGRESS_LABEL Recording ... {} of {}" '.format(index + 1, len(line_seg)),
            flush=True,
        )
        print(" %{} ".format(index + 1 / len(line_seg) * 100), flush=True)

    return line_seg


def split_line_fc(line):
    if line:
        return list(map(shapely.LineString, zip(line.coords[:-1], line.coords[1:])))
    else:
        return None


def split_into_segments(df):
    odf = df
    crs = odf.crs
    if "OLnSEG" not in odf.columns.array:
        df["OLnSEG"] = np.nan
    else:
        pass
    df = odf.assign(geometry=odf.apply(lambda x: split_line_fc(x.geometry), axis=1))
    df = df.explode()

    df["OLnSEG"] = df.groupby("OLnFID").cumcount()
    gdf = gpd.GeoDataFrame(df, geometry=df.geometry, crs=crs)
    gdf = gdf.sort_values(by=["OLnFID", "OLnSEG"])
    gdf = gdf.reset_index(drop=True)
    return gdf


def multiprocessing_copyparallel_lineLRC(dfL, dfR, dfc, processes, left_dis, right_dist, center_dist):
    try:
        line_arg = []
        total_steps = len(dfL)

        for item in dfL.index:
            item_list = [dfL, dfR, dfc, left_dis, right_dist, center_dist, item]
            line_arg.append(item_list)

        featuresL = []
        featuresR = []
        result = None
        step = 0

        if PARALLEL_MODE == ParallelMode.MULTIPROCESSING:
            with Pool(processes=int(processes)) as pool:
                # execute tasks in order, process results out of order
                for result in pool.imap_unordered(copyparallel_lineLRC, line_arg):
                    if BT_DEBUGGING:
                        print(f"Got result: {result}", flush=True)
                    if result:
                        featuresL.append(result[0])  # resultL
                        featuresR.append(result[1])  # resultR
                    step += 1
                    print(f" %{step / total_steps * 100} ")

                return gpd.GeoDataFrame(pd.concat(featuresL)), gpd.GeoDataFrame(
                    pd.concat(featuresR)
                )  # ,  gpd.GeoDataFrame(pd.concat(featuresC))
        elif PARALLEL_MODE == ParallelMode.SEQUENTIAL:
            for line in line_arg:
                result = copyparallel_lineLRC(line)
                if BT_DEBUGGING:
                    print(f"Got result: {result}", flush=True)
                if result:
                    featuresL.append(result[0])  # resultL
                    featuresR.append(result[1])  # resultR
                step += 1
                print(f" %{step / total_steps * 100} ")

            return gpd.GeoDataFrame(pd.concat(featuresL)), gpd.GeoDataFrame(
                pd.concat(featuresR)
            )  # , gpd.GeoDataFrame(pd.concat(featuresC))

    except OperationCancelledException:
        print("Operation cancelled")


def multiprocessing_Percentile(df, CanPercentile, CanThrPercentage, in_CHM, processes, side):
    try:
        line_arg = []
        total_steps = len(df)
        cal_percentile = cal_percentileLR
        which_side = side
        if side == "left":
            PerCol = "Percentile_L"
            which_side = "left"
            cal_percentile = cal_percentileLR
        elif side == "right":
            PerCol = "Percentile_R"
            which_side = "right"
            cal_percentile = cal_percentileLR
        elif side == "LRing":
            PerCol = "Percentile_LRing"
            cal_percentile = cal_percentileRing
            which_side = "left"
        elif side == "RRing":
            PerCol = "Percentile_RRing"
            which_side = "right"
            cal_percentile = cal_percentileRing

        print("Calculating surrounding ({}) forest population for buffer area ...".format(which_side))

        for item in df.index:
            item_list = [
                df.iloc[[item]],
                CanPercentile,
                CanThrPercentage,
                in_CHM,
                item,
                PerCol,
            ]
            line_arg.append(item_list)
            print(
                ' "PROGRESS_LABEL Preparing... {} of {}" '.format(item + 1, len(df)),
                flush=True,
            )
            print(" %{} ".format(item / len(df) * 100), flush=True)

        features = []
        # chunksize = math.ceil(total_steps / processes)
        # PARALLEL_MODE=False
        if PARALLEL_MODE == ParallelMode.MULTIPROCESSING:
            with Pool(processes=int(processes)) as pool:
                step = 0
                # execute tasks in order, process results out of order
                try:
                    for result in pool.imap_unordered(cal_percentile, line_arg):
                        if BT_DEBUGGING:
                            print("Got result: {}".format(result), flush=True)
                        features.append(result)
                        step += 1
                        print(
                            ' "PROGRESS_LABEL Calculate Percentile In Buffer Area {} of {}" '.format(
                                step, total_steps
                            ),
                            flush=True,
                        )
                        print("%{}".format(step / total_steps * 100), flush=True)
                except Exception:
                    print(Exception)
                    raise
                del line_arg

            return gpd.GeoDataFrame(pd.concat(features))
        else:
            verbose = False
            total_steps = len(line_arg)
            step = 0
            for row in line_arg:
                features.append(cal_percentile(row))
                step += 1
                if verbose:
                    print(
                        ' "PROGRESS_LABEL Calculate Percentile on line {} of {}" '.format(step, total_steps),
                        flush=True,
                    )
                    print(" %{} ".format(step / total_steps * 100), flush=True)
            return gpd.GeoDataFrame(pd.concat(features))

    except OperationCancelledException:
        print("Operation cancelled")


def cal_percentileLR(line_arg):
    from shapely import ops

    try:
        df = line_arg[0]
        CanPercentile = line_arg[1]
        CanThrPercentage = line_arg[2]
        in_CHM = line_arg[3]
        row_index = line_arg[4]
        PerCol = line_arg[5]
        line_buffer = df.loc[row_index, "geometry"]

        if line_buffer.is_empty or shapely.is_missing(line_buffer):
            return None
        if line_buffer.has_z:
            line_buffer = ops.transform(lambda x, y, z=None: (x, y), line_buffer)
    except Exception as e:
        print(e)
        print("Assigning variable on index:{} Error: ".format(line_arg) + sys.exc_info())
        exit()

    # TODO: temporary workaround for exception causing not percentile defined
    percentile = 0
    Dyn_Canopy_Threshold = 0.05
    try:
        with rasterio.open(in_CHM) as raster:
            clipped_raster, out_transform = rasterio.mask.mask(
                raster, [line_buffer], crop=True, nodata=BT_NODATA, filled=True
            )
            clipped_raster = np.squeeze(clipped_raster, axis=0)

            # mask all -9999 (nodata) value cells
            masked_raster = np.ma.masked_where(clipped_raster == BT_NODATA, clipped_raster)
            filled_raster = np.ma.filled(masked_raster, np.nan)

            # Calculate the percentile
            # masked_mean = np.ma.mean(masked_raster)
            percentile = np.nanpercentile(filled_raster, CanPercentile)  # ,method='hazen')
            median = np.nanmedian(filled_raster)
            if percentile > 0.05:  # (percentile+median)>0.0:
                Dyn_Canopy_Threshold = percentile * (CanThrPercentage / 100.0)
            else:
                # print("(percentile)<0.05 @ {}".format(row_index))
                Dyn_Canopy_Threshold = 0.05

            del clipped_raster, out_transform
        del raster
    # return the generated value
    except Exception as e:
        print(e)
        # print(sys.exc_info())
        percentile = 0
        Dyn_Canopy_Threshold = 0

    try:
        df.loc[row_index, PerCol] = percentile
        df.loc[row_index, "DynCanTh"] = Dyn_Canopy_Threshold
        return df
    except Exception as e:
        print("Error writing Percentile and Dynamic Canopy into table: " + sys.exc_info())


def cal_percentileRing(line_arg):
    from shapely import ops

    try:
        df = line_arg[0]
        CanPercentile = line_arg[1]
        CanThrPercentage = line_arg[2]
        in_CHM = line_arg[3]
        row_index = line_arg[4]
        PerCol = line_arg[5]

        line_buffer = df.loc[row_index, "geometry"]
        if line_buffer.is_empty or shapely.is_missing(line_buffer):
            return None
        if line_buffer.has_z:
            line_buffer = ops.transform(lambda x, y, z=None: (x, y), line_buffer)

    except Exception as e:
        print(e)
        print("Assigning variable on index:{} Error: ".format(line_arg) + sys.exc_info())
        exit()

    # TODO: temporary workaround for exception causing not percentile defined
    percentile = 0.5
    Dyn_Canopy_Threshold = 0.05
    try:
        # with rasterio.open(in_CHM) as raster:
        # clipped_raster, out_transform = rasterio.mask.mask(raster, [line_buffer], crop=True,
        #                                                    nodata=BT_NODATA, filled=True)
        clipped_raster, out_meta = clip_raster(in_CHM, line_buffer, 0)
        clipped_raster = np.squeeze(clipped_raster, axis=0)

        # mask all -9999 (nodata) value cells
        masked_raster = np.ma.masked_where(clipped_raster == BT_NODATA, clipped_raster)
        filled_raster = np.ma.filled(masked_raster, np.nan)

        # Calculate the percentile
        # masked_mean = np.ma.mean(masked_raster)
        percentile = np.nanpercentile(filled_raster, 50)  # CanPercentile)#,method='hazen')

        if percentile > 1:  # (percentile+median)>0.0:
            Dyn_Canopy_Threshold = percentile * (0.3)
        else:
            Dyn_Canopy_Threshold = 1

        del clipped_raster, out_meta
        # del raster
    # return the generated value
    except Exception as e:
        print(e)
        # print('Something wrong in ID:{}'.format(row_index))
        print("Default values are used.")

    finally:
        df.loc[row_index, PerCol] = percentile
        df.loc[row_index, "DynCanTh"] = Dyn_Canopy_Threshold
        return df


def copyparallel_lineLRC(line_arg):
    dfL = line_arg[0]
    dfR = line_arg[1]

    # Simplify input center lines
    geom = dfL.loc[line_arg[6], "geometry"]
    if not geom:
        return None

    lineL = dfL.loc[line_arg[6], "geometry"].simplify(tolerance=0.05, preserve_topology=True)
    lineR = dfR.loc[line_arg[6], "geometry"].simplify(tolerance=0.05, preserve_topology=True)
    # lineC = dfC.loc[line_arg[6], 'geometry'].simplify(tolerance=0.05, preserve_topology=True)
    offset_distL = float(line_arg[3])
    offset_distR = float(line_arg[4])

    # Older alternative method to the offset_curve() method,
    # but uses resolution instead of quad_segs and a side keyword (‘left’ or ‘right’) instead
    # of sign of the distance. This method is kept for backwards compatibility for now,
    # but it is recommended to use offset_curve() instead.
    # (ref: https://shapely.readthedocs.io/en/stable/manual.html#object.offset_curve)
    parallel_lineL = lineL.parallel_offset(
        distance=offset_distL, side="left", join_style=shapely.BufferJoinStyle.mitre
    )

    parallel_lineR = lineR.parallel_offset(
        distance=-offset_distR, side="right", join_style=shapely.BufferJoinStyle.mitre
    )

    if not parallel_lineL.is_empty:
        dfL.loc[line_arg[6], "geometry"] = parallel_lineL
    if not parallel_lineR.is_empty:
        dfR.loc[line_arg[6], "geometry"] = parallel_lineR

    return dfL.iloc[[line_arg[6]]], dfR.iloc[[line_arg[6]]]  # ,dfC.iloc[[line_arg[6]]]


if __name__ == "__main__":
    start_time = time.time()
    print(
        "Starting Dynamic Canopy Threshold calculation processing\n @ {}".format(
            time.strftime("%d %b %Y %H:%M:%S", time.localtime())
        )
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", type=json.loads)
    parser.add_argument("-p", "--processes")
    parser.add_argument("-v", "--verbose")
    args = parser.parse_args()
    args.input["full_step"] = False

    verbose = True if args.verbose == "True" else False
    main_canopy_threshold_relative(print, **args.input, processes=int(args.processes), verbose=verbose)

    print("%{}".format(100))
    print(
        "Finishing Dynamic Canopy Threshold calculation @ {}\n(or in {} second)".format(
            time.strftime("%d %b %Y %H:%M:%S", time.localtime()),
            round(time.time() - start_time, 5),
        )
    )
