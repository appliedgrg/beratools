"""Tests for shared canopy footprint request/result helpers."""

import geopandas as gpd

from beratools.core.algo_canopy_footprint_common import (
    CanopyFootprintRequest,
    CanopyFootprintResult,
    cast_request_types,
    save_aux_layers,
    save_main_footprint,
)


def test_cast_request_types_converts_numeric_values():
    req = CanopyFootprintRequest(
        in_line="in.gpkg|line",
        in_chm="in.tif",
        out_footprint="out.gpkg|fp",
        max_ln_width="32",
        processes="2",
        corridor_thresh="3.5",
        exp_shk_cell="1",
        tree_radius="1.5",
        max_line_dist="2.0",
        canopy_avoidance="0.1",
        exponent="2",
        canopy_thresh_percentage="50",
    )

    cast_request_types(req)

    assert isinstance(req.max_ln_width, float)
    assert isinstance(req.processes, int)
    assert isinstance(req.corridor_thresh, float)
    assert isinstance(req.exp_shk_cell, int)
    assert isinstance(req.tree_radius, float)
    assert isinstance(req.max_line_dist, float)
    assert isinstance(req.canopy_avoidance, float)
    assert isinstance(req.exponent, float)
    assert isinstance(req.canopy_thresh_percentage, float)


def test_save_main_footprint_returns_false_when_empty(capsys):
    result = CanopyFootprintResult(footprints_gdf=gpd.GeoDataFrame())
    saved = save_main_footprint(
        result,
        out_footprint="out.gpkg|fp",
        rejected_layer_name="rejected",
    )

    output = capsys.readouterr().out
    assert saved is False
    assert "No footprints generated" in output


def test_save_aux_layers_skips_empty_layers():
    result = CanopyFootprintResult(aux_layers={"lines_percentile": gpd.GeoDataFrame()})
    saved_layers = save_aux_layers(result, out_footprint="out.gpkg|fp")
    assert saved_layers == []
