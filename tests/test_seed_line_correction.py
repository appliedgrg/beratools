import geopandas as gpd
import numpy as np
import pandas as pd
import shapely.geometry as sh_geom

import beratools.core.algo_common as algo_common
import beratools.core.constants as bt_const
from beratools.core.algo_seed_line_correction import SeedLineCorrection
from beratools.utility.spatial_common import decode_file_layer


def assert_gdf_equal(gdf_new, gdf_ref, geom_tol=1e-6, sort_by=None):
    if sort_by:
        gdf_new = gdf_new.sort_values(sort_by).reset_index(drop=True)
        gdf_ref = gdf_ref.sort_values(sort_by).reset_index(drop=True)

    assert len(gdf_new) == len(gdf_ref), f"Feature count: {len(gdf_new)} vs {len(gdf_ref)}"

    attr_cols_new = sorted(c for c in gdf_new.columns if c != "geometry")
    attr_cols_ref = sorted(c for c in gdf_ref.columns if c != "geometry")
    assert attr_cols_new == attr_cols_ref, f"Columns differ: {attr_cols_new} vs {attr_cols_ref}"

    for col in attr_cols_ref:
        assert gdf_new[col].dtype == gdf_ref[col].dtype, (
            f"Column '{col}' dtype: {gdf_new[col].dtype} vs {gdf_ref[col].dtype}"
        )

    for col in attr_cols_ref:
        pd.testing.assert_series_equal(
            gdf_new[col].reset_index(drop=True),
            gdf_ref[col].reset_index(drop=True),
            check_names=False,
            obj=f"Column '{col}'",
        )

    assert gdf_new.crs == gdf_ref.crs, f"CRS differ: {gdf_new.crs} vs {gdf_ref.crs}"

    for i in range(len(gdf_ref)):
        coords_new = np.array(gdf_new.geometry.iloc[i].coords)
        coords_ref = np.array(gdf_ref.geometry.iloc[i].coords)
        assert coords_new.shape == coords_ref.shape, f"Line {i}: vertex count differs"
        assert np.allclose(coords_new, coords_ref, atol=geom_tol), (
            f"Line {i}: coords differ beyond {geom_tol}m"
        )


def _make_slc(args, in_file, in_layer):
    return SeedLineCorrection(
        in_file,
        args["in_raster"],
        args["search_distance"],
        args["line_radius"],
        processes=0,
        call_mode="test",
        layer=in_layer,
    )


def _make_local_slc(monkeypatch, *, close_distance=0.5, angle_tol=10.0):
    monkeypatch.setattr(
        algo_common,
        "generate_raster_footprint",
        lambda *_args, **_kwargs: sh_geom.box(-100.0, -100.0, 100.0, 100.0),
    )
    return SeedLineCorrection(
        "dummy.gpkg",
        "dummy.tif",
        search_distance=1.0,
        line_radius=1.0,
        processes=0,
        call_mode="test",
        optimize_internal_vertices=False,
        close_distance=close_distance,
        min_segment_length=close_distance,
        angle_tol=angle_tol,
    )


def test_slc_inmemory_matches_file(tool_arguments_integration):
    args = tool_arguments_integration["args_vertex_optimization"]
    in_file, in_layer = decode_file_layer(args["in_line"])

    input_gdf = gpd.read_file(in_file, layer=in_layer)

    slc_file = _make_slc(args, in_file, in_layer)
    slc_file.prepare_lines()

    slc_mem = _make_slc(args, in_file, in_layer)
    slc_mem.prepare_lines(lines_gdf=input_gdf)

    assert len(slc_mem.line_list) == len(slc_file.line_list)
    for idx in range(len(slc_file.line_list)):
        coords_file = np.array(slc_file.line_list[idx].geometry.iloc[0].coords)
        coords_mem = np.array(slc_mem.line_list[idx].geometry.iloc[0].coords)
        assert coords_mem.shape == coords_file.shape
        assert np.allclose(coords_mem, coords_file, atol=1e-6)

    slc_file.group_vertices()
    result_file = slc_file.optimize()

    slc_mem.group_vertices()
    result_mem = slc_mem.optimize()

    assert_gdf_equal(result_mem, result_file, sort_by="BT_UID")


def test_prepare_lines_removes_vertex_close_to_endpoint(monkeypatch):
    slc = _make_local_slc(monkeypatch, close_distance=0.5)
    line = sh_geom.LineString([(0.0, 0.0), (0.2, 0.0), (2.0, 0.0), (4.0, 0.0)])
    lines_gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[line], crs="EPSG:3857")

    slc.prepare_lines(lines_gdf=lines_gdf)

    assert len(slc.line_list) == 1
    coords = list(slc.line_list[0].geometry.iloc[0].coords)
    assert coords == [(0.0, 0.0), (2.0, 0.0), (4.0, 0.0)]


def test_prepare_lines_preserves_bend_while_thinning_close_vertices(monkeypatch):
    slc = _make_local_slc(monkeypatch, close_distance=0.5, angle_tol=10.0)
    line = sh_geom.LineString([(0.0, 0.0), (2.0, 0.0), (2.2, 0.3), (2.4, 0.3), (4.0, 0.3)])
    lines_gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[line], crs="EPSG:3857")

    slc.prepare_lines(lines_gdf=lines_gdf)

    coords = list(slc.line_list[0].geometry.iloc[0].coords)
    assert (2.4, 0.3) not in coords
    assert len(coords) >= 3
    assert any(coord[1] > 0.0 for coord in coords[1:])


def test_prepare_lines_dense_uniform_line_keeps_representatives(monkeypatch):
    close_distance = 0.5
    slc = _make_local_slc(monkeypatch, close_distance=close_distance, angle_tol=10.0)
    line = sh_geom.LineString([(idx * 0.2, 0.0) for idx in range(20)])
    lines_gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[line], crs="EPSG:3857")

    slc.prepare_lines(lines_gdf=lines_gdf)

    coords = list(slc.line_list[0].geometry.iloc[0].coords)
    assert coords[0] == (0.0, 0.0)
    assert np.isclose(coords[-1][0], 3.8)
    assert np.isclose(coords[-1][1], 0.0)
    assert len(coords) > 2
    assert all(
        sh_geom.Point(coords[i]).distance(sh_geom.Point(coords[i + 1]))
        >= close_distance - bt_const.SMALL_BUFFER
        for i in range(len(coords) - 1)
    )


def test_optimize_post_update_removes_vertex_close_to_moved_endpoint(monkeypatch):
    slc = _make_local_slc(monkeypatch, close_distance=2.0, angle_tol=10.0)
    line = sh_geom.LineString([(0.0, 0.0), (2.2, 0.0), (6.0, 0.0)])
    slc.line_list = [gpd.GeoDataFrame({"id": [1]}, geometry=[line], crs="EPSG:3857")]

    class _StubVertex:
        def __init__(self, vertex_opt):
            self.vertex_opt = vertex_opt
            self.lines = [type("LineRef", (), {"line_no": 0, "end_no": 0})()]

    slc.vertex_grp = [_StubVertex(sh_geom.Point(0.5, 0.0))]
    monkeypatch.setattr(slc, "compute", lambda: None)

    out = slc.optimize()

    assert out is not None
    coords = list(out.geometry.iloc[0].coords)
    assert coords == [(0.5, 0.0), (6.0, 0.0)]


def test_post_update_endpoint_cleanup_only_targets_endpoint_adjacent_vertices(monkeypatch):
    slc = _make_local_slc(monkeypatch, close_distance=2.0, angle_tol=10.0)
    line = sh_geom.LineString([(0.0, 0.0), (3.0, 0.0), (4.2, 0.0), (7.0, 0.0)])
    slc.line_list = [gpd.GeoDataFrame({"id": [1]}, geometry=[line], crs="EPSG:3857")]

    class _StubVertex:
        def __init__(self, vertex_opt):
            self.vertex_opt = vertex_opt
            self.lines = [type("LineRef", (), {"line_no": 0, "end_no": 0})()]

    slc.vertex_grp = [_StubVertex(sh_geom.Point(0.5, 0.0))]
    monkeypatch.setattr(slc, "compute", lambda: None)

    out = slc.optimize()

    assert out is not None
    coords = list(out.geometry.iloc[0].coords)
    assert coords == [(0.5, 0.0), (3.0, 0.0), (4.2, 0.0), (7.0, 0.0)]


def test_get_debug_layers_include_group_id(monkeypatch):
    slc = _make_local_slc(monkeypatch, close_distance=1.0, angle_tol=10.0)
    seed_line = sh_geom.LineString([(0.0, 0.0), (5.0, 0.0)])
    slc.line_list = [gpd.GeoDataFrame({"id": [1]}, geometry=[seed_line], crs="EPSG:3857")]

    class _StubVertex:
        def __init__(self, centerlines, anchors, vertex_opt):
            self.centerlines = centerlines
            self.anchors = anchors
            self.vertex_opt = vertex_opt

    slc.vertex_grp = [
        _StubVertex(
            centerlines=[sh_geom.LineString([(0.0, 0.0), (1.0, 0.0)])],
            anchors=[sh_geom.Point(0.0, 0.0), sh_geom.Point(1.0, 0.0)],
            vertex_opt=sh_geom.Point(0.5, 0.0),
        ),
        _StubVertex(
            centerlines=[sh_geom.LineString([(2.0, 0.0), (3.0, 0.0)])],
            anchors=[sh_geom.Point(2.0, 0.0), sh_geom.Point(3.0, 0.0)],
            vertex_opt=sh_geom.Point(2.5, 0.0),
        ),
    ]

    debug_layers = slc.get_debug_layers()

    for layer_name in ("lc_paths", "anchors", "vertices"):
        layer_gdf = debug_layers[layer_name]
        assert "SLC_GROUP" in layer_gdf.columns
        assert set(layer_gdf["SLC_GROUP"].unique()) == {0, 1}
