"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide main interface for centerline tool.
"""

import logging
import os
import platform
import stat
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

import beratools.core.algo_centerline as algo_centerline
import beratools.core.algo_common as algo_common
import beratools.core.constants as bt_const
import beratools.utility.spatial_common as sp_common
from beratools.core.logger import Logger
from beratools.core.tool_base import execute_multiprocessing
from beratools.utility.tool_args import CallMode

log = Logger("centerline", file_level=logging.INFO)
logger = log.get_logger()
print = log.print


def _to_bool(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False

    return bool(value)


def _validate_simplify_diameter(value):
    try:
        diameter = float(value)
    except (TypeError, ValueError):
        raise ValueError("simplify_diameter must be a number >= 0.")

    if diameter < 0:
        raise ValueError("simplify_diameter must be >= 0.")

    return diameter


def _resolve_geo_simplify_binary():
    external_dir = Path(__file__).resolve().parents[1] / "external" / "geo_simplify"
    system_name = platform.system()

    if system_name == "Windows":
        binary_path = external_dir / "geo-simplify-win-x64.exe"
    elif system_name == "Linux":
        binary_path = external_dir / "geo-simplify-linux-x64"
    else:
        raise RuntimeError(f"Centerline simplify is not supported on OS: {system_name}")

    if not binary_path.exists():
        raise FileNotFoundError(f"Missing geo-simplify binary: {binary_path}")

    if system_name == "Linux":
        mode = binary_path.stat().st_mode
        if not (mode & stat.S_IXUSR):
            binary_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return binary_path


def _build_temp_centerline_output(out_file):
    out_path = Path(out_file)
    out_dir = out_path.parent if out_path.parent else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f"{out_path.stem}_centerline_tmp_",
        suffix=".gpkg",
        dir=out_dir,
    )
    os.close(fd)
    return Path(temp_path)


def _run_geo_simplify_reduce_bend(temp_input, temp_layer, out_file, out_layer, diameter):
    binary_path = _resolve_geo_simplify_binary()
    command = [
        str(binary_path),
        "reduce-bend",
        "--input",
        str(temp_input),
        "--in-layer",
        temp_layer,
        "--output",
        out_file,
        "--diameter",
        str(diameter),
        "--smooth-line",
    ]

    if out_layer:
        command.extend(["--out-layer", out_layer])

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "geo-simplify reduce-bend failed "
            f"(exit code {result.returncode})\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def generate_line_class_list(
    in_vector,
    in_raster,
    line_radius,
    layer=None,
    proc_segments=True,
    guided_strategy=bt_const.CENTERLINE_GUIDED_STRATEGY.value,
) -> list:
    line_classes = []
    line_list = algo_common.prepare_lines_gdf(in_vector, layer, proc_segments)

    for item in line_list:
        line_classes.append(
            algo_centerline.SeedLine(
                item,
                in_raster,
                proc_segments,
                line_radius,
                guided_strategy=guided_strategy,
            )
        )

    return line_classes


def process_single_line_class(seed_line):
    seed_line.compute()
    return seed_line


def centerline(
    in_line,
    in_raster,
    line_radius,
    proc_segments,
    out_line,
    guided_strategy=bt_const.CENTERLINE_GUIDED_STRATEGY.value,
    simplify_centerline=False,
    simplify_diameter=10.0,
    use_angle_grouping=True,
    processes=0,
    call_mode=CallMode.CLI,
    log_level="INFO",
):
    """Run centerline extraction.

    guided_strategy modes:
    - MAIN_ROUTE: unguided main-route extraction.
    - PAIRWISE: endpoint-guided search over endpoint node pairs.
    - VIRTUAL_NODES: endpoint-guided search using virtual source/destination graph nodes.
    - DIRECT_INSERT: endpoint-guided search by inserting endpoints directly into the Voronoi graph.
    """
    if isinstance(guided_strategy, str):
        guided_strategy = bt_const.CenterlineStrategy(guided_strategy)

    guided_strategy_value = guided_strategy.value

    in_file, in_layer = sp_common.decode_file_layer(in_line)
    out_file, out_layer = sp_common.decode_file_layer(out_line)
    simplify_enabled = _to_bool(simplify_centerline)
    diameter = _validate_simplify_diameter(simplify_diameter)

    if not sp_common.compare_crs(sp_common.vector_crs(in_file, in_layer), sp_common.raster_crs(in_raster)):
        print("Line and CHM have different spatial references, please check.")
        return

    line_class_list = generate_line_class_list(
        in_file,
        in_raster,
        line_radius=float(line_radius),
        layer=in_layer,
        proc_segments=proc_segments,
        guided_strategy=guided_strategy_value,
    )

    print("{} lines to be processed.".format(len(line_class_list)))

    lc_path_list = []
    centerline_list = []
    corridor_poly_list = []
    result = execute_multiprocessing(
        process_single_line_class,
        line_class_list,
        "Centerline",
        processes,
        call_mode,
    )
    if not result:
        print("No centerlines found.")
        return 1

    for item in result:
        lc_path_list.append(item.lc_path)
        centerline_list.append(item.centerline)
        corridor_poly_list.append(item.corridor_poly_gpd)

    # Concatenate the lists of GeoDataFrames into single GeoDataFrames
    if len(lc_path_list) == 0 or len(centerline_list) == 0 or len(corridor_poly_list) == 0:
        print("No centerline generated.")
        return 1

    lc_path_list = pd.concat(lc_path_list, ignore_index=True)
    centerline_list = pd.concat(centerline_list, ignore_index=True)
    corridor_polys = pd.concat(corridor_poly_list, ignore_index=True)

    # Save the concatenated GeoDataFrames to the shapefile/gpkg
    centerline_list = algo_common.clean_geometries(
        centerline_list,
        stage="output",
        out_file=out_file,
        layer="rejected_output_centerlines",
    )
    if simplify_enabled and diameter > 0:
        temp_file = _build_temp_centerline_output(out_file)
        temp_layer = "centerline_temp"
        try:
            centerline_list.to_file(temp_file.as_posix(), layer=temp_layer)
            _run_geo_simplify_reduce_bend(
                temp_input=temp_file,
                temp_layer=temp_layer,
                out_file=out_file,
                out_layer=out_layer,
                diameter=diameter,
            )
        finally:
            if temp_file.exists():
                temp_file.unlink()
    else:
        if simplify_enabled and diameter == 0:
            print("Centerline simplify enabled with diameter 0; skipping simplify step.")
        centerline_list.to_file(out_file, layer=out_layer)

    print(f"Saved centerlines to: {out_file}")

    aux_file = algo_common.get_aux_path(out_file)
    print(f"Saved auxiliary data to: {aux_file}")

    # Save lc_path_list and corridor_polys to the new GeoPackage with '_aux' suffix
    lc_path_list.to_file(aux_file, layer="least_cost_path")
    corridor_polys.to_file(aux_file, layer="corridor_polygon")

    return 0


if __name__ == "__main__":
    import time

    from beratools.utility.tool_args import compose_tool_kwargs

    start_time = time.time()
    kwargs = compose_tool_kwargs("centerline")
    centerline(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))
