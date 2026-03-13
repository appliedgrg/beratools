"""Tooling helpers for invoking geo-simplify binaries."""

from __future__ import annotations

import os
import platform
import stat
import subprocess
import tempfile
from pathlib import Path


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
