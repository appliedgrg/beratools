"""Per-line vertex preclean helpers for line optimization workflows."""

import logging
import math

import geopandas as gpd
import pyproj
from shapely import ops as sh_ops
from shapely.geometry import LineString, Point
import shapely.geometry as sh_geom

import beratools.core.constants as bt_const
import beratools.core.algo_common as algo_common

try:
    import rasterio
except Exception:
    rasterio = None

logger = logging.getLogger(__name__)


class VertexPrecleaner:
    VALID_MODES = {"full", "endpoint_only"}

    def __init__(self, close_distance, angle_tol):
        self.close_distance = float(close_distance)
        self.angle_tol = float(angle_tol)

    @staticmethod
    def _point_distance(coord_a, coord_b):
        return math.hypot(coord_b[0] - coord_a[0], coord_b[1] - coord_a[1])

    def _bend_score(self, coord_a, coord_b, coord_c):
        v1x = coord_b[0] - coord_a[0]
        v1y = coord_b[1] - coord_a[1]
        v2x = coord_c[0] - coord_b[0]
        v2y = coord_c[1] - coord_b[1]

        norm1 = math.hypot(v1x, v1y)
        norm2 = math.hypot(v2x, v2y)
        if norm1 <= bt_const.SMALL_BUFFER or norm2 <= bt_const.SMALL_BUFFER:
            return 180.0

        dot = v1x * v2x + v1y * v2y
        cos_val = max(-1.0, min(1.0, dot / (norm1 * norm2)))
        return math.degrees(math.acos(cos_val))

    def _shape_loss(self, work_coords, remove_index):
        prev_coord = work_coords[remove_index - 1] if remove_index - 1 >= 0 else None
        curr_coord = work_coords[remove_index]
        next_coord = work_coords[remove_index + 1] if remove_index + 1 < len(work_coords) else None

        old_scores = []
        if prev_coord is not None and remove_index - 2 >= 0:
            old_scores.append(self._bend_score(work_coords[remove_index - 2], prev_coord, curr_coord))
        if next_coord is not None and remove_index + 2 < len(work_coords):
            old_scores.append(self._bend_score(curr_coord, next_coord, work_coords[remove_index + 2]))
        if prev_coord is not None and next_coord is not None:
            old_scores.append(self._bend_score(prev_coord, curr_coord, next_coord))

        new_scores = []
        if prev_coord is not None and next_coord is not None:
            if remove_index - 2 >= 0:
                new_scores.append(self._bend_score(work_coords[remove_index - 2], prev_coord, next_coord))
            if remove_index + 2 < len(work_coords):
                new_scores.append(self._bend_score(prev_coord, next_coord, work_coords[remove_index + 2]))

        old_peak = max(old_scores) if old_scores else 0.0
        new_peak = max(new_scores) if new_scores else 0.0
        significant_penalty = 50.0 if old_peak > self.angle_tol and new_peak <= self.angle_tol else 0.0
        return abs(old_peak - new_peak) + significant_penalty

    def _dedupe_consecutive_coords(self, coords):
        if not coords:
            return []

        work_coords = [coords[0]]
        for coord in coords[1:]:
            if self._point_distance(work_coords[-1], coord) > bt_const.SMALL_BUFFER:
                work_coords.append(coord)

        return work_coords

    def _finalize_line(self, coords, original_line):
        if len(coords) < 2:
            return None

        if self._point_distance(coords[0], coords[-1]) <= bt_const.SMALL_BUFFER:
            return None

        if len(coords) == len(original_line.coords):
            return original_line

        return sh_geom.LineString(coords)

    def _cleanup_endpoint_only(self, coords):
        while len(coords) > 2 and self._point_distance(coords[0], coords[1]) < self.close_distance:
            coords.pop(1)

        while len(coords) > 2 and self._point_distance(coords[-2], coords[-1]) < self.close_distance:
            coords.pop(-2)

        return coords

    def cleanup_line(self, line, mode="full"):
        if mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported vertex cleanup mode: {mode}")

        coords = [tuple(coord) for coord in line.coords]
        if len(coords) <= 2:
            return line

        work_coords = self._dedupe_consecutive_coords(coords)
        if len(work_coords) <= 2:
            return self._finalize_line(work_coords, line)

        work_coords = self._cleanup_endpoint_only(work_coords)
        if mode == "endpoint_only":
            return self._finalize_line(work_coords, line)

        i = 1
        while i < len(work_coords) - 2:
            left_coord = work_coords[i]
            right_coord = work_coords[i + 1]
            if self._point_distance(left_coord, right_coord) >= self.close_distance:
                i += 1
                continue

            left_score = self._bend_score(work_coords[i - 1], left_coord, right_coord)
            right_score = self._bend_score(left_coord, right_coord, work_coords[i + 2])

            if left_score > self.angle_tol and right_score <= self.angle_tol:
                remove_index = i + 1
            elif right_score > self.angle_tol and left_score <= self.angle_tol:
                remove_index = i
            else:
                remove_left_loss = self._shape_loss(work_coords, i)
                remove_right_loss = self._shape_loss(work_coords, i + 1)
                remove_index = i if remove_left_loss <= remove_right_loss else i + 1

            work_coords.pop(remove_index)
            if i > 1:
                i -= 1

        return self._finalize_line(work_coords, line)

    def remove_close_vertices(self, gdf, mode="full"):
        if mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported vertex cleanup mode: {mode}")

        if gdf is None or gdf.empty:
            return gdf

        if isinstance(gdf, gpd.GeoSeries):
            gdf = gpd.GeoDataFrame(geometry=gdf)

        out_gdf = gdf.copy()

        if any(getattr(geom, "geom_type", None) == "MultiLineString" for geom in out_gdf.geometry):
            out_gdf = out_gdf.explode(index_parts=False)

        cleaned_geoms = []
        for geom in out_gdf.geometry:
            if geom is None or geom.is_empty:
                cleaned_geoms.append(None)
                continue

            if geom.geom_type != "LineString":
                cleaned_geoms.append(geom)
                continue

            cleaned_geoms.append(self.cleanup_line(geom, mode=mode))

        geom_series = gpd.GeoSeries(cleaned_geoms, index=out_gdf.index, crs=out_gdf.crs)
        valid_mask = geom_series.notna() & ~geom_series.is_empty
        out_gdf = out_gdf.loc[valid_mask].copy()
        out_gdf.set_geometry(geom_series.loc[valid_mask], inplace=True)
        out_gdf = out_gdf[out_gdf.geometry.length > bt_const.SMALL_BUFFER]
        out_gdf = gpd.GeoDataFrame(out_gdf, crs=gdf.crs)
        out_gdf.reset_index(drop=True, inplace=True)

        return out_gdf


def _iter_line_parts(geom):
    if geom is None or geom.is_empty:
        return []

    if geom.geom_type == "LineString":
        return [geom]

    if geom.geom_type == "MultiLineString":
        return [part for part in geom.geoms if part and not part.is_empty and part.geom_type == "LineString"]

    if geom.geom_type == "GeometryCollection":
        parts = []
        for item in geom.geoms:
            parts.extend(_iter_line_parts(item))
        return parts

    return []


def _normalize_to_lines(gdf):
    if gdf is None:
        return gdf

    if gdf.empty:
        return gdf

    exploded = gdf.explode(index_parts=False).reset_index(drop=True)
    records = []

    for _, row in exploded.iterrows():
        line_parts = _iter_line_parts(row.geometry)
        if not line_parts:
            continue

        row_dict = row.to_dict()
        for line_geom in line_parts:
            rec = row_dict.copy()
            rec["geometry"] = line_geom
            records.append(rec)

    return gpd.GeoDataFrame(records, columns=gdf.columns, crs=gdf.crs)


def _require_crs(gdf, parameter_label):
    crs = pyproj.CRS.from_user_input(gdf.crs) if gdf.crs else None
    if crs is None:
        raise ValueError(f"Input line CRS is missing; cannot apply '{parameter_label}'.")
    return crs


def _build_linear_unit_context(crs, reference_geom):
    if crs.is_geographic:
        if reference_geom is None or reference_geom.is_empty:
            raise ValueError("Unable to determine reference geometry for geographic CRS unit conversion.")
        ref_point = reference_geom.representative_point()
        metric_crs = pyproj.CRS.from_proj4(
            f"+proj=aeqd +lat_0={ref_point.y} +lon_0={ref_point.x} +datum=WGS84 +units=m +no_defs"
        )
        to_metric = pyproj.Transformer.from_crs(crs, metric_crs, always_xy=True)
        to_source = pyproj.Transformer.from_crs(metric_crs, crs, always_xy=True)
        return {
            "is_geographic": True,
            "to_metric": to_metric,
            "to_source": to_source,
            "unit_factor": None,
        }

    unit_factor = crs.axis_info[0].unit_conversion_factor if crs.axis_info else None
    if unit_factor is None or unit_factor <= 0:
        raise ValueError("Unable to determine projected CRS linear units.")
    return {
        "is_geographic": False,
        "to_metric": None,
        "to_source": None,
        "unit_factor": unit_factor,
    }


def _meters_to_native_units(distance_m, unit_ctx):
    if unit_ctx["is_geographic"]:
        return float(distance_m)
    return float(distance_m) / float(unit_ctx["unit_factor"])


def _geometry_length_meters(geom, unit_ctx):
    if geom is None or geom.is_empty:
        return 0.0
    if unit_ctx["is_geographic"]:
        geom_metric = sh_ops.transform(unit_ctx["to_metric"].transform, geom)
        return float(geom_metric.length)
    return float(geom.length) * float(unit_ctx["unit_factor"])


def _geographic_raster_cell_size_m(src, crs, x_res, y_res):
    geod = crs.get_geod()
    if geod is None:
        raise ValueError("Unable to build geodesic calculator for geographic CRS.")

    bounds = src.bounds
    center_x = float((bounds.left + bounds.right) / 2.0)
    center_y = float((bounds.bottom + bounds.top) / 2.0)
    max_lat = 89.999999
    min_lat = -89.999999
    y_for_dx = min(max(center_y, min_lat), max_lat)
    y_start = min(max(center_y, min_lat), max_lat)
    y_for_dy = min(max(center_y + float(y_res), min_lat), max_lat)
    dist_x = abs(geod.inv(center_x, y_for_dx, center_x + float(x_res), y_for_dx)[2])
    dist_y = abs(geod.inv(center_x, y_start, center_x, y_for_dy)[2])
    return min(dist_x, dist_y)


def _default_close_distance_m(in_raster):
    fallback = 2.0
    max_auto_default = 30.0

    def _fallback(reason, exc=None):
        if exc is None:
            logger.warning(
                "Using fallback preclean distance %.2f m: %s (raster=%s)",
                fallback,
                reason,
                in_raster,
            )
        else:
            logger.warning(
                "Using fallback preclean distance %.2f m: %s (raster=%s, error=%s)",
                fallback,
                reason,
                in_raster,
                exc,
            )
        return fallback

    if not in_raster or rasterio is None:
        reason = "missing input raster"
        if rasterio is None:
            reason = "rasterio unavailable"
        return _fallback(reason)

    try:
        with rasterio.open(in_raster) as src:
            crs = pyproj.CRS.from_user_input(src.crs) if src.crs else None
            if crs is None:
                return _fallback("raster CRS missing or unreadable")

            x_res, y_res = src.res
            cell_size_native = min(abs(float(x_res)), abs(float(y_res)))
            if math.isclose(cell_size_native, 0.0):
                return _fallback("raster resolution is zero")

            if crs.is_geographic:
                try:
                    cell_size_m = _geographic_raster_cell_size_m(src, crs, x_res, y_res)
                except ValueError as exc:
                    return _fallback(str(exc))
            else:
                unit_factor = crs.axis_info[0].unit_conversion_factor if crs.axis_info else None
                if unit_factor is None or unit_factor <= 0:
                    return _fallback("unable to determine projected CRS linear unit factor")
                cell_size_m = cell_size_native * float(unit_factor)

            if math.isclose(cell_size_m, 0.0):
                return _fallback("computed metric cell size is zero")
            inferred_default = 1.5 * float(cell_size_m)
            return float(min(max_auto_default, max(fallback, inferred_default)))
    except Exception as exc:
        return _fallback("failed to derive raster-based default", exc=exc)


def _preclean_lines_full(gdf, close_distance_m, angle_tol_deg):
    if gdf.empty:
        return gdf, gdf.iloc[0:0].copy()

    valid_mask = ~gdf.geometry.isna() & ~gdf.geometry.is_empty
    out = gdf[valid_mask].copy()
    rejected = gdf[~valid_mask].copy()
    if out.empty:
        return out.reset_index(drop=True), rejected.reset_index(drop=True)

    crs = _require_crs(out, "Preclean close distance (m)")
    precleaner = VertexPrecleaner(close_distance=close_distance_m, angle_tol=angle_tol_deg)
    cleaned_records = []
    removed_records = []

    if crs.is_geographic:
        reference_geom = out.unary_union.envelope
        unit_ctx = _build_linear_unit_context(crs, reference_geom)
        for _, row in out.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty or geom.geom_type != "LineString":
                rec = row.to_dict()
                if geom is None or geom.is_empty:
                    removed_records.append(rec)
                else:
                    cleaned_records.append(rec)
                continue

            geom_metric = sh_ops.transform(unit_ctx["to_metric"].transform, geom)
            cleaned_metric = precleaner.cleanup_line(geom_metric, mode="full")
            if cleaned_metric is None or cleaned_metric.is_empty:
                removed_records.append(row.to_dict())
                continue

            rec = row.to_dict()
            rec["geometry"] = sh_ops.transform(unit_ctx["to_source"].transform, cleaned_metric)
            cleaned_records.append(rec)
    else:
        unit_ctx = _build_linear_unit_context(crs, out.unary_union.envelope)
        close_distance_native = max(
            _meters_to_native_units(close_distance_m, unit_ctx), bt_const.SMALL_BUFFER
        )
        precleaner_native = VertexPrecleaner(close_distance=close_distance_native, angle_tol=angle_tol_deg)
        for _, row in out.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty or geom.geom_type != "LineString":
                rec = row.to_dict()
                if geom is None or geom.is_empty:
                    removed_records.append(rec)
                else:
                    cleaned_records.append(rec)
                continue

            cleaned = precleaner_native.cleanup_line(geom, mode="full")
            if cleaned is None or cleaned.is_empty:
                removed_records.append(row.to_dict())
                continue

            rec = row.to_dict()
            rec["geometry"] = cleaned
            cleaned_records.append(rec)

    cleaned_gdf = gpd.GeoDataFrame(cleaned_records, columns=gdf.columns, crs=gdf.crs)
    removed_gdf = gpd.GeoDataFrame(
        [*rejected.to_dict("records"), *removed_records], columns=gdf.columns, crs=gdf.crs
    )
    return cleaned_gdf.reset_index(drop=True), removed_gdf.reset_index(drop=True)


def _clean_line_geometries_min_length_m(line_gdf, min_length_m):
    if line_gdf is None:
        return line_gdf, None
    if line_gdf.empty:
        return line_gdf.copy(), line_gdf.copy()

    valid_mask = ~line_gdf.geometry.isna() & ~line_gdf.geometry.is_empty
    out = line_gdf[valid_mask]
    rejected = line_gdf[~valid_mask].copy()

    if out.empty:
        return out.reset_index(drop=True), rejected.reset_index(drop=True)

    crs = _require_crs(out, "Minimum line length (m)")

    reference_geom = out.unary_union.envelope
    unit_ctx = _build_linear_unit_context(crs, reference_geom)
    min_len_m = max(float(min_length_m), bt_const.SMALL_BUFFER)

    if unit_ctx["is_geographic"]:
        mask = out.geometry.apply(lambda geom: _geometry_length_meters(geom, unit_ctx) > min_len_m)
        kept = out[mask]
        removed_short = out[~mask]
    else:
        min_len_native = max(_meters_to_native_units(min_len_m, unit_ctx), bt_const.SMALL_BUFFER)
        kept = out[out.geometry.length > min_len_native]
        removed_short = out[~(out.geometry.length > min_len_native)]

    if rejected.empty:
        rejected = removed_short.copy()
    elif not removed_short.empty:
        rejected = gpd.GeoDataFrame(
            [*rejected.to_dict("records"), *removed_short.to_dict("records")],
            columns=line_gdf.columns,
            crs=line_gdf.crs,
        )

    return kept.reset_index(drop=True), rejected.reset_index(drop=True)


def _clip_to_chm_footprint(gdf, in_raster, shrink_m):
    footprint = algo_common.generate_raster_footprint(in_raster, latlon=False)
    if footprint is None or footprint.is_empty:
        raise ValueError("Unable to build CHM footprint from input raster.")

    shrink_dist_m = abs(float(shrink_m))
    crs = _require_crs(gdf, "CHM footprint shrink (m)")
    unit_ctx = _build_linear_unit_context(crs, footprint)

    if unit_ctx["is_geographic"]:
        footprint_metric = sh_ops.transform(unit_ctx["to_metric"].transform, footprint)
        shrunken_metric = footprint_metric.buffer(-shrink_dist_m)
        shrunken = sh_ops.transform(unit_ctx["to_source"].transform, shrunken_metric)
    else:
        shrink_dist_units = _meters_to_native_units(shrink_dist_m, unit_ctx)
        shrunken = footprint.buffer(-shrink_dist_units)

    if shrunken is None or shrunken.is_empty:
        raise ValueError("CHM footprint became empty after inward shrink; reduce 'CHM footprint shrink (m)'.")

    clipped_records = []
    rejected_records = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            rejected_records.append(row.to_dict())
            continue

        clipped = geom.intersection(shrunken)
        if clipped is None or clipped.is_empty:
            rejected_records.append(row.to_dict())
            continue

        rec = row.to_dict()
        rec["geometry"] = clipped
        clipped_records.append(rec)

    clipped_gdf = gpd.GeoDataFrame(clipped_records, columns=gdf.columns, crs=gdf.crs)
    rejected_gdf = gpd.GeoDataFrame(rejected_records, columns=gdf.columns, crs=gdf.crs)
    return clipped_gdf, rejected_gdf, shrunken


def _parse_line_id(raw_id):
    if isinstance(raw_id, bool):
        return None
    try:
        val = int(raw_id)
        return val
    except (TypeError, ValueError):
        return None


def _choose_anchor(endpoint_a, endpoint_b):
    line_id_a = _parse_line_id(endpoint_a.get("line_id"))
    line_id_b = _parse_line_id(endpoint_b.get("line_id"))

    score_a = (
        -int(endpoint_a.get("degree", 0)),
        -endpoint_a["line_length"],
        0 if line_id_a is not None else 1,
        line_id_a if line_id_a is not None else float("inf"),
        endpoint_a["discovery_order"],
    )
    score_b = (
        -int(endpoint_b.get("degree", 0)),
        -endpoint_b["line_length"],
        0 if line_id_b is not None else 1,
        line_id_b if line_id_b is not None else float("inf"),
        endpoint_b["discovery_order"],
    )

    if score_a <= score_b:
        return endpoint_a, endpoint_b
    return endpoint_b, endpoint_a


def _snap_close_endpoints(gdf, tolerance):
    if gdf.empty:
        return gdf

    tol_m = float(tolerance)
    if tol_m <= bt_const.SMALL_BUFFER:
        return gdf

    crs = _require_crs(gdf, "Snap tolerance (m)")
    reference_geom = gdf.unary_union.envelope
    unit_ctx = _build_linear_unit_context(crs, reference_geom)
    tol_native = _meters_to_native_units(tol_m, unit_ctx)

    endpoints = []
    discovery_order = 0
    for row_index, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty or geom.geom_type != "LineString":
            continue

        coords = list(geom.coords)
        if len(coords) < 2:
            continue

        line_length = _geometry_length_meters(geom, unit_ctx)
        line_id = row.get("line_id")
        for endpoint_idx, coord in ((0, coords[0]), (-1, coords[-1])):
            metric_point = None
            if unit_ctx["is_geographic"]:
                metric_point = sh_ops.transform(unit_ctx["to_metric"].transform, Point(coord))
            endpoints.append(
                {
                    "gdf_index": row_index,
                    "endpoint_idx": endpoint_idx,
                    "point": Point(coord),
                    "metric_point": metric_point,
                    "line_length": line_length,
                    "line_id": line_id,
                    "discovery_order": discovery_order,
                }
            )
            discovery_order += 1

    if len(endpoints) < 2:
        return gdf

    neighbor_graph = {idx: set() for idx in range(len(endpoints))}
    for i in range(len(endpoints)):
        for j in range(i + 1, len(endpoints)):
            ep_i = endpoints[i]
            ep_j = endpoints[j]

            if ep_i["gdf_index"] == ep_j["gdf_index"]:
                continue

            if unit_ctx["is_geographic"]:
                dist = ep_i["metric_point"].distance(ep_j["metric_point"])
                close_threshold = bt_const.SMALL_BUFFER
                snap_threshold = tol_m
            else:
                dist = ep_i["point"].distance(ep_j["point"])
                close_threshold = bt_const.SMALL_BUFFER
                snap_threshold = tol_native

            if dist <= close_threshold:
                continue
            if dist <= snap_threshold:
                neighbor_graph[i].add(j)
                neighbor_graph[j].add(i)

    if not any(neighbor_graph.values()):
        return gdf

    for idx, endpoint in enumerate(endpoints):
        endpoint["degree"] = len(neighbor_graph[idx])

    visited = set()
    components = []
    active_nodes = [idx for idx, neighbors in neighbor_graph.items() if neighbors]
    for node in active_nodes:
        if node in visited:
            continue
        stack = [node]
        component = []
        while stack:
            curr = stack.pop()
            if curr in visited:
                continue
            visited.add(curr)
            component.append(curr)
            for neighbor in neighbor_graph[curr]:
                if neighbor not in visited:
                    stack.append(neighbor)

        if len(component) > 1:
            components.append(component)

    if not components:
        return gdf

    updates = {}
    for component in components:
        anchor_endpoint = endpoints[component[0]]
        for idx in component[1:]:
            candidate = endpoints[idx]
            anchor_endpoint, _ = _choose_anchor(anchor_endpoint, candidate)

        anchor_coord = tuple(anchor_endpoint["point"].coords[0])
        anchor_key = (anchor_endpoint["gdf_index"], anchor_endpoint["endpoint_idx"])

        for idx in component:
            endpoint = endpoints[idx]
            endpoint_key = (endpoint["gdf_index"], endpoint["endpoint_idx"])
            if endpoint_key == anchor_key:
                continue
            updates[endpoint_key] = anchor_coord

    if not updates:
        return gdf

    out = gdf.copy()
    for row_index, row in out.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty or geom.geom_type != "LineString":
            continue

        coords = list(geom.coords)
        changed = False
        for endpoint_idx in (0, -1):
            key = (row_index, endpoint_idx)
            if key in updates:
                target_coord = updates[key]
                if endpoint_idx == 0:
                    coords[0] = target_coord
                else:
                    coords[-1] = target_coord
                changed = True

        if changed:
            out.at[row_index, "geometry"] = LineString(coords)

    return out


def _interp_coord(start, end, ratio):
    n_dims = min(len(start), len(end))
    return tuple(start[i] + (end[i] - start[i]) * ratio for i in range(n_dims))


def _densify_linestring(line, max_segment_length):
    if line is None or line.is_empty or line.geom_type != "LineString":
        return line

    max_seg = float(max_segment_length)
    if max_seg <= bt_const.SMALL_BUFFER:
        raise ValueError("Max segment length must be greater than zero.")

    total_len = float(line.length)
    if total_len <= max_seg:
        return line

    n_parts = int(math.ceil(total_len / max_seg))
    spacing = total_len / n_parts
    split_distances = [spacing * i for i in range(1, n_parts)]

    coords = list(line.coords)
    if len(coords) < 2:
        return line

    out_coords = [coords[0]]
    curr_dist = 0.0
    split_idx = 0

    for seg_idx in range(len(coords) - 1):
        start = coords[seg_idx]
        end = coords[seg_idx + 1]
        seg_len = Point(start).distance(Point(end))
        if seg_len <= bt_const.SMALL_BUFFER:
            continue

        seg_end_dist = curr_dist + seg_len
        while split_idx < len(split_distances) and split_distances[split_idx] < seg_end_dist:
            ratio = (split_distances[split_idx] - curr_dist) / seg_len
            interp = _interp_coord(start, end, ratio)
            if Point(out_coords[-1]).distance(Point(interp)) > bt_const.SMALL_BUFFER:
                out_coords.append(interp)
            split_idx += 1

        if Point(out_coords[-1]).distance(Point(end)) > bt_const.SMALL_BUFFER:
            out_coords.append(end)
        curr_dist = seg_end_dist

    if len(out_coords) < 2:
        return line
    return LineString(out_coords)


def _densify_long_lines(gdf, max_segment_length):
    if gdf.empty:
        return gdf

    max_seg_m = float(max_segment_length)
    if max_seg_m <= bt_const.SMALL_BUFFER:
        raise ValueError("Max segment length must be greater than zero.")

    valid = gdf[~gdf.geometry.isna() & ~gdf.geometry.is_empty]
    if valid.empty:
        return gdf

    crs = _require_crs(valid, "Max segment length (m)")
    reference_geom = valid.unary_union.envelope
    unit_ctx = _build_linear_unit_context(crs, reference_geom)

    out = gdf.copy()

    if unit_ctx["is_geographic"]:
        for idx, row in out.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty or geom.geom_type != "LineString":
                continue

            geom_metric = sh_ops.transform(unit_ctx["to_metric"].transform, geom)
            if geom_metric.length <= max_seg_m:
                continue

            densified_metric = _densify_linestring(geom_metric, max_seg_m)
            out.at[idx, "geometry"] = sh_ops.transform(unit_ctx["to_source"].transform, densified_metric)

        return out

    max_seg_native = max(_meters_to_native_units(max_seg_m, unit_ctx), bt_const.SMALL_BUFFER)
    for idx, row in out.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty or geom.geom_type != "LineString":
            continue
        if geom.length <= max_seg_native:
            continue
        out.at[idx, "geometry"] = _densify_linestring(geom, max_seg_native)
    return out


def qc_merge_multilinestring(gdf):
    """
    QC step: Merge MultiLineStrings if possible, else split into LineStrings.

    Args:
        gdf (GeoDataFrame): Input GeoDataFrame.

    Returns:
        GeoDataFrame: Cleaned GeoDataFrame with only LineStrings.
    """
    from shapely.geometry.base import BaseGeometry

    from beratools.core.algo_merge_lines import custom_line_merge

    records = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        row_dict = row.to_dict()
        if geom.geom_type == "MultiLineString":
            merged = custom_line_merge(geom)
            if merged.geom_type == "MultiLineString":
                for part in getattr(merged, "geoms", []):
                    new_row = row_dict.copy()
                    new_row["geometry"] = part
                    if part.geom_type == "LineString":
                        records.append(new_row)
            elif merged.geom_type == "LineString":
                new_row = row_dict.copy()
                new_row["geometry"] = merged
                records.append(new_row)
            else:
                new_row = row_dict.copy()
                new_row["geometry"] = merged
                if hasattr(merged, "geom_type") and merged.geom_type == "LineString":
                    records.append(new_row)
        elif geom.geom_type == "LineString":
            records.append(row_dict)

    valid_records = [rec for rec in records if isinstance(rec.get("geometry", None), BaseGeometry)]
    out_gdf = gpd.GeoDataFrame.from_records(valid_records, columns=gdf.columns)
    out_gdf.set_crs(gdf.crs, inplace=True)
    out_gdf = out_gdf.reset_index(drop=True)
    return out_gdf


def qc_split_lines_at_intersections(gdf):
    """
    QC step: Split lines at intersections so each segment becomes a separate line object.

    Args:
        gdf (GeoDataFrame): Input GeoDataFrame of LineStrings.

    Returns:
        GeoDataFrame: New GeoDataFrame with lines split at all intersection points.
    """
    from beratools.core.algo_split_with_lines import LineSplitter

    splitter = LineSplitter(gdf)
    splitter.process()
    if splitter.split_lines_gdf is not None:
        if isinstance(splitter.split_lines_gdf, gpd.GeoDataFrame):
            return splitter.split_lines_gdf.reset_index(drop=True)
        return splitter.split_lines_gdf
    return gdf.reset_index(drop=True)

