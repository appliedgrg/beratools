"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: AUTHOR NAME

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

import beratools.utility.spatial_common as sp_common
import beratools.utility.tool_args as tool_args
from beratools.core.tool_base import execute_multiprocessing
from beratools.utility.tool_args import CallMode


def tool_template(in_feature, buffer_dist, out_feature, 
                  processes=0, call_mode=CallMode.CLI, log_level="INFO"):
    """
    Define tool entry point.

    Args:
        in_feature: input feature (encoded as "file:layer")
        buffer_dist: buffer for input lines
        out_feature: output feature (encoded as "file:layer")
        processes: number of processes to use
        verbose: verbosity level

    These arguments are defined in beratools.json file. Whenever possible,
    use execute_multiprocessing to run tasks in parallel to speedup.

    """
    in_file, in_layer = sp_common.decode_file_layer(in_feature)
    out_file, out_layer = sp_common.decode_file_layer(out_feature)

    buffer_dist = float(buffer_dist)
    gdf = gpd.read_file(in_file, layer=in_layer)
    gdf_list = [(gdf.iloc[[i]], buffer_dist) for i in range(len(gdf))]

    # Set verbose based on log_level
    results = execute_multiprocessing(buffer_worker, gdf_list, "tool_template", processes, call_mode)

    buffered_gdf = gpd.GeoDataFrame(pd.concat(results, ignore_index=True), crs=gdf.crs)
    buffered_gdf.to_file(out_file, layer=out_layer)


# task executed in a worker process
def buffer_worker(in_args):
    buffered = in_args[0].copy()
    buffer_dist = in_args[1]
    buffered["geometry"] = buffered.geometry.buffer(buffer_dist)
    return buffered


if __name__ == "__main__":
    start_time = time.time()
    kwargs = tool_args.compose_tool_kwargs("tool_template")
    tool_template(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))
