import geopandas as gpd
import numpy as np
import pandas as pd
import shapely.geometry as sh_geom

import beratools.core.algo_common as algo_common
import beratools.core.algo_vertex_optimization as algo_vertex_optimization
from beratools.core.algo_canopy_footprint_exp import FootprintCanopyAdaptive
from beratools.core.algo_vertex_preclean import preclean_vertices


def test_preclean_removes_close_internal_vertex():
    line = sh_geom.LineString([(0.0, 0.0), (0.2, 0.0), (2.0, 0.0)])
    gdf = gpd.GeoDataFrame({"BT_UID": [1]}, geometry=[line], crs="EPSG:3857")

    out = preclean_vertices(gdf, close_distance=0.5, min_segment_length=0.5, angle_tol=10.0)
    coords = list(out.geometry.iloc[0].coords)

    assert coords == [(0.0, 0.0), (2.0, 0.0)]


def test_preclean_keeps_single_internal_representative():
    line = sh_geom.LineString([(0.0, 0.0), (1.0, 0.0), (1.2, 0.0), (3.0, 0.0)])
    gdf = gpd.GeoDataFrame({"BT_UID": [2]}, geometry=[line], crs="EPSG:3857")

    out = preclean_vertices(gdf, close_distance=0.5, min_segment_length=0.5, angle_tol=10.0)
    coords = list(out.geometry.iloc[0].coords)

    assert coords == [(0.0, 0.0), (1.2, 0.0), (3.0, 0.0)]


def test_split_lines_to_segments_preserves_bt_uid():
    lines = gpd.GeoDataFrame(
        {"BT_UID": [10, 11]},
        geometry=[
            sh_geom.LineString([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]),
            sh_geom.LineString([(0.0, 1.0), (1.0, 1.0)]),
        ],
        crs="EPSG:3857",
    )

    split_rows = algo_common.split_lines_to_segments(lines)
    split_gdf = gpd.GeoDataFrame(pd.concat(split_rows, ignore_index=True), crs=lines.crs)

    assert len(split_gdf) == 3
    assert set(split_gdf["BT_UID"]) == {10, 11}


def test_endpoint_mode_applies_preclean(monkeypatch):
    footprint = sh_geom.box(-5.0, -5.0, 10.0, 5.0)
    line = sh_geom.LineString([(0.0, 0.0), (0.2, 0.0), (2.0, 0.0), (4.0, 0.0)])
    lines_gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[line], crs="EPSG:3857")

    monkeypatch.setattr(algo_common, "read_geospatial_file", lambda *args, **kwargs: lines_gdf)
    monkeypatch.setattr(algo_common, "generate_raster_footprint", lambda *args, **kwargs: footprint)

    vg = algo_vertex_optimization.VertexGrouping(
        in_line="dummy.gpkg",
        in_raster="dummy.tif",
        search_distance=1.0,
        line_radius=1.0,
        processes=1,
        call_mode="test",
        optimize_internal_vertices=False,
        close_distance=0.5,
        min_segment_length=0.5,
        angle_tol=10.0,
    )
    vg.create_all_vertex_groups()

    # The line should be kept whole (not split) but the close vertex (0.2, 0) should be removed
    assert len(vg.line_list) == 1
    coords = list(vg.line_list[0].geometry.iloc[0].coords)
    assert (0.2, 0.0) not in coords
    assert coords[0] == (0.0, 0.0)
    assert coords[-1] == (4.0, 0.0)


def test_internal_vertex_mode_keeps_segments_outside_raster(monkeypatch):
    footprint = sh_geom.box(0.0, -1.0, 1.0, 1.0)
    line = sh_geom.LineString([(-2.0, 0.0), (-1.0, 0.0), (0.5, 0.0)])
    lines_gdf = gpd.GeoDataFrame({"BT_UID": [7]}, geometry=[line], crs="EPSG:3857")

    monkeypatch.setattr(algo_common, "read_geospatial_file", lambda *args, **kwargs: lines_gdf)
    monkeypatch.setattr(algo_common, "generate_raster_footprint", lambda *args, **kwargs: footprint)
    monkeypatch.setattr(
        algo_vertex_optimization.algo_vertex_preclean, "preclean_vertices", lambda gdf, *_: gdf
    )

    vg = algo_vertex_optimization.VertexGrouping(
        in_line="dummy.gpkg",
        in_raster="dummy.tif",
        search_distance=1.0,
        line_radius=1.0,
        processes=1,
        call_mode="test",
        optimize_internal_vertices=True,
        close_distance=0.5,
        min_segment_length=0.5,
        angle_tol=10.0,
    )
    vg.create_all_vertex_groups()

    segments = [item.geometry.iloc[0] for item in vg.line_list]
    assert len(segments) == 2
    assert any(not seg.intersects(footprint) for seg in segments)


def _build_vertex_grouping(monkeypatch):
    monkeypatch.setattr(
        algo_common, "generate_raster_footprint", lambda *args, **kwargs: sh_geom.box(0, 0, 1, 1)
    )
    return algo_vertex_optimization.VertexGrouping(
        in_line="dummy.gpkg",
        in_raster="dummy.tif",
        search_distance=1.0,
        line_radius=1.0,
        processes=1,
        call_mode="test",
        optimize_internal_vertices=False,
        close_distance=0.5,
        min_segment_length=0.5,
        angle_tol=10.0,
    )


def test_save_all_layers_empty_lines_read_failed(monkeypatch, capsys):
    vg = _build_vertex_grouping(monkeypatch)
    vg.line_list = []

    write_calls = []

    def fake_to_file(self, *args, **kwargs):
        write_calls.append((self, args, kwargs))

    monkeypatch.setattr(algo_common, "read_geospatial_file", lambda *args, **kwargs: None)
    monkeypatch.setattr(gpd.GeoDataFrame, "to_file", fake_to_file)

    vg.save_all_layers("out.gpkg")
    output = capsys.readouterr().out

    assert "Saved output to:" not in output
    assert "No output written to:" in output
    assert len(write_calls) == 0


def test_save_all_layers_empty_lines_writes_empty(monkeypatch, capsys):
    vg = _build_vertex_grouping(monkeypatch)
    vg.line_list = []

    source_lines = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[sh_geom.LineString([(0.0, 0.0), (1.0, 0.0)])],
        crs="EPSG:3857",
    )
    write_calls = []

    def fake_to_file(self, *args, **kwargs):
        write_calls.append((len(self), args, kwargs))

    monkeypatch.setattr(algo_common, "read_geospatial_file", lambda *args, **kwargs: source_lines)
    monkeypatch.setattr(gpd.GeoDataFrame, "to_file", fake_to_file)

    vg.save_all_layers("out.gpkg")
    output = capsys.readouterr().out

    assert "Saved output to:" in output
    assert len(write_calls) == 1
    assert write_calls[0][0] == 0


def test_save_all_layers_with_populated_lines_writes(monkeypatch, capsys):
    vg = _build_vertex_grouping(monkeypatch)
    vg.line_list = [
        gpd.GeoDataFrame(
            {"id": [1]},
            geometry=[sh_geom.LineString([(0.0, 0.0), (2.0, 0.0)])],
            crs="EPSG:3857",
        )
    ]

    write_calls = []

    def fake_to_file(self, *args, **kwargs):
        write_calls.append((len(self), args, kwargs))

    monkeypatch.setattr(algo_vertex_optimization.bt_const, "BT_DEBUGGING", False)
    monkeypatch.setattr(gpd.GeoDataFrame, "to_file", fake_to_file)

    vg.save_all_layers("out.gpkg")
    output = capsys.readouterr().out

    assert "Saved output to:" in output
    assert len(write_calls) == 1
    assert write_calls[0][0] == 1


def test_read_geospatial_file_resets_index_after_clean(monkeypatch):
    empty_geom = sh_geom.GeometryCollection()
    input_gdf = gpd.GeoDataFrame(
        {"name": ["bad", "good_a", "good_b"]},
        geometry=[
            empty_geom,
            sh_geom.LineString([(0.0, 0.0), (1.0, 0.0)]),
            sh_geom.LineString([(2.0, 0.0), (3.0, 0.0)]),
        ],
        crs="EPSG:3857",
        index=pd.Index([0, 2, 3]),
    )

    monkeypatch.setattr(algo_common.gpd, "read_file", lambda *args, **kwargs: input_gdf)

    out = algo_common.read_geospatial_file("dummy.gpkg", layer="lines")

    assert out is not None
    assert list(out.index) == [0, 1]
    assert list(out["name"]) == ["good_a", "good_b"]
    assert list(out["BT_UID"]) == [0, 1]


def test_footprint_canopy_init_handles_rejected_geometry(monkeypatch):
    empty_geom = sh_geom.GeometryCollection()
    input_gdf = gpd.GeoDataFrame(
        {"id": [1, 2, 3]},
        geometry=[
            empty_geom,
            sh_geom.LineString([(0.0, 0.0), (1.0, 0.0)]),
            sh_geom.LineString([(1.0, 1.0), (2.0, 1.0)]),
        ],
        crs="EPSG:3857",
        index=pd.Index([0, 2, 3]),
    )

    monkeypatch.setattr(algo_common.gpd, "read_file", lambda *args, **kwargs: input_gdf)

    canopy = FootprintCanopyAdaptive("dummy.gpkg|lines", "dummy.tif")

    assert len(canopy.lines) == 2


def test_clean_geometries_handles_na_sentinels():
    gdf = gpd.GeoDataFrame(
        {"id": [1, 2, 3]},
        geometry=[pd.NA, np.nan, sh_geom.LineString([(0.0, 0.0), (1.0, 0.0)])],
        crs="EPSG:3857",
    )

    out = algo_common.clean_geometries(gdf, stage="input")

    assert out is not None
    assert len(out) == 1
    assert out.iloc[0]["id"] == 3


def test_clean_geometries_handles_na_and_empty_mix():
    gdf = gpd.GeoDataFrame(
        {"id": [1, 2, 3]},
        geometry=[pd.NA, sh_geom.GeometryCollection(), sh_geom.LineString([(0.0, 0.0), (1.0, 0.0)])],
        crs="EPSG:3857",
    )

    out = algo_common.clean_geometries(gdf, stage="input")

    assert out is not None
    assert len(out) == 1
    assert out.iloc[0]["id"] == 3
