"""Canopy footprint tool with exception handling."""

from pathlib import Path
from tabnanny import verbose

import beratools.utility.spatial_common as sp_common
from beratools.core.algo_canopy_footprint_exp import FootprintCanopy
from beratools.utility.tool_args import CallMode


def line_footprint_exp(
    in_line,
    in_chm,
    out_footprint,
    max_ln_width=32,
    tree_radius=1.5,
    max_line_dist=1.5,
    canopy_avoidance=0.0,
    exponent=1.0,
    canopy_thresh_percentage=50,
    processes=0,
    call_mode=CallMode.CLI,
    log_level="INFO",
):
    """Safe version of relative canopy footprint tool."""
    try:
        footprint = FootprintCanopy(in_line, in_chm)
    except Exception as e:
        print(f"Failed to initialize FootprintCanopy: {e}")
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
    if (
        hasattr(footprint, "footprints")
        and footprint.footprints is not None
        and hasattr(footprint.footprints, "empty")
        and not footprint.footprints.empty
    ):
        try:
            footprint.save_footprint(out_file, out_layer)
            print(f"Footprint saved to {out_footprint}")
        except Exception as e:
            print(f"Failed to save footprint: {e}")
    else:
        print("No valid footprints to save.")

    # Optionally save percentile lines (if needed)
    if (
        hasattr(footprint, "lines_percentile")
        and footprint.lines_percentile is not None
        and hasattr(footprint.lines_percentile, "empty")
        and not footprint.lines_percentile.empty
    ):
        out_file_path = Path(out_file)
        out_file_aux = out_file_path.with_stem(out_file_path.stem + "_aux")
        try:
            footprint.save_line_percentile(out_file_aux.as_posix())
            if verbose:
                print(f"Line percentile saved to {out_file_aux}")
        except Exception as e:
            print(f"Failed to save line percentile: {e}")

def parse_cli_args():
    import argparse

    parser = argparse.ArgumentParser(
        description="Canopy footprint tool with exception handling.",
        usage="%(prog)s in_line in_chm out_footprint [options]"
    )
    parser.add_argument("in_line", help="Input line file")
    parser.add_argument("in_chm", help="Input CHM file")
    parser.add_argument("out_footprint", help="Output footprint file")
    parser.add_argument("--max-ln-width", type=float, default=32, help="Maximum line width (default: 32)")
    parser.add_argument("--tree-radius", type=float, default=1.5, help="Tree radius (default: 1.5)")
    parser.add_argument("--max-line-dist", type=float, default=1.5, help="Maximum line distance (default: 1.5)")
    parser.add_argument("--canopy-avoidance", type=float, default=0.0, help="Canopy avoidance (default: 0.0)")
    parser.add_argument("--exponent", type=float, default=1.0, help="Exponent (default: 1.0)")
    parser.add_argument("--canopy-thresh-percentage", type=float, default=50, help="Canopy threshold percentage (default: 50)")
    parser.add_argument("--processes", type=int, default=0, help="Number of processes (default: 0)")
    parser.add_argument("--log-level", type=str, default="INFO", help="Log level (default: INFO)")

    args = parser.parse_args()
    return {
        "in_line": args.in_line,
        "in_chm": args.in_chm,
        "out_footprint": args.out_footprint,
        "max_ln_width": args.max_ln_width,
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
    line_footprint_exp(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))
