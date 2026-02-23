import pytest
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

    with pytest.raises(ValueError, match="guided_strategy must be one of"):
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
