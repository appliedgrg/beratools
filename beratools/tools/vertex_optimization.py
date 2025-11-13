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

import logging

import beratools.core.algo_vertex_optimization as bt_vo
import beratools.utility.spatial_common as sp_common
from beratools.core.logger import Logger
from beratools.utility.tool_args import CallMode

log = Logger("vertex_optimization", file_level=logging.INFO)
logger = log.get_logger()
print = log.print


def vertex_optimization(in_line, in_raster, search_distance, line_radius, out_line, 
                        processes=0, call_mode=CallMode.CLI, log_level="INFO"):
    in_file, in_layer = sp_common.decode_file_layer(in_line)
    if not sp_common.compare_crs(sp_common.vector_crs(in_file), sp_common.raster_crs(in_raster)):
        return

    vg = bt_vo.VertexGrouping(in_file, in_raster, search_distance, line_radius, processes, call_mode, layer=in_layer)
    vg.create_all_vertex_groups()
    vg.compute()
    vg.update_all_lines()
    vg.save_all_layers(out_line)

if __name__ == "__main__":
    import time

    from beratools.utility.tool_args import compose_tool_kwargs
    start_time = time.time()
    kwargs = compose_tool_kwargs("vertex_optimization")
    vertex_optimization(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))
