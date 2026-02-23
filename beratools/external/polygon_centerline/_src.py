from itertools import combinations
import logging
import networkx as nx
from networkx.exception import NetworkXNoPath
import numpy as np
import operator
from scipy.spatial import Voronoi
from scipy.ndimage import gaussian_filter1d
from shapely.geometry import LineString, MultiLineString, Point, MultiPoint

from .exceptions import CenterlineError
from shapely import STRtree

import networkit as nk

logger = logging.getLogger(__name__)

ANGLE_PENALTY_WEIGHT = 0.02
GUIDED_PATH_CANDIDATE_LIMIT = 40


def filter_nodes(geom, graph, vor, end_nodes):
    if not geom:
        return end_nodes

    pts = [Point(vor.vertices[i]) for i in end_nodes]  # points in graph
    idx = STRtree(pts)
    indices = idx.query(geom)

    idx_final = []
    for i in indices:
        if geom.contains(pts[i]):
            idx_final.append(end_nodes[i])

    return idx_final


def get_centerline(
    geom,
    segmentize_maxlen=0.5,
    max_points=3000,
    simplification=0.05,
    smooth_sigma=5,
    max_paths=5,
    src_geom=None,
    dst_geom=None,
    guided_strategy="virtual",
    endpoint_mode="strict",
    snap_tolerance=None,
    endpoint_candidate_k=5,
    max_terminal_angle=40,
    alpha=0.5,
):
    """
    Return centerline from geometry.

    Parameters:
    -----------
    geom : shapely Polygon or MultiPolygon
    segmentize_maxlen : Maximum segment length for polygon borders.
        (default: 0.5)
    max_points : Number of points per geometry allowed before simplifying.
        (default: 3000)
    simplification : Simplification threshold.
        (default: 0.05)
    smooth_sigma : Smoothness of the output centerlines.
        (default: 5)
    max_paths : Number of longest paths used to create the centerlines.
        (default: 5)
    src_geom, dst_geom : Optional endpoint guidance geometries.
    guided_strategy : "candidate", "virtual", or "main_route".
    endpoint_mode : "strict" or "soft".
    snap_tolerance : Maximum endpoint snap distance for soft mode.
    endpoint_candidate_k : Number of endpoint graph candidates.
    max_terminal_angle : Maximum allowed terminal deflection in degrees.
    alpha : Exponent for medial-aware edge weighting.

    Returns:
    --------
    geometry : LineString or MultiLineString

    Raises:
    -------
    CenterlineError : if centerline cannot be extracted from Polygon
    TypeError : if input geometry is not Polygon or MultiPolygon

    """
    logger.debug("geometry type %s", geom.geom_type)

    valid_endpoint_modes = {"strict", "soft"}
    if endpoint_mode not in valid_endpoint_modes:
        raise ValueError("endpoint_mode must be one of %s" % sorted(valid_endpoint_modes))

    valid_guided_strategies = {"candidate", "virtual", "main_route"}
    if guided_strategy not in valid_guided_strategies:
        raise ValueError("guided_strategy must be one of %s" % sorted(valid_guided_strategies))

    if geom.geom_type == "Polygon":
        # segmentized Polygon outline
        outline = _segmentize(geom.exterior, segmentize_maxlen)
        logger.debug("outline: %s", outline)

        # simplify segmentized geometry if necessary and get points
        outline_points = outline.coords
        simplification_updated = simplification
        while len(outline_points) > max_points:
            # if geometry is too large, apply simplification until geometry
            # is simplified enough (indicated by the "max_points" value)
            simplification_updated += simplification
            outline_points = outline.simplify(simplification_updated).coords
        logger.debug("simplification used: %s", simplification_updated)
        logger.debug("simplified points: %s", MultiPoint(outline_points))

        # calculate Voronoi diagram and convert to graph but only use points
        # from within the original polygon
        vor = Voronoi(outline_points)
        graph = _graph_from_voronoi(vor, geom)
        logger.debug("voronoi diagram: %s", _multilinestring_from_voronoi(vor, geom))

        # determine longest path between all end nodes from graph
        end_nodes = _get_end_nodes(graph)
        if len(end_nodes) < 2:
            logger.debug("Polygon has too few points")
            raise CenterlineError("Polygon has too few points")
        logger.debug("get longest path from %s end nodes", len(end_nodes))

        centerline = None
        src_point = _as_endpoint_point(src_geom)
        dst_point = _as_endpoint_point(dst_geom)
        if snap_tolerance is None:
            snap_tolerance = 2 * segmentize_maxlen

        guided_attempted = False
        if guided_strategy in {"candidate", "virtual"} and src_point is not None and dst_point is not None:
            guided_attempted = True
            src_nodes = filter_nodes(src_geom, graph, vor, end_nodes)
            dst_nodes = filter_nodes(dst_geom, graph, vor, end_nodes)
            src_candidates = _pick_endpoint_candidates(
                src_point,
                graph,
                vor,
                geom,
                endpoint_candidate_k,
                preferred_nodes=src_nodes,
            )
            dst_candidates = _pick_endpoint_candidates(
                dst_point,
                graph,
                vor,
                geom,
                endpoint_candidate_k,
                preferred_nodes=dst_nodes,
            )

            if guided_strategy == "virtual":
                guided = _get_guided_path_virtual(
                    graph,
                    vor,
                    geom,
                    src_point,
                    dst_point,
                    src_candidates,
                    dst_candidates,
                    max_terminal_angle,
                    alpha,
                    enforce_angle=(endpoint_mode == "strict"),
                )
            else:
                guided = _get_guided_path(
                    graph,
                    vor,
                    geom,
                    src_point,
                    dst_point,
                    src_candidates,
                    dst_candidates,
                    max_terminal_angle,
                    alpha,
                    enforce_angle=(endpoint_mode == "strict"),
                )

            if guided is None and endpoint_mode == "strict":
                logger.debug("strict endpoint guidance exceeded angle guard, retrying without guard")
                if guided_strategy == "virtual":
                    guided = _get_guided_path_virtual(
                        graph,
                        vor,
                        geom,
                        src_point,
                        dst_point,
                        src_candidates,
                        dst_candidates,
                        max_terminal_angle,
                        alpha,
                        enforce_angle=False,
                    )
                else:
                    guided = _get_guided_path(
                        graph,
                        vor,
                        geom,
                        src_point,
                        dst_point,
                        src_candidates,
                        dst_candidates,
                        max_terminal_angle,
                        alpha,
                        enforce_angle=False,
                    )

            if guided is not None:
                path_nodes = guided["path"]
                if endpoint_mode == "strict":
                    centerline = _line_from_nodes_with_anchors(path_nodes, vor, src_point, dst_point)
                    centerline = _smooth_linestring_fixed_ends(centerline, smooth_sigma)
                else:
                    centerline = LineString(vor.vertices[path_nodes])
                    centerline = _smooth_linestring(centerline, smooth_sigma)
                    centerline = _soft_snap_centerline_to_endpoints(
                        centerline, src_point, dst_point, snap_tolerance
                    )

        if centerline is None and guided_attempted and endpoint_mode == "strict":
            raise CenterlineError("endpoint-guided extraction failed for provided endpoints")

        if centerline is None and guided_attempted:
            logger.warning(
                "endpoint-guided extraction failed in soft mode; "
                "falling back to main-route longest-path extraction"
            )

        if centerline is None:
            graph_nk = _graph_from_voronoi_nk(vor, geom)
            longest_paths = _get_main_route_longest_paths(graph_nk)
            if not longest_paths:
                logger.debug("no paths found between end nodes")
                raise CenterlineError("no paths found between end nodes")
            if logger.getEffectiveLevel() <= 10:
                logger.debug("longest paths:")
                for path in longest_paths:
                    logger.debug(LineString(vor.vertices[path]))

            centerline = _smooth_linestring(
                LineString(vor.vertices[_get_least_curved_path(longest_paths, vor.vertices)]),
                smooth_sigma,
            )
        logger.debug("centerline: %s", centerline)
        logger.debug("return linestring")
        return centerline

    elif geom.geom_type == "MultiPolygon":
        logger.debug("MultiPolygon found with %s sub-geometries", len(geom.geoms))
        # get centerline for each part Polygon and combine into MultiLineString
        sub_centerlines = []
        for subgeom in geom.geoms:
            try:
                sub_centerline = get_centerline(
                    subgeom,
                    segmentize_maxlen,
                    max_points,
                    simplification,
                    smooth_sigma,
                    max_paths,
                    None,
                    None,
                    guided_strategy,
                    endpoint_mode,
                    snap_tolerance,
                    endpoint_candidate_k,
                    max_terminal_angle,
                    alpha,
                )
                sub_centerlines.append(sub_centerline)
            except CenterlineError as e:
                logger.debug("subgeometry error: %s", e)
        # for MultPolygon, only raise CenterlineError if all subgeometries fail
        if sub_centerlines:
            return MultiLineString(sub_centerlines)
        else:
            raise CenterlineError("all subgeometries failed")

    else:
        raise TypeError("Geometry type must be Polygon or MultiPolygon, not %s" % geom.geom_type)


# helper functions #
####################


def _segmentize(geom, max_len):
    """Interpolate points on segments if they exceed maximum length."""
    points = []
    for previous, current in zip(geom.coords, geom.coords[1:]):
        line_segment = LineString([previous, current])
        # add points on line segment if necessary
        points.extend(
            [
                line_segment.interpolate(max_len * i).coords[0]
                for i in range(int(line_segment.length / max_len))
            ]
        )
        # finally, add end point
        points.append(current)
    return LineString(points)


def _smooth_linestring(linestring, smooth_sigma):
    """Use a gauss filter to smooth out the LineString coordinates."""
    return LineString(
        zip(
            np.array(gaussian_filter1d(linestring.xy[0], smooth_sigma)),
            np.array(gaussian_filter1d(linestring.xy[1], smooth_sigma)),
        )
    )


def _smooth_linestring_fixed_ends(linestring, smooth_sigma):
    """Smooth interior vertices but keep first/last coordinates fixed."""
    coords = list(linestring.coords)
    if len(coords) < 3:
        return linestring
    smoothed = _smooth_linestring(linestring, smooth_sigma)
    smoothed_coords = list(smoothed.coords)
    smoothed_coords[0] = coords[0]
    smoothed_coords[-1] = coords[-1]
    return LineString(smoothed_coords)


def _as_endpoint_point(geom):
    """Convert endpoint guidance geometry to a representative point."""
    if geom is None:
        return None
    if geom.geom_type == "Point":
        return geom
    if hasattr(geom, "representative_point"):
        return geom.representative_point()
    return None


def _pick_endpoint_candidates(point, graph, vor, geometry, candidate_k, preferred_nodes=None):
    """Pick endpoint candidate graph nodes with distance/clearance score."""
    available_nodes = list(graph.nodes())
    if not available_nodes:
        return []

    preferred_nodes = preferred_nodes or []
    filtered_preferred = [node for node in preferred_nodes if node in graph]
    scored = []
    for node in available_nodes:
        node_pt = Point(vor.vertices[node])
        dist = point.distance(node_pt)
        boundary_dist = geometry.boundary.distance(node_pt)
        score = dist + (0.2 / max(boundary_dist, 1e-6))
        if node in filtered_preferred:
            score *= 0.6
        scored.append((score, node))
    scored.sort(key=operator.itemgetter(0, 1))

    chosen = []
    seen = set()
    for node in filtered_preferred:
        if node not in seen:
            chosen.append(node)
            seen.add(node)
        if len(chosen) >= candidate_k:
            return chosen

    for _, node in scored:
        if node in seen:
            continue
        chosen.append(node)
        seen.add(node)
        if len(chosen) >= candidate_k:
            break
    return chosen


def _build_medial_weighted_graph(graph, vor, geometry, alpha):
    """Build graph with edge costs biased to medial regions."""
    weighted = nx.Graph()
    for u, v in graph.edges():
        p1 = Point(vor.vertices[u])
        p2 = Point(vor.vertices[v])
        length = p1.distance(p2)
        clearance = min(geometry.boundary.distance(p1), geometry.boundary.distance(p2))
        weight = length / max(clearance, 1e-6) ** alpha
        weighted.add_edge(u, v, weight=weight)
    return weighted


def _build_medial_weighted_graph_nk(graph, vor, geometry, alpha):
    """Build NetworKit graph with edge costs biased to medial regions."""
    nodes = list(graph.nodes())
    if not nodes:
        return nk.graph.Graph(0, weighted=True)

    max_node_id = max(nodes)
    weighted_nk = nk.graph.Graph(max_node_id + 1, weighted=True)
    for u, v in graph.edges():
        p1 = Point(vor.vertices[u])
        p2 = Point(vor.vertices[v])
        length = p1.distance(p2)
        clearance = min(geometry.boundary.distance(p1), geometry.boundary.distance(p2))
        weight = length / max(clearance, 1e-6) ** alpha
        weighted_nk.addEdge(u, v, weight)
    return weighted_nk


def _nk_shortest_path_and_cost(graph_nk, src_node, dst_node):
    """Return shortest path and cost from NetworKit, or None if unreachable."""
    src_node = int(src_node)
    dst_node = int(dst_node)
    node_count = graph_nk.numberOfNodes()
    if src_node < 0 or dst_node < 0 or src_node >= node_count or dst_node >= node_count:
        return None

    solver = None
    if hasattr(nk.distance, "BidirectionalDijkstra"):
        try:
            solver = nk.distance.BidirectionalDijkstra(graph_nk, src_node, dst_node, True)
        except TypeError:
            solver = nk.distance.BidirectionalDijkstra(graph_nk, src_node, dst_node)

    if solver is None:
        solver = nk.distance.Dijkstra(graph_nk, src_node, True, False, dst_node)

    solver.run()

    distance = None
    for getter in (
        lambda: solver.getDistance(dst_node),
        lambda: solver.getDistance(),
        lambda: solver.distance(dst_node),
    ):
        try:
            distance = getter()
            break
        except Exception:
            continue

    if distance is None:
        return None

    distance = float(distance)
    if not np.isfinite(distance) or distance >= np.finfo(np.float64).max:
        return None

    path = None
    for getter in (
        lambda: solver.getPath(dst_node),
        lambda: solver.getPath(),
    ):
        try:
            path = getter()
            break
        except Exception:
            continue

    if not path:
        return None

    path_nodes = [int(node) for node in path]
    return path_nodes, distance


def _line_from_nodes_with_anchors(path_nodes, vor, src_point, dst_point):
    coords = [src_point.coords[0]]
    coords.extend([tuple(vor.vertices[node]) for node in path_nodes])
    coords.append(dst_point.coords[0])
    deduped = [coords[0]]
    for coord in coords[1:]:
        if coord != deduped[-1]:
            deduped.append(coord)
    return LineString(deduped)


def _soft_snap_centerline_to_endpoints(linestring, src_point, dst_point, tolerance):
    """Snap line ends only when endpoint is close enough."""
    coords = list(linestring.coords)
    if not coords:
        return linestring

    if Point(coords[0]).distance(src_point) <= tolerance:
        coords[0] = src_point.coords[0]
    if Point(coords[-1]).distance(dst_point) <= tolerance:
        coords[-1] = dst_point.coords[0]
    return LineString(coords)


def _terminal_deflection_angle(path, vertices, src_point, dst_point):
    """Get worst terminal deflection angle in degrees."""
    if len(path) < 2:
        return 0.0

    src_xy = np.array(src_point.coords[0])
    dst_xy = np.array(dst_point.coords[0])
    start_xy = np.array(vertices[path[0]])
    start_next_xy = np.array(vertices[path[1]])
    end_xy = np.array(vertices[path[-1]])
    end_prev_xy = np.array(vertices[path[-2]])

    start_angle = _angle_between_vectors(start_xy - src_xy, start_next_xy - start_xy)
    end_angle = _angle_between_vectors(end_prev_xy - end_xy, dst_xy - end_xy)
    return max(start_angle, end_angle)


def _angle_between_vectors(v1, v2):
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    cosang = np.dot(v1, v2) / (n1 * n2)
    cosang = max(-1.0, min(1.0, cosang))
    return float(np.degrees(np.arccos(cosang)))


def _get_guided_path(
    graph,
    vor,
    geometry,
    src_point,
    dst_point,
    src_candidates,
    dst_candidates,
    max_terminal_angle,
    alpha,
    enforce_angle=True,
):
    """Get best endpoint-guided path between candidate node sets."""
    if not src_candidates or not dst_candidates:
        return None

    weighted_nk = _build_medial_weighted_graph_nk(graph, vor, geometry, alpha)
    best = None

    for src_node in src_candidates:
        for dst_node in dst_candidates:
            if src_node == dst_node:
                continue
            solved = _nk_shortest_path_and_cost(weighted_nk, src_node, dst_node)
            if solved is None:
                continue
            path, score = solved

            src_connector_cost = _endpoint_connector_cost(src_point, src_node, vor, geometry)
            dst_connector_cost = _endpoint_connector_cost(dst_point, dst_node, vor, geometry)
            terminal_angle = _terminal_deflection_angle(path, vor.vertices, src_point, dst_point)
            if enforce_angle and terminal_angle > max_terminal_angle:
                continue

            total_score = (
                score + src_connector_cost + dst_connector_cost + ANGLE_PENALTY_WEIGHT * terminal_angle
            )
            candidate = {
                "path": path,
                "score": total_score,
                "angle": terminal_angle,
            }
            if best is None or candidate["score"] < best["score"]:
                best = candidate
    return best


def _endpoint_connector_cost(endpoint_point, node, vor, geometry):
    """Cost for connecting endpoint anchor to real graph node."""
    node_point = Point(vor.vertices[node])
    distance_cost = endpoint_point.distance(node_point)
    boundary_penalty = 0.2 / max(geometry.boundary.distance(node_point), 1e-6)
    return distance_cost + boundary_penalty


def _get_guided_path_virtual(
    graph,
    vor,
    geometry,
    src_point,
    dst_point,
    src_candidates,
    dst_candidates,
    max_terminal_angle,
    alpha,
    enforce_angle=True,
):
    """Get best path by solving on graph with virtual endpoint nodes."""
    if not src_candidates or not dst_candidates:
        return None

    src_virtual = "__SRC__"
    dst_virtual = "__DST__"
    augmented = _build_medial_weighted_graph(graph, vor, geometry, alpha)
    augmented.add_node(src_virtual)
    augmented.add_node(dst_virtual)

    src_added = 0
    for node in src_candidates:
        if node not in augmented:
            continue
        augmented.add_edge(
            src_virtual,
            node,
            weight=_endpoint_connector_cost(src_point, node, vor, geometry),
        )
        src_added += 1

    dst_added = 0
    for node in dst_candidates:
        if node not in augmented:
            continue
        augmented.add_edge(
            dst_virtual,
            node,
            weight=_endpoint_connector_cost(dst_point, node, vor, geometry),
        )
        dst_added += 1

    if src_added == 0 or dst_added == 0:
        return None

    best = None
    try:
        path_iter = nx.shortest_simple_paths(
            augmented,
            src_virtual,
            dst_virtual,
            weight="weight",
        )
        for index, raw_path in enumerate(path_iter):
            if index >= GUIDED_PATH_CANDIDATE_LIMIT:
                break
            path = [node for node in raw_path if node not in {src_virtual, dst_virtual}]
            if len(path) < 2:
                continue

            terminal_angle = _terminal_deflection_angle(path, vor.vertices, src_point, dst_point)
            if enforce_angle and terminal_angle > max_terminal_angle:
                continue

            score = nx.path_weight(augmented, raw_path, weight="weight")
            score = score + ANGLE_PENALTY_WEIGHT * terminal_angle
            candidate = {
                "path": path,
                "score": score,
                "angle": terminal_angle,
            }
            if best is None or candidate["score"] < best["score"]:
                best = candidate
            if not enforce_angle:
                break
    except NetworkXNoPath:
        return None

    return best


def _get_main_route_longest_paths(graph_nk):
    """Compute main-route longest-path extraction as fallback."""
    nk_nodes = list(graph_nk.iterNodes())
    if len(nk_nodes) < 2:
        return []

    all_pair_dijkstra = nk.distance.APSP(graph_nk)
    all_pair_dijkstra.run()
    unreachable_distance = np.finfo(np.float64).max
    distance = [
        (src, dst, all_pair_dijkstra.getDistance(src, dst))
        for src, dst in combinations(nk_nodes, 2)
        if all_pair_dijkstra.getDistance(src, dst) < unreachable_distance
    ]
    if not distance:
        return []
    distance.sort(key=operator.itemgetter(2), reverse=True)
    longest = distance[0]
    dijkstra = nk.distance.Dijkstra(graph_nk, longest[0], True, False, longest[1])
    dijkstra.run()
    longest_path = dijkstra.getPath(longest[1])
    if not longest_path:
        return []
    return [[int(i) for i in longest_path]]


def _get_least_curved_path(paths, vertices):
    """Return path with smallest angles."""
    return min(
        zip([_get_path_angles_sum(path, vertices) for path in paths], paths),
        key=operator.itemgetter(0),
    )[1]


def _get_path_angles_sum(path, vertices):
    """Return all angles between edges from path."""
    return sum(
        [
            _get_absolute_angle((vertices[pre], vertices[cur]), (vertices[cur], vertices[nex]))
            for pre, cur, nex in zip(path[:-1], path[1:], path[2:])
        ]
    )


def _get_absolute_angle(edge1, edge2):
    """Return absolute angle between edges."""
    v1 = edge1[0] - edge1[1]
    v2 = edge2[0] - edge2[1]
    return abs(np.degrees(np.arctan2(np.linalg.det([v1, v2]), np.dot(v1, v2))))


def _get_end_nodes(graph):
    """Return list of nodes with just one neighbor node."""
    return [i for i in graph.nodes() if len(list(graph.neighbors(i))) == 1]


def _graph_from_voronoi(vor, geometry):
    """Return networkx.Graph from Voronoi diagram within geometry."""
    graph = nx.Graph()
    for x, y, dist in _yield_ridge_vertices(vor, geometry, dist=True):
        graph.add_nodes_from([x, y])
        graph.add_edge(x, y, weight=dist)
    return graph


def _graph_from_voronoi_nk(vor, geometry):
    """Return networkit.Graph from Voronoi diagram within geometry."""
    edges = list(_yield_ridge_vertices(vor, geometry, dist=True))
    if not edges:
        return nk.graph.Graph(0, weighted=True)

    max_node_id = max(max(x, y) for x, y, _ in edges)
    graph = nk.graph.Graph(max_node_id + 1, weighted=True)
    for x, y, dist in edges:
        graph.addEdge(x, y, dist)
    return graph


def _multilinestring_from_voronoi(vor, geometry):
    """Return MultiLineString geometry from Voronoi diagram."""
    return MultiLineString(
        [
            LineString([Point(vor.vertices[[x, y]][0]), Point(vor.vertices[[x, y]][1])])
            for x, y in _yield_ridge_vertices(vor, geometry)
        ]
    )


def _yield_ridge_vertices(vor, geometry, dist=False):
    """Yield Voronoi ridge vertices within geometry."""
    for x, y in vor.ridge_vertices:
        if x < 0 or y < 0:
            continue
        point1 = Point(vor.vertices[[x, y]][0])
        point2 = Point(vor.vertices[[x, y]][1])
        # Eliminate all points outside our geometry.
        if point1.within(geometry) and point2.within(geometry):
            if dist:
                yield x, y, point1.distance(point2)
            else:
                yield x, y
