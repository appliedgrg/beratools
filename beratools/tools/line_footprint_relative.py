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
# line_footprint_relative.py
# Script Author: Maverick Fong
# Date: 2023-May
# Use open sources python library for produce dynamic footprint
# from dynamic canopy and cost raster with lines and CHM input.
# Prerequisite:  Line feature class must have the attribute Fields: "OLnFID" adn CHM raster
# line_footprint_relative.py
# This script is part of the BERA toolset
# Webpage: https://github.com/
#
# Purpose: Creates dynamic footprint polygons for each input line based on a least
# cost corridor method and individual line thresholds.
#
# ---------------------------------------------------------------------------
import sys
import json
import time
import argparse
from pathlib import Path
from inspect import getsourcefile

if __name__ == "__main__":
    current_file = Path(getsourcefile(lambda: 0)).resolve()
    btool_dir = current_file.parents[2]
    sys.path.insert(0, btool_dir.as_posix())

from beratools.core.line_footprint_functions import *
from beratools.core.canopy_threshold_relative import *
from beratools.utility.tool_args import CallMode

if __name__ == "__main__":
    start_time = time.time()
    print("Dynamic CC and Footprint processing started")
    print("Current time: {}".format(time.strftime("%d %b %Y %H:%M:%S", time.localtime())))
    debug_mode=False
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", type=json.loads)
    # parser.add_argument("-p", "--processes")
    # parser.add_argument("-v", "--verbose")

    parser.add_argument("-c", "--call_mode", default=CallMode.CLI.value)
    parser.add_argument("-p", "--processes", type=int, default=1)
    parser.add_argument("-l", "--log_level", default="INFO")

    args = parser.parse_args()
    args.input["full_step"] = True
    del args.input["out_footprint"]
    del args.input["out_centerline"]
    del args.input["exp_shk_cell"]
    del args.input["max_ln_width"]
    del args.input["off_ln_dist"]
    del args.input["tree_radius"]
    del args.input["max_line_dist"]
    del args.input["canopy_avoidance"]
    del args.input["exponent"]


    verbose = True if args.call_mode == CallMode.GUI.value else False
    dy_cl_line = main_canopy_threshold_relative(
    **args.input, processes=int(args.processes), verbose=verbose
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", type=json.loads)
    parser.add_argument("-p", "--processes")
    parser.add_argument("-v", "--verbose")
    args = parser.parse_args()
    args.input["full_step"] = True
    args.input["in_line"] = dy_cl_line.replace("\\","/")
    del args.input["off_ln_dist"]
    del args.input["canopy_percentile"]
    verbose = True if args.call_mode == CallMode.GUI.value else False
    main_line_footprint_relative(print, **args.input, processes=int(args.processes), verbose=verbose,debug_mode=debug_mode)

    print("{}%".format(100))
    print("Dynamic CC and Footprint processes finished")
    print("Current time: {}".format(time.strftime("%d %b %Y %H:%M:%S", time.localtime())))
    print("Total processing time (seconds): {}".format(round(time.time() - start_time, 3)))
