"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide main interface for canopy footprint tool.
"""

import logging
import time

import geopandas as gpd
import pandas as pd

from beratools.core.algo_canopy_footprint_absolute import (
    FootprintCanopyAdaptive,
    generate_absolute_line_class_list,
    process_single_absolute_line,
)
from beratools.core.algo_canopy_footprint_common import (
    CanopyFootprintRequest,
    CanopyFootprintResult,
    cast_request_types,
    save_aux_layers,
    save_main_footprint,
)
import beratools.core.tool_base as bt_base
import beratools.utility.spatial_common as sp_common
from beratools.core.logger import Logger
from beratools.utility.tool_args import CallMode

log = Logger("canopy_footprint_abs", file_level=logging.INFO)
logger = log.get_logger()
print = log.print


def _is_valid_gdf(obj, attr):
    """Check if obj has a non-empty GeoDataFrame attribute."""

    gdf = getattr(obj, attr, None)
    return gdf is not None and hasattr(gdf, "empty") and not gdf.empty


def canopy_footprint_abs(
    in_line,
    in_chm,
    corridor_thresh=3.0,
    max_ln_width=32.0,
    exp_shk_cell=0,
    out_footprint=None,
    footprint_mode="absolute",
    tree_radius=1.5,
    max_line_dist=1.5,
    canopy_avoidance=0.0,
    exponent=1.0,
    canopy_thresh_percentage=50,
    processes=0,
    call_mode=CallMode.CLI,
    log_level="INFO",
):
    """Run canopy footprint in absolute or adaptive mode."""

    if not out_footprint:
        raise ValueError("out_footprint is required")

    request = cast_request_types(
        CanopyFootprintRequest(
            in_line=in_line,
            in_chm=in_chm,
            out_footprint=out_footprint,
            max_ln_width=max_ln_width,
            corridor_thresh=corridor_thresh,
            exp_shk_cell=exp_shk_cell,
            tree_radius=tree_radius,
            max_line_dist=max_line_dist,
            canopy_avoidance=canopy_avoidance,
            exponent=exponent,
            canopy_thresh_percentage=canopy_thresh_percentage,
            processes=processes,
            call_mode=call_mode,
            log_level=log_level,
        )
    )

    mode = str(footprint_mode).strip().lower()
    if mode == "adaptive":
        result = _run_adaptive_request(request)
        rejected_layer_name = "rejected_output_canopy_footprint_adaptive"
    else:
        result = _run_absolute_request(request)
        rejected_layer_name = "rejected_output_canopy_footprint_absolute"

    for message in result.messages:
        print(message)

    save_main_footprint(
        result,
        request.out_footprint,
        rejected_layer_name=rejected_layer_name,
        printer=print,
    )
    if mode == "adaptive":
        save_aux_layers(result, request.out_footprint, printer=print)


def _run_absolute_request(req: CanopyFootprintRequest) -> CanopyFootprintResult:
    """Run absolute footprint workflow using shared request/result contracts."""

    in_file, in_layer = sp_common.decode_file_layer(req.in_line)

    corridor_thresh = req.corridor_thresh if req.corridor_thresh is not None else 3.0
    exp_shk_cell = req.exp_shk_cell if req.exp_shk_cell is not None else 0

    footprint_list = []
    line_class_list = generate_absolute_line_class_list(
        in_file,
        req.in_chm,
        corridor_thresh,
        req.max_ln_width,
        exp_shk_cell,
        in_layer,
    )

    run_call_mode = req.call_mode
    if isinstance(run_call_mode, str):
        run_call_mode = CallMode(run_call_mode)

    feat_list = bt_base.execute_multiprocessing(
        process_single_absolute_line,
        line_class_list,
        "Line footprint",
        req.processes,
        run_call_mode,
    )

    if feat_list:
        for item in feat_list:
            if item.footprint is not None:
                footprint_list.append(item.footprint)

    result = CanopyFootprintResult(
        stats={
            "line_count": len(line_class_list),
            "success_count": len(footprint_list),
            "fail_count": max(len(line_class_list) - len(footprint_list), 0),
        }
    )

    if footprint_list:
        result.footprints_gdf = gpd.GeoDataFrame(pd.concat(footprint_list)).reset_index(drop=True)
    else:
        result.messages.append("No footprints generated.")

    return result


def _run_adaptive_request(req: CanopyFootprintRequest) -> CanopyFootprintResult:
    """Run adaptive footprint workflow using shared request/result contracts."""

    result = CanopyFootprintResult()
    try:
        footprint = FootprintCanopyAdaptive(
            req.in_line,
            req.in_chm,
            max_line_width=int(float(req.max_ln_width)),
            tree_radius=req.tree_radius if req.tree_radius is not None else 1.5,
            max_line_dist=req.max_line_dist if req.max_line_dist is not None else 1.5,
            canopy_avoidance=req.canopy_avoidance if req.canopy_avoidance is not None else 0.0,
            exponent=req.exponent if req.exponent is not None else 1.0,
            canopy_thresh_percentage=(
                int(float(req.canopy_thresh_percentage)) if req.canopy_thresh_percentage is not None else 50
            ),
        )
    except Exception as err:
        result.messages.append(f"Failed to initialize FootprintCanopyAdaptive: {err}")
        return result

    try:
        footprint.compute(req.processes)
    except Exception as err:
        result.messages.append(f"Error in compute(): {err}")
        import traceback

        traceback.print_exc()
        return result

    if _is_valid_gdf(footprint, "footprints"):
        result.footprints_gdf = footprint.footprints
    else:
        result.messages.append("No valid footprints to save.")

    if _is_valid_gdf(footprint, "lines_percentile"):
        result.aux_layers["lines_percentile"] = gpd.GeoDataFrame(footprint.lines_percentile)

    result.stats = {
        "line_count": len(footprint.lines),
        "success_count": 0 if result.footprints_gdf is None else int(len(result.footprints_gdf)),
        "fail_count": 0,
    }

    return result


if __name__ == "__main__":
    from beratools.utility.tool_args import compose_tool_kwargs

    start_time = time.time()
    print("Footprint processing started")
    kwargs = compose_tool_kwargs("canopy_footprint_absolute")
    canopy_footprint_abs(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))
