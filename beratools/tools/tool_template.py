"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: AUTHOR_NAME

Description:
    This script is tool template for the BERA Tools. The tool showcases
    how to create a new tool for the BERA Tools framework. It is a
    starting point for developers to implement their own tools. 
    It uses the GeoPandas to read and write geospatial data, 
    and the multiprocessing library to process the geospatial data.

    To integrate with GUI, work in the gui/assets/beratools.json is needed.
    Please see developer's guide for more details.

    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide template for tool.
"""

import time

import geopandas as gpd
import pandas as pd

import beratools.tools.common as bt_common
from beratools.core.tool_base import execute_multiprocessing


def tool_name(in_feature, in_layer, buffer_dist, out_feature, out_layer, processes, verbose):
    """
    Define tool entry point.

    Args:
        in_feature: input feature
        in_layer: layer name
        buffer_dist: buffer for input lines
        out_feature: output feature
        out_layer: layer name
        processes: number of processes to use
        verbose: verbosity level

    These arguments are defined in beratools.json file. Whenever possible,
    use execute_multiprocessing to run tasks in parallel to speedup.

    """
    buffer_dist = float(buffer_dist)
    gdf = gpd.read_file(in_feature, layer=in_layer)
    gdf_list = [(gdf.iloc[[i]], buffer_dist) for i in range(len(gdf))]

    results = execute_multiprocessing(buffer_worker, gdf_list, "tool_template", processes, verbose=verbose)

    buffered_gdf = gpd.GeoDataFrame(pd.concat(results, ignore_index=True), crs=gdf.crs)
    buffered_gdf.to_file(out_feature, layer=out_layer)


# task executed in a worker process
def buffer_worker(in_args):
    buffered = in_args[0].copy()
    buffer_dist = in_args[1]
    buffered["geometry"] = buffered.geometry.buffer(buffer_dist)
    return buffered


if __name__ == "__main__":
    start_time = time.time()
    in_args, in_verbose = bt_common.check_arguments()
    tool_name(**in_args.input, processes=int(in_args.processes), verbose=in_verbose)
    print("Elapsed time: {}".format(time.time() - start_time))
