"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide main interface for line grouping tool.
"""

import logging
import time

import geopandas as gpd

import beratools.tools.common as bt_common
from beratools.core.algo_line_grouping import LineGrouping
from beratools.core.logger import Logger


def check_seed_line(callback, in_line, out_line, processes, verbose, in_layer=None, out_layer=None):
    print("check_seed_line started")
    in_line_gdf = gpd.read_file(in_line, layer=in_layer)
    lg = LineGrouping(in_line_gdf)
    lg.run_grouping()
    lg.lines.to_file(out_line, layer=out_layer)


log = Logger("check_seed_line", file_level=logging.INFO)
logger = log.get_logger()
print = log.print

if __name__ == "__main__":
    in_args, in_verbose = bt_common.check_arguments()
    start_time = time.time()
    check_seed_line(print, **in_args.input, processes=int(in_args.processes), verbose=in_verbose)

    print("Elapsed time: {}".format(time.time() - start_time))
