import geopandas as gpd
import pytest
from shapely.geometry import GeometryCollection, LineString, Point, box
import json
from pathlib import Path

import beratools.core.constants as bt_const
from beratools.core.algo_common import clean_line_geometries
import beratools.tools.check_seed_line as csl


def _write_seed_input(tmp_path, geoms, data=None, layer="seed_lines"):
    in_gpkg = tmp_path / "seed_input.gpkg"
    attrs = data if data is not None else {"id": list(range(1, len(geoms) + 1))}
    src = gpd.GeoDataFrame(attrs, geometry=geoms, crs="EPSG:3857")
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
        csl, "generate_raster_footprint", lambda *_args, **_kwargs: Point(100.0, 100.0).buffer(100.0)
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
        csl, "generate_raster_footprint", lambda *_args, **_kwargs: Point(0.0, 0.0).buffer(50.0)
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
        csl, "generate_raster_footprint", lambda *_args, **_kwargs: box(-0.001, -0.001, 0.001, 0.001)
    )

    out = csl._clip_to_chm_footprint(gdf, in_raster="dummy.tif", shrink_m=15.0)

    assert not out.empty
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
        csl,
        "generate_raster_footprint",
        lambda *_args, **_kwargs: box(-0.00005, -0.00005, 0.00005, 0.00005),
    )

    with pytest.raises(ValueError, match="CHM footprint became empty"):
        csl._clip_to_chm_footprint(gdf, in_raster="dummy.tif", shrink_m=15.0)


def test_check_seed_line_requires_in_raster():
    with pytest.raises(ValueError, match="in_raster"):
        csl.check_seed_line(in_line="dummy.gpkg|seed", in_raster="", out_line="out.gpkg|seed")


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
        return gdf

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
