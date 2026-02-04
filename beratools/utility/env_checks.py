"""Environment validation helpers for BERA Tools."""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path


def get_gdal_proj_env_warning() -> str | None:
    """Return a Windows-only GDAL/PROJ environment warning message, or None."""
    if not sys.platform.startswith("win"):
        return None

    gdal_data_env = os.environ.get("GDAL_DATA")
    proj_lib_env = os.environ.get("PROJ_LIB")
    if not (gdal_data_env or proj_lib_env):
        return None

    prefix_path = Path(sys.prefix).resolve()
    mismatches: list[tuple[str, str]] = []

    if gdal_data_env:
        gdal_path = Path(gdal_data_env).resolve()
        if not gdal_path.is_relative_to(prefix_path):
            mismatches.append(("GDAL_DATA", gdal_data_env))

    if proj_lib_env:
        proj_path = Path(proj_lib_env).resolve()
        if not proj_path.is_relative_to(prefix_path):
            mismatches.append(("PROJ_LIB", proj_lib_env))

    if not mismatches:
        return None

    mismatch_details = "\n".join(
        f"{env_name:<9}: {env_value}" for env_name, env_value in mismatches
    )

    return (
        "[GDAL/PROJ Warning] Potential env mismatch\n"
        f"Python env: {sys.prefix}\n"
        f"{mismatch_details}\n"
        "If you encounter GDAL/PROJ errors, ensure these env paths belong to this Python environment."
    )


def warn_gdal_proj_env() -> None:
    """Emit a warning for CLI/headless usage if GDAL/PROJ env vars look mismatched."""
    warning_message = get_gdal_proj_env_warning()
    if warning_message:
        warnings.warn(warning_message)