from itertools import combinations
import logging
import networkx as nx
import scipy.ndimage
from networkx.exception import NetworkXNoPath
import numpy as np
import operator
from scipy.spatial import Voronoi, cKDTree
from scipy.ndimage import gaussian_filter1d, distance_transform_edt
from shapely.geometry import LineString, MultiLineString, Point, MultiPoint
from skimage.morphology import skeletonize
from .exceptions import CenterlineError
from shapely import STRtree
import shapely.geometry as shp_geom
import shapely.ops as shp_ops

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

def filter_nodes_v2(geom:shp_geom.Point,
                    end_nodes:list,
                    max_dist=5)->list:
    """
    graph node contains the coordinates tuples
    end_nodes should within
    """
    if geom is None:
        return end_nodes

    return [node for node in end_nodes if Point(node).distance(geom) <= max_dist]

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
    max_terminal_angle=55,
    alpha=0.5,
    snap_clearance_weight=5.0,
    cell_size=1.0,
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
    try:
        logger.debug("geometry type %s", geom.geom_type)

        valid_endpoint_modes = {"strict", "soft"}
        if endpoint_mode not in valid_endpoint_modes:
            raise ValueError("endpoint_mode must be one of %s" % sorted(valid_endpoint_modes))

    valid_guided_strategies = {"pairwise", "virtual_nodes", "direct_insert", "main_route"}
    if guided_strategy not in valid_guided_strategies:
        raise ValueError("guided_strategy must be one of %s" % sorted(valid_guided_strategies))

    if geom.geom_type == "Polygon":
        # segmentized Polygon outline
        outline = _segmentize(geom.exterior, segmentize_maxlen)
        logger.debug("outline: %s", outline)
        valid_guided_strategies = {"pairwise", "virtual_nodes", "direct_insert", "main_route"}
        if guided_strategy not in valid_guided_strategies:
            raise ValueError("guided_strategy must be one of %s" % sorted(valid_guided_strategies))
        #Skeletonize and width analysis
        if geom.geom_type == "Polygon":
            #test corridor bottleneck
            #Automatically repair long 1-cell-wide raster corridors
            #until the Voronoi skeleton becomes essentially connected.
            BOTTLENECK_CELLS = 3
            MIN_NARROW_LENGTH = 5.0
            poly_mask = shp_rasterize(geom, cell_size)
            dist = distance_transform_edt(poly_mask)
            skel = skeletonize(poly_mask)
            width_cells = 2 * dist[skel]  #cells
            try:
                narrow = skel & (2 * dist <= BOTTLENECK_CELLS)
                labels, n = scipy.ndimage.label(narrow)
                max_narrow_pixels = 0
                for i in range(1, n + 1):
                    max_narrow_pixels = max(
                        max_narrow_pixels,
                        np.count_nonzero(labels == i))
                max_narrow_length = (max_narrow_pixels* cell_size)
            except Exception as e:
                import traceback
            long_skinny_risk = (
                    np.percentile(width_cells, 5) <= BOTTLENECK_CELLS
                    and
                    max_narrow_length >= MIN_NARROW_LENGTH
            )
            c_geom=geom
            if long_skinny_risk:
                for factor in [1.5,2.0]:
                    vor_geom = (geom.buffer(cell_size * factor))
                    outline_test = _segmentize(vor_geom.exterior,cell_size)
                    vor_test = Voronoi(outline_test.coords)
                    graph_test = _graph_from_voronoi(vor_test,vor_geom)
                    try:
                        largest_ratio = largest_component_ratio(graph_test)
                        if largest_ratio> 0.98:
                            c_geom = vor_geom
                            break
                    except Exception as e:
                        print(f"Test voronoi fail: {e}")
            coords = list(c_geom.exterior.coords)
            cleaned = [coords[0]]
            for pt in coords[1:]:
                if pt != cleaned[-1]:
                    cleaned.append(pt)
            c_geom=shp_geom.Polygon(cleaned).buffer(cell_size).buffer(-cell_size)
            # segmentized Polygon outline
            outline = _segmentize(c_geom.exterior, segmentize_maxlen)
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
            # simplify segmentized geometry if necessary and get points
            outline=segmentize_to_target_density(outline, min_points=3000, max_points=12000)
            outline_points = outline.coords

        # calculate Voronoi diagram and convert to graph but only use points
        # from within the original polygon
        vor = Voronoi(outline_points)
        graph = _graph_from_voronoi(vor, geom)
        logger.debug("voronoi diagram: %s", _multilinestring_from_voronoi(vor, geom))
            # calculate Voronoi diagram and convert to graph but only use points
            # from within the original polygon, graph nodes are store in coordinates
            vor = Voronoi(outline_points)
            graph = _graph_from_voronoi(vor, shp_geom.Polygon(outline))
            components = list(nx.connected_components(graph))
            try:
                if len(components)>1:
                    MIN_MAJOR_SIZE = 50
                    MAX_MAJOR_GAP = 1.0
                    MIN_INSIDE_RATIO = 0.99
                    MIN_RECOVERABEL_RATIO= 0.95
                    MAX_RECOVERABLE_GAP = 20.0
                    MAX_OUTSIDE_LENGTH = 1.0
                    MAX_SMALL_GAP = 4.5
                    # separate components into large (nodes>=20) or small (nodes<20)
                    #first merge the small components to nearest bigger compo
                    merged=True
                    merge_iter=0
                    while merged:

                        merge_iter+=1
                        # print(f"small merge iter={merge_iter}", flush=True)
                        merged=False
                        components = list(nx.connected_components(graph))
                        large = [(cid, comp) for cid, comp in enumerate(components) if len(comp) >= 20]
                        small = [(cid, comp) for cid, comp in enumerate(components) if 1<len(comp) < 20]

                        for small_id, small_comp in small:
                            best = None
                            for large_id, large_comp in large:
                                pair, dist = nearest_pair_ckdtree(
                                    small_comp,
                                    large_comp)
                                if best is None or dist < best[0]:
                                    best = (dist, pair,large_id)
                            if best is None:
                                continue

                            dist,pair,large_id=best
                            a = pair[0]
                            b = pair[1]
                            bridge = shp_geom.LineString([a,b])
                            if bridge.length == 0:
                                continue
                            if (    dist <= MAX_SMALL_GAP and
                                    bridge.covered_by(c_geom)):
                                before=nx.number_connected_components(graph)
                                graph.add_edge(a,b,weight=dist)
                                after=nx.number_connected_components(graph)
                                if after<before:
                                    merged=True

                                print(
                                        f"Merged small components "
                                        f"{small_id} ↔ {large_id}, "
                                        f"gap={dist:.3f}, "
                                        f"after merge:{nx.number_connected_components(graph)}"
                                    )
                                break
                        if merge_iter>500:
                            # print("above small merge",flush=True)
                            break
                    merged = True
                    while merged:
                        merged = False
                        components = sorted(
                            nx.connected_components(graph),
                            key=len,
                            reverse=True
                        )
                        major = [
                            comp
                            for comp in components
                            if len(comp) >= MIN_MAJOR_SIZE
                        ]

                        for i in range(len(major)):
                            for j in range(i + 1, len(major)):
                                pair, dist = nearest_pair_ckdtree(major[i], major[j])
                                a, b = pair
                                bridge = LineString([a, b])
                                if bridge.length==0:
                                    continue
                                # print("testing bridge",dist,flush=True)
                                inside_len = bridge.intersection(c_geom).length
                                outside_len = bridge.length - inside_len
                                inside_ratio = (inside_len/ bridge.length)
                                deg_a = graph.degree[a]
                                deg_b = graph.degree[b]
                                if (deg_a <=2 and deg_b <=2 and (
                                        (dist <= MAX_MAJOR_GAP and inside_ratio >= MIN_INSIDE_RATIO)
                                    or (dist <= MAX_RECOVERABLE_GAP and outside_len <= MAX_OUTSIDE_LENGTH
                                        and inside_ratio>=MIN_RECOVERABEL_RATIO))):
                                    graph.add_edge(a, b, weight=dist)
                                    merged = True
                                    break
                            if merged:
                                break
            except Exception:
                import traceback
                print(traceback.print_exc(),flush=True)
                raise
            logger.debug("voronoi diagram: %s", _multilinestring_from_voronoi(vor, c_geom))


            # determine longest path between all end nodes from graph
            end_nodes = _get_end_nodes(graph)
            if len(end_nodes) < 2:
                # list of nodes with <=2 neighbor node
                end_nodes = [i for i in graph.nodes() if len(list(graph.neighbors(i))) <= 2]
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
                    coords.append(tuple(_get_vertex_coords(n, vor, ext)))
                coords.append(dst_point.coords[0])
                deduped = [coords[0]]
                for c in coords[1:]:
                    if c != deduped[-1]:
                        deduped.append(c)
                centerline = _smooth_linestring_fixed_ends(LineString(deduped), smooth_sigma)
            guided_attempted = False
            if (
                guided_strategy == "direct_insert"
                and src_point is not None
                and dst_point is not None
            ):
                guided_attempted = True
                guided = _get_guided_path_direct_insert(
                    graph, vor, c_geom, src_point, dst_point,
                    max_terminal_angle, alpha,
                    enforce_angle=(endpoint_mode == "strict"),
                    snap_clearance_weight=snap_clearance_weight,
                )
                if guided is None and endpoint_mode == "strict":
                    logger.debug("direct_insert strict mode failed, retrying without angle guard")
                    guided = _get_guided_path_direct_insert(
                        graph, vor, c_geom, src_point, dst_point,
                        max_terminal_angle, alpha,
                        enforce_angle=False,
                        snap_clearance_weight=snap_clearance_weight,
                    )
                if guided is not None:
                    ext = guided.get("extended_coords", {})
                    coords = [src_point.coords[0]]
                    for n in guided["path"]:
                        coords.append(tuple(_get_vertex_coords(n, vor, ext)))
                    coords.append(dst_point.coords[0])
                    deduped = [coords[0]]
                    for c in coords[1:]:
                        if c != deduped[-1]:
                            deduped.append(c)
                    if len(deduped) < 2:
                        centerline = _smooth_linestring_fixed_ends(LineString([src_point.coords[0],dst_point.coords[0]]), smooth_sigma)
                    else:
                        centerline = _smooth_linestring_fixed_ends(LineString(deduped), smooth_sigma)

            elif (
                guided_strategy in {"pairwise", "virtual_nodes"}
                and src_point is not None
                and dst_point is not None
            ):
                guided_attempted = True
                src_nodes = filter_nodes_v2(src_geom, end_nodes)
                dst_nodes = filter_nodes_v2(dst_geom, end_nodes)
                if endpoint_mode=='strict':
                    src_candidates = _pick_endpoint_candidates_v2(
                        src_point,
                        dst_point,
                        graph,
                        c_geom,
                        endpoint_candidate_k,
                        preferred_nodes=src_nodes,
                    )
                    dst_candidates = _pick_endpoint_candidates_v2(
                        dst_point,
                        src_point,
                        graph,
                        c_geom,
                        endpoint_candidate_k,
                        preferred_nodes=dst_nodes,
                    )
                else:
                    src_candidates = nearest_nodes(src_point,graph,k=8)

                    dst_candidates = nearest_nodes(dst_point,graph,k=8)

            if guided_strategy == "virtual_nodes":
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
                if guided_strategy == "virtual_nodes":
                    guided = _get_guided_path_virtual(
                        graph,
                        vor,
                        c_geom,
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
                        c_geom,
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
                if guided_strategy == "virtual_nodes":
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
                if guided is None and endpoint_mode == "strict":
                    logger.debug("strict endpoint guidance exceeded angle guard, retrying without guard")
                    if guided_strategy == "virtual_nodes":
                        guided = _get_guided_path_virtual(
                            graph,
                            vor,
                            c_geom,
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
                            c_geom,
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
                        centerline = _line_from_nodes_with_anchors(path_nodes,  src_point, dst_point)
                        centerline = _smooth_linestring_fixed_ends(centerline, smooth_sigma)
                        centerline = trim_to_seed_projections(centerline, src_point, dst_point)

                    else:
                        coords=[node_to_xy(node,vor) for node in path_nodes]
                        coords=[src_point]+coords+[dst_point]
                        centerline = LineString(coords)
                        centerline = _smooth_linestring(centerline, smooth_sigma)
                        centerline = _soft_snap_centerline_to_endpoints(
                                centerline, src_point, dst_point, snap_tolerance
                            )

            if centerline is None and guided_attempted and endpoint_mode == "strict":
                print("endpoint_mode:",endpoint_mode,flush=True)
                print("guided_strategy:", guided_strategy, flush=True)
                logger.warning(
                    "endpoint-guided extraction failed in soft mode; "
                    "falling back to main-route longest-path extraction"
                )
                centerline=None
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
            if centerline is None:
                graph_nk = _graph_from_voronoi_nk(vor, c_geom)
                longest_paths = _get_main_route_longest_paths(graph_nk)
                if not longest_paths:
                    logger.debug("no paths found between end nodes")
                    raise CenterlineError("no paths found between end nodes")
                else:
                    longest_paths_xy = [[tuple(vor.vertices[idx]) for idx in path]
                                    for path in longest_paths]


                if len(longest_paths_xy)==1:
                    best_longest_paths_xy=longest_paths_xy[0]
                else:
                    # best_longest_paths_xy = max(longest_paths_xy,key=lambda p: LineString(p).length)
                    best_longest_paths_xy = min(longest_paths_xy, key=path_curvature)
                if logger.getEffectiveLevel() <= 10:
                    logger.debug("longest paths:")
                    logger.debug(LineString(best_longest_paths_xy))
                centerline = _smooth_linestring(LineString(best_longest_paths_xy),smooth_sigma)
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

    except Exception:
        import traceback
        print(traceback.format_exc(),flush=True)
        raise

from math import hypot
from scipy.spatial import cKDTree

def nearest_pair_ckdtree(comp_a, comp_b):
    nodes_a=list(comp_a)
    nodes_b=list(comp_b)

    arr_a = np.asarray(nodes_a,dtype=float)
    arr_b = np.asarray(nodes_b,dtype=float)

    if len(arr_a)==0 or len(arr_b)==0:
        return None,float("inf")

    tree=cKDTree(arr_b)
    #nearest node in comp_b for every node in comp_a
    dists,idx=tree.query(arr_a,k=1)
    #global minimum
    best_i=np.argmin(dists)
    a = nodes_a[best_i]
    b = nodes_b[idx[best_i]]
    # if a==b:
    #     print("duplicate snapped node",a)
    return ((a,b),float(dists[best_i]))


def nearest_pair_strtree(comp_a, comp_b):
    pts_b=[Point(x,y) for x,y in comp_b]
    tree_b=STRtree(pts_b)

    best_pair = None
    best_dist = float("inf")
    for a in comp_a:
        pa=Point(a)
        pb=tree_b.nearest(pa)
        d=pa.distance(pb)
        if d<best_dist:
            best_dist=d
            best_pair=(a,(pb.x,pb.y))
    return best_pair,best_dist

def nearest_pair(comp_a, comp_b):
    """
        Find nearest node pair
    """
    best_pair = None
    best_dist = float("inf")

    for a in comp_a:
        for b in comp_b:

            dist = hypot(
                a[0] - b[0],
                a[1] - b[1]
            )

            if dist < best_dist:
                best_dist = dist
                best_pair = (a, b)

    return best_pair, best_dist


def resample_polygon(poly, spacing):
    ring = shp_geom.LinearRing(poly.exterior.coords)

    n = int(np.ceil(ring.length / spacing))

    coords = [
        ring.interpolate(i * ring.length / n).coords[0]
        for i in range(n)
    ]

    coords.append(coords[0])  # close ring

    return shp_geom.Polygon(coords)




def get_centerline_fr_dissolved_corrider(
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
    logger.debug("geometry type %s", geom.geom_type)
    src_point = _as_endpoint_point(src_geom)
    dst_point = _as_endpoint_point(dst_geom)
    valid_endpoint_modes = {"strict", "soft"}
    if endpoint_mode not in valid_endpoint_modes:
        raise ValueError("endpoint_mode must be one of %s" % sorted(valid_endpoint_modes))

    valid_guided_strategies = {"pairwise", "virtual_nodes", "direct_insert", "main_route"}
    if guided_strategy not in valid_guided_strategies:
        raise ValueError("guided_strategy must be one of %s" % sorted(valid_guided_strategies))

    if geom.geom_type == "Polygon":



        coords = list(geom.exterior.coords)
        cleaned = [coords[0]]
        for pt in coords[1:]:
            if pt != cleaned[-1]:
                cleaned.append(pt)
        c_geom=shp_geom.Polygon(cleaned)
        # segmentized Polygon outline
        outline = _segmentize(c_geom.exterior, segmentize_maxlen)
        logger.debug("outline: %s", outline)

        # simplify segmentized geometry if necessary and get points
        outline_points = outline.coords
        simplification_updated = simplification
        try:
            while len(outline_points) > max_points:
                # if geometry is too large, apply simplification until geometry
                # is simplified enough (indicated by the "max_points" value)
                simplification_updated += simplification
                outline_points = outline.simplify(simplification_updated).coords
        except Exception:
            import traceback
            print(traceback.format_exc(),flush=True)
            raise
        logger.debug("simplification used: %s", simplification_updated)
        logger.debug("simplified points: %s", MultiPoint(outline_points))

        # calculate Voronoi diagram and convert to graph but only use points
        # from within the original polygon
        vor = Voronoi(np.array(outline_points),qhull_options="Qbb Qc Qz")
        graph = _graph_from_voronoi_v2(vor, c_geom)
        src_node = min(
            graph.nodes,
            key=lambda n: Point(n).distance(src_point)
        )

        dst_node = min(
            graph.nodes,
            key=lambda n: Point(n).distance(dst_point)
        )
        if nx.has_path(graph, src_node, dst_node):
            path = nx.shortest_path(
            graph,
            src_node,
            dst_node,
            weight="weight"
            )
            centerline = LineString(path)
        logger.debug("voronoi diagram: %s", _multilinestring_from_voronoi(vor, geom))
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
    points = [geom.coords[0]]

    for previous, current in zip(geom.coords, geom.coords[1:]):

        seg = LineString([previous, current])

        n = max(1, int(np.ceil(seg.length / max_len)))

        for i in range(1, n):
            points.append(
                seg.interpolate(i * seg.length / n).coords[0]
            )

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

def _pick_endpoint_candidates_v2(
    point,
    other_point,
    graph,
    geometry,
    candidate_k,
    preferred_nodes=None,
):

    preferred_nodes = preferred_nodes or []

    filtered_preferred = [
        node
        for node in preferred_nodes
        if node in graph
    ]

    available_nodes = list(filtered_preferred)

    available_nodes.extend(
        nearest_nodes(
            point.coords[0],
            graph,
            k=50
        )
    )

    available_nodes = list(
        dict.fromkeys(available_nodes)
    )

    scored = []

    point_xy = np.array(point.coords[0])
    other_xy = np.array(other_point.coords[0])

    corridor_dir = other_xy - point_xy
    corridor_norm = np.linalg.norm(corridor_dir)

    for node in available_nodes:

        node_xy = np.array(node)

        dist = point.distance(Point(node))

        boundary_dist = geometry.boundary.distance(
            Point(node)
        )

        alignment = 0.0

        candidate_dir = node_xy - point_xy
        candidate_norm = np.linalg.norm(candidate_dir)

        if corridor_norm > 0 and candidate_norm > 0:

            alignment = np.dot(
                corridor_dir / corridor_norm,
                candidate_dir / candidate_norm
            )

            if alignment < 0:
                continue

        score = (
            dist
            + (0.2 / max(boundary_dist, 0.1))
            + (1.0 - alignment) * 100.0
        )

        if node in filtered_preferred:
            score *= 0.6

        scored.append(
            (score, node)
        )

    scored.sort(key=lambda x: x[0])

    return [
        node
        for score, node in scored[:candidate_k]
    ]


def _alignment_score(seed_xy, other_seed_xy, candidate_xy):
    """
    Returns alignment in [-1, 1]

     1 = perfect direction
     0 = perpendicular
    -1 = opposite direction
    """

    corridor_dir = np.array(other_seed_xy) - np.array(seed_xy)
    cand_dir = np.array(candidate_xy) - np.array(seed_xy)

    nc = np.linalg.norm(corridor_dir)
    nd = np.linalg.norm(cand_dir)

    if nc == 0 or nd == 0:
        return -1.0

    corridor_dir /= nc
    cand_dir /= nd

    return float(np.dot(corridor_dir, cand_dir))




def trim_to_seed_projections(line, src_point, dst_point):

    src_d = line.project(src_point)
    dst_d = line.project(dst_point)

    start_d = min(src_d, dst_d)
    end_d = max(src_d, dst_d)

    trimmed = shp_ops.substring(line, start_d, end_d)

    coords = list(trimmed.coords)

    coords[0] = src_point.coords[0]
    coords[-1] = dst_point.coords[0]

    return LineString(coords)



def _build_medial_weighted_graph(graph, vor, geometry, alpha):
    """Build graph with edge costs biased to medial regions."""
    weighted = nx.Graph()
    for u, v in graph.edges():
        p1 = Point(node_to_xy(u,vor))
        p2 = Point(node_to_xy(v,vor))
        length = p1.distance(p2)
        clearance = min(geometry.boundary.distance(p1), geometry.boundary.distance(p2))
        weight = length / max(clearance, 1e-6) ** alpha
        weighted.add_edge(u, v, weight=weight)
    return weighted


def _build_medial_weighted_graph_nk(graph, vor, geometry, alpha):
    """Build NetworKit graph with edge costs biased to medial regions."""
def _build_medial_weighted_graph_nk(
    graph,
    geometry,
    alpha,
):

    nodes = list(graph.nodes())
    if not nodes:
        return None, {}, {}

    node_to_id = {
        node: idx
        for idx, node in enumerate(nodes)
    }

    id_to_node = {
        idx: node
        for node, idx in node_to_id.items()
    }

    weighted_nk = nk.graph.Graph(
        len(nodes),
        weighted=True
    )

    for u, v in graph.edges():

        p1 = Point(u)
        p2 = Point(v)

        length = p1.distance(p2)

        clearance = min(
            geometry.boundary.distance(p1),
            geometry.boundary.distance(p2)
        )

        weight = (
            length
            / max(clearance, 1e-6) ** alpha
        )

        weighted_nk.addEdge(
            node_to_id[u],
            node_to_id[v],
            weight
        )

    return weighted_nk, node_to_id, id_to_node



def _nk_shortest_path_and_cost(graph_nk, src_node, dst_node):
    """Return shortest path and cost from NetworKit, or None if unreachable."""
    node_count = graph_nk.numberOfNodes()

    if (
            src_node < 0
            or dst_node < 0
            or src_node >= node_count
            or dst_node >= node_count
    ):
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
def _line_from_nodes_with_anchors(path_nodes, src_point, dst_point,vor=None):

    if not path_nodes:
        return LineString([src_point.coords[0],dst_point.coords[0]])
    coords = [src_point.coords[0]]
    coords.extend(node_to_xy(node,vor) for node in path_nodes)
    coords.append(dst_point.coords[0])
    deduped = [coords[0]]
    for coord in coords[1:]:
        if coord != deduped[-1]:
            deduped.append(coord)
    if len(deduped)<=2:
        return LineString([src_point.coords[0],dst_point.coords[0]])
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


def _terminal_deflection_angle(path,src_point, dst_point):
    """Get worst terminal deflection angle in degrees."""
    if len(path) < 2:
        return 0.0

    src_xy = np.array(src_point.coords[0])
    dst_xy = np.array(dst_point.coords[0])
    start_xy = np.array([path[0]])
    start_next_xy = np.array([path[1]])
    end_xy = np.array([path[-1]])
    end_prev_xy = np.array([path[-2]])
    corridor_dir = dst_xy - src_xy

    start_dir = start_next_xy - start_xy

    start_angle = _angle_between_vectors(
        corridor_dir,
        start_dir
    )
    start_angle = min(start_angle, 180 - start_angle)

    end_dir = end_xy - end_prev_xy

    end_angle = _angle_between_vectors(
        corridor_dir,
        end_dir
    )
    end_angle = min(end_angle, 180 - end_angle)
    # print("src connector:", start_xy - src_xy)
    # print("path start dir:", start_next_xy - start_xy)
    #
    # print("dst connector:", dst_xy - end_xy)
    # print("path end dir:", end_xy - end_prev_xy)

    return max(start_angle, end_angle)


def _angle_between_vectors(v1, v2):
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    cosang = np.dot(v1, v2) / (n1 * n2)
    # cosang = max(-1.0, min(1.0, cosang))
    cosang = np.clip(cosang, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosang)))


def _get_guided_path(
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
    """Get best endpoint-guided path between candidate node sets."""
    if not src_candidates or not dst_candidates:
        return None

    weighted_nk,node_to_id, id_to_node = _build_medial_weighted_graph_nk(graph, geometry, alpha)
    best = None

    for src_node in src_candidates:
        for dst_node in dst_candidates:
            if src_node == dst_node:
                continue
            solved = _nk_shortest_path_and_cost(weighted_nk, node_to_id[src_node], node_to_id[dst_node])
            if solved is None:
                continue
            path_ids, score = solved

            path = [
                id_to_node[node_id]
                for node_id in path_ids
            ]
            # print("path length:", len(path))
            # print("unique:", len(set(path)))
            # for n in path:
            #     d = graph.degree(n)
            #     if d > 2:
            #         print("junction:", n, "degree:", d)

            src_connector_cost = _endpoint_connector_cost(src_point, src_node,  geometry)
            dst_connector_cost = _endpoint_connector_cost(dst_point, dst_node,  geometry)
            # terminal_angle = _terminal_deflection_angle(path, vor.vertices, src_point, dst_point)
            start_angle, end_angle = _terminal_angles(path,src_point,dst_point)
            effective_limit = max(max_terminal_angle, 55.0)
            try:
                if enforce_angle:
                    if start_angle > effective_limit:
                        continue
                    if end_angle > effective_limit:
                        continue
            except Exception:
                import traceback
                print(traceback.format_exc(), flush=True)
                raise
            terminal_penalty = (start_angle +end_angle )

            total_score = (
                score + src_connector_cost + dst_connector_cost + ANGLE_PENALTY_WEIGHT * terminal_penalty
            )
            candidate = {
                "path": path,
                "score": total_score,
                "start_angle": start_angle,
                "end_angle": end_angle,
            }
            if best is None or candidate["score"] < best["score"]:
                best = candidate
    return best


def _endpoint_connector_cost(endpoint_point, node, geometry):
    """Cost for connecting endpoint anchor to real graph node."""
    # node_point = Point(vor.vertices[node])
    node_point = Point(node)
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
            weight=_endpoint_connector_cost(src_point, node,  geometry),
        )
        src_added += 1

    dst_added = 0
    for node in dst_candidates:
        if node not in augmented:
            continue
        augmented.add_edge(
            dst_virtual,
            node,
            weight=_endpoint_connector_cost(dst_point, node,  geometry),
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

            terminal_angle = _terminal_deflection_angle(path, src_point, dst_point)
            try:
                if enforce_angle and terminal_angle > max_terminal_angle:
                    continue
            except Exception:
                import traceback
                print(traceback.format_exc(), flush=True)
                raise

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


def _get_vertex_coords(node, vor, extended_coords):
    """Get coordinates for a graph node, checking extended coords first."""
    if extended_coords and node in extended_coords:
        return extended_coords[node]
    return node_to_xy(node,vor)


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
        p1 = np.array(_get_vertex_coords(u, vor, extended_coords))
        p2 = np.array(_get_vertex_coords(v, vor, extended_coords))
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
    # new_id = max(weighted_graph.nodes()) + 1
    new_id=(float(best_projected[0]),best_projected[1])
    extended_coords[new_id] = best_projected

    weighted_graph.remove_edge(u, v)
    p_new = Point(best_projected)
    clearance_new = geometry.boundary.distance(p_new)

    for nbr in (u, v):
        nbr_coords = _get_vertex_coords(nbr, vor, extended_coords)
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
    weighted = _build_medial_weighted_graph(graph, vor, geometry, alpha)
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
    start_xy = np.array(_get_vertex_coords(path[0], vor, extended_coords))
    next_xy = np.array(_get_vertex_coords(path[1], vor, extended_coords))
    end_xy = np.array(_get_vertex_coords(path[-1], vor, extended_coords))
    prev_xy = np.array(_get_vertex_coords(path[-2], vor, extended_coords))
    src_xy = np.array(src_point.coords[0])
    dst_xy = np.array(dst_point.coords[0])

    start_angle = _angle_between_vectors(start_xy - src_xy, next_xy - start_xy)
    end_angle = _angle_between_vectors(prev_xy - end_xy, dst_xy - end_xy)
    terminal_angle = max(start_angle, end_angle)
    try:
        if enforce_angle and terminal_angle > max_terminal_angle:
            return None
    except Exception:
        import traceback
        print(traceback.format_exc(), flush=True)
        raise

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
    distance.sort(key=operator.itemgetter(2), reverse=True)
    longest = distance[0]
    dijkstra = nk.distance.Dijkstra(graph_nk, longest[0], True, False, longest[1])
    dijkstra.run()
    longest_path = dijkstra.getPath(longest[1])
    if not longest_path:
        return []
    longest_paths= [[int(i) for i in longest_path]]
    return longest_paths


def _get_least_curved_path(paths, vertices):
    """Return path with smallest angles."""
    return min(
        zip([_get_path_angles_sum(path, vertices) for path in paths], paths),
        key=operator.itemgetter(0),
    )[1]

def path_curvature(coords):

    if len(coords) < 3:
        return 0

    total = 0

    for i in range(1, len(coords) - 1):

        p0 = np.array(coords[i - 1])
        p1 = np.array(coords[i])
        p2 = np.array(coords[i + 1])

        v1 = p1 - p0
        v2 = p2 - p1

        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)

        if n1 == 0 or n2 == 0:
            continue

        cosang = np.clip(
            np.dot(v1, v2) / (n1 * n2),
            -1.0,
            1.0,
        )

        total += np.arccos(cosang)

    return total




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
    for x, y, dist in _yield_ridge_vertices_v2(vor, geometry, dist=True):
        graph.add_nodes_from([x, y])
        graph.add_edge(x, y, weight=dist)
    return graph

def _graph_from_voronoi_v2(vor, geometry):
    """Return networkx.Graph from Voronoi diagram within geometry."""
    graph = nx.Graph()
    for x, y, dist in _yield_ridge_vertices_v2(vor, geometry, dist=True):
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


def _yield_ridge_vertices_v2(vor, geometry, dist=False):
    """Yield Voronoi ridge vertices within geometry."""
    def snap(pt,precision=5):
        return (
            round(pt[0],precision),
            round(pt[1],precision),
        )

    for x, y in vor.ridge_vertices:

        if x < 0 or y < 0:
            continue

        ridge = LineString([
            vor.vertices[x],
            vor.vertices[y]
        ])
        if ridge.within(geometry):
            clipped=ridge

        else:
            clipped = ridge.intersection(geometry)

        if clipped.is_empty:
            continue

        if clipped.geom_type == "LineString":

            coords = list(clipped.coords)

            for i in range(len(coords) - 1):

                u = snap(coords[i])
                v = snap(coords[i + 1])
                if u==v:
                    continue
                if dist:
                    yield u, v, LineString([u, v]).length
                else:
                    yield u, v

        elif clipped.geom_type == "MultiLineString":

            for seg in clipped.geoms:

                coords = list(seg.coords)

                for i in range(len(coords) - 1):

                    u = snap(coords[i])
                    v = snap(coords[i + 1])

                    if dist:
                        yield u, v, LineString([u, v]).length
                    else:
                        yield u, v


def _terminal_angles(path, src_point, dst_point):
    """
    Returns:
        start_angle, end_angle
    """

    if len(path) < 2:
        return 180.0, 180.0

    src_xy = np.array(src_point.coords[0])
    dst_xy = np.array(dst_point.coords[0])

    #
    # Start angle
    #
    first_vertex = np.array(path[0])
    second_vertex = np.array(path[1])

    corridor_dir = dst_xy - src_xy
    start_dir = second_vertex - src_xy

    start_angle = _angle_between_vectors(
        corridor_dir,
        start_dir
    )

    #
    # End angle
    #
    last_vertex = np.array(path[-1])
    prev_vertex = np.array(path[-2])

    end_corridor_dir = src_xy - dst_xy
    end_dir = prev_vertex - dst_xy

    end_angle = _angle_between_vectors(
        end_corridor_dir,
        end_dir
    )

    return start_angle, end_angle



def _get_graph_diameter_path(graph):
    terminals = [
        n
        for n in graph.nodes()
        if graph.degree(n) == 1
    ]

    if len(terminals) < 2:
        return None

    best_path = None
    best_length = -1

    for src in terminals:

        lengths, paths = nx.single_source_dijkstra(
            graph,
            src,
            weight="weight"
        )

        for dst in terminals:

            if dst == src:
                continue

            if dst not in lengths:
                continue

            length = lengths[dst]

            try:
                if length > best_length:
                    best_length = length
                    best_path = paths[dst]
            except Exception:
                import traceback
                print(traceback.format_exc(), flush=True)
                raise

    return best_path


def nk_to_nx(weighted_nk, id_to_node):
    g = nx.Graph()

    for u, v in weighted_nk.iterEdges():
        gu = id_to_node[u]
        gv = id_to_node[v]

        g.add_edge(
            gu,
            gv,
            weight=weighted_nk.weight(u, v)
        )

    return g

def corridor_width(node_xy, polygon):
    return 2.0 * Point(node_xy).distance(polygon.boundary)

def is_narrow(node_xy, polygon, cell_size):
    width = corridor_width(node_xy, polygon)
    return width <= 2 * cell_size

def narrow_length(graph, polygon, cell_size):
    total = 0.0

    for u, v in graph.edges:

        wu = corridor_width(u, polygon)
        wv = corridor_width(v, polygon)

        if (
            wu <= 2 * cell_size
            and
            wv <= 2 * cell_size
        ):
            total += LineString([u, v]).length

    return total

def has_long_narrow_section(
        graph,
        polygon,
        cell_size,
        max_width_cells=2,
        min_length_cells=20):

    narrow_length = 0

    for u, v in graph.edges:

        wu = 2 * Point(u).distance(
            polygon.boundary
        )

        wv = 2 * Point(v).distance(
            polygon.boundary
        )

        if (
            wu <= max_width_cells * cell_size and
            wv <= max_width_cells * cell_size
        ):
            narrow_length += (
                LineString([u, v]).length
            )

    return (
        narrow_length >
        min_length_cells * cell_size
    )

def shp_rasterize(in_geom,cell_size):
    import numpy as np
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    # Shapely polygon
    poly = in_geom

    minx, miny, maxx, maxy = poly.bounds

    width = int(np.ceil((maxx - minx) / cell_size))
    height = int(np.ceil((maxy - miny) / cell_size))

    transform = from_origin(
        minx,
        maxy,
        cell_size,
        cell_size
    )

    mask = rasterize(
        [(poly, 1)],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype=np.uint8
    )
    # profile = {
    #     'driver': 'GTiff',
    #     'height': mask.shape[0],
    #     'width': mask.shape[1],
    #     'count': 1,
    #     'dtype': mask.dtype,
    #     'crs': 'EPSG:22812',
    #     'transform': transform
    # }

    return mask.astype(bool)


def longest_run(mask):
    longest = current = 0

    for v in mask:
        if v:
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    return longest

def largest_component_ratio(graph):

    if graph.number_of_nodes() == 0:
        return 0

    comps = list(nx.connected_components(graph))

    largest = max(len(c) for c in comps)

    return largest / graph.number_of_nodes()


def component_ratio(graph):
    ratio=[]
    if graph.number_of_nodes() == 0:
        return 0

    comps = list(nx.connected_components(graph))

    for comp in comps:
       ratio.append(len(comp)/graph.number_of_nodes())

    return ratio




def nearest_nodes(
        pt,
        graph,
        k=5,
        max_distance=None):

    p = Point(pt)

    candidates = []

    for node in graph.nodes:

        d = p.distance(Point(node))

        if (
            max_distance is not None
            and d > max_distance
        ):
            continue

        candidates.append((d, node))

    candidates.sort(key=lambda x: x[0])

    return [node for d, node in candidates[:k]]


def segmentize_to_target_density(
        line,
        min_points=3000,
        max_points=12000,
        initial_spacing=1.0):
    n0=len(line.coords)
    if min_points <= n0 <=max_points:
        return line

    if n0>max_points:
        spacing=line.length/max_points
    else:
        spacing=line.length/min_points

    return _segmentize(line, spacing)


def node_to_xy(node,vor=None):
    """
    Accept either
        -Voronoi vertex id(int)
        -coordinate tuple (x,y)
        -numpy coordinate array

    Return:
        (x,y) tuple of floats
    """
    if isinstance(node,(tuple,list,np.ndarray)):
        if len(node)==2:
            return float(node[0]),float(node[1])
    if isinstance(node,(int,np.integer)):
         if vor is None:
             raise ValueError("vor is required for vertex ids")

         xy=vor.vertices[node]
         return float(xy[0]),float(xy[1])

    raise TypeError(f"Unsupported node type: {type(node)}")
