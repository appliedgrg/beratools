"""Contract tests for canopy footprint adapter runners."""

from types import SimpleNamespace

import geopandas as gpd
import shapely.geometry as sh_geom

from beratools.core.algo_canopy_footprint_absolute import CanopyFootprintRequest, cast_request_types
from beratools.tools.canopy_footprint_absolute import _run_absolute_request, _run_adaptive_request


def _single_poly_gdf():
    return gpd.GeoDataFrame(
        {"geometry": [sh_geom.box(0.0, 0.0, 1.0, 1.0)]},
        geometry="geometry",
        crs="EPSG:3857",
    )


def test_run_absolute_request_returns_contract_shape(monkeypatch):
    fake_line_classes = [SimpleNamespace(), SimpleNamespace()]
    fake_items = [SimpleNamespace(footprint=_single_poly_gdf()), SimpleNamespace(footprint=None)]

    monkeypatch.setattr(
        "beratools.tools.canopy_footprint_absolute.generate_absolute_line_class_list",
        lambda *args, **kwargs: fake_line_classes,
    )
    monkeypatch.setattr(
        "beratools.tools.canopy_footprint_absolute.bt_base.execute_multiprocessing",
        lambda *args, **kwargs: fake_items,
    )

    req = cast_request_types(
        CanopyFootprintRequest(
            in_line="dummy.gpkg|line",
            in_chm="dummy.tif",
            out_footprint="out.gpkg|fp",
            max_ln_width=32,
            corridor_thresh=3,
            exp_shk_cell=0,
            processes=0,
        )
    )
    result = _run_absolute_request(req)

    assert result.footprints_gdf is not None
    assert result.stats["line_count"] == 2
    assert result.stats["success_count"] == 1
    assert result.stats["fail_count"] == 1


def test_run_adaptive_request_returns_contract_shape(monkeypatch):
    class FakeAdaptive:
        def __init__(self, *args, **kwargs):
            self.lines = [1, 2, 3]
            self.footprints = _single_poly_gdf()
            self.lines_percentile = gpd.GeoDataFrame(
                {
                    "geometry": [sh_geom.LineString([(0.0, 0.0), (1.0, 0.0)])],
                    "percentile": [50.0],
                    "side": ["left"],
                },
                geometry="geometry",
                crs="EPSG:3857",
            )

        def compute(self, processes):
            return None

    monkeypatch.setattr("beratools.tools.canopy_footprint_absolute.FootprintCanopyAdaptive", FakeAdaptive)

    req = cast_request_types(
        CanopyFootprintRequest(
            in_line="dummy.gpkg|line",
            in_chm="dummy.tif",
            out_footprint="out.gpkg|fp",
            max_ln_width=32,
            tree_radius=1.5,
            max_line_dist=1.5,
            canopy_avoidance=0.0,
            exponent=1.0,
            canopy_thresh_percentage=50,
            processes=0,
        )
    )
    result = _run_adaptive_request(req)

    assert result.footprints_gdf is not None
    assert "lines_percentile" in result.aux_layers
    assert result.stats["line_count"] == 3
    assert result.stats["success_count"] == 1
