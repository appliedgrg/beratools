import math
import os.path
from multiprocessing.pool import Pool
from pathlib import Path

import pandas as pd
from parallel_pandas import ParallelPandas
from pandarallel import pandarallel

from beratools.core.constants import *
from beratools.tools.common import *
from beratools.utility.spatial_common import *
from beratools.core.tool_base import parallel_mode


class OperationCancelledException(Exception):
    pass


def main_canopy_threshold_relative(
    in_line: str,
    in_chm: str,
    canopy_percentile: int,
    canopy_thresh_percentage: int,
    full_step: bool,
    processes:int,
    out_dyn_centerline: str=None, #for Test tool only
)-> str | None:
    """
    This is a function finding approximate surrounding forest canopy height
    and surrounding forest edge distance from input CHM
    Args:
        in_line: Path like string
        in_chm: Path like string
        canopy_percentile: Percentile as integer range 1-100
        canopy_thresh_percentage: Percentage as integer range 1-100

    Returns:
        Path like string of the saved centerlines with extra attributes
    """
    file_path, in_file_name = os.path.split(Path(in_line))
    in_file, layer = decode_file_layer(in_line)
    if out_dyn_centerline==None:
        out_dyn_centerline = os.path.join(Path(file_path), "DynCanTh_" + in_file_name)
    out_cl_file, out_layer = decode_file_layer(out_dyn_centerline)
    line_seg = gpd.GeoDataFrame.from_file(in_file, layer=layer)
    _,processes=parallel_mode(processes)
    # check coordinate systems between line and raster features
    # with rasterio.open(in_chm) as in_raster:
    if compare_crs(vector_crs(in_file,layer), raster_crs(in_chm)):
        pass
    else:
        print("Line and raster spatial references are not same, please check.")
        exit()

    # Check the canopy threshold percent in 0-100 range.  If it is not, 50% will be applied
    if not 100 >= int(canopy_percentile) > 0:
        canopy_percentile = 50

    # Check the Dynamic Canopy threshold column in data. If it is not, new column will be created
    if "DynCanTh" not in line_seg.columns.array:
        print("New column created: {}".format("DynCanTh"))
        line_seg["DynCanTh"] = np.nan

    # Check the OLnFID column in data. If it is not, column will be created
    if "OLnFID" not in line_seg.columns.array:
        print("New column created: {}".format("OLnFID"))
        line_seg["OLnFID"] = line_seg.index

    # Check the OLnSEG column in data. If it is not, column will be created
    if "OLnSEG" not in line_seg.columns.array:
        print("New column created: {}".format("OLnSEG"))
        line_seg["OLnSEG"] = 0

    # Check input line for multipart
    line_seg = chk_df_multipart(line_seg, "LineString")[0]

    #Not splitting lines
    proc_segments = False
    if proc_segments:
        line_seg = split_into_segments(line_seg)
    else:
        pass

    # copy original line input to another GeoDataframe and simplify the line geometry for buffering
    workln_df_c = gpd.GeoDataFrame.copy(line_seg, deep=True)
    workln_df_c.geometry = workln_df_c.geometry.simplify(tolerance=0.5, preserve_topology=True)

    print("{}%".format(5))
    # copy simplified line input for ring buffer for two sides buffering
    worklnbuffer_df_l_ring = gpd.GeoDataFrame.copy((workln_df_c),deep=True)
    worklnbuffer_df_r_ring = gpd.GeoDataFrame.copy((workln_df_c),deep=True)

    print("Create ring buffer for input line to find the forest edge....")

    def multiringbuffer(df: gpd.GeoDataFrame,
                        nrings:int,
                        ringdist:int)->list:
        """
        Buffers an input dataframes geometry nring (number of rings) times, with a distance between
        rings of ringdist and returns a list of non overlapping buffers
        """
        import numpy as np
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
            print(" {}% ".format((ring / ringdist) * 100))

        return rings  # return the list

    # Create a column with the rings as a list
    print("Create rings buffer to forest edge on one side....")
    pandarallel.initialize(progress_bar=False,nb_workers=processes)
    worklnbuffer_df_l_ring["mgeometry"] = worklnbuffer_df_l_ring.parallel_apply(
        lambda x: multiringbuffer(df=x, nrings=1, ringdist=15), axis=1
    )

    # Explode to create a row for each ring
    worklnbuffer_df_l_ring = worklnbuffer_df_l_ring.explode("mgeometry")
    worklnbuffer_df_l_ring = worklnbuffer_df_l_ring.set_geometry("mgeometry")
    worklnbuffer_df_l_ring = (
        worklnbuffer_df_l_ring.drop(columns=["geometry"]).rename_geometry("geometry").set_crs(workln_df_c.crs)
    )
    worklnbuffer_df_l_ring["iRing"] = worklnbuffer_df_l_ring.groupby(["OLnFID", "OLnSEG"]).cumcount()
    worklnbuffer_df_l_ring = worklnbuffer_df_l_ring.sort_values(by=["OLnFID", "OLnSEG", "iRing"])
    worklnbuffer_df_l_ring = worklnbuffer_df_l_ring.reset_index(drop=True)

    print("Create rings buffer to forest edge on the other side....")
    pandarallel.initialize(progress_bar=False, nb_workers=processes)
    worklnbuffer_df_r_ring["mgeometry"] = worklnbuffer_df_r_ring.parallel_apply(
        lambda x: multiringbuffer(df=x, nrings=-1, ringdist=-15), axis=1
    )

    worklnbuffer_df_r_ring = worklnbuffer_df_r_ring.explode("mgeometry")  # Explode to create a row for each ring
    worklnbuffer_df_r_ring = worklnbuffer_df_r_ring.set_geometry("mgeometry")
    worklnbuffer_df_r_ring = (
        worklnbuffer_df_r_ring.drop(columns=["geometry"]).rename_geometry("geometry").set_crs(workln_df_c.crs)
    )
    worklnbuffer_df_r_ring["iRing"] = worklnbuffer_df_r_ring.groupby(["OLnFID", "OLnSEG"]).cumcount()
    worklnbuffer_df_r_ring = worklnbuffer_df_r_ring.sort_values(by=["OLnFID", "OLnSEG", "iRing"])
    worklnbuffer_df_r_ring = worklnbuffer_df_r_ring.reset_index(drop=True)

    print("Create rings buffer.... done.")
    print("{}%".format(20))

    worklnbuffer_df_r_ring["Percentile_RRing"] = np.nan
    worklnbuffer_df_l_ring["Percentile_LRing"] = np.nan
    line_seg["CL_CutHt"] = np.nan
    line_seg["CR_CutHt"] = np.nan
    line_seg["RDist_Cut"] = np.nan
    line_seg["LDist_Cut"] = np.nan
    print("{}%".format(30))

    # calculate the Height percentile for each parallel area using CHM
    worklnbuffer_df_l_ring = multiprocessing_percentile(
        worklnbuffer_df_l_ring,
        int(canopy_percentile),
        int(canopy_thresh_percentage),
        in_chm,
        processes,
        side="LRing",
    )

    worklnbuffer_df_l_ring = worklnbuffer_df_l_ring.sort_values(by=["OLnFID", "OLnSEG", "iRing"])
    worklnbuffer_df_l_ring = worklnbuffer_df_l_ring.reset_index(drop=True)
    print("{}%".format(60))
    worklnbuffer_df_r_ring = multiprocessing_percentile(
        worklnbuffer_df_r_ring,
        int(canopy_percentile),
        int(canopy_thresh_percentage),
        in_chm,
        processes,
        side="RRing",
    )

    worklnbuffer_df_r_ring = worklnbuffer_df_r_ring.sort_values(by=["OLnFID", "OLnSEG", "iRing"])
    worklnbuffer_df_r_ring = worklnbuffer_df_r_ring.reset_index(drop=True)

    result = multiprocessing_RofC(line_seg, worklnbuffer_df_l_ring, worklnbuffer_df_r_ring, processes)
    print("{}%".format(80))
    print("Calculating forest population done.")

    print("Saving percentile information to input line ...")
    gpd.GeoDataFrame.to_file(result, out_cl_file, layer=out_layer)
    print("Saving percentile information to input line ...done.")

    if full_step:
        return out_dyn_centerline  # TODO: make sure this is correct

    print("{}%".format(100))


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
        print(" {}% ".format(((index + 1) / len(line_seg)) * 100))

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
                    print("{}%".format(step / total_steps * 100), flush=True)
            except Exception:
                print(Exception)
                raise

            gpdL = gpd.GeoDataFrame(pd.concat(featuresL, axis=1).T)
        with Pool(processes=int(processes)) as pool:
            step=0
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
                        "{}%".format((step + len(in_argsL)) / total_steps * 100),
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

    line_seg = line_seg.set_index(['OLnFID', 'OLnSEG'], drop=True)
    gpdL['geometry'] = gpdL['geometry'].normalize()
    gpdL['wkt'] = gpdL['geometry'].apply(lambda x: x.wkt)
    deduplicated_gpdL = gpdL.drop_duplicates(subset=['wkt'], keep='first')
    deduplicated_gpdL = deduplicated_gpdL.drop(columns=['wkt']).reset_index(drop=True)
    gpdR['geometry'] = gpdR['geometry'].normalize()
    gpdR['wkt'] = gpdR['geometry'].apply(lambda x: x.wkt)
    deduplicated_gpdR = gpdR.drop_duplicates(subset=['wkt'], keep='first')
    deduplicated_gpdR = deduplicated_gpdR.drop(columns=['wkt']).reset_index(drop=True)

    mapping_left_ldist_cut = deduplicated_gpdL.set_index(['OLnFID', 'OLnSEG'])['LDist_Cut']
    mapping_left_rdist_cut = deduplicated_gpdR.set_index(['OLnFID', 'OLnSEG'])['RDist_Cut']
    mapping_left_lcl_cut = deduplicated_gpdL.set_index(['OLnFID', 'OLnSEG'])['CL_CutHt']
    mapping_left_rcl_cut = deduplicated_gpdR.set_index(['OLnFID', 'OLnSEG'])['CR_CutHt']

    condition_ldist_cut = line_seg.index.isin(mapping_left_ldist_cut.index)
    condition_rdist_cut = line_seg.index.isin(mapping_left_rdist_cut.index)
    condition_lcl_cut = line_seg.index.isin(mapping_left_lcl_cut.index)
    condition_rcl_cut = line_seg.index.isin(mapping_left_rcl_cut.index)

    line_seg.loc[condition_ldist_cut, "LDist_Cut"] = line_seg.index.map(mapping_left_ldist_cut)
    line_seg.loc[condition_rdist_cut, "RDist_Cut"] = line_seg.index.map(mapping_left_rdist_cut)
    line_seg.loc[condition_lcl_cut, "CL_CutHt"] = line_seg.index.map(mapping_left_lcl_cut)
    line_seg.loc[condition_rcl_cut, "CR_CutHt"] = line_seg.index.map(mapping_left_rcl_cut)
    line_seg["DynCanTh"] = (line_seg["CL_CutHt"] + line_seg["CR_CutHt"]) / 2
    line_seg=line_seg.reset_index(drop=False)


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

def multiprocessing_percentile(df:gpd.GeoDataFrame,
                               can_percentile:int,
                               can_thr_percentage:int,
                               in_chm: str,
                               processes:int,
                               side:str)->gpd.GeoDataFrame | None:
    try:
        line_arg = []
        total_steps = len(df)
        cal_percentile = cal_percentile_ring
        which_side = side
        per_col="Percentile_LRing"
        if side == "LRing":
            per_col = "Percentile_LRing"
            which_side = "left"
        elif side == "RRing":
            per_col = "Percentile_RRing"
            which_side = "right"

        print("Calculating surrounding ({}) forest population for buffer area ...".format(which_side))

        for item in df.index:
            item_list = [
                df.iloc[[item]],
                can_percentile,
                can_thr_percentage,
                in_chm,
                item,
                per_col,
            ]
            line_arg.append(item_list)
            print(
                ' "PROGRESS_LABEL Preparing lines... {} of {}" '.format(item + 1, len(df)),
                flush=True,
            )
            print(" {}% ".format(item / len(df) * 100), flush=True)

        features = []

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
                        print("{}%".format(step / total_steps * 100), flush=True)
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
                    print(" {}% ".format(step / total_steps * 100), flush=True)
            return gpd.GeoDataFrame(pd.concat(features))

    except OperationCancelledException:
        print("Operation cancelled")
        return None


def cal_percentile_ring(line_arg):
    from shapely import ops
    import traceback

    try:
        df = line_arg[0]
        can_percentile = line_arg[1]
        can_thr_percentage = line_arg[2]
        in_chm = line_arg[3]
        row_index = line_arg[4]
        per_col = line_arg[5]

        percentile = 1
        dyn_canopy_threshold = 1

        line_buffer = df.loc[row_index, "geometry"]
        if line_buffer.is_empty or shapely.is_missing(line_buffer):
            return None
        if line_buffer.has_z:
            line_buffer = ops.transform(lambda x, y, z=None: (x, y), line_buffer)

    except Exception as e:
        print(e)
        print("Assigning variable on index:{} Error: ".format(line_arg) + traceback.format_exc())
        exit()

    if isinstance(can_percentile,int):
        if 100>can_percentile>0:
            pass
        else:
            can_percentile = 50
    else:
        can_percentile =50

    try:

        clipped_raster, out_meta = clip_raster(in_chm, line_buffer, 0)
        clipped_raster = np.squeeze(clipped_raster, axis=0)

        # mask all -9999 (nodata) value cells
        masked_raster = np.ma.masked_where(clipped_raster == BT_NODATA, clipped_raster)
        filled_raster = np.ma.filled(masked_raster, np.nan)

        percentile = np.nanpercentile(filled_raster, can_percentile)

        if percentile > 1:
            dyn_canopy_threshold = percentile * (can_thr_percentage/100)
        else:
            dyn_canopy_threshold = 1

        del clipped_raster, out_meta

    # return the generated value
    except Exception as e:
        print(e)
        print("Default values are used.")

    finally:
        df.loc[row_index, per_col] = percentile
        df.loc[row_index, "DynCanTh"] = dyn_canopy_threshold
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

    return dfL.iloc[[line_arg[6]]], dfR.iloc[[line_arg[6]]]
