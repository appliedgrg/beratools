import geopandas as gpd
import pyogrio.errors
import pytest
from shapely.geometry import LineString, Polygon

import beratools.tools.ground_footprint as gf


class _DummyLineGrouping:
    def __init__(self, line_gdf, _merge_group):
        self._line_gdf = line_gdf

    def run_grouping(self):
        return None

    def run_line_merge(self):
        return self._line_gdf


def _run_ground_footprint_until_prepare_line_args(monkeypatch, line_crs):
    captured = {}

    line_gdf = gpd.GeoDataFrame(
        {"BT_GROUP": [1]},
        geometry=[LineString([(0.0, 0.0), (10.0, 0.0)])],
        crs=line_crs,
    )
    fp_gdf = gpd.GeoDataFrame(
        {"BT_GROUP": [1]},
        geometry=[Polygon([(0.0, -5.0), (20.0, -5.0), (20.0, 5.0), (0.0, 5.0)])],
        crs=line_crs,
    )

    def _fake_read_file(path, layer=None, **_kwargs):
        if path == "line.gpkg" and layer == "line":
            return line_gdf.copy()
        if path == "line.gpkg" and layer == "least_cost_path":
            raise pyogrio.errors.DataLayerError("missing")
        if path == "fp.gpkg" and layer == "fp":
            return fp_gdf.copy()
        raise ValueError(f"unexpected read_file call: {path}|{layer}")

    def _fake_prepare_line_args(_line_gdf, _poly_gdf, _n_samples, offset, _width_percentile):
        captured["offset"] = offset
        raise RuntimeError("stop-after-offset")

    monkeypatch.setattr(gf.gpd, "read_file", _fake_read_file)
    monkeypatch.setattr(gf.algo_common, "clean_geometries", lambda gdf, **_kwargs: gdf)
    monkeypatch.setattr(gf.algo_common, "remove_holes", lambda geom: geom)
    monkeypatch.setattr(gf.sp_common, "vector_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(gf.sp_common, "compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(gf.sp_common, "check_vector_vector_extent_overlap", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(gf.sp_common, "check_vector_vector_overlap", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(gf, "LineGrouping", _DummyLineGrouping)
    monkeypatch.setattr(gf, "prepare_line_args", _fake_prepare_line_args)

    with pytest.raises(RuntimeError, match="stop-after-offset"):
        gf.ground_footprint(
            in_line="line.gpkg|line",
            in_footprint="fp.gpkg|fp",
            n_samples=10,
            offset=10.0,
            max_width=True,
            out_footprint="out.gpkg|ground",
            merge_group=True,
            trim_output=False,
        )

    return captured


def test_ground_footprint_converts_perpendicular_length_meters_to_native(monkeypatch):
    captured = _run_ground_footprint_until_prepare_line_args(monkeypatch, "EPSG:2263")
    assert captured["offset"] == pytest.approx(32.8083333333, rel=1e-6)


def test_ground_footprint_rejects_geographic_crs_for_meter_length(monkeypatch):
    line_gdf = gpd.GeoDataFrame(
        {"BT_GROUP": [1]},
        geometry=[LineString([(0.0, 0.0), (0.01, 0.0)])],
        crs="EPSG:4326",
    )

    monkeypatch.setattr(gf.gpd, "read_file", lambda *_args, **_kwargs: line_gdf.copy())
    monkeypatch.setattr(gf.algo_common, "clean_geometries", lambda gdf, **_kwargs: gdf)

    with pytest.raises(ValueError, match="requires a projected CRS"):
        gf.ground_footprint(
            in_line="line.gpkg|line",
            in_footprint="fp.gpkg|fp",
            n_samples=10,
            offset=10.0,
            max_width=True,
            out_footprint="out.gpkg|ground",
            merge_group=True,
            trim_output=False,
        )


def test_ground_footprint_stops_when_line_and_footprint_do_not_overlap(monkeypatch):
    line_gdf = gpd.GeoDataFrame(
        {"BT_GROUP": [1]},
        geometry=[LineString([(0.0, 0.0), (1.0, 0.0)])],
        crs="EPSG:2263",
    )
    fp_gdf = gpd.GeoDataFrame(
        {"BT_GROUP": [1]},
        geometry=[Polygon([(100.0, 100.0), (110.0, 100.0), (110.0, 110.0), (100.0, 110.0)])],
        crs="EPSG:2263",
    )

    def _fake_read_file(path, layer=None, **_kwargs):
        if path == "line.gpkg" and layer == "line":
            return line_gdf.copy()
        if path == "line.gpkg" and layer == "least_cost_path":
            raise pyogrio.errors.DataLayerError("missing")
        if path == "fp.gpkg" and layer == "fp":
            return fp_gdf.copy()
        raise ValueError(f"unexpected read_file call: {path}|{layer}")

    called = {"prepare": 0}

    def _fake_prepare_line_args(*_args, **_kwargs):
        called["prepare"] += 1
        raise RuntimeError("should-not-run")

    monkeypatch.setattr(gf.gpd, "read_file", _fake_read_file)
    monkeypatch.setattr(gf.algo_common, "clean_geometries", lambda gdf, **_kwargs: gdf)
    monkeypatch.setattr(gf.algo_common, "remove_holes", lambda geom: geom)
    monkeypatch.setattr(gf.sp_common, "vector_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(gf.sp_common, "compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(gf.sp_common, "check_vector_vector_extent_overlap", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(gf.sp_common, "check_vector_vector_overlap", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(gf, "prepare_line_args", _fake_prepare_line_args)

    result = gf.ground_footprint(
        in_line="line.gpkg|line",
        in_footprint="fp.gpkg|fp",
        n_samples=10,
        offset=10.0,
        max_width=True,
        out_footprint="out.gpkg|ground",
        merge_group=True,
        trim_output=False,
    )

    assert result is None
    assert called["prepare"] == 0


def test_ground_footprint_stops_on_extent_precheck_without_loading_features(monkeypatch):
    monkeypatch.setattr(gf.sp_common, "check_vector_vector_extent_overlap", lambda *_args, **_kwargs: False)

    called = {"read": 0}

    def _fake_read(*_args, **_kwargs):
        called["read"] += 1
        raise RuntimeError("should-not-read")

    monkeypatch.setattr(gf.gpd, "read_file", _fake_read)

    result = gf.ground_footprint(
        in_line="line.gpkg|line",
        in_footprint="fp.gpkg|fp",
        n_samples=10,
        offset=10.0,
        max_width=True,
        out_footprint="out.gpkg|ground",
        merge_group=True,
        trim_output=False,
    )

    assert result is None
    assert called["read"] == 0
