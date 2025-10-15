"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is the public interface for vertex optimization.
"""

import time

import beratools.core.algo_vertex_optimization as bt_vo
import beratools.tools.common as bt_common


def vertex_optimization(
    in_line,
    in_raster,
    search_distance,
    line_radius,
    out_line,
    processes,
    verbose,
    in_layer=None,
    out_layer=None,
):
    if not bt_common.compare_crs(bt_common.vector_crs(in_line), bt_common.raster_crs(in_raster)):
        return

    vg = bt_vo.VertexGrouping(
        in_line,
        in_raster,
        search_distance,
        line_radius,
        out_line,
        processes,
        verbose,
        in_layer,
        out_layer,
    )
    vg.create_all_vertex_groups()
    vg.compute()
    vg.update_all_lines()
    vg.save_all_layers(out_line)


if __name__ == "__main__":
    in_args, in_verbose = bt_common.check_arguments()
    start_time = time.time()
    vertex_optimization(**in_args.input, processes=int(in_args.processes), verbose=in_verbose)
    print("Elapsed time: {}".format(time.time() - start_time))
