"""Adaptive relative canopy footprint tool with exception handling."""

import beratools.core.algo_common as algo_common
import beratools.utility.spatial_common as sp_common
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
    try:
        footprint = FootprintCanopyAdaptive(
            in_line,
            in_chm,
            max_line_width=max_line_width,
            tree_radius=tree_radius,
            max_line_dist=max_line_dist,
            canopy_avoidance=canopy_avoidance,
            exponent=exponent,
            canopy_thresh_percentage=canopy_thresh_percentage,
        )
    except Exception as e:
        print(f"Failed to initialize FootprintCanopyAdaptive: {e}")
        return

    try:
        footprint.compute(processes)
    except Exception as e:
        print(f"Error in compute(): {e}")
        import traceback

        traceback.print_exc()
        return

    # Save only if footprints were actually generated
    out_file, out_layer = sp_common.decode_file_layer(out_footprint)
    if _is_valid_gdf(footprint, "footprints"):
        try:
            footprint.save_footprint(out_file, out_layer)
            print(f"Footprint saved to {out_footprint}")
        except Exception as e:
            print(f"Failed to save footprint: {e}")
    else:
        print("No valid footprints to save.")

    # Optionally save percentile lines (if needed)
    if _is_valid_gdf(footprint, "lines_percentile"):
        out_file_aux = algo_common.get_aux_path(out_file)
        try:
            footprint.save_line_percentile(out_file_aux)
        except Exception as e:
            print(f"Failed to save line percentile: {e}")


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
