import geopandas as gpd
import numpy as np
import pandas as pd

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
