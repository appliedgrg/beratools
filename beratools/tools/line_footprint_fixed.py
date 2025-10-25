"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng, Maverick Fong

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    This file hosts the line_footprint_fixed tool.
"""

import math
import time
from itertools import chain
from pathlib import Path

import geopandas as gpd
import pyogrio.errors
import numpy as np
import pandas as pd
import shapely.geometry as sh_geom
import shapely.ops as sh_ops
from shapely.ops import linemerge

import beratools.core.algo_common as algo_common
import beratools.core.constants as bt_const
import beratools.tools.common as bt_common
from beratools.core.algo_line_grouping import LineGrouping
from beratools.core.algo_merge_lines import MergeLines, custom_line_merge
from beratools.core.algo_split_with_lines import LineSplitter
from beratools.core.tool_base import execute_multiprocessing

FP_FIXED_WIDTH_DEFAULT = 5.0


def prepare_line_args(line_gdf, poly_gdf, n_samples, offset, width_percentile):
    """
    Generate arguments for each line in the GeoDataFrame.

    Args:
        line_gdf
        poly_gdf
        n_samples
        offset

    Returns:
        line_args : list
            row :
            inter_poly :
            n_samples :
            offset :
            width_percentile :

    """
    spatial_index = poly_gdf.sindex
    line_args = []

    for idx in line_gdf.index:
        row = line_gdf.loc[[idx]]
        line = row.geometry.iloc[0]

        # Skip rows where geometry is None
        if line is None:
            print(row)
            continue

        inter_poly = poly_gdf.loc[spatial_index.query(line)]
        if bt_const.BT_GROUP in inter_poly.columns:
            inter_poly = inter_poly[inter_poly[bt_const.BT_GROUP] == row[bt_const.BT_GROUP].values[0]]

        try:
            line_args.append([row, inter_poly, n_samples, offset, width_percentile])
        except Exception as e:
            print(e)

    return line_args


# Calculating Line Widths
def generate_sample_points(line, n_samples=10):
    """
    Generate evenly spaced points along a line.

    Args:
        line (LineString): The line along which to generate points.
        n_samples (int): The number of points to generate (default is 10).

    Returns:
        list:  List of shapely Point objects.

    """
    # TODO: determine line type
    try:
        pts = line.coords
    except Exception as e:  # TODO: check the code
        print(e)
        line = sh_ops.linemerge(line)
        tuple_coord = sh_geom.mapping(line)["coordinates"]
        pts = list(chain(*tuple_coord))

    return [sh_geom.Point(item) for item in pts]


def process_single_line(line_arg):
    row = line_arg[0]
    inter_poly = line_arg[1]
    n_samples = line_arg[2]
    offset = line_arg[3]
    width_percentile = line_arg[4]

    # TODO: deal with case when inter_poly is empty
    try:
        widths, line, perp_lines, perp_lines_original = calculate_average_width(
            row.iloc[0].geometry, inter_poly, offset, n_samples
        )
    except Exception as e:
        print(e)
        return None

    # Calculate the 75th percentile width
    # filter zeros in width array
    arr_filter = [False if math.isclose(i, 0.0) else True for i in widths]
    widths = widths[arr_filter]

    q3_width = FP_FIXED_WIDTH_DEFAULT
    q4_width = FP_FIXED_WIDTH_DEFAULT
    try:
        # TODO: check the code. widths is empty
        if len(widths) > 0:
            q3_width = np.percentile(widths, width_percentile)
            q4_width = np.percentile(widths, 90)
    except Exception as e:
        print(e)

    # Store the 75th percentile width as a new attribute
    row["avg_width"] = q3_width
    row["max_width"] = q4_width

    row["geometry"] = line
    try:
        row["perp_lines"] = perp_lines
        row["perp_lines_original"] = perp_lines_original
    except Exception as e:
        print(e)

    return row


def generate_fixed_width_footprint(line_gdf, max_width=False):
    """
    Create a buffer around each line.

    In the GeoDataFrame using its 'max_width' attribute and
    saves the resulting polygons in a new shapefile.

    Args:
    line_gdf: GeoDataFrame containing LineString with 'max_width' attribute.
    max_width: Use max width or not to produce buffer.

    """
    # Create a new GeoDataFrame with the buffer polygons
    buffer_gdf = line_gdf.copy(deep=True)

    mean_avg_width = line_gdf["avg_width"].mean()
    mean_max_width = line_gdf["max_width"].mean()

    # Use .loc to avoid chained assignment
    line_gdf.loc[line_gdf["avg_width"].isna(), "avg_width"] = mean_avg_width
    line_gdf.loc[line_gdf["max_width"].isna(), "max_width"] = mean_max_width

    line_gdf.loc[line_gdf["avg_width"] == 0.0, "avg_width"] = mean_avg_width
    line_gdf.loc[line_gdf["max_width"] == 0.0, "max_width"] = mean_max_width

    if not max_width:
        print("Using quantile 75% width")
        buffer_gdf["geometry"] = line_gdf.apply(
            lambda row: row.geometry.buffer(row.avg_width / 2) if row.geometry is not None else None,
            axis=1,
        )
    else:
        print("Using quantile 90% + 20% width")
        buffer_gdf["geometry"] = line_gdf.apply(
            lambda row: row.geometry.buffer(row.max_width * 1.2 / 2) if row.geometry is not None else None,
            axis=1,
        )

    return buffer_gdf


def calculate_average_width(line, in_poly, offset, n_samples):
    """Calculate the average width of a polygon perpendicular to the given line."""
    # Smooth the line
    try:
        line = line.simplify(0.1)

        valid_widths = 0
        sample_points = generate_sample_points(line, n_samples=n_samples)
        sample_points_pairs = list(zip(sample_points[:-2], sample_points[1:-1], sample_points[2:]))
        widths = np.zeros(len(sample_points_pairs))
        perp_lines = []
        perp_lines_original = []
    except Exception as e:
        print(e)

    try:
        for i, points in enumerate(sample_points_pairs):
            try:
                perp_line = algo_common.generate_perpendicular_line_precise(points, offset=offset)
                perp_lines_original.append(perp_line)
            except Exception as e:
                print(f"Failed to generate perpendicular at index {i}: {e}")
                perp_lines_original.append(None)
                continue

            try:
                polygon_intersect = in_poly.iloc[in_poly.sindex.query(perp_line)]
                intersections = polygon_intersect.intersection(perp_line)
            except Exception as e:
                print(f"Failed intersection at index {i}: {e}")
                intersections = []

            line_list = []
            for inter in intersections:
                if inter.is_empty:
                    continue

                if isinstance(inter, sh_geom.GeometryCollection):
                    for item in inter.geoms:
                        if isinstance(item, sh_geom.LineString):
                            line_list.append(item)
                elif isinstance(inter, sh_geom.MultiLineString):
                    line_list += list(inter.geoms)
                else:
                    line_list.append(inter)

            perp_lines += line_list

            if isinstance(line_list, sh_geom.GeometryCollection):
                print("Found 2: GeometryCollection")

            for item in line_list:
                widths[i] = max(widths[i], item.length)
                valid_widths += 1

            # Todo: check missing perpendicular lines
            # if len(perp_lines_original) < len(sample_points_pairs):
            #     print(f"Missing perpendicular at index {i}")

    except Exception as e:
        print(f"loop: {e}")

    return (
        widths,
        line,
        sh_geom.MultiLineString(perp_lines),
        sh_geom.MultiLineString(perp_lines_original),
    )


def line_footprint_fixed(
    in_line,
    in_footprint,
    n_samples,
    offset,
    max_width,
    out_footprint,
    processes,
    verbose,
    in_layer=None,
    in_layer_lc_path="least_cost_path",
    in_layer_fp=None,
    out_layer=None,
    merge_group=True,
    width_percentile=75,
    parallel_mode=bt_const.ParallelMode.MULTIPROCESSING,
    trim_output=True,
):
    n_samples = int(n_samples)
    offset = float(offset)
    width_percentile = int(width_percentile)

    import time
    print(f"[{time.time()}] Starting line_footprint_fixed")

    # TODO: refactor this code for better line quality check
    print("Step: Reading input files")
    line_gdf = gpd.read_file(in_line, layer=in_layer)
    if bt_const.BT_GROUP not in line_gdf.columns:
        line_gdf[bt_const.BT_GROUP] = range(1, len(line_gdf) + 1)

    use_least_cost_path = True
    try:
        print("Step: Reading least cost path layer")
        lc_path_gdf = gpd.read_file(in_line, layer=in_layer_lc_path)
    except (ValueError, OSError, pyogrio.errors.DataLayerError):
        print(f"Layer '{in_layer_lc_path}' not found in {in_line}, skipping least cost path logic.")
        use_least_cost_path = False

    print(f"[{time.time()}] Finished reading input files")

    if not merge_group:
        print("Step: Merging lines")
        line_gdf["geometry"] = line_gdf.geometry.apply(custom_line_merge)
        if use_least_cost_path:
            lc_path_gdf["geometry"] = lc_path_gdf.geometry.apply(custom_line_merge)

    print("Step: Cleaning line geometries")
    line_gdf = algo_common.clean_line_geometries(line_gdf)
    print(f"[{time.time()}] Finished cleaning line geometries")

    # read footprints and remove holes
    print("Step: Reading footprint polygons")
    poly_gdf = gpd.read_file(in_footprint, layer=in_layer_fp)
    poly_gdf["geometry"] = poly_gdf["geometry"].apply(algo_common.remove_holes)
    print(f"[{time.time()}] Finished reading footprint polygons")

    # merge group and/or split lines at intersections
    merged_line_gdf = line_gdf.copy(deep=True)
    if merge_group:
        print("Step: Running line grouping and merging")
        lg = LineGrouping(line_gdf, merge_group)
        lg.run_grouping()
        merged_line_gdf = lg.run_line_merge()
    else:
        print("Step: Running line grouping, merging, and splitting")
        try:
            lg = LineGrouping(line_gdf, not merge_group)
            lg.run_grouping()
            merged_line_gdf = lg.run_line_merge()
            splitter = LineSplitter(merged_line_gdf)
            splitter.process()
            splitter.save_to_geopackage(
                out_footprint,
                line_layer="split_centerline",
                intersection_layer="inter_points",
                invalid_layer="invalid_splits",
            )

            # least cost path merge and split
            if use_least_cost_path:
                print("Step: Running least cost path grouping, merging, and splitting")
                lg_leastcost = LineGrouping(lc_path_gdf, not merge_group)
                lg_leastcost.run_grouping()
                merged_lc_path_gdf = lg_leastcost.run_line_merge()
                splitter_leastcost = LineSplitter(merged_lc_path_gdf)
                splitter_leastcost.process(splitter.intersection_gdf)

                splitter_leastcost.save_to_geopackage(
                    out_footprint,
                    line_layer="split_leastcost",
                )

                lg = LineGrouping(splitter.split_lines_gdf, merge_group)
                lg.run_grouping()
                merged_line_gdf = lg.run_line_merge()
        except ValueError as e:
            print(f"Exception: line_footprint_fixed: {e}")

        print(f"[{time.time()}] Finished merging and splitting lines")

                # save original merged lines
    print("Step: Saving merged lines")
    merged_line_gdf.to_file(out_footprint, layer="merged_lines_original")

    # prepare line arguments
    print("Step: Preparing line arguments for multiprocessing")
    line_args = prepare_line_args(merged_line_gdf, poly_gdf, n_samples, offset, width_percentile)
    print(f"[{time.time()}] Finished preparing line arguments")

    print("Step: Running multiprocessing for fixed footprint calculation")
    out_lines = execute_multiprocessing(
    process_single_line, line_args, "Fixed footprint", processes, mode=parallel_mode
    )
    line_attr = pd.concat(out_lines)
    print(f"[{time.time()}] Finished multiprocessing")

    # Ensure BT_GROUP is present in line_attr
    if bt_const.BT_GROUP not in line_attr.columns:
        raise ValueError("BT_GROUP column is required in line_attr but is missing.")

    # update avg_width and max_width by max value of group
    if not merge_group:
        group_max = (
            line_attr.groupby(bt_const.BT_GROUP).agg({"avg_width": "max", "max_width": "max"}).reset_index()
        )

        # Merge the result back to the original dataframe based on 'group'
        line_attr = line_attr.merge(group_max, on=bt_const.BT_GROUP, suffixes=("", "_max"))

        # Overwrite the original columns directly with the max values
        line_attr["avg_width"] = line_attr["avg_width_max"]
        line_attr["max_width"] = line_attr["max_width_max"]

        # Drop the temporary max columns
        line_attr.drop(columns=["avg_width_max", "max_width_max"], inplace=True)

        print(f"[{time.time()}] Finished updating widths")

    # create fixed width footprint (always assign buffer_gdf)
    print("Step: Generating fixed width footprints")
    buffer_gdf = generate_fixed_width_footprint(line_attr, max_width=max_width)
    print(f"[{time.time()}] Finished generating footprints")

    # reserve all layers for output
    perp_lines_gdf = buffer_gdf.copy(deep=True)
    perp_lines_original_gdf = buffer_gdf.copy(deep=True)

    # Save untrimmed fixed width footprint
    buffer_gdf = buffer_gdf.drop(columns=["perp_lines"])
    buffer_gdf = buffer_gdf.drop(columns=["perp_lines_original"])
    buffer_gdf = buffer_gdf.set_crs(perp_lines_gdf.crs, allow_override=True)
    buffer_gdf.reset_index(inplace=True, drop=True)

    print("Step: Saving untrimmed fixed width footprint")
    untrimmed_footprint = "untrimmed_footprint"
    buffer_gdf.to_file(out_footprint, layer=untrimmed_footprint)
    print(f"Untrimmed fixed width footprint saved as '{untrimmed_footprint}'")
    print(f"[{time.time()}] Finished saving untrimmed footprint")

    # trim lines and footprints
    if trim_output:
        print("Step: Trimming lines and footprints")
        lg.run_cleanup(buffer_gdf)
        # Ensure only polygons are saved in clean_footprint
        def ensure_polygons(gdf, buffer_width=0.01):
            gdf['geometry'] = gdf['geometry'].apply(
                lambda geom: geom.buffer(buffer_width) if geom.geom_type in ['LineString', 'MultiLineString'] else geom
            )
            gdf = gdf[gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]
            return gdf
        # Patch: after trimming, ensure polygons in clean_footprint layer
        if hasattr(lg, "merged_lines_trimmed") and lg.merged_lines_trimmed is not None:
            lg.merged_lines_trimmed = ensure_polygons(lg.merged_lines_trimmed)
            print("Step: Saving trimmed outputs")
            lg.save_file(out_footprint)
            print(f"[{time.time()}] Finished trimming")
        else:
            print("Skipping line and footprint trimming per user option.")

    # perpendicular lines
    layer = "perp_lines"
    out_footprint = Path(out_footprint)
    out_aux_gpkg = out_footprint.with_stem(out_footprint.stem + "_aux").with_suffix(".gpkg")
    print("Step: Saving auxiliary outputs")
    perp_lines_gdf = perp_lines_gdf.set_geometry("perp_lines")
    perp_lines_gdf = perp_lines_gdf.drop(columns=["perp_lines_original"])
    perp_lines_gdf = perp_lines_gdf.drop(columns=["geometry"])
    perp_lines_gdf = perp_lines_gdf.set_crs(buffer_gdf.crs, allow_override=True)
    perp_lines_gdf.to_file(out_aux_gpkg.as_posix(), layer=layer)

    layer = "perp_lines_original"
    perp_lines_original_gdf = perp_lines_original_gdf.set_geometry("perp_lines_original")
    perp_lines_original_gdf = perp_lines_original_gdf.drop(columns=["perp_lines"])
    perp_lines_original_gdf = perp_lines_original_gdf.drop(columns=["geometry"])
    perp_lines_original_gdf = perp_lines_original_gdf.set_crs(buffer_gdf.crs, allow_override=True)
    perp_lines_original_gdf.to_file(out_aux_gpkg.as_posix(), layer=layer)

    layer = "centerline_simplified"
    # Drop perp_lines_original column if present to avoid export warnings
    if "perp_lines_original" in line_attr.columns:
        line_attr = line_attr.drop(columns=["perp_lines_original"])
    line_attr = line_attr.drop(columns="perp_lines")
    line_attr.to_file(out_aux_gpkg.as_posix(), layer=layer)

    # save footprints without holes
    poly_gdf.to_file(out_aux_gpkg.as_posix(), layer="footprint_no_holes")

    print(f"[{time.time()}] Finished saving auxiliary outputs")
    print("Step: Finished fixed width footprint tool")


if __name__ == "__main__":
    in_args, in_verbose = bt_common.check_arguments()
    start_time = time.time()
    line_footprint_fixed(**in_args.input, processes=int(in_args.processes), verbose=in_verbose)
    print("Elapsed time: {}".format(time.time() - start_time))
