"""Reusable A* path and corridor algorithms for centerline workflows."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from itertools import count
from typing import Iterable

import numpy as np
import rasterio
import skimage
from rasterio.features import geometry_mask
from scipy import ndimage
from shapely.geometry import LineString,Point


SQRT2 = math.sqrt(2.0)
ASTAR_LINE_BIAS = 0.001
DEFAULT_CORRIDOR_LINE_BIAS_WEIGHT = 0.1
DEFAULT_CORRIDOR_DISTANCE_PENALTY_WEIGHT = 0.2

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


@dataclass(frozen=True)
class AStarAccumulation:
    path: list[tuple[int, int]]
    best_cost: float
    g_scores: np.ndarray
    closed: np.ndarray

def alt_astar_accumulation_corridor_raster(
    cost_arr,
    meta: dict,
    lc_path: LineString,
    corridor_threshold: float,
    line_bias_weight: float = DEFAULT_CORRIDOR_LINE_BIAS_WEIGHT,
    distance_penalty_weight: float = DEFAULT_CORRIDOR_DISTANCE_PENALTY_WEIGHT,
) -> tuple[np.ma.MaskedArray, dict[str, object]]:
    if lc_path is None or lc_path.is_empty or len(lc_path.coords) < 2:
        raise RuntimeError("A* corridor requires a valid least-cost path")

    cost = _prepare_cost_surface(cost_arr, meta)
    rows, cols = cost.shape
    transform = meta["transform"]
    transformer = rasterio.transform.AffineTransformer(transform)
    segment_list = []
    try:
        target_spacing = 5.0
        min_tail = 2.0

        if lc_path.length <= target_spacing:
            multipoint_along_line = [
                Point(lc_path.coords[0]),
                Point(lc_path.coords[-1]),
            ]
        else:
            distances = np.arange(0, lc_path.length, target_spacing)

            tail = lc_path.length - distances[-1]

            if tail < min_tail:
                distances[-1] = lc_path.length
            else:
                distances = np.append(distances, lc_path.length)

            multipoint_along_line = [
                lc_path.interpolate(d)
                for d in distances
            ]
    except Exception as e:
        raise RuntimeError("1 Error: A* sampling along LCP fail")

    forward_list=[]
    reverse_list=[]
    total_forward_path=[]
    dist_to_path_list=[]
    total_score_=np.zeros(cost.shape, dtype=float)
    valid_total=np.zeros(cost.shape, dtype=bool)
    total_score_.fill(np.inf)
    list_forward_best_cost=[]
    forward_closed_list=[]
    reverse_closed_list=[]
    for i in range(0, len(multipoint_along_line) - 1):
        try:
            start_xy=multipoint_along_line[i].coords[0]
            end_xy=multipoint_along_line[i+1].coords[0]
            if start_xy == end_xy:
                continue
            source = _clamp_row_col(transformer.rowcol(*start_xy), rows, cols)
            destination = _clamp_row_col(transformer.rowcol(*end_xy), rows, cols)
            if source == destination:
                continue
            sampling = _raster_sampling(transform)
        except Exception as e:
            print (f"2 Error: {e}, skipping")
            continue
        try:
            forward = _astar_mcp_geometric_accumulation(
                cost,
                source,
                destination,
                sampling=sampling,
                line_bias_weight=line_bias_weight,
            )
            forward_list.append(forward)
            reverse =_astar_mcp_geometric_accumulation(
                cost,
                destination,
                source,
                sampling=sampling,
                line_bias_weight=line_bias_weight,
            )
            reverse_list.append(reverse)
        except Exception as e:
            print("3 Error: {e}, skipping")
            continue

        try:
            valid = forward.closed | reverse.closed
            local_data = forward.g_scores + reverse.g_scores - forward.best_cost
            total_forward_path = total_forward_path + forward.path
            valid_total[(valid)]=valid[(valid)]
            if source!=destination:
                astar_path = _path_to_linestring(
                        forward.path,
                        transformer,
                        start_xy=source,
                        end_xy=destination,
                    )
            else:
                continue

            dist_to_path_list.append(_distance_raster_to_line(astar_path, meta, cost.shape))
            valid_local = np.isfinite(local_data)
            total_score_[valid_local] = np.minimum(total_score_[valid_local],local_data[valid_local])
            valid_total |= valid
            total_score_[~np.isinf(local_data)] = local_data[~np.isinf(local_data)]
        except Exception as e:
            print(f"4 Error: {e}, skipping")
            continue

    total_score_[np.isinf(total_score_)] = 0.
    try:
        cleaned_arrays = [np.where(np.isinf(arr), np.nan, arr) for arr in dist_to_path_list]
        total_distance_to_path=np.fmin.reduce(cleaned_arrays)
    except Exception as e:
        raise RuntimeError(f"5 Error: A* corridor segments error: {e}.")

    if distance_penalty_weight > 0.0:
        total_score = total_score_ + total_distance_to_path * distance_penalty_weight
    else:
        total_score = total_score_ + total_distance_to_path

    score = np.ma.masked_invalid(total_score)
    buffer_pixels = max(
        1, min(10,int(round(1.0 / max(distance_penalty_weight, 0.1))))    )
    score = np.ma.array(score, mask=np.ma.getmaskarray(score) |
                                    ~skimage.morphology.dilation(valid_total,
                                skimage.morphology.disk(buffer_pixels)))

    inside = (~np.ma.getmaskarray(score)) & np.asarray(
        score.filled(np.inf) < corridor_threshold, dtype=bool
    )
    corridor = np.ma.where(inside, 0.0, 1.0)
    corridor = np.ma.array(corridor, mask=np.ma.getmaskarray(score))
    for forward,reverse in zip(forward_list,reverse_list):
        list_forward_best_cost.append(forward.best_cost)
        forward_closed_list.append(forward.closed)
        reverse_closed_list.append(reverse.closed)
    total_forward_closed=np.any(np.array(forward_closed_list), axis=0)
    total_reverse_closed = np.any(np.array(reverse_closed_list), axis=0)

    details = {
        "corridor_threshold": float(corridor_threshold),
        "astar_line_bias_weight": float(line_bias_weight),
        "astar_distance_penalty_weight": float(distance_penalty_weight),
        "astar_best_cost": float( min(list_forward_best_cost)),
        "inside_cells": int(np.count_nonzero(inside)),
        "inside_area": float(np.count_nonzero(inside) * _cell_area(transform)),
        "forward_closed_cells": int(np.count_nonzero(total_forward_closed)),
        "reverse_closed_cells": int(np.count_nonzero(total_reverse_closed)),
        "both_closed_cells": int(np.count_nonzero(valid_total)),
        "astar_path_vertices": int(len(total_forward_path)),
    }
    return corridor, details


def find_least_cost_path_astar_closest_line(cost_arr, meta: dict, input_line: LineString) -> LineString | None:
    """Find an 8-neighbor A* LCP, tie-broken toward the seed-line direction."""

    if input_line is None or input_line.is_empty or len(input_line.coords) < 2:
        return None

    costs, walkable = _prepare_lcp_costs(cost_arr, meta.get("nodata"))
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
    heapq.heappush(heap, _lcp_queue_entry(start, end, start, 0.0, 0.0, min_cost, next(sequence)))

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
            new_g = g_scores[current] + _lcp_edge_cost(costs, current, neighbor)
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
                _lcp_queue_entry(neighbor, end, start, new_g, new_tie, min_cost, next(sequence)),
            )

    return None


def astar_accumulation_corridor_raster(
    cost_arr,
    meta: dict,
    lc_path: LineString,
    *,
    corridor_threshold: float,
    line_bias_weight: float = DEFAULT_CORRIDOR_LINE_BIAS_WEIGHT,
    distance_penalty_weight: float = DEFAULT_CORRIDOR_DISTANCE_PENALTY_WEIGHT,
) -> tuple[np.ma.MaskedArray, dict[str, object]]:
    """Build an A* accumulation corridor raster using BERA's 0-inside/1-outside convention."""

    if lc_path is None or lc_path.is_empty or len(lc_path.coords) < 2:
        raise RuntimeError("A* corridor requires a valid least-cost path")

    cost = _prepare_corridor_cost_surface(cost_arr, meta)
    rows, cols = cost.shape
    transform = meta["transform"]
    transformer = rasterio.transform.AffineTransformer(transform)
    start_xy = lc_path.coords[0]
    end_xy = lc_path.coords[-1]
    source = _clamp_row_col(transformer.rowcol(*start_xy), rows, cols)
    destination = _clamp_row_col(transformer.rowcol(*end_xy), rows, cols)
    sampling = _raster_sampling(transform)

    forward = _astar_mcp_geometric_accumulation(
        cost,
        source,
        destination,
        sampling=sampling,
        line_bias_weight=line_bias_weight,
    )
    reverse = _astar_mcp_geometric_accumulation(
        cost,
        destination,
        source,
        sampling=sampling,
        line_bias_weight=line_bias_weight,
    )

    valid = forward.closed & reverse.closed
    score_data = forward.g_scores + reverse.g_scores - forward.best_cost
    if distance_penalty_weight > 0.0:
        astar_path = _path_to_linestring(forward.path, transformer, start_xy, end_xy)
        distance_to_path = _distance_raster_to_line(astar_path, meta, cost.shape)
        score_data = score_data + distance_to_path * distance_penalty_weight

    score = np.ma.masked_invalid(score_data)
    score = np.ma.array(score, mask=np.ma.getmaskarray(score) | ~valid)
    inside = (~np.ma.getmaskarray(score)) & np.asarray(score.filled(np.inf) < corridor_threshold, dtype=bool)
    corridor = np.ma.where(inside, 0.0, 1.0)
    corridor = np.ma.array(corridor, mask=np.ma.getmaskarray(score))

    details = {
        "corridor_threshold": float(corridor_threshold),
        "astar_line_bias_weight": float(line_bias_weight),
        "astar_distance_penalty_weight": float(distance_penalty_weight),
        "astar_best_cost": float(forward.best_cost),
        "inside_cells": int(np.count_nonzero(inside)),
        "inside_area": float(np.count_nonzero(inside) * _cell_area(transform)),
        "forward_closed_cells": int(np.count_nonzero(forward.closed)),
        "reverse_closed_cells": int(np.count_nonzero(reverse.closed)),
        "both_closed_cells": int(np.count_nonzero(valid)),
        "astar_path_vertices": int(len(forward.path)),
    }
    return corridor, details


def _prepare_lcp_costs(cost_arr, nodata) -> tuple[np.ndarray, np.ndarray]:
    array = np.ma.asarray(cost_arr)
    if array.ndim > 2:
        array = np.ma.squeeze(array, axis=0)
    costs = np.asarray(array.filled(np.nan), dtype="float64")
    walkable = np.isfinite(costs) & (costs > 0.0)
    if nodata is not None:
        walkable &= costs != float(nodata)
    return costs, walkable


def _prepare_corridor_cost_surface(cost_arr, meta: dict) -> np.ndarray:
    arr = np.ma.asarray(cost_arr)
    if arr.ndim > 2:
        arr = np.ma.squeeze(arr, axis=0)
    cost = np.asarray(arr.filled(np.inf), dtype="float64")
    nodata = meta.get("nodata")
    if nodata is not None:
        cost[cost == float(nodata)] = np.inf
    cost[~np.isfinite(cost)] = np.inf
    cost[cost <= 0.0] = np.inf
    return cost


def _astar_mcp_geometric_accumulation(
    cost: np.ndarray,
    source: tuple[int, int],
    destination: tuple[int, int],
    *,
    sampling: tuple[float, float],
    line_bias_weight: float,
) -> AStarAccumulation:
    if not np.isfinite(cost[source]) or not np.isfinite(cost[destination]):
        raise RuntimeError("A* source or destination is not traversable")

    rows, cols = cost.shape
    walkable = np.isfinite(cost) & (cost > 0.0)
    min_cost = float(cost[walkable].min()) if np.any(walkable) else 0.0
    g_scores = np.full(cost.shape, math.inf, dtype="float64")
    tie_scores = np.full(cost.shape, math.inf, dtype="float64")
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {source: None}
    closed_nodes: set[tuple[int, int]] = set()
    closed = np.zeros(cost.shape, dtype=bool)
    sequence = count()
    heap: list[tuple[float, float, float, int, tuple[int, int]]] = []

    g_scores[source] = 0.0
    tie_scores[source] = 0.0
    destination_path = None
    destination_cost = None
    heapq.heappush(
        heap,
        _corridor_queue_entry(
            source,
            destination,
            source,
            0.0,
            0.0,
            min_cost,
            sampling,
            line_bias_weight,
            next(sequence),
        ),
    )

    while heap:
        *_, current = heapq.heappop(heap)
        if current in closed_nodes:
            continue
        if current == destination and destination_path is None:
            destination_path = _reconstruct_path(came_from, destination)
            destination_cost = float(g_scores[destination])
        closed_nodes.add(current)
        closed[current] = True

        for neighbor in _neighbors(current, rows, cols, walkable):
            if neighbor in closed_nodes:
                continue
            new_g = g_scores[current] + _geometric_edge_cost(cost, current, neighbor, sampling)
            new_tie = _line_bias_score(neighbor, source, destination)
            improved = new_g < g_scores[neighbor] - 1e-9
            tied_better = abs(new_g - g_scores[neighbor]) <= 1e-9 and new_tie < tie_scores[neighbor]
            if not improved and not tied_better:
                continue
            g_scores[neighbor] = new_g
            tie_scores[neighbor] = new_tie
            came_from[neighbor] = current
            heapq.heappush(
                heap,
                _corridor_queue_entry(
                    neighbor,
                    destination,
                    source,
                    new_g,
                    new_tie,
                    min_cost,
                    sampling,
                    line_bias_weight,
                    next(sequence),
                ),
            )

    if destination_path is None or destination_cost is None:
        raise RuntimeError("A* path did not reach destination")

    return AStarAccumulation(
        path=destination_path,
        best_cost=destination_cost,
        g_scores=g_scores,
        closed=closed,
    )


def _neighbors(node: tuple[int, int], rows: int, cols: int, walkable: np.ndarray) -> Iterable[tuple[int, int]]:
    row, col = node
    for d_row, d_col in NEIGHBORS:
        neighbor = row + d_row, col + d_col
        if 0 <= neighbor[0] < rows and 0 <= neighbor[1] < cols and walkable[neighbor]:
            yield neighbor


def _lcp_edge_cost(costs: np.ndarray, current: tuple[int, int], neighbor: tuple[int, int]) -> float:
    base = (float(costs[current]) + float(costs[neighbor])) / 2.0
    return base * (SQRT2 if current[0] != neighbor[0] and current[1] != neighbor[1] else 1.0)


def _geometric_edge_cost(
    cost: np.ndarray,
    current: tuple[int, int],
    neighbor: tuple[int, int],
    sampling: tuple[float, float],
) -> float:
    d_row = neighbor[0] - current[0]
    d_col = neighbor[1] - current[1]
    offset_length = math.hypot(d_row * sampling[0], d_col * sampling[1])
    return offset_length * 0.5 * (float(cost[current]) + float(cost[neighbor]))


def _lcp_queue_entry(
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


def _corridor_queue_entry(
    node: tuple[int, int],
    destination: tuple[int, int],
    source: tuple[int, int],
    g_score: float,
    tie_score: float,
    min_cost: float,
    sampling: tuple[float, float],
    line_bias_weight: float,
    sequence: int,
) -> tuple[float, float, float, int, tuple[int, int]]:
    heuristic = _euclidean_grid_distance(node, destination, sampling) * min_cost
    priority = g_score + heuristic + tie_score * line_bias_weight
    return priority, heuristic, _line_bias_score(node, source, destination), sequence, node


def _octile(a: tuple[int, int], b: tuple[int, int]) -> float:
    d_row = abs(a[0] - b[0])
    d_col = abs(a[1] - b[1])
    return d_row + d_col + (SQRT2 - 2.0) * min(d_row, d_col)


def _euclidean_grid_distance(a: tuple[int, int], b: tuple[int, int], sampling: tuple[float, float]) -> float:
    return math.hypot((a[0] - b[0]) * sampling[0], (a[1] - b[1]) * sampling[1])


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


def _path_to_linestring(path: list[tuple[int, int]], transformer, start_xy, end_xy) -> LineString | None:
    if len(path) < 2:
        return None
    points = [transformer.xy(row, col) for row, col in path]
    points[0] = (start_xy[0], start_xy[1])
    points[-1] = (end_xy[0], end_xy[1])
    return LineString(points)


def _distance_raster_to_line(line: LineString, meta: dict, shape: tuple[int, int]) -> np.ndarray:
    transform = meta["transform"]
    cell_size = max(abs(float(transform.a)), abs(float(transform.e)))
    path_mask = geometry_mask(
        [line.buffer(cell_size * 0.5)],
        out_shape=shape,
        transform=transform,
        invert=True,
        all_touched=True,
    )
    return ndimage.distance_transform_edt(~path_mask, sampling=_raster_sampling(transform))


def _raster_sampling(transform) -> tuple[float, float]:
    return (abs(float(transform.e)), abs(float(transform.a)))


def _cell_area(transform) -> float:
    return abs(float(transform.a) * float(transform.e))


def _clamp_row_col(row_col: tuple[int, int], rows: int, cols: int) -> tuple[int, int]:
    return max(0, min(int(row_col[0]), rows - 1)), max(0, min(int(row_col[1]), cols - 1))


def _prepare_cost_surface(cost_arr, meta: dict) -> np.ndarray:
    try:
        arr = np.ma.asarray(cost_arr)
        if arr.ndim > 2:
            arr = np.ma.squeeze(arr, axis=0)
        cost = np.asarray(arr.filled(np.inf), dtype="float32")
        nodata = meta.get("nodata")
        if nodata is not None:
            cost[cost == float(nodata)] = np.inf
        cost[~np.isfinite(cost)] = np.inf
        cost[cost <= 0.0] = np.inf
        return cost
    except Exception as e:
        print(f"Failed to prepare cost surface: {e}")
        return cost_arr

def astar_accumulation_corridor_raster_v2(
    cost_arr,
    meta: dict,
    lc_path: LineString,
    *,
    corridor_threshold: float,
    line_bias_weight: float = DEFAULT_CORRIDOR_LINE_BIAS_WEIGHT,
    distance_penalty_weight: float = DEFAULT_CORRIDOR_DISTANCE_PENALTY_WEIGHT,
) -> tuple[np.ma.MaskedArray, dict[str, object]]:
    """Build an A* accumulation corridor raster using BERA's 0-inside/1-outside convention."""

    if lc_path is None or lc_path.is_empty or len(lc_path.coords) < 2:
        raise RuntimeError("A* corridor requires a valid least-cost path")

    cost = _prepare_corridor_cost_surface(cost_arr, meta)
    rows, cols = cost.shape
    transform = meta["transform"]
    transformer = rasterio.transform.AffineTransformer(transform)
    start_xy = lc_path.coords[0]
    end_xy = lc_path.coords[-1]
    source = _clamp_row_col(transformer.rowcol(*start_xy), rows, cols)
    destination = _clamp_row_col(transformer.rowcol(*end_xy), rows, cols)
    sampling = _raster_sampling(transform)

    forward = _astar_mcp_geometric_accumulation(
        cost,
        source,
        destination,
        sampling=sampling,
        line_bias_weight=line_bias_weight,
    )
    reverse = _astar_mcp_geometric_accumulation(
        cost,
        destination,
        source,
        sampling=sampling,
        line_bias_weight=line_bias_weight,
    )

    valid = forward.closed | reverse.closed
    score_data = forward.g_scores + reverse.g_scores - forward.best_cost
    if distance_penalty_weight > 0.0:
        astar_path = _path_to_linestring(forward.path, transformer, start_xy, end_xy)
        distance_to_path = _distance_raster_to_line(astar_path, meta, cost.shape)
        score_data = score_data + distance_to_path * distance_penalty_weight

    score = np.ma.array(score_data, mask=np.logical_and(np.ma.masked_invalid(score_data).mask , ~valid))
    inside = (~np.ma.getmaskarray(score)) & np.asarray(score < corridor_threshold, dtype=bool)
    corridor = np.ma.where(inside, 0.0, 1.0)
    corridor = np.ma.array(corridor, mask=np.ma.getmaskarray(score))

    details = {
        "corridor_threshold": float(corridor_threshold),
        "astar_line_bias_weight": float(line_bias_weight),
        "astar_distance_penalty_weight": float(distance_penalty_weight),
        "astar_best_cost": float(forward.best_cost),
        "inside_cells": int(np.count_nonzero(inside)),
        "inside_area": float(np.count_nonzero(inside) * _cell_area(transform)),
        "forward_closed_cells": int(np.count_nonzero(forward.closed)),
        "reverse_closed_cells": int(np.count_nonzero(reverse.closed)),
        "both_closed_cells": int(np.count_nonzero(valid)),
        "astar_path_vertices": int(len(forward.path)),
    }
    return corridor, details



