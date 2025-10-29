"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide main interface for centerline tool.
"""

import logging
import time
from pathlib import Path

import pandas as pd

import beratools.core.algo_centerline as algo_centerline
import beratools.core.algo_common as algo_common
import beratools.core.constants as bt_const
import beratools.utility.spatial_common as sp_common
from beratools.core.logger import Logger
from beratools.core.tool_base import execute_multiprocessing

log = Logger("centerline", file_level=logging.INFO)
logger = log.get_logger()
print = log.print


def generate_line_class_list(in_vector, in_raster, line_radius, layer=None, proc_segments=True) -> list:
    line_classes = []
    line_list = algo_common.prepare_lines_gdf(in_vector, layer, proc_segments)

    for item in line_list:
        line_classes.append(algo_centerline.SeedLine(item, in_raster, proc_segments, line_radius))

    return line_classes


def process_single_line_class(seed_line):
    seed_line.compute()
    return seed_line


def centerline(
    in_line,
    in_raster,
    line_radius,
    proc_segments,
    out_line,
    processes,
    verbose,
    in_layer=None,
    out_layer=None,
    parallel_mode=bt_const.ParallelMode.MULTIPROCESSING,
):
    if not sp_common.compare_crs(sp_common.vector_crs(in_line), sp_common.raster_crs(in_raster)):
        print("Line and CHM have different spatial references, please check.")
        return

    line_class_list = generate_line_class_list(
        in_line,
        in_raster,
        line_radius=float(line_radius),
        layer=in_layer,
        proc_segments=proc_segments,
    )

    print("{} lines to be processed.".format(len(line_class_list)))

    lc_path_list = []
    centerline_list = []
    corridor_poly_list = []
    result = execute_multiprocessing(
        process_single_line_class,
        line_class_list,
        "Centerline",
        processes,
        verbose=verbose,
        mode=parallel_mode,
    )
    if not result:
        print("No centerlines found.")
        return

    for item in result:
        lc_path_list.append(item.lc_path)
        centerline_list.append(item.centerline)
        corridor_poly_list.append(item.corridor_poly_gpd)

    # Concatenate the lists of GeoDataFrames into single GeoDataFrames
    if len(lc_path_list) == 0 or len(centerline_list) == 0 or len(corridor_poly_list) == 0:
        print("No centerline generated.")
        return 1

    lc_path_list = pd.concat(lc_path_list, ignore_index=True)
    centerline_list = pd.concat(centerline_list, ignore_index=True)
    corridor_polys = pd.concat(corridor_poly_list, ignore_index=True)

    # Save the concatenated GeoDataFrames to the shapefile/gpkg
    centerline_list.to_file(out_line, layer=out_layer)

    # Check if the output file is a shapefile
    out_line_path = Path(out_line)

    if out_line_path.suffix == ".shp":
        # Generate the new file name for the GeoPackage with '_aux' appended
        aux_file = out_line_path.with_name(out_line_path.stem + "_aux.gpkg")
        print(f"Saved auxiliary data to: {aux_file}")
    else:
        aux_file = out_line  # continue using out_line (gpkg)

    # Save lc_path_list and corridor_polys to the new GeoPackage with '_aux' suffix
    lc_path_list.to_file(aux_file, layer="least_cost_path")
    corridor_polys.to_file(aux_file, layer="corridor_polygon")


# TODO: fix geometries when job done
if __name__ == "__main__":
    in_args, in_verbose = sp_common.check_arguments()
    start_time = time.time()
    centerline(**in_args.input, processes=int(in_args.processes), verbose=in_verbose)
    print("Elapsed time: {}".format(time.time() - start_time))
