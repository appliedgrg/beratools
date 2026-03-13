"""Contract tests for canopy footprint adapter runners."""

from types import SimpleNamespace

import geopandas as gpd
import shapely.geometry as sh_geom
import pytest
import pyproj

from beratools.core.algo_canopy_footprint_absolute import CanopyFootprintRequest, cast_request_types
from beratools.tools.canopy_footprint_absolute import (
    _run_absolute_request,
    _run_adaptive_request,
    canopy_footprint_abs,
)
from beratools.utility.tool_args import CallMode


def _single_poly_gdf():
    return gpd.GeoDataFrame(
        {"geometry": [sh_geom.box(0.0, 0.0, 1.0, 1.0)]},
        geometry="geometry",
        crs="EPSG:3857",
    )


def test_run_absolute_request_returns_contract_shape(monkeypatch):
    fake_line_classes = [SimpleNamespace(), SimpleNamespace()]
    fake_items = [SimpleNamespace(footprint=_single_poly_gdf()), SimpleNamespace(footprint=None)]

    monkeypatch.setattr(
        "beratools.tools.canopy_footprint_absolute.generate_absolute_line_class_list",
        lambda *args, **kwargs: fake_line_classes,
    )
    monkeypatch.setattr(
        "beratools.tools.canopy_footprint_absolute.bt_base.execute_multiprocessing",
        lambda *args, **kwargs: fake_items,
    )

    req = cast_request_types(
        CanopyFootprintRequest(
            in_line="dummy.gpkg|line",
            in_chm="dummy.tif",
            out_footprint="out.gpkg|fp",
            max_ln_width=32,
            corridor_thresh=3,
            exp_shk_cell=0,
            processes=0,
        )
    )
    result = _run_absolute_request(req)

    assert result.footprints_gdf is not None
    assert result.stats["line_count"] == 2
    assert result.stats["success_count"] == 1
    assert result.stats["fail_count"] == 1


def test_run_adaptive_request_returns_contract_shape(monkeypatch):
    class FakeAdaptive:
        def __init__(self, *args, **kwargs):
            self.lines = [
                SimpleNamespace(footprint=_single_poly_gdf()),
                SimpleNamespace(footprint=None),
                SimpleNamespace(footprint=None),
            ]
            self.footprints = _single_poly_gdf()
            self.lines_percentile = gpd.GeoDataFrame(
                {
                    "geometry": [sh_geom.LineString([(0.0, 0.0), (1.0, 0.0)])],
                    "percentile": [50.0],
                    "side": ["left"],
                },
                geometry="geometry",
                crs="EPSG:3857",
            )

        def compute(self, processes, call_mode=CallMode.CLI):
            return None

    monkeypatch.setattr("beratools.tools.canopy_footprint_absolute.FootprintCanopyAdaptive", FakeAdaptive)

    req = cast_request_types(
        CanopyFootprintRequest(
            in_line="dummy.gpkg|line",
            in_chm="dummy.tif",
            out_footprint="out.gpkg|fp",
            max_ln_width=32,
            tree_radius=1.5,
            max_line_dist=1.5,
            canopy_avoidance=0.0,
            exponent=1.0,
            canopy_thresh_percentage=50,
            processes=0,
        )
    )
    result = _run_adaptive_request(req)

    assert result.footprints_gdf is not None
    assert "lines_percentile" in result.aux_layers
    assert result.stats["line_count"] == 3
    assert result.stats["success_count"] == 1
    assert result.stats["fail_count"] == 2


def test_canopy_footprint_abs_rejects_invalid_mode():
    with pytest.raises(ValueError, match="footprint_mode"):
        canopy_footprint_abs(
            in_line="dummy.gpkg|line",
            in_chm="dummy.tif",
            out_footprint="out.gpkg|fp",
            footprint_mode="adpative",
        )


def test_canopy_footprint_abs_converts_max_ln_width_meters_to_native_units(monkeypatch):
    captured = {}

    class _FakeOSR:
        def __init__(self, crs_text):
            self._crs_text = crs_text

        def ExportToWkt(self):
            return self._crs_text

    monkeypatch.setattr(
        "beratools.tools.canopy_footprint_absolute.sp_common.vector_crs",
        lambda *_args, **_kwargs: _FakeOSR(pyproj.CRS.from_epsg(2263).to_wkt()),
    )

    def _fake_run_absolute(req):
        captured["max_ln_width"] = req.max_ln_width
        return SimpleNamespace(messages=[], footprints_gdf=gpd.GeoDataFrame(), aux_layers={}, stats={})

    monkeypatch.setattr(
        "beratools.tools.canopy_footprint_absolute._run_absolute_request",
        _fake_run_absolute,
    )
    monkeypatch.setattr(
        "beratools.tools.canopy_footprint_absolute.save_main_footprint",
        lambda *_args, **_kwargs: True,
    )

    canopy_footprint_abs(
        in_line="dummy.gpkg|line",
        in_chm="dummy.tif",
        out_footprint="out.gpkg|fp",
        footprint_mode="absolute",
        max_ln_width=10.0,
    )

    assert captured["max_ln_width"] == pytest.approx(32.8083333333, rel=1e-6)


def test_canopy_footprint_abs_rejects_geographic_crs_for_max_width(monkeypatch):
    class _FakeOSR:
        def __init__(self, crs_text):
            self._crs_text = crs_text

        def ExportToWkt(self):
            return self._crs_text

    monkeypatch.setattr(
        "beratools.tools.canopy_footprint_absolute.sp_common.vector_crs",
        lambda *_args, **_kwargs: _FakeOSR(pyproj.CRS.from_epsg(4326).to_wkt()),
    )

    with pytest.raises(ValueError, match="requires a projected CRS"):
        canopy_footprint_abs(
            in_line="dummy.gpkg|line",
            in_chm="dummy.tif",
            out_footprint="out.gpkg|fp",
            footprint_mode="absolute",
            max_ln_width=10.0,
        )


def test_run_adaptive_request_preserves_float_threshold_inputs(monkeypatch):
    captured = {}

    class FakeAdaptive:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            self.lines = []
            self.footprints = gpd.GeoDataFrame()
            self.lines_percentile = gpd.GeoDataFrame()

        def compute(self, processes, call_mode=CallMode.CLI):
            return None

    monkeypatch.setattr("beratools.tools.canopy_footprint_absolute.FootprintCanopyAdaptive", FakeAdaptive)

    req = cast_request_types(
        CanopyFootprintRequest(
            in_line="dummy.gpkg|line",
            in_chm="dummy.tif",
            out_footprint="out.gpkg|fp",
            max_ln_width=32.7,
            canopy_thresh_percentage=55.5,
            processes=0,
        )
    )

    _run_adaptive_request(req)

    assert captured["max_line_width"] == 32.7
    assert captured["canopy_thresh_percentage"] == 55.5


def test_run_adaptive_request_passes_call_mode(monkeypatch):
    captured = {}

    class FakeAdaptive:
        def __init__(self, *args, **kwargs):
            self.lines = []
            self.footprints = gpd.GeoDataFrame()
            self.lines_percentile = gpd.GeoDataFrame()

        def compute(self, processes, call_mode=CallMode.CLI):
            captured["processes"] = processes
            captured["call_mode"] = call_mode

    monkeypatch.setattr("beratools.tools.canopy_footprint_absolute.FootprintCanopyAdaptive", FakeAdaptive)

    req = cast_request_types(
        CanopyFootprintRequest(
            in_line="dummy.gpkg|line",
            in_chm="dummy.tif",
            out_footprint="out.gpkg|fp",
            processes=2,
            call_mode=CallMode.GUI.value,
        )
    )

    _run_adaptive_request(req)

    assert captured["processes"] == 2
    assert captured["call_mode"] == CallMode.GUI
