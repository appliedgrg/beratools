"""Tooling helpers for invoking geo-simplify binaries."""

from __future__ import annotations

import os
import platform
import stat
import subprocess
import tempfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString


def validate_diameter(value):
    try:
        diameter = float(value)
    except (TypeError, ValueError):
        raise ValueError("simplify_diameter must be a number >= 0.")

    if diameter < 0:
        raise ValueError("simplify_diameter must be >= 0.")

    return diameter


def build_temp_output_same_folder(out_file, suffix=".gpkg", prefix="centerline_tmp_"):
    out_path = Path(out_file)
    out_dir = out_path.parent if out_path.parent else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=out_dir)
    os.close(fd)
    return Path(temp_path)


def simplify_line_reduce_bend(line: LineString, *, crs, diameter: float, smooth_line=True) -> LineString:
    if diameter <= 0:
        return line

    with tempfile.TemporaryDirectory(prefix="beratools_line_simplify_") as temp_dir:
        temp_path = Path(temp_dir)
        input_file = temp_path / "input.gpkg"
        output_file = temp_path / "output.gpkg"
        in_layer = "line_temp"
        out_layer = "line_simplified"
        gdf = gpd.GeoDataFrame([{}], geometry=[line], crs=crs)
        gdf.to_file(input_file, layer=in_layer)
        run_reduce_bend(
            input_file=input_file,
            in_layer=in_layer,
            output_file=output_file.as_posix(),
            out_layer=out_layer,
            diameter=diameter,
            smooth_line=smooth_line,
        )
        simplified = gpd.read_file(output_file, layer=out_layer)
        if simplified.empty:
            raise RuntimeError("geo-simplify returned no features")
        geom = simplified.geometry.iloc[0]
        if geom is None or geom.is_empty:
            raise RuntimeError("geo-simplify returned empty geometry")
        if geom.geom_type == "MultiLineString" and len(geom.geoms) == 1:
            geom = geom.geoms[0]
        if not isinstance(geom, LineString):
            raise RuntimeError(f"geo-simplify returned unsupported geometry: {geom.geom_type}")
        return geom


def run_reduce_bend(input_file, in_layer, output_file, out_layer, diameter, smooth_line=True):
    binary_path = _geo_simplify_resolve_binary_path()
    command = [
        str(binary_path),
        "reduce-bend",
        "--input",
        str(input_file),
        "--in-layer",
        in_layer,
        "--output",
        output_file,
        "--diameter",
        str(diameter),
    ]

    if smooth_line:
        command.append("--smooth-line")

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


def _geo_simplify_resolve_binary_path():
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
        _geo_simplify_ensure_executable(binary_path)

    return binary_path


def _geo_simplify_ensure_executable(binary_path):
    mode = binary_path.stat().st_mode
    if not (mode & stat.S_IXUSR):
        binary_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
