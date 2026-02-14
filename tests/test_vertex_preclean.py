import geopandas as gpd
import pandas as pd
import shapely.geometry as sh_geom

import beratools.core.algo_common as algo_common
import beratools.core.algo_vertex_optimization as algo_vertex_optimization
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
