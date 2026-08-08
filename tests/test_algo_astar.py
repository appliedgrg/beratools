from __future__ import annotations

import numpy as np
from rasterio.transform import from_origin
from shapely.geometry import LineString

from beratools.core.algo_astar import (
    astar_accumulation_corridor_raster,
    find_least_cost_path_astar_closest_line,
)


def test_grid_astar_closest_line_returns_linestring():
    cost = np.ones((5, 5), dtype=np.float32)
    cost[2, 1:4] = 10.0
    meta = _meta(cost)
    line = LineString([(0.5, 4.5), (4.5, 0.5)])

    path = find_least_cost_path_astar_closest_line(cost, meta, line)

    assert path is not None
    assert len(path.coords) >= 2
    assert path.coords[0] == line.coords[0]
    assert path.coords[-1] == line.coords[-1]


def test_astar_uses_stable_closest_line_route_on_uniform_tie_heavy_grid():
    cost = np.ones((12, 20), dtype=np.float32)
    meta = _meta(cost)
    line = LineString([(0.5, 11.5), (19.5, 0.5)])

    astar_path = find_least_cost_path_astar_closest_line(cost, meta, line)

    assert astar_path is not None
    assert astar_path.coords[0] == line.coords[0]
    assert astar_path.coords[-1] == line.coords[-1]
    assert len(astar_path.coords) >= 2


def test_astar_corridor_uses_zero_inside_one_outside():
    cost = np.ones((20, 20), dtype=np.float32)
    meta = _meta(cost)
    line = LineString([(1.5, 10.5), (18.5, 10.5)])

    corridor, details = astar_accumulation_corridor_raster(
        cost,
        meta,
        line,
        corridor_threshold=2.5,
        line_bias_weight=0.1,
        distance_penalty_weight=0.0,
    )

    values = set(np.unique(np.ma.asarray(corridor).compressed()).tolist())
    assert values == {0.0, 1.0}
    assert details["inside_cells"] == int(np.count_nonzero(corridor == 0.0))
    assert details["inside_cells"] > len(line.coords)


def test_astar_corridor_expands_when_threshold_increases():
    cost = np.ones((30, 30), dtype=np.float32)
    meta = _meta(cost)
    line = LineString([(2.5, 15.5), (27.5, 15.5)])

    narrow, _ = astar_accumulation_corridor_raster(
        cost,
        meta,
        line,
        corridor_threshold=0.1,
        line_bias_weight=0.1,
        distance_penalty_weight=0.0,
    )
    wide, _ = astar_accumulation_corridor_raster(
        cost,
        meta,
        line,
        corridor_threshold=4.0,
        line_bias_weight=0.1,
        distance_penalty_weight=0.0,
    )

    assert np.count_nonzero(wide == 0.0) > np.count_nonzero(narrow == 0.0)


def test_distance_penalty_does_not_expand_corridor():
    cost = np.ones((30, 30), dtype=np.float32)
    meta = _meta(cost)
    line = LineString([(2.5, 15.5), (27.5, 15.5)])

    wide, _ = astar_accumulation_corridor_raster(
        cost,
        meta,
        line,
        corridor_threshold=4.0,
        line_bias_weight=0.1,
        distance_penalty_weight=0.0,
    )
    tight, _ = astar_accumulation_corridor_raster(
        cost,
        meta,
        line,
        corridor_threshold=4.0,
        line_bias_weight=0.1,
        distance_penalty_weight=0.5,
    )

    assert np.count_nonzero(tight == 0.0) <= np.count_nonzero(wide == 0.0)


def _meta(cost: np.ndarray) -> dict:
    return {
        "transform": from_origin(0.0, float(cost.shape[0]), 1.0, 1.0),
        "width": cost.shape[1],
        "height": cost.shape[0],
        "crs": "EPSG:3857",
        "nodata": -9999.0,
    }
