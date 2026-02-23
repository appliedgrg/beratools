"""Adaptive relative canopy footprint tool with exception handling."""

from typing import cast

import geopandas as gpd

from beratools.core.algo_canopy_footprint_common import (
    CanopyFootprintRequest,
    CanopyFootprintResult,
    cast_request_types,
    save_aux_layers,
    save_main_footprint,
)
from beratools.core.algo_canopy_footprint_exp import FootprintCanopyAdaptive
from beratools.utility.tool_args import CallMode


def _is_valid_gdf(obj, attr):
    """Check if obj has a non-empty GeoDataFrame attribute."""
    gdf = getattr(obj, attr, None)
    return gdf is not None and hasattr(gdf, "empty") and not gdf.empty


def line_footprint_adaptive(
    in_line,
    in_chm,
    out_footprint,
    max_line_width=32,
    tree_radius=1.5,
    max_line_dist=1.5,
    canopy_avoidance=0.0,
    exponent=1.0,
    canopy_thresh_percentage=50,
    processes=0,
    call_mode=CallMode.CLI,
    log_level="INFO",
):
    """Safe version of adaptive relative canopy footprint tool."""
    request = cast_request_types(
        CanopyFootprintRequest(
            in_line=in_line,
            in_chm=in_chm,
            out_footprint=out_footprint,
            max_ln_width=max_line_width,
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

    result = _run_adaptive_request(request)
    for message in result.messages:
        print(message)

    save_main_footprint(
        result,
        request.out_footprint,
        rejected_layer_name="rejected_output_canopy_footprint_adaptive",
        printer=print,
    )
    save_aux_layers(result, request.out_footprint, printer=print)


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
        result.aux_layers["lines_percentile"] = cast(gpd.GeoDataFrame, footprint.lines_percentile)

    result.stats = {
        "line_count": len(footprint.lines),
        "success_count": 0 if result.footprints_gdf is None else int(len(result.footprints_gdf)),
        "fail_count": 0,
    }
    return result


def parse_cli_args():
    import argparse

    parser = argparse.ArgumentParser(
        description="Adaptive relative canopy footprint tool with exception handling.",
        usage="%(prog)s in_line in_chm out_footprint [options]",
    )
    parser.add_argument("in_line", help="Input line file")
    parser.add_argument("in_chm", help="Input CHM file")
    parser.add_argument("out_footprint", help="Output footprint file")
    parser.add_argument("--max-line-width", type=float, default=32, help="Maximum line width (default: 32)")
    parser.add_argument("--tree-radius", type=float, default=1.5, help="Tree radius (default: 1.5)")
    parser.add_argument(
        "--max-line-dist", type=float, default=1.5, help="Maximum line distance (default: 1.5)"
    )
    parser.add_argument("--canopy-avoidance", type=float, default=0.0, help="Canopy avoidance (default: 0.0)")
    parser.add_argument("--exponent", type=float, default=1.0, help="Exponent (default: 1.0)")
    parser.add_argument(
        "--canopy-thresh-percentage", type=float, default=50, help="Canopy threshold percentage (default: 50)"
    )
    parser.add_argument("--processes", type=int, default=0, help="Number of processes (default: 0)")
    parser.add_argument("--log-level", type=str, default="INFO", help="Log level (default: INFO)")

    args = parser.parse_args()
    return {
        "in_line": args.in_line,
        "in_chm": args.in_chm,
        "out_footprint": args.out_footprint,
        "max_line_width": args.max_line_width,
        "tree_radius": args.tree_radius,
        "max_line_dist": args.max_line_dist,
        "canopy_avoidance": args.canopy_avoidance,
        "exponent": args.exponent,
        "canopy_thresh_percentage": args.canopy_thresh_percentage,
        "processes": args.processes,
        "log_level": args.log_level,
    }


if __name__ == "__main__":
    import time

    start_time = time.time()
    kwargs = parse_cli_args()
    line_footprint_adaptive(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))


# Backward-compatible alias
line_footprint_exp = line_footprint_adaptive
