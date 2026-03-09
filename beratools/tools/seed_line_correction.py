"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is the public interface for seed line correction.
"""

import logging
from pathlib import Path

import beratools.core.algo_common as algo_common
import beratools.core.constants as bt_const
import beratools.core.algo_seed_line_correction as algo_slc
import beratools.utility.spatial_common as sp_common
from beratools.core.logger import Logger
from beratools.utility.tool_args import CallMode

log = Logger("seed_line_correction", file_level=logging.INFO)
logger = log.get_logger()
print = log.print


def _save_layers(line_file, slc, optimized_lines):
    out_file, out_layer = sp_common.decode_file_layer(line_file)
    line_file = Path(line_file)

    if optimized_lines is None:
        print(f"No output written to: {line_file} (failed to read input lines)", flush=True)
        return

    optimized_lines.to_file(out_file, layer=out_layer)
    print(f"Saved output to: {line_file}", flush=True)

    if bt_const.BT_DEBUGGING:
        aux_file = algo_common.get_aux_path(out_file)
        debug_layers = slc.get_debug_layers()
        debug_layers["lc_paths"].to_file(aux_file, layer="lc_paths")
        debug_layers["anchors"].to_file(aux_file, layer="anchors")
        debug_layers["vertices"].to_file(aux_file, layer="vertices")


def seed_line_correction(
    in_line,
    in_raster,
    search_distance,
    line_radius,
    out_line,
    optimize_internal_vertices=False,
    processes=0,
    call_mode=CallMode.CLI,
    log_level="INFO",
):
    del log_level

    if isinstance(optimize_internal_vertices, str):
        optimize_internal_vertices = optimize_internal_vertices.lower() in ["true", "1", "yes"]

    in_file, in_layer = sp_common.decode_file_layer(in_line)
    if not sp_common.compare_crs(sp_common.vector_crs(in_file, in_layer), sp_common.raster_crs(in_raster)):
        return

    slc = algo_slc.SeedLineCorrection(
        in_file,
        in_raster,
        search_distance,
        line_radius,
        processes,
        call_mode,
        layer=in_layer,
        optimize_internal_vertices=optimize_internal_vertices,
    )
    slc.prepare_lines()
    slc.group_vertices()
    optimized_lines = slc.optimize()
    _save_layers(out_line, slc, optimized_lines)


if __name__ == "__main__":
    import time

    from beratools.utility.tool_args import compose_tool_kwargs

    start_time = time.time()
    kwargs = compose_tool_kwargs("vertex_optimization")
    seed_line_correction(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))
