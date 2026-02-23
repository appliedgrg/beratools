"""Shared contracts and output helpers for canopy footprint tools."""

from dataclasses import dataclass, field

import geopandas as gpd

import beratools.core.algo_common as algo_common
import beratools.utility.spatial_common as sp_common
from beratools.utility.tool_args import CallMode


@dataclass
class CanopyFootprintRequest:
    """Common request contract for canopy footprint runs."""

    in_line: str
    in_chm: str
    out_footprint: str
    max_ln_width: float = 32.0
    processes: int = 0
    call_mode: CallMode | str = CallMode.CLI
    log_level: str = "INFO"
    corridor_thresh: float | None = None
    exp_shk_cell: int | None = None
    tree_radius: float | None = None
    max_line_dist: float | None = None
    canopy_avoidance: float | None = None
    exponent: float | None = None
    canopy_thresh_percentage: float | None = None


@dataclass
class CanopyFootprintResult:
    """Common result contract for canopy footprint runs."""

    footprints_gdf: gpd.GeoDataFrame | None = None
    aux_layers: dict[str, gpd.GeoDataFrame] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)


def cast_request_types(request: CanopyFootprintRequest) -> CanopyFootprintRequest:
    """Cast optional numeric values to expected types."""

    request.max_ln_width = float(request.max_ln_width)
    request.processes = int(request.processes)

    if request.corridor_thresh is not None:
        request.corridor_thresh = float(request.corridor_thresh)
    if request.exp_shk_cell is not None:
        request.exp_shk_cell = int(request.exp_shk_cell)
    if request.tree_radius is not None:
        request.tree_radius = float(request.tree_radius)
    if request.max_line_dist is not None:
        request.max_line_dist = float(request.max_line_dist)
    if request.canopy_avoidance is not None:
        request.canopy_avoidance = float(request.canopy_avoidance)
    if request.exponent is not None:
        request.exponent = float(request.exponent)
    if request.canopy_thresh_percentage is not None:
        request.canopy_thresh_percentage = float(request.canopy_thresh_percentage)

    return request


def save_main_footprint(
    result: CanopyFootprintResult,
    out_footprint: str,
    rejected_layer_name: str,
    default_layer_name: str = "canopy_footprint",
    printer=print,
) -> bool:
    """Save main footprint output and return whether save succeeded."""

    if result.footprints_gdf is None or result.footprints_gdf.empty:
        printer("Warning: No footprints generated. Output file not written.")
        return False

    out_file, out_layer = sp_common.decode_file_layer(out_footprint)
    layer_name = out_layer if out_layer else default_layer_name

    results = gpd.GeoDataFrame(result.footprints_gdf).reset_index(drop=True)
    results = algo_common.clean_geometries(
        results,
        stage="output",
        out_file=out_file,
        layer=rejected_layer_name,
    )

    if results is None or results.empty:
        printer("Warning: No valid footprints generated after cleaning. Output file not written.")
        return False

    results.to_file(out_file, layer=layer_name)
    printer(f"Saved footprint to {out_file}, layer: {layer_name}")
    return True


def save_aux_layers(result: CanopyFootprintResult, out_footprint: str, printer=print) -> list[str]:
    """Save optional auxiliary layers and return saved layer names."""

    saved_layers = []
    if not result.aux_layers:
        return saved_layers

    out_file, _ = sp_common.decode_file_layer(out_footprint)
    out_file_aux = algo_common.get_aux_path(out_file)

    for layer_name, gdf in result.aux_layers.items():
        if gdf is None or not hasattr(gdf, "empty") or gdf.empty:
            continue
        gdf.to_file(out_file_aux, layer=layer_name)
        saved_layers.append(layer_name)
        printer(f"Saved auxiliary layer '{layer_name}' to {out_file_aux}")

    return saved_layers
