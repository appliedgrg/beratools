"""Environment validation helpers for BERA Tools."""

from __future__ import annotations

import os
import sys
import warnings


def get_gdal_proj_env_warning() -> str | None:
    """Return a Windows-only GDAL/PROJ environment warning message, or None."""
    if not sys.platform.startswith("win"):
        return None

    gdal_data_env = os.environ.get("GDAL_DATA")
    proj_lib_env = os.environ.get("PROJ_LIB")
    if not (gdal_data_env or proj_lib_env):
        return None

    prefix_path = os.path.normcase(os.path.abspath(sys.prefix))
    mismatch = False

    if gdal_data_env:
        gdal_path = os.path.normcase(os.path.abspath(gdal_data_env))
        if not gdal_path.startswith(prefix_path):
            mismatch = True

    if proj_lib_env:
        proj_path = os.path.normcase(os.path.abspath(proj_lib_env))
        if not proj_path.startswith(prefix_path):
            mismatch = True

    if not mismatch:
        return None

    return (
        "[GDAL/PROJ Warning] Potential env mismatch\n"
        f"Python env: {sys.prefix}\n"
        f"GDAL_DATA : {gdal_data_env or '<not set>'}\n"
        f"PROJ_LIB  : {proj_lib_env or '<not set>'}\n"
        "If you encounter GDAL/PROJ errors, ensure these env paths belong to this Python environment."
    )


def warn_gdal_proj_env() -> None:
    """Emit a warning for CLI/headless usage if GDAL/PROJ env vars look mismatched."""
    warning_message = get_gdal_proj_env_warning()
    if warning_message:
        warnings.warn(warning_message)