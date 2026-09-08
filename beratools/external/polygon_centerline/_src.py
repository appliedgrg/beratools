from itertools import combinations
import logging
import networkx as nx
from networkx.exception import NetworkXNoPath
import numpy as np
import operator
from scipy.spatial import QhullError, Voronoi
from scipy.ndimage import gaussian_filter1d
from shapely.geometry import LineString, MultiLineString, Point, MultiPoint
import shapely.geometry as sh_geom
from .exceptions import CenterlineError
from shapely import STRtree
import igraph as ig

import networkit as nk

import beratools.core.constants as bt_const
from beratools.core.logger import Logger
LOGGER_NAME = "centerline"
log = Logger(LOGGER_NAME, file_level=logging.DEBUG,console_level=logging.INFO)
logger = log.get_logger()
log_print = log.print

ANGLE_PENALTY_WEIGHT = 5.0
GUIDED_PATH_CANDIDATE_LIMIT = 40
QHULL_STABILIZED_OPTIONS = "Qbb Qc Qz Q12"
THIN_POLYGON_RATIO = 0.02
_LAST_CENTERLINE_INFO = {}


def get_last_centerline_info():
    return dict(_LAST_CENTERLINE_INFO)


def _set_last_centerline_info(**kwargs):
    _LAST_CENTERLINE_INFO.clear()
    _LAST_CENTERLINE_INFO.update(kwargs)


def filter_nodes(geom, graph, vor, end_nodes):
    if not geom:
        return end_nodes

    pts = [_node_point(graph, i) for i in end_nodes]  # points in graph
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
    guided_strategy="virtual_nodes",
    endpoint_mode="strict",
    snap_tolerance=None,
    endpoint_candidate_k=5,
    max_terminal_angle=40,
    alpha=0.5,
    snap_clearance_weight=5.0,
    cell_size=1.0,
    corridor_id=None,
    input_line=None,

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
    guided_strategy : "pairwise", "virtual_nodes", "direct_insert", or "main_route".
    endpoint_mode : "strict" or "soft".
    snap_tolerance : Maximum endpoint snap distance for soft mode.
    endpoint_candidate_k : Number of endpoint graph candidates.
    max_terminal_angle : Maximum allowed terminal deflection in degrees.
    alpha : Exponent for medial-aware edge weighting.
    snap_clearance_weight : (direct_insert only) Penalty for peripheral edges
        when choosing insertion point. 0 = pure nearest; higher = prefer
        interior edges. (default: 0.0)

    Returns:
    --------
    geometry : LineString or MultiLineString

    Raises:
    -------
    CenterlineError : if centerline cannot be extracted from Polygon
    TypeError : if input geometry is not Polygon or MultiPolygon

    """
    cid = f"[CID={corridor_id}] " if corridor_id else "[CID=UNKNOWN] "
    if cid=="[CID=232_0] " and guided_strategy=="main_route":
        print("debug start")
    # logger.debug_file_only(cid+"geometry type %s", geom.geom_type)
    _set_last_centerline_info(
        qhull_retry="none",
        polygon_stabilized=False,
        thin_polygon_ratio=None,
    )

    valid_endpoint_modes = {"strict", "soft"}
    if endpoint_mode not in valid_endpoint_modes:
        raise ValueError("endpoint_mode must be one of %s" % sorted(valid_endpoint_modes))

    valid_guided_strategies = {"pairwise", "virtual_nodes", "direct_insert", "main_route"}
    if guided_strategy not in valid_guided_strategies:
        raise ValueError("guided_strategy must be one of %s" % sorted(valid_guided_strategies))

    if geom.geom_type == "Polygon":
        # segmentized Polygon outline
        # outline = _segmentize(geom.exterior, segmentize_maxlen)
        outline=_densify_boundary(geom.exterior,step=0.25)
        # logger.debug("Number of outline points: %s", len(outline.coords))
        # logger.debug("outline: %s", outline)

        # simplify segmentized geometry if necessary and get points
        outline_points = outline.coords
        # simplification_updated = simplification
        # while len(outline_points) > max_points:
        #     # if geometry is too large, apply simplification until geometry
        #     # is simplified enough (indicated by the "max_points" value)
        #     simplification_updated += simplification
        #     outline_points = outline.simplify(simplification_updated).coords
        # logger.debug("simplification used: %s", simplification_updated)
        # logger.debug("Number of simplified points: %s", len(outline_points))
        s_geom = sh_geom.Polygon(outline_points)
        # calculate Voronoi diagram and convert to graph but only use points
        # from within the original polygon
        vor, vor_geom, vor_info = _safe_voronoi_for_polygon(
            s_geom,
            segmentize_maxlen,
            max_points,
            simplification,
            outline_points,
        )
        _set_last_centerline_info(**vor_info)
        graph = _graph_from_voronoi_coord(vor, vor_geom)
        _prepare_node_spatial_index(graph)
        # graph = reconnect_nearby_nodes(graph)
        # graph = _prune_cycles(graph,vor,s_geom,src_geom,dst_geom,corridor_id,)
        # graph = bridge_major_components_coord(
        #     graph,
        #     min_component_size=50,
        #     bridge_distance=5.0,
        #     cid=cid,
        # )

        # largest_cc = max(
        #     nx.connected_components(backbone_graph),
        #     key=len
        # )
        #
        # backbone_graph = backbone_graph.subgraph(
        #     largest_cc
        # ).copy()

        graph_nk = _build_medial_weighted_graph_nk(graph, s_geom, alpha)
        # logger.debug("voronoi diagram: %s", _multilinestring_from_voronoi(vor, geom))

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
        if (
            guided_strategy == "direct_insert"
            and src_point is not None
            and dst_point is not None
        ):
            guided_attempted = True
            guided = _get_guided_path_direct_insert(
                graph, vor, geom, src_point, dst_point,
                max_terminal_angle, alpha,
                enforce_angle=(endpoint_mode == "strict"),
                snap_clearance_weight=snap_clearance_weight,
            )
            if guided is None and endpoint_mode == "strict":
                logger.debug("direct_insert strict mode failed, retrying without angle guard")
                guided = _get_guided_path_direct_insert(
                    graph, vor, geom, src_point, dst_point,
                    max_terminal_angle, alpha,
                    enforce_angle=False,
                    snap_clearance_weight=snap_clearance_weight,
                )
            if guided is not None:
                ext = guided.get("extended_coords", {})
                coords = [src_point.coords[0]]
                for n in guided["path"]:
                    coords.append(tuple(_get_vertex_coords(n, vor,ext,graph=graph)))
                coords.append(dst_point.coords[0])
                deduped = [coords[0]]
                for c in coords[1:]:
                    if c != deduped[-1]:
                        deduped.append(c)
                centerline = _smooth_linestring_fixed_ends(LineString(deduped), smooth_sigma)

        elif (
            guided_strategy in {"pairwise", "virtual_nodes"}
            and src_point is not None
            and dst_point is not None
        ):
            guided_attempted = True
            src_nodes = filter_nodes(src_geom, graph, vor, end_nodes)
            dst_nodes = filter_nodes(dst_geom, graph, vor, end_nodes)
            src_candidates = _pick_endpoint_candidates_v2(
                src_point,
                graph,
                geom,
                endpoint_candidate_k,
                preferred_nodes=src_nodes,
            )
            dst_candidates = _pick_endpoint_candidates_v2(
                dst_point,
                graph,
                geom,
                endpoint_candidate_k,
                preferred_nodes=dst_nodes,
            )

            if guided_strategy == "virtual_nodes":
                guided = _get_guided_path_virtual(
                    graph,
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
                    graph,  # NetworkX graph with coord_lookup
                    graph_nk,  # NetworKit graph
                    geom,
                    src_point,
                    dst_point,
                    src_candidates,
                    dst_candidates,
                    max_terminal_angle,
                    enforce_angle=(endpoint_mode == "strict"),
                )

            if guided is None and endpoint_mode == "strict":
                logger.debug("strict endpoint guidance exceeded angle guard, retrying without guard")
                if guided_strategy == "virtual_nodes":
                    guided = _get_guided_path_virtual(
                        graph,
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
                        graph_nk,
                        geom,
                        src_point,
                        dst_point,
                        src_candidates,
                        dst_candidates,
                        max_terminal_angle,
                        enforce_angle=False,
                    )

            if guided is not None:
                path_nodes = guided["path"]
                if endpoint_mode == "strict":
                    centerline = _line_from_nodes_with_anchors_v2(path_nodes,
                                                                  src_point,
                                                                  dst_point,graph)
                    centerline = _smooth_linestring_fixed_ends(centerline, smooth_sigma)
                else:
                    centerline = LineString([_node_coords(graph, n) for n in path_nodes])
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
            igraph_graph = ig.Graph.from_networkx(graph)
            igraph_betweenness = igraph_graph.betweenness(directed=False)
            n = graph.number_of_nodes()
            norm = ((n - 1) * (n - 2)) / 2
            centrality = {
                node: val / norm
                for node, val in zip(
                    graph.nodes(),
                    igraph_betweenness)}
            cutoff = np.percentile(
                list(centrality.values()),
                75
            )
            backbone_nodes = {
                n
                for n, c in centrality.items()
                if c >= cutoff}

            backbone_graph = graph.subgraph(
                backbone_nodes).copy()

            # largest_cc = max(
            #     nx.connected_components(backbone_graph),
            #     key=len
            # )

            # logger.info(
            #     f"backbone_graph largest_cc={len(largest_cc)} "
            #     f"of {backbone_graph.number_of_nodes()}"
            # )

            backbone_graph = reconnect_nearby_nodes(backbone_graph,geometry=s_geom)
            backbone_graph = bridge_major_components_coord(
                backbone_graph,
                geometry=s_geom,
                min_component_size=50,
                bridge_distance=5.0,
                cid=cid,
            )

            backbone_graph_nk = nx_to_networkit(backbone_graph)
            longest_paths = _get_main_route_longest_paths(backbone_graph_nk)
            if not longest_paths:
                logger.debug("no paths found between end nodes")
                raise CenterlineError("no paths found between end nodes")
            if logger.getEffectiveLevel() <= 10:
                logger.debug("longest paths:")
            best_path = max(
                longest_paths,
                key=lambda p: _path_score(
                    backbone_graph,p))
            # logger.file_only(
            #     f"{cid} BEST SCORE="
            #     f"{_path_score(backbone_graph, best_path):.2f}\n "
            #     f"{cid} BEST_PATH_NODES="
            #     f"{len(best_path)}\n"
            #     f"{cid} BRANCH_COUNT="
            #     f"{sum(1 for n in best_path if backbone_graph.degree(n) > 2)}"
            # )
            coords = []
            for u, v in zip(best_path[:-1],best_path[1:]):
                edge_data = backbone_graph[u][v]
                seg_geom = edge_data.get("geometry")
                if seg_geom is None:
                    seg_geom = LineString([
                        _node_coords(backbone_graph, u),
                        _node_coords(backbone_graph, v),
                    ])
                if isinstance(seg_geom, sh_geom.LineString):
                    seg_coords = list(seg_geom.coords)
                    if not coords:
                        coords.extend(seg_coords)
                    else:
                        coords.extend(seg_coords[1:])

                elif isinstance(seg_geom, sh_geom.MultiLineString):
                    for seg in seg_geom.geoms:
                        seg_coords = list(seg.coords)
                        if not coords:
                            coords.extend(seg_coords)
                        else:
                            coords.extend(seg_coords[1:])
            centerline = _smooth_linestring(LineString(coords),smooth_sigma,)

        #     logger.file_only(
        #         f"{cid} FINAL_LEN={centerline.length:.2f}"
        #     )
        #
        #     coords = list(centerline.coords)
        #
        #     logger.file_only(
        #         f"{cid} FINAL_START={coords[0]}"
        #     )
        #
        #     logger.file_only(
        #             f"{cid} FINAL_END={coords[-1]}"
        #         )
        # logger.debug("centerline: %s", centerline)
        # logger.debug("return linestring")
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


def _safe_voronoi_for_polygon(geom, segmentize_maxlen, max_points, simplification, outline_points):
    """Build Voronoi while suppressing noisy Qhull precision dumps."""
    thin_ratio = _polygon_thin_ratio(geom)
    is_thin_polygon = thin_ratio is not None and thin_ratio < THIN_POLYGON_RATIO
    info = {
        "qhull_retry": "none",
        "polygon_stabilized": False,
        "thin_polygon_ratio": thin_ratio,
    }

    q12_failed = False
    if is_thin_polygon:
        try:
            info["qhull_retry"] = "q12_thin_precheck"
            return Voronoi(outline_points, qhull_options=QHULL_STABILIZED_OPTIONS), geom, info
        except QhullError as e:
            q12_failed = True
            logger.info(
                "Thin polygon precheck Q12 retry failed; retrying with a tiny stabilized footprint. %s",
                _qhull_error_summary(e),
            )

    if not q12_failed:
        try:
            return Voronoi(outline_points), geom, info
        except QhullError as e:
            logger.info(
                "Voronoi failed for likely thin/degenerate polygon; retrying with Q12. %s",
                _qhull_error_summary(e),
            )

        try:
            info["qhull_retry"] = "q12"
            return Voronoi(outline_points, qhull_options=QHULL_STABILIZED_OPTIONS), geom, info
        except QhullError as e:
            logger.info(
                "Voronoi Q12 retry failed; retrying with a tiny stabilized footprint. %s",
                _qhull_error_summary(e),
            )

    stabilized = _stabilize_polygon_for_voronoi(geom, segmentize_maxlen, thin_ratio)
    stabilized_outline = _segmentize(stabilized.exterior, segmentize_maxlen)
    stabilized_points = stabilized_outline.coords
    simplification_updated = simplification
    while len(stabilized_points) > max_points:
        simplification_updated += simplification
        stabilized_points = stabilized_outline.simplify(simplification_updated).coords

    try:
        info["qhull_retry"] = "q12_buffered_polygon"
        info["polygon_stabilized"] = True
        return Voronoi(stabilized_points, qhull_options=QHULL_STABILIZED_OPTIONS), geom, info
    except QhullError as e:
        raise CenterlineError(
            "Voronoi failed for thin/degenerate polygon after stabilized retry"
        ) from e


def _polygon_thin_ratio(geom):
    try:
        rect = geom.minimum_rotated_rectangle
        coords = list(rect.exterior.coords)
    except Exception:
        return None

    if len(coords) < 4:
        return None

    side_lengths = [Point(coords[i]).distance(Point(coords[i + 1])) for i in range(4)]
    positive_lengths = [length for length in side_lengths if length > 0]
    if len(positive_lengths) < 2:
        return None

    short_side = min(positive_lengths)
    long_side = max(positive_lengths)
    if long_side <= 0:
        return None
    return short_side / long_side


def _stabilize_polygon_for_voronoi(geom, segmentize_maxlen, thin_ratio):
    bounds_width = max(geom.bounds[2] - geom.bounds[0], geom.bounds[3] - geom.bounds[1])
    if bounds_width <= 0:
        bounds_width = segmentize_maxlen
    buffer_distance = min(segmentize_maxlen * 0.1, bounds_width * 0.001)
    if thin_ratio is not None and thin_ratio < THIN_POLYGON_RATIO:
        buffer_distance = min(segmentize_maxlen * 0.25, max(buffer_distance, bounds_width * 0.0005))
    buffer_distance = max(buffer_distance, 1e-9)

    stabilized = geom.buffer(buffer_distance)
    if not stabilized or stabilized.is_empty:
        return geom
    return stabilized


def _qhull_error_summary(error):
    message = str(error).splitlines()
    for line in message:
        stripped = line.strip()
        if stripped:
            return stripped
    return error.__class__.__name__


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

def _pick_endpoint_candidates_v2(
    point,
    graph,
    geometry,
    candidate_k,
    preferred_nodes=None,
):
    width_est = max(1.0,2.0 * geometry.area / geometry.length)
    search_radius = np.clip(1.5*width_est,5.0,25.0,)
    preferred_nodes=preferred_nodes or []
    filtered_preferred = {node for node in preferred_nodes if node in graph}
    tree = graph.graph["node_tree"]
    node_ids = graph.graph["node_ids"]
    node_points = graph.graph["node_points"]

    raw_idx = tree.query(point.buffer(search_radius))

    if len(raw_idx) == 0:
        raw_idx = np.atleast_1d(tree.query_nearest(point))

    scored = []

    for idx in raw_idx:

        node = node_ids[idx]
        node_pt = node_points[idx]

        dist = point.distance(node_pt)
        boundary_dist = geometry.boundary.distance(node_pt)

        score = dist + (
            0.2 / max(boundary_dist, 1e-6)
        )
        if node in filtered_preferred:
            score *= 0.6

        scored.append((score, node))

    scored.sort(key=operator.itemgetter(0))

    return [
        node
        for _, node in scored[:candidate_k]
    ]
def _pick_endpoint_candidates(point, graph,
                              geometry, candidate_k, preferred_nodes=None):
    """Pick endpoint candidate graph nodes with distance/clearance score."""
    available_nodes = list(graph.nodes())
    if not available_nodes:
        return []

    preferred_nodes = preferred_nodes or []
    filtered_preferred = [node for node in preferred_nodes if node in graph]
    scored = []
    for node in available_nodes:
        node_pt = _node_point(graph, node)
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


def _build_medial_weighted_graph(graph,  geometry, alpha):
    """Build graph with edge costs biased to medial regions."""
    weighted = nx.Graph()
    if "coord_lookup" in graph.graph:
        weighted.graph["coord_lookup"] = (
            graph.graph["coord_lookup"]
        )
    else:
        weighted.graph["coord_lookup"] = {}
    for u, v ,data in graph.edges(data=True):
        p1 = _node_point(graph,u)
        p2 = _node_point(graph,v)
        length = p1.distance(p2)
        clearance = min(geometry.boundary.distance(p1), geometry.boundary.distance(p2))
        weight = length / max(clearance, 1e-6) ** alpha
        weighted.add_edge(
            u,
            v,
            weight=weight,
            length=data.get("length", length),
            geometry=data.get("geometry"),
            bridge=data.get("bridge", False),
        )

    return weighted


def _build_medial_weighted_graph_nk(graph,  geometry, alpha):
    """Build NetworKit graph with edge costs biased to medial regions."""
    nodes = list(graph.nodes())
    if not nodes:
        return nk.graph.Graph(0, weighted=True)

    max_node_id = max(nodes)
    weighted_nk = nk.graph.Graph(max_node_id + 1, weighted=True)


    for u, v,data in graph.edges(data=True):

        p1 = _node_point(graph,u)
        p2 = _node_point(graph,v)
        length = data.get("length",p1.distance(p2))
        clearance = min(geometry.boundary.distance(p1), geometry.boundary.distance(p2))
        weight = length / max(clearance, 1e-6) ** alpha
        weighted_nk.addEdge(u, v, weight,)
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


def _line_from_nodes_with_anchors(path_nodes, vor, src_point, dst_point,graph):
    coords = [src_point.coords[0]]
    coords.extend([_node_coords(graph, node) for node in path_nodes])
    coords.append(dst_point.coords[0])
    deduped = [coords[0]]
    for coord in coords[1:]:
        if coord != deduped[-1]:
            deduped.append(coord)
    return LineString(deduped)

def _line_from_nodes_with_anchors_v2(
    path_nodes,
    src_point,
    dst_point,
    graph,
):
    coords = [src_point.coords[0]]

    for u, v in zip(path_nodes[:-1], path_nodes[1:]):

        seg_geom = graph[u][v].get("geometry")

        if seg_geom is None:
            seg_coords = [
                _node_coords(graph, u),
                _node_coords(graph, v)
            ]
        else:
            seg_coords = list(seg_geom.coords)

        if len(coords) == 1:
            coords.extend(seg_coords)
        else:
            coords.extend(seg_coords[1:])

    coords.append(dst_point.coords[0])

    return LineString(coords)

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


def _terminal_deflection_angle(path,
                               vertices,
                               src_point, dst_point):
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


def _terminal_deflection_angle_coord(path, graph,
                                     src_point, dst_point):
    """Get worst terminal deflection angle in degrees."""
    if len(path) < 2:
        return 0.0

    src_xy = np.array(src_point.coords[0])
    dst_xy = np.array(dst_point.coords[0])
    start_xy = np.array(_node_coords(graph,path[0]))
    start_next_xy = np.array(_node_coords(graph,path[1]))
    end_xy = np.array(_node_coords(graph,path[-1]))
    end_prev_xy = np.array(_node_coords(graph,path[-2]))

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
    graph,# geometry lookup
    graph_nk,
    geometry,
    src_point,
    dst_point,
    src_candidates,
    dst_candidates,
    max_terminal_angle,
    enforce_angle=True,
):
    """Get best endpoint-guided path between candidate node sets."""
    if not src_candidates or not dst_candidates:
        return None

    best = None

    for src_node in src_candidates:
        for dst_node in dst_candidates:
            if src_node == dst_node:
                continue
            solved = _nk_shortest_path_and_cost(graph_nk, src_node, dst_node)

            if solved is None:
                continue

            path, score = solved

            terminal_angle = _terminal_deflection_angle_coord(path,graph,src_point,dst_point)

            src_connector_cost = _endpoint_connector_cost(src_point, src_node, geometry,graph)
            dst_connector_cost = _endpoint_connector_cost(dst_point, dst_node, geometry,graph)

            path_length = sum(
                graph[u][v]["length"]
                for u, v in zip(path[:-1], path[1:])
            )

            # straight_length = (
            #     src_point.distance(dst_point)
            # )
            # logger.info(
            #     f"path_len={path_length:.1f} "
            #     f"straight_len={straight_length:.1f} "
            #     f"ratio={path_length / max(straight_length, 1):.2f} "
            #     f"src={src_node} "
            #     f"dst={dst_node} "
            #     f"path_nodes={len(path)} "
            #     f"score={score:.2f} "
            #     f"angle={terminal_angle:.2f} "
            #     f"src connector cost={src_connector_cost:.2f} "
            #     f"dst connector cost={dst_connector_cost:.2f} "
            # )

            if enforce_angle and terminal_angle > max_terminal_angle:
                continue
            tortuosity = (path_length /
                max(src_point.distance(dst_point), 1.0))
            total_score = (
                score*tortuosity + src_connector_cost + dst_connector_cost + ANGLE_PENALTY_WEIGHT * terminal_angle
            )

            candidate = {
                "path": path,
                "score": total_score,
                "angle": terminal_angle,
            }
            if best is None or candidate["score"] < best["score"]:
                best = candidate
    return best


def _endpoint_connector_cost(endpoint_point, node, geometry,graph):
    """Cost for connecting endpoint anchor to real graph node."""
    node_point =_node_point(graph, node)
    distance_cost = endpoint_point.distance(node_point)
    boundary_penalty = 0.2 / max(geometry.boundary.distance(node_point), 1e-6)
    return distance_cost + boundary_penalty


def _get_guided_path_virtual(
    graph,
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
    augmented = _build_medial_weighted_graph(graph,  geometry, alpha)
    augmented.add_node(src_virtual)
    augmented.add_node(dst_virtual)

    src_added = 0
    for node in src_candidates:
        if node not in augmented:
            continue
        augmented.add_edge(
            src_virtual,
            node,
            weight=_endpoint_connector_cost(src_point, node, geometry,graph),
        )
        src_added += 1

    dst_added = 0
    for node in dst_candidates:
        if node not in augmented:
            continue
        augmented.add_edge(
            dst_virtual,
            node,
            weight=_endpoint_connector_cost(dst_point, node, geometry,graph),
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

            terminal_angle = _terminal_deflection_angle_coord(path, graph, src_point, dst_point)
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


def _get_vertex_coords(node, vor, extended_coords,graph):
    """Get coordinates for a graph node, checking extended coords first."""
    if extended_coords and node in extended_coords:
        return extended_coords[node]
    return _node_coords(graph,node)


def _insert_endpoint_node(
    point, weighted_graph, vor, geometry, alpha, extended_coords, snap_clearance_weight=5.0
):
    """Insert endpoint into weighted graph by splitting the nearest edge.

    Projects *point* onto the closest edge of *weighted_graph*, splits that
    edge at the projection, and stores the new node coordinates in
    *extended_coords*.  Returns the new node ID, or ``None`` on failure.

    *snap_clearance_weight* controls how much to penalise edges close to the
    polygon boundary.  ``0`` (default) uses pure nearest distance; higher
    values bias the selection toward more medial (interior) edges.
    """
    point_xy = np.array(point.coords[0])
    best_score = float("inf")
    best_edge = None
    best_projected = None

    for u, v in list(weighted_graph.edges()):
        p1 = np.array(_get_vertex_coords(u, vor, extended_coords,weighted_graph))
        p2 = np.array(_get_vertex_coords(v, vor, extended_coords,weighted_graph))
        seg = p2 - p1
        seg_len_sq = float(np.dot(seg, seg))
        if seg_len_sq < 1e-12:
            projected = p1
        else:
            t = float(np.dot(point_xy - p1, seg) / seg_len_sq)
            t = max(0.0, min(1.0, t))
            projected = p1 + t * seg

        dist = float(np.linalg.norm(point_xy - projected))
        clearance = geometry.boundary.distance(Point(projected))
        score = dist + snap_clearance_weight / max(clearance, 1e-6)
        if score < best_score:
            best_score = score
            best_edge = (u, v)
            best_projected = projected

    if best_edge is None:
        return None

    u, v = best_edge
    new_id = max(weighted_graph.nodes()) + 1
    extended_coords[new_id] = best_projected

    weighted_graph.remove_edge(u, v)
    p_new = Point(best_projected)
    clearance_new = geometry.boundary.distance(p_new)

    for nbr in (u, v):
        nbr_coords = _get_vertex_coords(nbr, vor, extended_coords,weighted_graph)
        p_nbr = Point(nbr_coords)
        length = p_nbr.distance(p_new)
        clearance = geometry.boundary.distance(p_nbr)
        weight = length / max(min(clearance, clearance_new), 1e-6) ** alpha
        weighted_graph.add_edge(nbr, new_id, weight=weight)

    return new_id


def _get_guided_path_direct_insert(
    graph,
    vor,
    geometry,
    src_point,
    dst_point,
    max_terminal_angle,
    alpha,
    enforce_angle=True,
    snap_clearance_weight=5.0,
):
    """Get path by inserting src/dst directly into the Voronoi graph.

    Instead of picking candidate nodes and searching many paths, this mode
    projects each endpoint onto the nearest Voronoi edge, splits that edge,
    and runs a single shortest-path query between the two inserted nodes.

    *snap_clearance_weight* controls how much to penalise peripheral edges
    when choosing the insertion point.  ``0`` = pure nearest distance;
    higher values bias toward more medial (interior) edges.
    """
    weighted = _build_medial_weighted_graph(graph,  geometry, alpha)
    extended_coords = {}

    src_node = _insert_endpoint_node(
        src_point, weighted, vor, geometry, alpha, extended_coords, snap_clearance_weight
    )
    dst_node = _insert_endpoint_node(
        dst_point, weighted, vor, geometry, alpha, extended_coords, snap_clearance_weight
    )

    if src_node is None or dst_node is None:
        return None

    try:
        path = nx.shortest_path(weighted, src_node, dst_node, weight="weight")
        score = nx.path_weight(weighted, path, weight="weight")
    except NetworkXNoPath:
        return None

    if len(path) < 2:
        return None

    # Terminal angle check using extended coords
    start_xy = np.array(_get_vertex_coords(path[0], vor, extended_coords,weighted))
    next_xy = np.array(_get_vertex_coords(path[1], vor, extended_coords,weighted))
    end_xy = np.array(_get_vertex_coords(path[-1], vor, extended_coords,weighted))
    prev_xy = np.array(_get_vertex_coords(path[-2], vor, extended_coords,weighted))
    src_xy = np.array(src_point.coords[0])
    dst_xy = np.array(dst_point.coords[0])

    start_angle = _angle_between_vectors(start_xy - src_xy, next_xy - start_xy)
    end_angle = _angle_between_vectors(prev_xy - end_xy, dst_xy - end_xy)
    terminal_angle = max(start_angle, end_angle)

    if enforce_angle and terminal_angle > max_terminal_angle:
        return None

    score += ANGLE_PENALTY_WEIGHT * terminal_angle

    return {
        "path": path,
        "score": score,
        "angle": terminal_angle,
        "extended_coords": extended_coords,
    }


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
    distance.sort(key=operator.itemgetter(2),reverse=True,)
    top_pairs = distance[:10]
    paths = []

    for src, dst, _ in top_pairs:
        dijkstra = nk.distance.Dijkstra(
            graph_nk,
            src,
            True,
            False,
            dst,
        )
        dijkstra.run()
        path = dijkstra.getPath(dst)
        if path:
            paths.append(
                [int(i) for i in path]
            )
    return paths
    # dijkstra = nk.distance.Dijkstra(graph_nk, longest[0], True, False, longest[1])
    # dijkstra.run()
    # longest_path = dijkstra.getPath(longest[1])
    # if not longest_path:
    #     return []
    # return [[int(i) for i in longest_path]]


# def _get_least_curved_path(paths, vertices):
#     """Return path with smallest angles."""
#     return min(
#         zip([_get_path_angles_sum(path, vertices) for path in paths], paths),
#         key=operator.itemgetter(0),
#     )[1]

#
# def _get_path_angles_sum(path, vertices):
#     """Return all angles between edges from path."""
#     return sum(
#         [
#             _get_absolute_angle((vertices[pre], vertices[cur]), (vertices[cur], vertices[nex]))
#             for pre, cur, nex in zip(path[:-1], path[1:], path[2:])
#         ]
#     )


# def _get_absolute_angle(edge1, edge2):
#     """Return absolute angle between edges."""
#     v1 = edge1[0] - edge1[1]
#     v2 = edge2[0] - edge2[1]
#     return abs(np.degrees(np.arctan2(np.linalg.det([v1, v2]), np.dot(v1, v2))))
#

def _get_end_nodes(graph):
    """Return list of nodes with just one neighbor node."""
    return [i for i in graph.nodes() if len(list(graph.neighbors(i))) == 1]


# def _graph_from_voronoi(vor, geometry):
#     """Return networkx.Graph from Voronoi diagram within geometry."""
#     graph = nx.Graph()
#     for x, y, dist in _yield_ridge_vertices(vor, geometry,graph, dist=True):
#         graph.add_nodes_from([x, y])
#         graph.add_edge(x, y, weight=dist)
#     return graph


# def _graph_from_voronoi_nk(vor, geometry):
#     """Return networkit.Graph from Voronoi diagram within geometry."""
#     edges = list(_yield_ridge_vertices(vor, geometry, dist=True))
#     if not edges:
#         return nk.graph.Graph(0, weighted=True)
#
#     max_node_id = max(max(x, y) for x, y, _ in edges)
#     graph = nk.graph.Graph(max_node_id + 1, weighted=True)
#     for x, y, dist in edges:
#         graph.addEdge(x, y, dist)
#     return graph


# def _multilinestring_from_voronoi(vor,
#                                   geometry, graph):
#     """Return MultiLineString geometry from Voronoi ridges."""
#     return MultiLineString(
#         [
#             LineString([start_xy, end_xy])
#             for start_xy, end_xy,*_ in _yield_ridge_segments(vor, geometry)
#         ]
#     )

# def _multilinestring_from_voronoi_v2(vor, geometry, graph=None):
#     """
#     Return MultiLineString geometry from clipped Voronoi ridges.
#     """
#     segments = [seg_geom
#         for _, _, seg_geom, _
#         in _yield_ridge_segments(vor, geometry)]
#
#     return MultiLineString(segments)

# def _prune_cycles(
#     graph,
#     vor,
#     geom,
#     src_geom,
#     dst_geom,
#     corridor_id=None,
# ):
#     cid = (
#         f"[CID={corridor_id}] "
#         if corridor_id else ""
#     )
#
#     cycles = nx.cycle_basis(graph)
#
#     logger.info(
#         cid +
#         f"Before prune: "
#         f"cycles={len(cycles)}, "
#         f"components="
#         f"{nx.number_connected_components(graph)}"
#     )
#
#     for cycle in cycles:
#
#         # skip large structural cycles
#         if len(cycle) > 10:
#             continue
#
#         cycle_edges = []
#
#         for u, v in zip(
#             cycle,
#             cycle[1:] + [cycle[0]]
#         ):
#
#             p1 = _node_point(graph, u)
#             p2 = _node_point(graph, v)
#
#             length = p1.distance(p2)
#
#             cycle_edges.append(
#                 (
#                     length,
#                     u,
#                     v,
#                 )
#             )
#
#         cycle_edges.sort()
#
#         removed = False
#
#         for length, u, v in cycle_edges:
#
#             trial = graph.copy()
#
#             try:
#                 trial.remove_edge(u, v)
#             except Exception:
#                 continue
#
#             # keep graph connected
#             if (
#                 nx.number_connected_components(trial)
#                 ==
#                 nx.number_connected_components(graph)
#             ):
#
#                 graph.remove_edge(u, v)
#
#                 # logger.file_only(
#                 #     cid +
#                 #     f" removed cycle edge "
#                 #     f"({u}, {v}) "
#                 #     f"len={length:.3f}"
#                 # )
#
#                 removed = True
#                 break
#
#         if not removed:
#
#             logger.info(
#                 cid +
#                 " cycle retained "
#                 "(all removals disconnect graph)"
#             )
#
#     logger.info(
#         cid +
#         f"After prune: "
#         f"components="
#         f"{nx.number_connected_components(graph)}"
#     )
#
#     return graph

# def _component_metadata(components, graph, min_size=50):
#     """Works on coordinate-graph version
#        Converts raw connected components into something can reason about spatially"""
#     metadata = []
#
#     for cc_id, comp in enumerate(components):
#
#         if len(comp) < min_size:
#             continue
#
#         pts = [_node_coords(graph, n) for n in comp]
#
#         cx = sum(p[0] for p in pts) / len(pts)
#         cy = sum(p[1] for p in pts) / len(pts)
#
#         metadata.append({
#             "id": cc_id,
#             "nodes": set(comp),
#             "size": len(comp),
#             "centroid": Point(cx, cy),
#         })
#
#     return metadata


# def _nearest_node_pair(comp_a, comp_b,graph):
#
#     best_dist = float("inf")
#     best_pair = None
#
#     for na in comp_a:
#
#         pa = _node_point(graph, na)
#
#         for nb in comp_b:
#
#             pb = _node_point(graph, nb)
#
#             d = pa.distance(pb)
#
#             if d < best_dist:
#                 best_dist = d
#                 best_pair = (na, nb)
#
#     return best_pair, best_dist


# def bridge_major_components(
#     graph,
#     vor,
#     min_component_size=50,
#     bridge_distance=10.0,
#     cid=None,
# ):
#
#     components = list(nx.connected_components(graph))
#
#     meta = _component_metadata(
#         components,
#         graph,
#         min_size=min_component_size,
#     )
#
#     if len(meta) <= 1:
#         return graph
#
#     #
#     # Build component graph
#     #
#     component_graph = nx.Graph()
#
#     for comp in meta:
#         component_graph.add_node(
#             comp["id"]
#         )
#
#     bridge_candidates = {}
#
#     for comp_a, comp_b in combinations(meta, 2):
#
#         pair, node_dist = _nearest_node_pair(
#             comp_a["nodes"],
#             comp_b["nodes"],
#             graph,)
#
#         if node_dist > bridge_distance:
#             continue
#
#         component_graph.add_edge(
#             comp_a["id"],
#             comp_b["id"],
#             weight=node_dist,
#         )
#
#         bridge_candidates[
#             (comp_a["id"], comp_b["id"])
#         ] = (
#             pair,
#             node_dist,
#         )
#
#     #
#     # Connect components using MST
#     #
#     if component_graph.number_of_edges() == 0:
#         return graph
#
#     mst = nx.minimum_spanning_tree(
#         component_graph,
#         weight="weight",
#     )
#
#     for cc_a, cc_b in mst.edges():
#
#         pair, node_dist = bridge_candidates[
#             (cc_a, cc_b)
#         ]
#
#         na, nb = pair
#
#         graph.add_edge(
#             na,
#             nb,
#             weight=node_dist,
#         )
#
#         # logger.file_only(
#         #     f"{cid} BRIDGE "
#         #     f"cc{cc_a} -> cc{cc_b} "
#         #     f"dist={node_dist:.2f} "
#         #     f"nodeA={na} "
#         #     f"nodeB={nb}"
#         # )
#
#     return graph

def nx_to_networkit(nx_graph):
    """
    Convert NetworkX graph to NetworKit graph.
    Assumes integer node ids.
    """

    max_node = max(nx_graph.nodes())

    nk_graph = nk.graph.Graph(
        max_node + 1,
        weighted=True
    )

    for u, v, data in nx_graph.edges(data=True):
        weight = data.get("weight", 1.0)

        nk_graph.addEdge(
            int(u),
            int(v),
            float(weight))

    return nk_graph

def _yield_ridge_segments(vor, geometry):

    def snap_coord(coord, precision=3):
        return (
            round(coord[0], precision),
            round(coord[1], precision),
        )

    line_count = 0
    mls_count = 0
    for x, y in vor.ridge_vertices:

        if x < 0 or y < 0:
            continue

        ridge = LineString([
            vor.vertices[x],
            vor.vertices[y]
        ])

        clipped = ridge.intersection(geometry)

        if clipped.is_empty:
            continue

        if clipped.geom_type == "LineString":
            line_count += 1
            coords = list(clipped.coords)

            if len(coords) < 2:
                continue

            yield (
                snap_coord(coords[0]),
                snap_coord(coords[-1]),
                clipped,
                clipped.length,
            )

        elif clipped.geom_type == "MultiLineString":
            mls_count += 1
            for seg in clipped.geoms:

                if seg.length <= 0:
                    continue

                coords = list(seg.coords)

                if len(coords) < 2:
                    continue

                yield (
                    snap_coord(coords[0]),
                    snap_coord(coords[-1]),
                    seg,
                    seg.length,
                )
    # logger.file_only(
    #     f"lines={line_count} "
    #     f"multilines={mls_count}"
    # )
def _graph_from_voronoi_coord(vor, geometry):
    """
    Build a graph from Voronoi ridges clipped to the corridor.

    Topology is based on the clipped segment endpoints, not the
    original Voronoi vertex ids. This makes LineString and
    MultiLineString handling consistent.
    """

    graph = nx.Graph()

    line_count = 0
    mls_count = 0
    segment_count = 0
    subseg_count = 0

    coord_to_node = {}
    node_to_coord = {}
    next_node_id = 0

    def get_node_id(coord):
        nonlocal next_node_id

        key = (round(float(coord[0]), 6),
            round(float(coord[1]), 6),)

        if key not in coord_to_node:
            coord_to_node[key] = next_node_id
            node_to_coord[next_node_id] = key
            next_node_id += 1

        return coord_to_node[key]

    for x, y in vor.ridge_vertices:

        if x < 0 or y < 0:
            continue

        ridge = LineString([
            vor.vertices[x],
            vor.vertices[y],
        ])

        clipped = ridge.intersection(geometry)

        if clipped.is_empty:
            continue

        segment_count += 1

        #
        # LineString
        #
        if clipped.geom_type == "LineString":
            if clipped.length <= 0:
                continue
            coords = list(clipped.coords)
            if len(coords) < 2:
                continue
            u = get_node_id(coords[0])
            v = get_node_id(coords[-1])
            graph.add_edge(
                u,
                v,
                geometry=clipped,
                length=float(clipped.length),
                weight=float(clipped.length),)

            line_count += 1
        #
        # MultiLineString
        #
        elif clipped.geom_type == "MultiLineString":
            mls_count += 1
            for seg in clipped.geoms:
                if seg.length <= 0:
                    continue
                coords = list(seg.coords)
                if len(coords) < 2:
                    continue
                u = get_node_id(coords[0])
                v = get_node_id(coords[-1])
                graph.add_edge(
                    u,
                    v,
                    geometry=seg,
                    length=float(seg.length),
                    weight=float(seg.length),
                )
                subseg_count += 1

    graph.graph["coord_lookup"] = node_to_coord

    # logger.file_only(
    #     f"lines={line_count} "
    #     f"multilines={mls_count} "
    #     f"multiline_segments={subseg_count}"
    # )
    #
    # logger.file_only(
    #     f"node_count={graph.number_of_nodes()} "
    #     f"edge_count={graph.number_of_edges()} "
    #     f"coord_lookup={len(node_to_coord)}"
    # )
    #
    # sanity check
    #
    missing = [
        n
        for n in graph.nodes()
        if n not in node_to_coord
    ]

    if missing:
        logger.error(
            f"coord_lookup missing {len(missing)} nodes. "
            f"First few: {missing[:10]}"
        )

    return graph

# def _graph_from_voronoi_nk_coord(vor, geometry):
#
#     edges = list(
#         _yield_ridge_segments(
#             vor,
#             geometry,
#         )
#     )
#
#     if not edges:
#         return nk.graph.Graph(
#             0,
#             weighted=True
#         )
#
#     node_lookup = {}
#     next_id = 0
#
#     def get_node_id(coord):
#
#         nonlocal next_id
#
#         if coord not in node_lookup:
#             node_lookup[coord] = next_id
#             next_id += 1
#
#         return node_lookup[coord]
#
#     for u_xy, v_xy, *_ in edges:
#         get_node_id(u_xy)
#         get_node_id(v_xy)
#
#     graph = nk.graph.Graph(
#         len(node_lookup),
#         weighted=True
#     )
#
#     for u_xy, v_xy,clipped_geom,dist in edges:
#
#         u = node_lookup[u_xy]
#         v = node_lookup[v_xy]
#
#         graph.addEdge(
#             u,
#             v,
#             float(dist),
#         )
#
#     return graph



def bridge_major_components_coord(
        graph,
        geometry,
        min_component_size=50,
        bridge_distance=5.0,
        cid=None):

    coord_lookup = graph.graph["coord_lookup"]

    components = list(
        nx.connected_components(graph)
    )

    major_components = [
        comp
        for comp in components
        if len(comp) >= min_component_size
    ]

    for comp_a, comp_b in combinations(
            major_components, 2):

        best_dist = float("inf")
        best_pair = None

        for na in comp_a:

            pa = Point(
                coord_lookup[na]
            )

            for nb in comp_b:

                pb = Point(
                    coord_lookup[nb]
                )

                d = pa.distance(pb)

                if d < best_dist:

                    best_dist = d
                    best_pair = (
                        na,
                        nb,
                    )

        if (
            best_pair is None
            or best_dist > bridge_distance
        ):
            continue

        na, nb = best_pair

        bridge_geom = LineString([
            _node_coords(graph, na),
            _node_coords(graph, nb),
        ])

        if not geometry.covers(bridge_geom):
            continue

        graph.add_edge(
            na,
            nb,
            weight=float(best_dist),
            length=float(best_dist),
            geometry=bridge_geom,
            bridge=True,
        )

        # logger.file_only(
        #     f"{cid} BRIDGE "
        #     f"{na}->{nb} "
        #     f"dist={best_dist:.2f}"
        # )

    return graph

# def _nxgraph_to_nkgraph(nx_graph):
#
#     node_count = max(nx_graph.nodes()) + 1
#
#     nk_graph = nk.graph.Graph(
#         node_count,
#         weighted=True,
#     )
#
#     for u, v, data in nx_graph.edges(data=True):
#
#         nk_graph.addEdge(
#             int(u),
#             int(v),
#             float(data.get("weight", 1.0)),
#         )
#
#     return nk_graph

def _node_point(graph, node):
    """ Return point geometry for node id. """
    if "coord_lookup" in graph.graph:
        x, y = graph.graph["coord_lookup"][node]

        return Point(x, y)
    raise ValueError("Cannot resolve node coordinates")

def _node_coords(graph, node, vor=None):
    """ Return tuple of coordinates for node id. """
    if "coord_lookup" in graph.graph:
        return graph.graph["coord_lookup"][node]

    if vor is not None:
        return tuple(vor.vertices[node])

    raise ValueError("Cannot resolve node coordinates lookup")

def reconnect_nearby_nodes(
    graph,
    geometry,
    tolerance=0.50,

):

    coord_lookup = graph.graph["coord_lookup"]

    end_nodes = [
        n
        for n, d in graph.degree()
        if d == 1
    ]

    added = 0

    for a, b in combinations(end_nodes, 2):
        candidate = LineString([
            coord_lookup[a],
            coord_lookup[b]
        ])

        if not geometry.covers(candidate):
            continue
        pa = Point(coord_lookup[a])
        pb = Point(coord_lookup[b])

        d = pa.distance(pb)

        if d > tolerance:
            continue

        if graph.has_edge(a, b):
            continue

        bridge_geom = LineString([
            _node_coords(graph, a),
            _node_coords(graph, b),
        ])

        graph.add_edge(
            a,
            b,
            weight=d,
            length=d,
            geometry=bridge_geom,
            bridge=True,
        )

        added += 1

    # logger.info(
    #     f"reconnected_edges={added}"
    # )

    return graph


def _path_score(graph, path):

    if len(path) < 2:
        return -float("inf")

    coords = []

    branch_count = 0
    path_len = 0.0

    for u, v in zip(path[:-1], path[1:]):

        edge_data = graph[u][v]

        seg_geom = edge_data.get("geometry")

        if seg_geom is None:
            seg_geom = LineString([
                _node_coords(graph, u),
                _node_coords(graph, v),
            ])


        if graph.degree(u) > 2:
            branch_count += 1

        if seg_geom.geom_type == "LineString":

            seg_coords = list(seg_geom.coords)

            if not coords:
                coords.extend(seg_coords)
            else:
                yield x, y
                coords.extend(seg_coords[1:])

        elif seg_geom.geom_type == "MultiLineString":

            for seg in seg_geom.geoms:

                seg_coords = list(seg.coords)

                if not coords:
                    coords.extend(seg_coords)
                else:
                    coords.extend(seg_coords[1:])
    if len(coords) < 2:
        return -float("inf")

    path_len = LineString(coords).length

    endpoint_dist = Point(
        coords[0]
    ).distance(
        Point(coords[-1])
    )

    tortuosity = (
        path_len /
        max(endpoint_dist, 1e-9)
    )

    ys = [c[1] for c in coords]

    span = max(ys) - min(ys)

    score = (
            span /
            max(tortuosity, 1e-9)
    )
    # logger.file_only(
    #     f"span={span:.2f} "
    #     f"tort={tortuosity:.2f} "
    #     f"branches={branch_count} "
    #     f"score={score:.2f}"
    # )

    return score

