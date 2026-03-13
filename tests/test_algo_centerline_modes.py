import pytest
from pathlib import Path
import geopandas as gpd
import pyproj
from shapely.geometry import LineString, Point, Polygon

import beratools.core.algo_centerline as algo_centerline


def test_is_endpoint_anchored_detects_direct_and_reverse():
    seed = LineString([(0, 0), (10, 0)])
    direct = LineString([(0, 0), (3, 0), (10, 0)])
    reverse = LineString([(10, 0), (4, 0), (0, 0)])
    not_anchored = LineString([(1, 0), (9, 0)])

    assert algo_centerline._is_endpoint_anchored(direct, seed)
    assert algo_centerline._is_endpoint_anchored(reverse, seed)
    assert not algo_centerline._is_endpoint_anchored(not_anchored, seed)


def test_find_centerline_pairwise_forwards_guidance_and_skips_trim_snap(monkeypatch):
    poly = Polygon([(-10, -10), (50, -10), (50, 10), (-10, 10), (-10, -10)])
    seed = LineString([(0, 0), (40, 0)])
    captured = {}

    def fake_extract(_poly, src_geom, dst_geom, guided_strategy):
        captured["guided_strategy"] = guided_strategy
        captured["src_geom"] = src_geom
        captured["dst_geom"] = dst_geom
        return LineString([(0, 0), (20, 0), (40, 0)])

    trim_snap_calls = {"count": 0}

    def fake_trim_and_snap(_centerline, _seed, max_snap_dist=None):
        trim_snap_calls["count"] += 1
        return _centerline

    monkeypatch.setattr(algo_centerline, "_extract_centerline_from_polygon", fake_extract)
    monkeypatch.setattr(algo_centerline, "_trim_and_snap_centerline", fake_trim_and_snap)
    monkeypatch.setattr(algo_centerline, "centerline_is_valid", lambda *_args, **_kwargs: True)

    centerline, status = algo_centerline.find_centerline(poly, seed, guided_strategy="pairwise")

    assert centerline.is_valid
    assert status == algo_centerline.CenterlineStatus.SUCCESS
    assert captured["guided_strategy"] == "pairwise"
    assert captured["src_geom"] is not None
    assert captured["dst_geom"] is not None
    assert trim_snap_calls["count"] == 0


def test_find_centerline_pairwise_uses_trim_snap_fallback_when_not_anchored(monkeypatch):
    poly = Polygon([(-10, -10), (50, -10), (50, 10), (-10, 10), (-10, -10)])
    seed = LineString([(0, 0), (40, 0)])

    def fake_extract(_poly, _src_geom, _dst_geom, _guided_strategy):
        return LineString([(5, 0), (20, 0), (35, 0)])

    trim_snap_calls = {"count": 0}

    def fake_trim_and_snap(_centerline, _seed, max_snap_dist=None):
        trim_snap_calls["count"] += 1
        assert max_snap_dist == algo_centerline.CenterlineParams.GUIDED_FALLBACK_MAX_SNAP
        return LineString([(0, 0), (20, 0), (40, 0)])

    monkeypatch.setattr(algo_centerline, "_extract_centerline_from_polygon", fake_extract)
    monkeypatch.setattr(algo_centerline, "_trim_and_snap_centerline", fake_trim_and_snap)
    monkeypatch.setattr(algo_centerline, "centerline_is_valid", lambda *_args, **_kwargs: True)

    centerline, status = algo_centerline.find_centerline(poly, seed, guided_strategy="pairwise")

    assert centerline.is_valid
    assert status == algo_centerline.CenterlineStatus.SUCCESS
    assert trim_snap_calls["count"] == 1


def test_find_centerline_main_route_always_uses_trim_snap(monkeypatch):
    poly = Polygon([(-10, -10), (50, -10), (50, 10), (-10, 10), (-10, -10)])
    seed = LineString([(0, 0), (40, 0)])
    captured = {}

    def fake_extract(_poly, src_geom, dst_geom, guided_strategy):
        captured["guided_strategy"] = guided_strategy
        captured["src_geom"] = src_geom
        captured["dst_geom"] = dst_geom
        return LineString([(0, 0), (20, 0), (40, 0)])

    trim_snap_calls = {"count": 0}

    def fake_trim_and_snap(_centerline, _seed, max_snap_dist=None):
        trim_snap_calls["count"] += 1
        assert max_snap_dist is None
        return _centerline

    monkeypatch.setattr(algo_centerline, "_extract_centerline_from_polygon", fake_extract)
    monkeypatch.setattr(algo_centerline, "_trim_and_snap_centerline", fake_trim_and_snap)
    monkeypatch.setattr(algo_centerline, "centerline_is_valid", lambda *_args, **_kwargs: True)

    centerline, status = algo_centerline.find_centerline(poly, seed, guided_strategy="main_route")

    assert centerline is not None
    assert centerline.is_valid
    assert status == algo_centerline.CenterlineStatus.SUCCESS
    assert captured["guided_strategy"] == "main_route"
    assert captured["src_geom"] is None
    assert captured["dst_geom"] is None
    assert trim_snap_calls["count"] == 1


def test_pairwise_retries_main_route_when_guided_extract_fails(monkeypatch):
    poly = Polygon([(-10, -10), (50, -10), (50, 10), (-10, 10), (-10, -10)])
    seed = LineString([(0, 0), (40, 0)])
    calls = []

    def fake_extract(_poly, _src_geom, _dst_geom, guided_strategy):
        calls.append(guided_strategy)
        if guided_strategy == "pairwise":
            return None
        return LineString([(0, 0), (20, 0), (40, 0)])

    trim_snap_args = {"max_snap_dist": "unset", "count": 0}

    def fake_trim(_centerline, _seed, max_snap_dist=None):
        trim_snap_args["count"] += 1
        trim_snap_args["max_snap_dist"] = max_snap_dist
        return _centerline

    monkeypatch.setattr(algo_centerline, "_extract_centerline_from_polygon", fake_extract)
    monkeypatch.setattr(algo_centerline, "_trim_and_snap_centerline", fake_trim)
    monkeypatch.setattr(algo_centerline, "centerline_is_valid", lambda *_args, **_kwargs: True)

    centerline, status = algo_centerline.find_centerline(poly, seed, guided_strategy="pairwise")
    assert centerline is not None
    assert centerline.is_valid
    assert status == algo_centerline.CenterlineStatus.SUCCESS
    assert calls == ["pairwise", "main_route"]
    assert trim_snap_args["count"] == 1
    assert trim_snap_args["max_snap_dist"] is None


def test_snap_end_to_end_respects_max_snap_distance():
    ref = LineString([(0, 0), (100, 0)])
    line = LineString([(20, 0), (80, 0)])

    snapped = algo_centerline.snap_end_to_end(line, ref, max_snap_dist=5)
    assert snapped is not None
    assert list(snapped.coords)[0] == (20.0, 0.0)
    assert list(snapped.coords)[-1] == (80.0, 0.0)


def test_centerline_tool_rejects_unknown_guided_strategy():
    from beratools.tools.centerline import centerline

    with pytest.raises(ValueError, match="not a valid CenterlineStrategy"):
        centerline(
            in_line="dummy.gpkg|line",
            in_raster="dummy.tif",
            line_radius=15,
            proc_segments=True,
            out_line="out.gpkg|centerline",
            guided_strategy="unknown",
        )


def test_find_centerline_virtual_forwards_guidance(monkeypatch):
    poly = Polygon([(-10, -10), (50, -10), (50, 10), (-10, 10), (-10, -10)])
    seed = LineString([(0, 0), (40, 0)])
    captured = {}

    def fake_extract(_poly, src_geom, dst_geom, guided_strategy):
        captured["guided_strategy"] = guided_strategy
        captured["src_geom"] = src_geom
        captured["dst_geom"] = dst_geom
        return LineString([(0, 0), (20, 0), (40, 0)])

    monkeypatch.setattr(algo_centerline, "_extract_centerline_from_polygon", fake_extract)
    monkeypatch.setattr(algo_centerline, "_trim_and_snap_centerline", lambda c, _s, max_snap_dist=None: c)
    monkeypatch.setattr(algo_centerline, "centerline_is_valid", lambda *_args, **_kwargs: True)

    centerline, status = algo_centerline.find_centerline(poly, seed, guided_strategy="virtual_nodes")
    assert centerline is not None
    assert centerline.is_valid
    assert status == algo_centerline.CenterlineStatus.SUCCESS
    assert captured["guided_strategy"] == "virtual_nodes"
    assert isinstance(captured["src_geom"], Point)
    assert isinstance(captured["dst_geom"], Point)


def test_validate_simplify_diameter_accepts_zero():
    from beratools.core import tool_geo_simplify

    assert tool_geo_simplify.validate_diameter(0) == 0.0


def test_validate_simplify_diameter_rejects_negative():
    from beratools.core import tool_geo_simplify

    with pytest.raises(ValueError, match=">= 0"):
        tool_geo_simplify.validate_diameter(-1)


def test_run_geo_simplify_reduce_bend_builds_expected_command(monkeypatch, tmp_path):
    from beratools.core import tool_geo_simplify

    captured = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(command, capture_output, text):
        captured["command"] = command
        captured["capture_output"] = capture_output
        captured["text"] = text
        return _Result()

    monkeypatch.setattr(tool_geo_simplify, "_geo_simplify_resolve_binary_path", lambda: Path("geo-simplify"))
    monkeypatch.setattr(tool_geo_simplify.subprocess, "run", _fake_run)

    tool_geo_simplify.run_reduce_bend(
        input_file=tmp_path / "centerline_temp.gpkg",
        in_layer="centerline_temp",
        output_file=str(tmp_path / "out.gpkg"),
        out_layer="centerline",
        diameter=10.0,
        smooth_line=True,
    )

    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["command"] == [
        "geo-simplify",
        "reduce-bend",
        "--input",
        str(tmp_path / "centerline_temp.gpkg"),
        "--in-layer",
        "centerline_temp",
        "--output",
        str(tmp_path / "out.gpkg"),
        "--diameter",
        "10.0",
        "--smooth-line",
        "--out-layer",
        "centerline",
    ]


def test_run_geo_simplify_reduce_bend_omits_out_layer_when_empty(monkeypatch, tmp_path):
    from beratools.core import tool_geo_simplify

    captured = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(command, capture_output, text):
        captured["command"] = command
        return _Result()

    monkeypatch.setattr(tool_geo_simplify, "_geo_simplify_resolve_binary_path", lambda: Path("geo-simplify"))
    monkeypatch.setattr(tool_geo_simplify.subprocess, "run", _fake_run)

    tool_geo_simplify.run_reduce_bend(
        input_file=tmp_path / "centerline_temp.gpkg",
        in_layer="centerline_temp",
        output_file=str(tmp_path / "out.gpkg"),
        out_layer=None,
        diameter=10.0,
        smooth_line=True,
    )

    assert "--smooth-line" in captured["command"]
    assert "--out-layer" not in captured["command"]


def test_centerline_tool_converts_line_radius_meters_to_projected_native_units(monkeypatch):
    from beratools.tools.centerline import centerline

    captured = {}

    class _FakeOSR:
        def __init__(self, crs_text):
            self._crs_text = crs_text

        def ExportToWkt(self):
            return self._crs_text

    feet_crs_wkt = pyproj.CRS.from_epsg(2263).to_wkt()

    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.vector_crs",
        lambda *_args, **_kwargs: _FakeOSR(feet_crs_wkt),
    )
    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.raster_crs",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr("beratools.tools.centerline.sp_common.compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        "beratools.tools.centerline.gpd.read_file",
        lambda *_args, **_kwargs: gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1, 0)])], crs="EPSG:2263"),
    )
    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.check_vector_raster_overlap",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.check_vector_raster_extent_overlap",
        lambda *_args, **_kwargs: True,
    )

    def _fake_generate(
        _in_file, _in_raster, line_radius, layer=None, proc_segments=True, guided_strategy=None
    ):
        captured["line_radius"] = line_radius
        return []

    monkeypatch.setattr("beratools.tools.centerline.generate_line_class_list", _fake_generate)

    result = centerline(
        in_line="dummy.gpkg|line",
        in_raster="dummy.tif",
        line_radius=10.0,
        proc_segments=True,
        out_line="out.gpkg|centerline",
    )

    assert result == 1
    assert captured["line_radius"] == pytest.approx(32.8083333333, rel=1e-6)


def test_centerline_tool_rejects_geographic_crs_for_meter_radius(monkeypatch):
    from beratools.tools.centerline import centerline

    class _FakeOSR:
        def __init__(self, crs_text):
            self._crs_text = crs_text

        def ExportToWkt(self):
            return self._crs_text

    geo_crs_wkt = pyproj.CRS.from_epsg(4326).to_wkt()

    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.vector_crs",
        lambda *_args, **_kwargs: _FakeOSR(geo_crs_wkt),
    )

    with pytest.raises(ValueError, match="requires a projected CRS"):
        centerline(
            in_line="dummy.gpkg|line",
            in_raster="dummy.tif",
            line_radius=10.0,
            proc_segments=True,
            out_line="out.gpkg|centerline",
        )


def test_centerline_tool_terminates_when_lines_do_not_overlap_raster(monkeypatch):
    from beratools.tools.centerline import centerline

    class _FakeOSR:
        def ExportToWkt(self):
            return pyproj.CRS.from_epsg(2263).to_wkt()

    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.vector_crs", lambda *_args, **_kwargs: _FakeOSR()
    )
    monkeypatch.setattr("beratools.tools.centerline.sp_common.raster_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr("beratools.tools.centerline.sp_common.compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        "beratools.tools.centerline.gpd.read_file",
        lambda *_args, **_kwargs: gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1, 0)])], crs="EPSG:2263"),
    )
    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.check_vector_raster_overlap",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.check_vector_raster_extent_overlap",
        lambda *_args, **_kwargs: True,
    )

    called = {"generate": 0}

    def _fake_generate(*_args, **_kwargs):
        called["generate"] += 1
        raise RuntimeError("should-not-be-called")

    monkeypatch.setattr("beratools.tools.centerline.generate_line_class_list", _fake_generate)

    result = centerline(
        in_line="dummy.gpkg|line",
        in_raster="dummy.tif",
        line_radius=10.0,
        proc_segments=True,
        out_line="out.gpkg|centerline",
    )

    assert result is None
    assert called["generate"] == 0


def test_centerline_tool_continues_when_lines_partially_overlap_raster(monkeypatch):
    from beratools.tools.centerline import centerline

    class _FakeOSR:
        def ExportToWkt(self):
            return pyproj.CRS.from_epsg(2263).to_wkt()

    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.vector_crs", lambda *_args, **_kwargs: _FakeOSR()
    )
    monkeypatch.setattr("beratools.tools.centerline.sp_common.raster_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr("beratools.tools.centerline.sp_common.compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        "beratools.tools.centerline.gpd.read_file",
        lambda *_args, **_kwargs: gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1, 0)])], crs="EPSG:2263"),
    )
    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.check_vector_raster_overlap",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.check_vector_raster_extent_overlap",
        lambda *_args, **_kwargs: True,
    )

    called = {"generate": 0}

    def _fake_generate(*_args, **_kwargs):
        called["generate"] += 1
        return []

    monkeypatch.setattr("beratools.tools.centerline.generate_line_class_list", _fake_generate)

    result = centerline(
        in_line="dummy.gpkg|line",
        in_raster="dummy.tif",
        line_radius=10.0,
        proc_segments=True,
        out_line="out.gpkg|centerline",
    )

    assert result == 1
    assert called["generate"] == 1


def test_centerline_tool_terminates_on_extent_precheck_without_loading_features(monkeypatch):
    from beratools.tools.centerline import centerline

    class _FakeOSR:
        def ExportToWkt(self):
            return pyproj.CRS.from_epsg(2263).to_wkt()

    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.vector_crs", lambda *_args, **_kwargs: _FakeOSR()
    )
    monkeypatch.setattr("beratools.tools.centerline.sp_common.raster_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr("beratools.tools.centerline.sp_common.compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        "beratools.tools.centerline.sp_common.check_vector_raster_extent_overlap",
        lambda *_args, **_kwargs: False,
    )

    called = {"read": 0}

    def _fake_read(*_args, **_kwargs):
        called["read"] += 1
        raise RuntimeError("should-not-read")

    monkeypatch.setattr("beratools.tools.centerline.gpd.read_file", _fake_read)

    result = centerline(
        in_line="dummy.gpkg|line",
        in_raster="dummy.tif",
        line_radius=10.0,
        proc_segments=True,
        out_line="out.gpkg|centerline",
    )

    assert result is None
    assert called["read"] == 0
