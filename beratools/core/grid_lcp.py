from __future__ import annotations

import heapq
import math
from itertools import count
from typing import Iterable

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import LineString
from beratools.core.algo_dijkstra import _hausdorff_dist

SQRT2 = math.sqrt(2.0)
ASTAR_LINE_BIAS = 0.001
SMOOTH_CORRIDOR_CELLS = 2.0
SMOOTH_MAX_DISTANCE_CELLS = 1.5


NEIGHBORS: tuple[tuple[int, int], ...] = (
    (1, 0),
    (0, -1),
    (-1, 0),
    (0, 1),
    (1, -1),
    (1, 1),
    (-1, -1),
    (-1, 1),
)


def find_least_cost_path_astar_closest_line(
    seedline_class,cost_arr, meta: dict, input_line: LineString
) -> LineString | None:
    lcp=_find_astar_path(seedline_class,cost_arr, meta, input_line)
    if _hausdorff_dist(lcp, input_line) > float(seedline_class.line_radius) / 2:
        lcp=input_line
    return lcp


def find_least_cost_path_astar_smooth_closest_line(
    cost_arr, meta: dict, input_line: LineString
) -> LineString | None:
    raw_path = find_least_cost_path_astar_closest_line(cost_arr, meta, input_line)
    if raw_path is None or raw_path.is_empty or len(raw_path.coords) < 2:
        return raw_path

    smooth_path = _smooth_path_in_astar_corridor(cost_arr, meta, input_line, raw_path)
    if smooth_path is None or smooth_path.is_empty or len(smooth_path.coords) < 2:
        return raw_path
    return smooth_path


def apply_line_buffer_cost_reduction(
    cost_arr,
    meta: dict,
    input_line: LineString,
    *,
    buffer_distance: float,
    multiplier: float,
):
    if input_line is None or input_line.is_empty or buffer_distance <= 0:
        return np.ma.array(cost_arr, copy=True)

    array = np.ma.asarray(cost_arr)
    reduced = np.ma.array(array, copy=True)
    costs = np.asarray(reduced.data, dtype="float64")
    walkable = np.isfinite(costs)
    nodata = meta.get("nodata")
    if nodata is not None:
        walkable &= costs != float(nodata)
    if np.ma.is_masked(reduced):
        walkable &= ~np.ma.getmaskarray(reduced)

    corridor = input_line.buffer(max(float(buffer_distance), 0.0))
    if corridor.is_empty:
        return reduced
    mask = geometry_mask(
        [corridor],
        out_shape=costs.shape,
        transform=meta["transform"],
        invert=True,
        all_touched=True,
    )
    target = walkable & mask
    costs[target] = np.maximum(0.001, costs[target] * max(float(multiplier), 0.0))
    reduced.data[...] = costs.astype(np.asarray(reduced.data).dtype, copy=False)
    return reduced


def _find_astar_path(seedline_class,cost_arr, meta: dict, input_line: LineString) -> LineString | None:
    if input_line is None or input_line.is_empty or len(input_line.coords) < 2:
        return None

    costs, walkable = _prepare_costs(cost_arr, meta.get("nodata"))
    rows, cols = costs.shape
    transformer = rasterio.transform.AffineTransformer(meta["transform"])
    start_xy = input_line.coords[0]
    end_xy = input_line.coords[-1]
    start = _clamp_row_col(transformer.rowcol(start_xy[0], start_xy[1]), rows, cols)
    end = _clamp_row_col(transformer.rowcol(end_xy[0], end_xy[1]), rows, cols)
    if not walkable[start] or not walkable[end]:
        return None

    min_cost = float(costs[walkable].min()) if np.any(walkable) else 0.0
    tie_scores = np.full((rows, cols), math.inf, dtype="float64")
    g_scores = np.full((rows, cols), math.inf, dtype="float64")
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    closed: set[tuple[int, int]] = set()
    sequence = count()
    heap: list[tuple] = []

    g_scores[start] = 0.0
    tie_scores[start] = 0.0
    heapq.heappush(heap, _queue_entry(start, end, start, 0.0, 0.0, min_cost, next(sequence)))

    while heap:
        *_, current = heapq.heappop(heap)
        if current in closed:
            continue
        if current == end:
            return _path_to_linestring(_reconstruct_path(came_from, end), transformer, start_xy, end_xy)
        closed.add(current)

        for neighbor in _neighbors(current, rows, cols, walkable):
            if neighbor in closed:
                continue
            new_g = g_scores[current] + _edge_cost(costs, current, neighbor)
            new_tie = _line_bias_score(neighbor, start, end)
            current_g = g_scores[neighbor]
            current_tie = tie_scores[neighbor]
            improved = new_g < current_g - 1e-6
            tied_better = abs(new_g - current_g) <= 1e-6 and new_tie < current_tie
            if not improved and not tied_better:
                continue
            g_scores[neighbor] = new_g
            tie_scores[neighbor] = new_tie
            came_from[neighbor] = current
            heapq.heappush(
                heap,
                _queue_entry(
                    neighbor,
                    end,
                    start,
                    new_g,
                    new_tie,
                    min_cost,
                    next(sequence),
                ),
            )

    return None


def _prepare_costs(cost_arr, nodata) -> tuple[np.ndarray, np.ndarray]:
    array = np.ma.asarray(cost_arr)
    if array.ndim > 2:
        array = np.ma.squeeze(array, axis=0)
    costs = np.asarray(array.filled(np.nan), dtype="float64")
    walkable = np.isfinite(costs) & (costs > 0.0)
    if nodata is not None:
        walkable &= costs != float(nodata)
    return costs, walkable


def _smooth_path_in_astar_corridor(
    cost_arr, meta: dict, input_line: LineString, raw_path: LineString
) -> LineString | None:
    try:
        from skimage import graph as sk_graph
    except ImportError:
        return None

    costs, walkable = _prepare_costs(cost_arr, meta.get("nodata"))
    cell_size = _cell_size(meta["transform"])
    corridor_width = cell_size * SMOOTH_CORRIDOR_CELLS
    max_distance = cell_size * SMOOTH_MAX_DISTANCE_CELLS
    corridor = raw_path.buffer(corridor_width)
    if corridor.is_empty:
        return None

    mask = geometry_mask(
        [corridor],
        out_shape=costs.shape,
        transform=meta["transform"],
        invert=True,
        all_touched=True,
    )
    prepared_cost = costs.copy()
    prepared_cost[~walkable | ~mask] = np.inf

    transformer = rasterio.transform.AffineTransformer(meta["transform"])
    rows, cols = costs.shape
    start_xy = input_line.coords[0]
    end_xy = input_line.coords[-1]
    source = _clamp_row_col(transformer.rowcol(start_xy[0], start_xy[1]), rows, cols)
    destination = _clamp_row_col(transformer.rowcol(end_xy[0], end_xy[1]), rows, cols)
    if not np.isfinite(prepared_cost[source]) or not np.isfinite(prepared_cost[destination]):
        return None

    sampling = _raster_sampling(meta["transform"])
    mcp = sk_graph.MCP_Geometric(prepared_cost, sampling=sampling)
    accum_costs, _ = mcp.find_costs([source])
    if not np.isfinite(accum_costs[destination]):
        return None

    smooth_path = _trace_smoothed_path(
        accum_costs=accum_costs,
        source=source,
        destination=destination,
        transform=meta["transform"],
        start_xy=start_xy,
        end_xy=end_xy,
    )
    if smooth_path is None or smooth_path.is_empty:
        return None
    if not smooth_path.is_simple:
        return None
    if smooth_path.distance(raw_path) > max_distance:
        return None
    return smooth_path


def _cell_size(transform) -> float:
    return max(abs(float(transform.a)), abs(float(transform.e)))


def _raster_sampling(transform) -> tuple[float, float]:
    return (abs(float(transform.e)), abs(float(transform.a)))


def _trace_smoothed_path(
    *,
    accum_costs: np.ndarray,
    source: tuple[int, int],
    destination: tuple[int, int],
    transform,
    start_xy,
    end_xy,
) -> LineString | None:
    current = np.array(destination, dtype="float64")
    source_point = np.array(source, dtype="float64")
    points: list[tuple[float, float]] = [tuple(current)]
    step = 0.35
    max_steps = max(accum_costs.shape) * 40

    for _ in range(max_steps):
        if float(np.linalg.norm(current - source_point)) <= 0.6:
            points.append(tuple(source_point))
            break

        current_cost = _sample_cost(accum_costs, current)
        if not np.isfinite(current_cost):
            return None

        gradient = _sample_gradient(accum_costs, current)
        next_point: np.ndarray | None = None
        if np.all(np.isfinite(gradient)):
            magnitude = float(np.linalg.norm(gradient))
            if magnitude > 1e-6:
                candidate = _clip_point(
                    current - (gradient / magnitude) * step, accum_costs.shape
                )
                candidate_cost = _sample_cost(accum_costs, candidate)
                if np.isfinite(candidate_cost) and candidate_cost < current_cost - 1e-6:
                    next_point = candidate

        if next_point is None:
            fallback = _best_lower_neighbor(accum_costs, current)
            if fallback is None:
                break
            next_point = np.array(fallback, dtype="float64")

        if float(np.linalg.norm(next_point - current)) <= 1e-6:
            break

        current = next_point
        if float(np.linalg.norm(np.array(points[-1]) - current)) >= 0.15:
            points.append(tuple(current))

    if len(points) < 2:
        return None

    points.reverse()
    world_points = [_grid_point_to_world(transform, row, col) for row, col in points]
    world_points[0] = (start_xy[0], start_xy[1])
    world_points[-1] = (end_xy[0], end_xy[1])
    world_points = _collapse_redundant_points(world_points)
    if len(world_points) < 2:
        return None
    path = LineString(world_points)
    return path.simplify(_cell_size(transform) * 0.05, preserve_topology=False)


def _best_lower_neighbor(
    accum_costs: np.ndarray, current: np.ndarray
) -> tuple[int, int] | None:
    row = int(round(float(current[0])))
    col = int(round(float(current[1])))
    row = min(max(row, 0), accum_costs.shape[0] - 1)
    col = min(max(col, 0), accum_costs.shape[1] - 1)
    current_cost = float(accum_costs[row, col])
    best: tuple[int, int] | None = None
    best_cost = current_cost
    for row_offset in (-1, 0, 1):
        for col_offset in (-1, 0, 1):
            if row_offset == 0 and col_offset == 0:
                continue
            cand_row = row + row_offset
            cand_col = col + col_offset
            if (
                cand_row < 0
                or cand_col < 0
                or cand_row >= accum_costs.shape[0]
                or cand_col >= accum_costs.shape[1]
            ):
                continue
            candidate_cost = float(accum_costs[cand_row, cand_col])
            if np.isfinite(candidate_cost) and candidate_cost < best_cost - 1e-6:
                best = (cand_row, cand_col)
                best_cost = candidate_cost
    return best


def _sample_gradient(accum_costs: np.ndarray, point: np.ndarray) -> np.ndarray:
    step = 0.5
    row_grad = (
        _sample_cost(
            accum_costs, _clip_point(point + np.array([step, 0.0]), accum_costs.shape)
        )
        - _sample_cost(
            accum_costs, _clip_point(point - np.array([step, 0.0]), accum_costs.shape)
        )
    ) / (2.0 * step)
    col_grad = (
        _sample_cost(
            accum_costs, _clip_point(point + np.array([0.0, step]), accum_costs.shape)
        )
        - _sample_cost(
            accum_costs, _clip_point(point - np.array([0.0, step]), accum_costs.shape)
        )
    ) / (2.0 * step)
    return np.array([row_grad, col_grad], dtype="float64")


def _sample_cost(accum_costs: np.ndarray, point: np.ndarray) -> float:
    row = float(point[0])
    col = float(point[1])
    row = min(max(row, 0.0), accum_costs.shape[0] - 1.0)
    col = min(max(col, 0.0), accum_costs.shape[1] - 1.0)
    row0 = int(np.floor(row))
    col0 = int(np.floor(col))
    row1 = min(row0 + 1, accum_costs.shape[0] - 1)
    col1 = min(col0 + 1, accum_costs.shape[1] - 1)
    dr = row - row0
    dc = col - col0
    q00 = float(accum_costs[row0, col0])
    q01 = float(accum_costs[row0, col1])
    q10 = float(accum_costs[row1, col0])
    q11 = float(accum_costs[row1, col1])
    if not np.all(np.isfinite([q00, q01, q10, q11])):
        neighborhood = [value for value in (q00, q01, q10, q11) if np.isfinite(value)]
        return float(min(neighborhood)) if neighborhood else float("inf")
    top = q00 * (1.0 - dc) + q01 * dc
    bottom = q10 * (1.0 - dc) + q11 * dc
    return float(top * (1.0 - dr) + bottom * dr)


def _clip_point(point: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    return np.array(
        [
            min(max(float(point[0]), 0.0), shape[0] - 1.0),
            min(max(float(point[1]), 0.0), shape[1] - 1.0),
        ],
        dtype="float64",
    )


def _grid_point_to_world(transform, row: float, col: float) -> tuple[float, float]:
    x, y = transform * (col + 0.5, row + 0.5)
    return (float(x), float(y))


def _collapse_redundant_points(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    collapsed: list[tuple[float, float]] = []
    for point in points:
        if not collapsed or point != collapsed[-1]:
            collapsed.append(point)
    return collapsed


def _clamp_row_col(row_col: tuple[int, int], rows: int, cols: int) -> tuple[int, int]:
    return max(0, min(int(row_col[0]), rows - 1)), max(0, min(int(row_col[1]), cols - 1))


def _neighbors(
    node: tuple[int, int], rows: int, cols: int, walkable: np.ndarray
) -> Iterable[tuple[int, int]]:
    row, col = node
    for d_row, d_col in NEIGHBORS:
        neighbor = row + d_row, col + d_col
        if 0 <= neighbor[0] < rows and 0 <= neighbor[1] < cols and walkable[neighbor]:
            yield neighbor


def _edge_cost(costs: np.ndarray, current: tuple[int, int], neighbor: tuple[int, int]) -> float:
    base = (float(costs[current]) + float(costs[neighbor])) / 2.0
    return base * (SQRT2 if current[0] != neighbor[0] and current[1] != neighbor[1] else 1.0)


def _queue_entry(
    node: tuple[int, int],
    end: tuple[int, int],
    start: tuple[int, int],
    g_score: float,
    tie_score: float,
    min_cost: float,
    sequence: int,
) -> tuple:
    heuristic = _octile(node, end) * min_cost
    priority = g_score + heuristic + tie_score * ASTAR_LINE_BIAS
    return priority, g_score + heuristic, tie_score, heuristic, sequence, node


def _octile(a: tuple[int, int], b: tuple[int, int]) -> float:
    d_row = abs(a[0] - b[0])
    d_col = abs(a[1] - b[1])
    return d_row + d_col + (SQRT2 - 2.0) * min(d_row, d_col)


def _line_bias_score(node: tuple[int, int], start: tuple[int, int], end: tuple[int, int]) -> float:
    dx1 = node[1] - end[1]
    dy1 = node[0] - end[0]
    dx2 = start[1] - end[1]
    dy2 = start[0] - end[0]
    return abs(dx1 * dy2 - dx2 * dy1) / max(1.0, math.hypot(dx2, dy2))


def _reconstruct_path(
    came_from: dict[tuple[int, int], tuple[int, int] | None], end: tuple[int, int]
) -> list[tuple[int, int]]:
    path = [end]
    current = end
    while came_from[current] is not None:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def _path_to_linestring(
    path: list[tuple[int, int]], transformer, start_xy, end_xy
) -> LineString | None:
    if len(path) < 2:
        return None
    points = [transformer.xy(row, col) for row, col in path]
    points[0] = (start_xy[0], start_xy[1])
    points[-1] = (end_xy[0], end_xy[1])
    return LineString(points)
