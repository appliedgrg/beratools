import geopandas as gpd
import pytest
from shapely.geometry import GeometryCollection, LineString, Point, box
import json
import sqlite3
from pathlib import Path

import beratools.core.constants as bt_const
from beratools.core.algo_common import clean_line_geometries
import beratools.tools.check_seed_line as csl


def _write_seed_input(tmp_path, geoms, data=None, layer="seed_lines", crs="EPSG:3857"):
    in_gpkg = tmp_path / "seed_input.gpkg"
    attrs = data if data is not None else {"id": list(range(1, len(geoms) + 1))}
    src = gpd.GeoDataFrame(attrs, geometry=geoms, crs=crs)
    src.to_file(in_gpkg, layer=layer)
    return in_gpkg


def test_clean_line_geometries_respects_min_length():
    gdf = gpd.GeoDataFrame(
        {"id": [1, 2, 3]},
        geometry=[
            LineString([(0.0, 0.0), (0.0, 0.0)]),
            LineString([(0.0, 0.0), (0.5, 0.0)]),
            LineString([(0.0, 0.0), (2.0, 0.0)]),
        ],
        crs="EPSG:3857",
    )

    out = clean_line_geometries(gdf, min_length=1.0)
    assert len(out) == 1
    assert out.iloc[0]["id"] == 3


def test_snap_close_endpoints_directed_to_longer_line():
    gdf = gpd.GeoDataFrame(
        {"line_id": [10, 11]},
        geometry=[
            LineString([(0.0, 0.0), (10.0, 0.0)]),
            LineString([(10.5, 0.0), (12.0, 0.0)]),
        ],
        crs="EPSG:3857",
    )

    out = csl._snap_close_endpoints(gdf, tolerance=1.0)
    long_line = out.geometry.iloc[0]
    short_line = out.geometry.iloc[1]

    assert Point(long_line.coords[-1]).equals(Point(10.0, 0.0))
    assert Point(short_line.coords[0]).equals(Point(10.0, 0.0))


def test_snap_close_endpoints_tie_break_by_lower_line_id():
    gdf = gpd.GeoDataFrame(
        {"line_id": [5, 3]},
        geometry=[
            LineString([(0.0, 0.0), (2.0, 0.0)]),
            LineString([(2.5, 0.0), (4.5, 0.0)]),
        ],
        crs="EPSG:3857",
    )

    out = csl._snap_close_endpoints(gdf, tolerance=1.0)
    line_with_higher_id = out.geometry.iloc[0]
    line_with_lower_id = out.geometry.iloc[1]

    assert Point(line_with_lower_id.coords[0]).equals(Point(2.5, 0.0))
    assert Point(line_with_higher_id.coords[-1]).equals(Point(2.5, 0.0))


def test_snap_close_endpoints_locks_anchor_to_prevent_chain_disconnect():
    gdf = gpd.GeoDataFrame(
        {"line_id": [30, 20, 10]},
        geometry=[
            LineString([(-1.0, 0.0), (0.0, 0.0)]),
            LineString([(-1.6, 0.0), (0.4, 0.0)]),
            LineString([(-2.2, 0.0), (0.8, 0.0)]),
        ],
        crs="EPSG:3857",
    )

    out = csl._snap_close_endpoints(gdf, tolerance=0.6)

    a_end = Point(out.geometry.iloc[0].coords[-1])
    b_end = Point(out.geometry.iloc[1].coords[-1])
    c_end = Point(out.geometry.iloc[2].coords[-1])

    assert a_end.equals(b_end)
    assert not b_end.equals(c_end)


def test_snap_close_endpoints_anchor_can_snap_multiple_movers():
    gdf = gpd.GeoDataFrame(
        {"line_id": [30, 10, 20]},
        geometry=[
            LineString([(-1.0, 0.0), (0.1, 0.0)]),
            LineString([(-2.5, 0.0), (0.5, 0.0)]),
            LineString([(-1.1, 0.0), (0.9, 0.0)]),
        ],
        crs="EPSG:3857",
    )

    out = csl._snap_close_endpoints(gdf, tolerance=0.5)

    a_end = Point(out.geometry.iloc[0].coords[-1])
    b_end = Point(out.geometry.iloc[1].coords[-1])
    c_end = Point(out.geometry.iloc[2].coords[-1])

    assert a_end.equals(b_end)
    assert c_end.equals(b_end)


def test_snap_close_endpoints_geographic_uses_meter_tolerance():
    gdf = gpd.GeoDataFrame(
        {"line_id": [1, 2]},
        geometry=[
            LineString([(-0.001, 0.0), (0.0, 0.0)]),
            LineString([(-0.001, 0.0), (0.0001, 0.0)]),
        ],
        crs="EPSG:4326",
    )

    out = csl._snap_close_endpoints(gdf, tolerance=5.0)

    a_end = Point(out.geometry.iloc[0].coords[-1])
    b_end = Point(out.geometry.iloc[1].coords[-1])
    assert not a_end.equals(b_end)


def test_snap_close_endpoints_geographic_snaps_with_larger_meter_tolerance():
    gdf = gpd.GeoDataFrame(
        {"line_id": [1, 2]},
        geometry=[
            LineString([(-0.001, 0.0), (0.0, 0.0)]),
            LineString([(-0.001, 0.0), (0.0001, 0.0)]),
        ],
        crs="EPSG:4326",
    )

    out = csl._snap_close_endpoints(gdf, tolerance=20.0)

    a_end = Point(out.geometry.iloc[0].coords[-1])
    b_end = Point(out.geometry.iloc[1].coords[-1])
    assert a_end.equals(b_end)


def test_densify_long_lines_preserves_feature_count_and_max_length():
    gdf = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[LineString([(0.0, 0.0), (9.0, 0.0)])],
        crs="EPSG:3857",
    )

    out = csl._densify_long_lines(gdf, max_segment_length=2.0)
    assert len(out) == 1
    assert out.geometry.iloc[0].geom_type == "LineString"

    coords = list(out.geometry.iloc[0].coords)
    seg_lengths = [Point(coords[i]).distance(Point(coords[i + 1])) for i in range(len(coords) - 1)]
    assert all(seg <= 2.0 + bt_const.SMALL_BUFFER for seg in seg_lengths)


def test_densify_long_lines_geographic_uses_meter_threshold():
    gdf = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[LineString([(0.0, 0.0), (0.02, 0.0)])],
        crs="EPSG:4326",
    )

    out = csl._densify_long_lines(gdf, max_segment_length=500.0)
    coords = list(out.geometry.iloc[0].coords)
    assert len(coords) > 2

    crs = csl._require_crs(out, "Max segment length (m)")
    unit_ctx = csl._build_linear_unit_context(crs, out.unary_union.envelope)
    seg_lengths_m = [
        csl._geometry_length_meters(LineString([coords[i], coords[i + 1]]), unit_ctx)
        for i in range(len(coords) - 1)
    ]
    assert all(seg <= 500.0 + bt_const.SMALL_BUFFER for seg in seg_lengths_m)


def test_densify_long_lines_projected_feet_converts_meter_threshold():
    gdf = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[LineString([(0.0, 0.0), (4000.0, 0.0)])],
        crs="EPSG:2263",
    )

    out = csl._densify_long_lines(gdf, max_segment_length=500.0)
    coords = list(out.geometry.iloc[0].coords)
    assert len(coords) > 2

    crs = csl._require_crs(out, "Max segment length (m)")
    unit_ctx = csl._build_linear_unit_context(crs, out.unary_union.envelope)
    seg_lengths_m = [
        csl._geometry_length_meters(LineString([coords[i], coords[i + 1]]), unit_ctx)
        for i in range(len(coords) - 1)
    ]
    assert all(seg <= 500.0 + bt_const.SMALL_BUFFER for seg in seg_lengths_m)


def test_normalize_to_lines_filters_non_line_parts():
    line = LineString([(0.0, 0.0), (1.0, 0.0)])
    mixed = GeometryCollection([line, Point(1.0, 0.0)])
    gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[mixed], crs="EPSG:3857")

    out = csl._normalize_to_lines(gdf)
    assert len(out) == 1
    assert out.geometry.iloc[0].geom_type == "LineString"


def test_check_seed_line_early_return_writes_empty_output(tmp_path, monkeypatch):
    in_gpkg = _write_seed_input(tmp_path, [LineString([(0.0, 0.0), (1.0, 0.0)])])
    out_gpkg = tmp_path / "seed_output.gpkg"

    monkeypatch.setattr(csl.sp_common, "vector_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(csl.sp_common, "raster_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(csl.sp_common, "compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        csl.algo_common,
        "generate_raster_footprint",
        lambda *_args, **_kwargs: Point(100.0, 100.0).buffer(100.0),
    )

    csl.check_seed_line(
        in_line=f"{in_gpkg.as_posix()}|seed_lines",
        in_raster="dummy.tif",
        out_line=f"{out_gpkg.as_posix()}|seed_checked",
    )

    out = gpd.read_file(out_gpkg, layer="seed_checked")
    assert out.empty
    assert "id" in out.columns


def test_check_seed_line_merge_guard_assigns_unique_bt_group(tmp_path, monkeypatch):
    in_gpkg = _write_seed_input(
        tmp_path,
        [
            LineString([(0.0, 0.0), (1.0, 0.0)]),
            LineString([(3.0, 0.0), (4.0, 0.0)]),
        ],
        data={"id": [1, 2]},
    )
    out_gpkg = tmp_path / "seed_output.gpkg"

    monkeypatch.setattr(csl.sp_common, "vector_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(csl.sp_common, "raster_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(csl.sp_common, "compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        csl.algo_common,
        "generate_raster_footprint",
        lambda *_args, **_kwargs: Point(0.0, 0.0).buffer(50.0),
    )

    csl.check_seed_line(
        in_line=f"{in_gpkg.as_posix()}|seed_lines",
        in_raster="dummy.tif",
        out_line=f"{out_gpkg.as_posix()}|seed_checked",
        group_lines=False,
        merge_by_group=True,
    )

    out = gpd.read_file(out_gpkg, layer="seed_checked")
    assert len(out) == 2
    assert bt_const.BT_GROUP in out.columns
    assert out[bt_const.BT_GROUP].nunique() == len(out)


def test_clip_to_chm_footprint_shrink_is_meters_for_geographic_crs(monkeypatch):
    gdf = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[LineString([(-0.0015, 0.0), (0.0015, 0.0)])],
        crs="EPSG:4326",
    )

    monkeypatch.setattr(
        csl.algo_common,
        "generate_raster_footprint",
        lambda *_args, **_kwargs: box(-0.001, -0.001, 0.001, 0.001),
    )

    out, rejected, footprint = csl._clip_to_chm_footprint(gdf, in_raster="dummy.tif", shrink_m=15.0)

    assert not out.empty
    assert rejected.empty
    assert footprint is not None
    clipped = out.geometry.iloc[0]
    assert clipped.length > 0
    assert clipped.bounds[0] > -0.001
    assert clipped.bounds[2] < 0.001


def test_clip_to_chm_footprint_geographic_overshrink_raises(monkeypatch):
    gdf = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[LineString([(-0.0003, 0.0), (0.0003, 0.0)])],
        crs="EPSG:4326",
    )

    monkeypatch.setattr(
        csl.algo_common,
        "generate_raster_footprint",
        lambda *_args, **_kwargs: box(-0.00005, -0.00005, 0.00005, 0.00005),
    )

    with pytest.raises(ValueError, match="CHM footprint became empty"):
        csl._clip_to_chm_footprint(gdf, in_raster="dummy.tif", shrink_m=15.0)


def test_check_seed_line_minimum_length_geographic_uses_meters(tmp_path, monkeypatch):
    in_gpkg = _write_seed_input(
        tmp_path,
        [
            LineString([(0.0, 0.0), (0.00008, 0.0)]),
            LineString([(0.0, 0.001), (0.00002, 0.001)]),
        ],
        data={"id": [1, 2]},
        crs="EPSG:4326",
    )
    out_gpkg = tmp_path / "seed_output.gpkg"

    monkeypatch.setattr(csl.sp_common, "vector_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(csl.sp_common, "raster_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(csl.sp_common, "compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        csl,
        "_clip_to_chm_footprint",
        lambda gdf, *_args, **_kwargs: (gdf, gdf.iloc[0:0].copy(), Point(0.0, 0.0).buffer(1.0)),
    )

    csl.check_seed_line(
        in_line=f"{in_gpkg.as_posix()}|seed_lines",
        in_raster="dummy.tif",
        out_line=f"{out_gpkg.as_posix()}|seed_checked",
        remove_short_lines=True,
        minimum_line_length=5.0,
        snap_close_endpoints=False,
        group_lines=False,
    )

    out = gpd.read_file(out_gpkg, layer="seed_checked")
    assert len(out) == 1
    assert out.iloc[0]["id"] == 1


def test_check_seed_line_missing_raster_logs_error_and_continues(tmp_path, monkeypatch):
    in_gpkg = _write_seed_input(tmp_path, [LineString([(0.0, 0.0), (1.0, 0.0)])])
    out_gpkg = tmp_path / "seed_output.gpkg"

    clip_calls = []
    errors = []

    monkeypatch.setattr(
        csl, "_clip_to_chm_footprint", lambda gdf, *_args, **_kwargs: clip_calls.append(1) or gdf
    )
    monkeypatch.setattr(csl, "qc_split_lines_at_intersections", lambda gdf: gdf)
    monkeypatch.setattr(csl.logger, "error", lambda msg, *args: errors.append(msg % args if args else msg))

    csl.check_seed_line(
        in_line=f"{in_gpkg.as_posix()}|seed_lines",
        in_raster="",
        out_line=f"{out_gpkg.as_posix()}|seed_checked",
        clip_to_chm_footprint=True,
        group_lines=False,
    )

    out = gpd.read_file(out_gpkg, layer="seed_checked")
    assert len(out) == 1
    assert clip_calls == []
    assert any("in_raster" in msg for msg in errors)


def test_check_seed_line_skips_clip_when_disabled(tmp_path, monkeypatch):
    in_gpkg = _write_seed_input(tmp_path, [LineString([(0.0, 0.0), (1.0, 0.0)])])
    out_gpkg = tmp_path / "seed_output.gpkg"

    clip_calls = []
    monkeypatch.setattr(
        csl, "_clip_to_chm_footprint", lambda gdf, *_args, **_kwargs: clip_calls.append(1) or gdf
    )
    monkeypatch.setattr(csl, "qc_split_lines_at_intersections", lambda gdf: gdf)

    csl.check_seed_line(
        in_line=f"{in_gpkg.as_posix()}|seed_lines",
        in_raster="",
        out_line=f"{out_gpkg.as_posix()}|seed_checked",
        clip_to_chm_footprint=False,
        group_lines=False,
    )

    out = gpd.read_file(out_gpkg, layer="seed_checked")
    assert len(out) == 1
    assert clip_calls == []


def test_pipeline_runs_snap_before_split(tmp_path, monkeypatch):
    in_gpkg = _write_seed_input(
        tmp_path,
        [
            LineString([(0.0, 0.0), (10.0, 0.0)]),
            LineString([(10.5, 0.0), (12.0, 0.0)]),
        ],
        data={"line_id": [1, 2]},
    )
    out_gpkg = tmp_path / "seed_output.gpkg"

    monkeypatch.setattr(csl.sp_common, "vector_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(csl.sp_common, "raster_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(csl.sp_common, "compare_crs", lambda *_args, **_kwargs: True)

    call_order = []

    def _fake_clip(gdf, *_args, **_kwargs):
        return gdf, gdf.iloc[0:0].copy(), Point(0.0, 0.0).buffer(1.0)

    def _fake_snap(gdf, *_args, **_kwargs):
        call_order.append("snap")
        return gdf

    def _fake_split(gdf):
        call_order.append("split")
        return gdf

    monkeypatch.setattr(csl, "_clip_to_chm_footprint", _fake_clip)
    monkeypatch.setattr(csl, "_snap_close_endpoints", _fake_snap)
    monkeypatch.setattr(csl, "qc_split_lines_at_intersections", _fake_split)

    csl.check_seed_line(
        in_line=f"{in_gpkg.as_posix()}|seed_lines",
        in_raster="dummy.tif",
        out_line=f"{out_gpkg.as_posix()}|seed_checked",
        snap_close_endpoints=True,
        group_lines=False,
    )

    assert call_order == ["snap", "split"]


def test_check_seed_line_writes_qc_doc_tables(tmp_path, monkeypatch):
    in_gpkg = _write_seed_input(
        tmp_path,
        [
            LineString([(0.0, 0.0), (1.0, 0.0)]),
            LineString([(100.0, 100.0), (101.0, 100.0)]),
        ],
        data={"id": [1, 2]},
    )
    out_gpkg = tmp_path / "seed_output.gpkg"

    monkeypatch.setattr(csl.sp_common, "vector_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(csl.sp_common, "raster_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(csl.sp_common, "compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        csl.algo_common,
        "generate_raster_footprint",
        lambda *_args, **_kwargs: box(-20.0, -20.0, 20.0, 20.0),
    )

    csl.check_seed_line(
        in_line=f"{in_gpkg.as_posix()}|seed_lines",
        in_raster="dummy.tif",
        out_line=f"{out_gpkg.as_posix()}|seed_checked",
        group_lines=False,
        clip_to_chm_footprint=True,
    )

    aux_gpkg = out_gpkg.with_stem(out_gpkg.stem + "_aux")
    with sqlite3.connect(aux_gpkg.as_posix()) as conn:
        tables = {row[0] for row in conn.execute("SELECT table_name FROM gpkg_contents")}
        assert "qc_manifest" in tables
        assert "qc_run_summary" in tables

        manifest_rows = conn.execute(
            "SELECT layer_name, feature_count, written FROM qc_manifest WHERE layer_name='qc_removed_clipped'"
        ).fetchall()
        assert len(manifest_rows) == 1
        assert manifest_rows[0][1] >= 1
        assert manifest_rows[0][2] == 1


def test_check_seed_line_accounts_input_cleanup_in_manifest(tmp_path):
    in_gpkg = _write_seed_input(
        tmp_path,
        [
            LineString([(0.0, 0.0), (1.0, 0.0)]),
            None,
        ],
        data={"id": [1, 2]},
    )
    out_gpkg = tmp_path / "seed_output.gpkg"

    csl.check_seed_line(
        in_line=f"{in_gpkg.as_posix()}|seed_lines",
        in_raster="",
        out_line=f"{out_gpkg.as_posix()}|seed_checked",
        clip_to_chm_footprint=False,
        group_lines=False,
    )

    out = gpd.read_file(out_gpkg, layer="seed_checked")
    assert len(out) == 1

    aux_gpkg = out_gpkg.with_stem(out_gpkg.stem + "_aux")
    with sqlite3.connect(aux_gpkg.as_posix()) as conn:
        row = conn.execute(
            "SELECT feature_count, written FROM qc_manifest WHERE layer_name='qc_removed_input_cleanup'"
        ).fetchone()
        assert row is not None
        assert row[0] == 1
        assert row[1] == 1


def test_check_seed_line_overwrites_qc_tables_on_rerun(tmp_path, monkeypatch):
    in_gpkg = _write_seed_input(
        tmp_path,
        [
            LineString([(0.0, 0.0), (1.0, 0.0)]),
            LineString([(100.0, 100.0), (101.0, 100.0)]),
        ],
        data={"id": [1, 2]},
    )
    out_gpkg = tmp_path / "seed_output.gpkg"

    monkeypatch.setattr(csl.sp_common, "vector_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(csl.sp_common, "raster_crs", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(csl.sp_common, "compare_crs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        csl.algo_common,
        "generate_raster_footprint",
        lambda *_args, **_kwargs: box(-20.0, -20.0, 20.0, 20.0),
    )

    csl.check_seed_line(
        in_line=f"{in_gpkg.as_posix()}|seed_lines",
        in_raster="dummy.tif",
        out_line=f"{out_gpkg.as_posix()}|seed_checked",
        clip_to_chm_footprint=False,
        group_lines=False,
    )

    csl.check_seed_line(
        in_line=f"{in_gpkg.as_posix()}|seed_lines",
        in_raster="dummy.tif",
        out_line=f"{out_gpkg.as_posix()}|seed_checked",
        clip_to_chm_footprint=True,
        group_lines=False,
    )

    aux_gpkg = out_gpkg.with_stem(out_gpkg.stem + "_aux")
    with sqlite3.connect(aux_gpkg.as_posix()) as conn:
        summary_count = conn.execute("SELECT COUNT(*) FROM qc_run_summary").fetchone()[0]
        output_count = conn.execute("SELECT output_feature_count FROM qc_run_summary").fetchone()[0]
        clipped = conn.execute(
            "SELECT feature_count, written FROM qc_manifest WHERE layer_name='qc_removed_clipped'"
        ).fetchone()

    assert summary_count == 1
    assert output_count == 1
    assert clipped is not None
    assert clipped[0] >= 1
    assert clipped[1] == 1


def test_schema_marks_chm_shrink_as_optional():
    schema_path = Path(__file__).resolve().parents[1] / "beratools" / "gui" / "assets" / "beratools.json"
    data = json.loads(schema_path.read_text(encoding="utf-8"))

    check_tool = None
    for category in data.get("toolbox", []):
        for tool in category.get("tools", []):
            if tool.get("name") == "Check Seed Lines":
                check_tool = tool
                break
        if check_tool:
            break

    assert check_tool is not None
    params = {param["variable"]: param for param in check_tool.get("parameters", [])}
    assert params["chm_footprint_shrink"]["optional"] is True
    assert params["clip_to_chm_footprint"]["default"] is True
    assert params["clip_to_chm_footprint"]["optional"] is True


def test_schema_centerline_guided_strategy_parameter():
    schema_path = Path(__file__).resolve().parents[1] / "beratools" / "gui" / "assets" / "beratools.json"
    data = json.loads(schema_path.read_text(encoding="utf-8"))

    centerline_tool = None
    for category in data.get("toolbox", []):
        for tool in category.get("tools", []):
            if tool.get("name") == "Centerline":
                centerline_tool = tool
                break
        if centerline_tool:
            break

    assert centerline_tool is not None
    params = {param["variable"]: param for param in centerline_tool.get("parameters", [])}
    assert "guided_strategy" in params
    assert params["guided_strategy"]["type"] == "list"
    assert params["guided_strategy"]["subtype"] == "text"
    assert params["guided_strategy"]["data"] == ["main_route", "candidate"]
    assert params["guided_strategy"]["default"] == "main_route"
