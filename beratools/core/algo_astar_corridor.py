from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from itertools import count
from typing import Iterable

import numpy as np
import rasterio,skimage
from rasterio.features import geometry_mask
from scipy import ndimage
from shapely.geometry import LineString, Point



DEFAULT_LINE_BIAS_WEIGHT = 0.1
DEFAULT_DISTANCE_PENALTY_WEIGHT = 0.5

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
    *,
    corridor_threshold: float,
    line_bias_weight: float = DEFAULT_LINE_BIAS_WEIGHT,
    distance_penalty_weight: float = DEFAULT_DISTANCE_PENALTY_WEIGHT,
) -> tuple[np.ma.MaskedArray, dict[str, object]]:
    if lc_path is None or lc_path.is_empty or len(lc_path.coords) < 2:
        raise RuntimeError("A* corridor requires a valid least-cost path")

    cost = _prepare_cost_surface(cost_arr, meta)
    rows, cols = cost.shape
    transform = meta["transform"]
    transformer = rasterio.transform.AffineTransformer(transform)
    segment_list = []
    try:
        for coord in lc_path.coords:
            segment_list.append(coord)
        if lc_path.length >= 10:
            distance_delta = 5
        else:
            distance_delta=2
        distances = np.arange(0, lc_path.length, distance_delta)
        multipoint_along_line = [lc_path.interpolate(distance) for distance in distances]
        multipoint_along_line.append(Point(segment_list[-1]))
    except Exception as e:
        raise RuntimeError("1 A* corridor requires a valid least-cost path")

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

            valid = forward.closed | reverse.closed
            local_data = forward.g_scores + reverse.g_scores - forward.best_cost
            total_forward_path = total_forward_path + forward.path
            valid_total[(valid)]=valid[(valid)]
            astar_path = _path_to_linestring(
                    forward.path,
                    transformer,
                    start_xy=source,
                    end_xy=destination,
                )
            dist_to_path_list.append(_distance_raster_to_line(astar_path, meta, cost.shape))
            total_score_[~np.isinf(local_data)] = local_data[~np.isinf(local_data)]
        except Exception as e:
            print("3 A* corridor requires a valid least-cost path")
            continue

    total_score_[np.isinf(total_score_)] = 0.
    cleaned_arrays = [np.where(np.isinf(arr), np.nan, arr) for arr in dist_to_path_list]
    total_distance_to_path=np.fmin.reduce(cleaned_arrays)

    if distance_penalty_weight > 0.0:
        total_score = total_score_ + total_distance_to_path * distance_penalty_weight
    else:
        total_score = total_score_ + total_distance_to_path

    score = np.ma.masked_invalid(total_score)

    score = np.ma.array(score, mask=np.ma.getmaskarray(score) | ~skimage.morphology.dilation(valid_total, skimage.morphology.disk(int(1/distance_penalty_weight))))
    # score = np.ma.array(score, mask=np.ma.getmaskarray(score) | ~valid_total)

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

def _prepare_cost_surface(cost_arr, meta: dict) -> np.ndarray:
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

    min_costs = {source: 0.0}
    parent_map = {source: None}

    g_scores[source] = 0.0
    tie_scores[source] = 0.0
    heapq.heappush(
        heap,
        _queue_entry(
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
        current_cost,_,_,_, current = heapq.heappop(heap)
        if current in closed_nodes:
            continue

        if current == destination:
            closed_nodes.add(current)
            closed[current] = True
            return AStarAccumulation(
                path=_reconstruct_path(came_from, destination),
                best_cost=float(g_scores[destination]),
                g_scores=g_scores,
                closed=closed,
            )
        closed_nodes.add(current)
        closed[current] = True

        for neighbor in _neighbors(current, rows, cols, walkable):
            if neighbor in closed_nodes:
                continue
            new_g = g_scores[current] + _geometric_edge_cost(
                cost, current, neighbor, sampling
            )
            new_tie = _line_bias_score(neighbor, source, destination)
            improved = new_g < g_scores[neighbor] - 1e-9
            tied_better = (
                abs(new_g - g_scores[neighbor]) <= 1e-9
                and new_tie < tie_scores[neighbor]
            )
            if not improved and not tied_better:
                continue
            #  Relaxation step
            if new_g < min_costs.get(neighbor, float('inf')):
                min_costs[neighbor] = new_g
                parent_map[neighbor] = current

            g_scores[neighbor] = new_g
            tie_scores[neighbor] = new_tie
            came_from[neighbor] = current
            heapq.heappush(
                heap,
                _queue_entry(
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

    raise RuntimeError("A* MCP_Geometric path did not reach destination")


def _queue_entry(
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


def _neighbors(
    node: tuple[int, int], rows: int, cols: int, walkable: np.ndarray
) -> Iterable[tuple[int, int]]:
    row, col = node
    for dr, dc in NEIGHBORS:
        candidate = row + dr, col + dc
        if 0 <= candidate[0] < rows and 0 <= candidate[1] < cols and walkable[candidate]:
            yield candidate


def _geometric_edge_cost(
    cost: np.ndarray,
    current: tuple[int, int],
    neighbor: tuple[int, int],
    sampling: tuple[float, float],
) -> float:
    dr = neighbor[0] - current[0]
    dc = neighbor[1] - current[1]
    offset_length = math.hypot(dr * sampling[0], dc * sampling[1])
    return offset_length * 0.5 * (float(cost[current]) + float(cost[neighbor]))


def _euclidean_grid_distance(
    a: tuple[int, int], b: tuple[int, int], sampling: tuple[float, float]
) -> float:
    return math.hypot((a[0] - b[0]) * sampling[0], (a[1] - b[1]) * sampling[1])


def _line_bias_score(
    node: tuple[int, int], source: tuple[int, int], destination: tuple[int, int]
) -> float:
    dx1 = node[1] - destination[1]
    dy1 = node[0] - destination[0]
    dx2 = source[1] - destination[1]
    dy2 = source[0] - destination[0]
    return abs(dx1 * dy2 - dx2 * dy1) / max(1.0, math.hypot(dx2, dy2))


def _reconstruct_path(
    came_from: dict[tuple[int, int], tuple[int, int] | None],
    destination: tuple[int, int],
) -> list[tuple[int, int]]:
    path = [destination]
    current = destination
    while came_from[current] is not None:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def _path_to_linestring(
    path: list[tuple[int, int]],
    transformer,
    *,
    start_xy: tuple[float, float],
    end_xy: tuple[float, float],
) -> LineString:
    points = [transformer.xy(row, col) for row, col in path]
    # points[0] = start_xy
    # points[-1] = end_xy
    return LineString(points)


def _distance_raster_to_line(
    line: LineString, meta: dict, shape: tuple[int, int]
) -> np.ndarray:
    transform = meta["transform"]
    cell_size = max(abs(float(transform.a)), abs(float(transform.e)))
    path_mask = geometry_mask(
        [line.buffer(max(cell_size*0.5,5) )],
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
    return max(0, min(int(row_col[0]), rows - 1)), max(
        0, min(int(row_col[1]), cols - 1)
    )
