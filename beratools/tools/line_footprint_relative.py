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

from matplotlib.pylab import f

# if __name__ == "__main__":
#     current_file = Path(getsourcefile(lambda: 0)).resolve()
#     btool_dir = current_file.parents[2]
#     sys.path.insert(0, btool_dir.as_posix())

from beratools.core.line_footprint_functions import *
from beratools.core.canopy_threshold_relative import *


def line_footprint_relative(
    in_line,
    in_chm,
    max_ln_width,
    exp_shk_cell,
    out_footprint,
    out_centerline,
    off_ln_dist,
    canopy_percentile,
    canopy_thresh_percentage,
    tree_radius,
    max_line_dist,
    canopy_avoidance,
    exponent,
    processes,
    call_mode,
    log_level,
):

    verbose = True if call_mode == CallMode.GUI.value else False

    dy_cl_line = main_canopy_threshold_relative(
        in_line=in_line,
        in_chm=in_chm,
        canopy_percentile=int(float(canopy_percentile)),
        canopy_thresh_percentage=int(float(canopy_thresh_percentage)),
        full_step=bool(True),
        processes=int(float(processes)),
        verbose=bool(verbose),
    )

    if not dy_cl_line:
        print("[error]: main_canopy_threshold_relative did not return a valid path. Aborting footprint step.")
        return

    main_line_footprint_relative(
        in_line=dy_cl_line,
        in_chm=in_chm,
        max_ln_width=float(max_ln_width),
        out_footprint=out_footprint or "",
        out_centerline=out_centerline or "",
        exp_shk_cell=int(float(exp_shk_cell)),
        tree_radius=float(tree_radius),
        max_line_dist=float(max_line_dist),
        canopy_avoidance=float(canopy_avoidance),
        exponent=float(exponent),
        full_step=bool(True),
        canopy_thresh_percentage=int(float(canopy_thresh_percentage)),
        processes=int(float(processes)),
        verbose=bool(verbose),
    )

if __name__ == "__main__":
    from beratools.utility.tool_args import CallMode, compose_tool_kwargs
    start_time = time.time()
    print("[info]: Dynamic CC and Footprint processing started")
    print("[info]: Current time: {}".format(time.strftime("%d %b %Y %H:%M:%S", time.localtime())))

    args=compose_tool_kwargs("line_footprint_relative")

    line_footprint_relative(**args)

    print("{}%".format(100))
    print("[info]: Dynamic CC and Footprint processes finished")
    print("[info]: Current time: {}".format(time.strftime("%d %b %Y %H:%M:%S", time.localtime())))
    print("[info]: Total processing time (seconds): {}".format(round(time.time() - start_time, 3)))
