import geopandas as gpd
import pyproj
import pytest
from shapely.geometry import LineString, Polygon

import beratools.tools.canopy_footprint_absolute as cfa


class _FakeOSR:
    def ExportToWkt(self):
        return pyproj.CRS.from_epsg(2263).to_wkt()


def _line_gdf():
    return gpd.GeoDataFrame(geometry=[LineString([(0.0, 0.0), (5.0, 0.0)])], crs="EPSG:2263")


def _patch_common_guards(monkeypatch, overlap_result):
    monkeypatch.setattr(cfa.sp_common, "vector_crs", lambda *_args, **_kwargs: _FakeOSR())
    monkeypatch.setattr(cfa.sp_common, "raster_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cfa.sp_common, "compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(cfa.gpd, "read_file", lambda *_args, **_kwargs: _line_gdf())
    monkeypatch.setattr(cfa.sp_common, "check_vector_raster_extent_overlap", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        cfa.sp_common, "check_vector_raster_overlap", lambda *_args, **_kwargs: overlap_result
    )


def test_canopy_footprint_absolute_stops_when_no_line_raster_overlap(monkeypatch):
    _patch_common_guards(monkeypatch, overlap_result=False)

    called = {"run": 0}

    def _fake_run(*_args, **_kwargs):
        called["run"] += 1
        raise RuntimeError("should-not-run")

    monkeypatch.setattr(cfa, "_run_absolute_request", _fake_run)

    result = cfa.canopy_footprint_abs(
        in_line="line.gpkg|line",
        in_chm="chm.tif",
        out_footprint="out.gpkg|footprint",
        footprint_mode="absolute",
    )

    assert result is None
    assert called["run"] == 0


def test_canopy_footprint_absolute_continues_when_partial_overlap(monkeypatch):
    _patch_common_guards(monkeypatch, overlap_result=True)

    called = {"run": 0}

    def _fake_run(*_args, **_kwargs):
        called["run"] += 1
        return cfa.CanopyFootprintResult(messages=[])

    monkeypatch.setattr(cfa, "_run_absolute_request", _fake_run)
    monkeypatch.setattr(cfa, "save_main_footprint", lambda *_args, **_kwargs: True)

    cfa.canopy_footprint_abs(
        in_line="line.gpkg|line",
        in_chm="chm.tif",
        out_footprint="out.gpkg|footprint",
        footprint_mode="absolute",
    )

    assert called["run"] == 1


def test_canopy_footprint_forwards_polygon_processing_options(monkeypatch):
    _patch_common_guards(monkeypatch, overlap_result=True)

    captured = {}

    def _fake_run(req):
        captured["request"] = req
        return cfa.CanopyFootprintResult(messages=[])

    monkeypatch.setattr(cfa, "_run_absolute_request", _fake_run)
    monkeypatch.setattr(cfa, "save_main_footprint", lambda *_args, **_kwargs: True)

    cfa.canopy_footprint_abs(
        in_line="line.gpkg|line",
        in_chm="chm.tif",
        out_footprint="out.gpkg|footprint",
        footprint_mode="absolute",
        simplify_footprint_polygon=False,
        footprint_simplify_length=1.25,
        smooth_footprint_polygon=True,
        footprint_polygon_smooth_iterations=2,
    )

    req = captured["request"]
    assert req.simplify_footprint_polygon is False
    assert req.footprint_simplify_length == pytest.approx(4.10104167)
    assert req.smooth_footprint_polygon is True
    assert req.footprint_polygon_smooth_iterations == 2


def test_canopy_footprint_adaptive_converts_polygon_simplification_length(monkeypatch):
    _patch_common_guards(monkeypatch, overlap_result=True)

    captured = {}

    def _fake_run(req):
        captured["request"] = req
        return cfa.CanopyFootprintResult(messages=[])

    monkeypatch.setattr(cfa, "_run_adaptive_request", _fake_run)
    monkeypatch.setattr(cfa, "save_main_footprint", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(cfa, "save_aux_layers", lambda *_args, **_kwargs: True)

    cfa.canopy_footprint_abs(
        in_line="line.gpkg|line",
        in_chm="chm.tif",
        out_footprint="out.gpkg|footprint",
        footprint_mode="adaptive",
        footprint_simplify_length=1.25,
    )

    assert captured["request"].footprint_simplify_length == pytest.approx(4.10104167)


def test_process_footprint_polygon_gdf_simplifies_and_smooths():
    from beratools.core.algo_canopy_footprint_absolute import process_footprint_polygon_gdf

    polygon = Polygon([(0, 0), (4, 0), (4, 2), (0, 2), (0, 0)])
    gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:3857")

    processed = process_footprint_polygon_gdf(
        gdf,
        simplify_footprint_polygon=True,
        footprint_simplify_length=0.1,
        smooth_footprint_polygon=True,
        footprint_polygon_smooth_iterations=1,
    )

    assert processed.crs == gdf.crs
    assert processed.geometry.iloc[0].is_valid
    assert len(processed.geometry.iloc[0].exterior.coords) > len(polygon.exterior.coords)


def test_canopy_footprint_adaptive_stops_when_no_line_raster_overlap(monkeypatch):
    _patch_common_guards(monkeypatch, overlap_result=False)

    called = {"run": 0}

    def _fake_run(*_args, **_kwargs):
        called["run"] += 1
        raise RuntimeError("should-not-run")

    monkeypatch.setattr(cfa, "_run_adaptive_request", _fake_run)

    result = cfa.canopy_footprint_abs(
        in_line="line.gpkg|line",
        in_chm="chm.tif",
        out_footprint="out.gpkg|footprint",
        footprint_mode="adaptive",
    )

    assert result is None
    assert called["run"] == 0


def test_canopy_footprint_stops_on_extent_precheck_without_loading_features(monkeypatch):
    monkeypatch.setattr(cfa.sp_common, "vector_crs", lambda *_args, **_kwargs: _FakeOSR())
    monkeypatch.setattr(cfa.sp_common, "raster_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cfa.sp_common, "compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        cfa.unit_conversion, "convert_meters_param_projected_from_osr", lambda *_args, **_kwargs: 32.0
    )
    monkeypatch.setattr(cfa.sp_common, "check_vector_raster_extent_overlap", lambda *_args, **_kwargs: False)

    called = {"read": 0, "run": 0}

    def _fake_read(*_args, **_kwargs):
        called["read"] += 1
        raise RuntimeError("should-not-read")

    def _fake_run(*_args, **_kwargs):
        called["run"] += 1
        raise RuntimeError("should-not-run")

    monkeypatch.setattr(cfa.gpd, "read_file", _fake_read)
    monkeypatch.setattr(cfa, "_run_absolute_request", _fake_run)

    result = cfa.canopy_footprint_abs(
        in_line="line.gpkg|line",
        in_chm="chm.tif",
        out_footprint="out.gpkg|footprint",
        footprint_mode="absolute",
    )

    assert result is None
    assert called["read"] == 0
    assert called["run"] == 0
