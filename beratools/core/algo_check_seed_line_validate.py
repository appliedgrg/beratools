"""Final validation pass on check_seed_line outputs to detect remaining issues."""

import math

import geopandas as gpd
import numpy as np
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPoint, Point

import beratools.core.constants as bt_const
import beratools.utility.unit_conversion as unit_conversion

try:
    import rasterio
    from rasterio.windows import Window
except Exception:
    rasterio = None
    Window = None


ISSUE_COLUMNS = [
    "issue_type",
    "description",
    "line_id",
    "line_id_2",
    "value",
    "threshold",
    "geometry",
]


def _iter_line_parts(geom):
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type == "MultiLineString":
        return [part for part in geom.geoms if part is not None and not part.is_empty]
    if geom.geom_type == "GeometryCollection":
        parts = []
        for item in geom.geoms:
            parts.extend(_iter_line_parts(item))
        return parts
    return []


def _build_unit_ctx(gdf):
    crs = unit_conversion.require_crs(gdf, "QC report checks")
    reference_geom = None if gdf.empty else gdf.unary_union.envelope
    return unit_conversion.build_linear_unit_context(crs, reference_geom)


def _point_distance_m(point_a, point_b, unit_ctx):
    if unit_ctx["is_geographic"]:
        point_a_m = Point(unit_ctx["to_metric"].transform(point_a.x, point_a.y))
        point_b_m = Point(unit_ctx["to_metric"].transform(point_b.x, point_b.y))
        return float(point_a_m.distance(point_b_m))
    return float(point_a.distance(point_b)) * float(unit_ctx["unit_factor"])


def _raster_cell_size_m(src, row, col, unit_ctx):
    row = min(max(int(row), 0), src.height - 1)
    col = min(max(int(col), 0), src.width - 1)
    center = Point(src.xy(row, col))

    samples = []
    if col + 1 < src.width:
        samples.append(Point(src.xy(row, col + 1)))
    if row + 1 < src.height:
        samples.append(Point(src.xy(row + 1, col)))
    if col > 0:
        samples.append(Point(src.xy(row, col - 1)))
    if row > 0:
        samples.append(Point(src.xy(row - 1, col)))

    distances = [_point_distance_m(center, sample, unit_ctx) for sample in samples]
    distances = [dist for dist in distances if dist > bt_const.SMALL_BUFFER]
    if distances:
        return min(distances)

    return max(abs(float(src.transform.a)), abs(float(src.transform.e)), bt_const.SMALL_BUFFER)


def _raster_valid_mask(data, nodata):
    values = np.ma.getdata(data)
    invalid = np.ma.getmaskarray(data).copy()

    if nodata is not None:
        try:
            invalid |= np.isclose(values, nodata)
        except TypeError:
            invalid |= values == nodata

    if np.issubdtype(values.dtype, np.floating):
        invalid |= np.isnan(values)

    return ~invalid


def _nearest_valid_distance_m(src, valid_mask, row_offset, col_offset, point, unit_ctx, exclude_cell=None):
    valid_rows, valid_cols = np.nonzero(valid_mask)
    best_distance = None

    for local_row, local_col in zip(valid_rows, valid_cols):
        global_row = int(row_offset + local_row)
        global_col = int(col_offset + local_col)
        if exclude_cell is not None and (global_row, global_col) == exclude_cell:
            continue

        candidate = Point(src.xy(global_row, global_col))
        distance_m = _point_distance_m(point, candidate, unit_ctx)
        if best_distance is None or distance_m < best_distance:
            best_distance = float(distance_m)

    return best_distance


def _check_chm_point(src, point, search_radius_m, unit_ctx):
    try:
        row, col = src.index(point.x, point.y)
    except Exception:
        return {"reason": "outside_raster", "nearest_valid_m": None}

    in_bounds = 0 <= row < src.height and 0 <= col < src.width
    center_row = min(max(int(row), 0), src.height - 1)
    center_col = min(max(int(col), 0), src.width - 1)
    cell_size_m = _raster_cell_size_m(src, center_row, center_col, unit_ctx)
    radius_px = max(1, int(math.ceil(float(search_radius_m) / max(cell_size_m, bt_const.SMALL_BUFFER))))

    row_start = max(center_row - radius_px, 0)
    row_stop = min(center_row + radius_px + 1, src.height)
    col_start = max(center_col - radius_px, 0)
    col_stop = min(center_col + radius_px + 1, src.width)

    if row_stop <= row_start or col_stop <= col_start:
        return {"reason": "outside_raster", "nearest_valid_m": None}

    window = Window(col_start, row_start, col_stop - col_start, row_stop - row_start)
    data = src.read(1, window=window, masked=True)
    valid_mask = _raster_valid_mask(data, src.nodata)

    center_valid = False
    if in_bounds:
        local_row = int(row - row_start)
        local_col = int(col - col_start)
        center_valid = bool(valid_mask[local_row, local_col])

    if center_valid:
        local_row = int(row - row_start)
        local_col = int(col - col_start)
        neighbor_row_start = max(local_row - 1, 0)
        neighbor_row_stop = min(local_row + 2, valid_mask.shape[0])
        neighbor_col_start = max(local_col - 1, 0)
        neighbor_col_stop = min(local_col + 2, valid_mask.shape[1])
        neighbors = valid_mask[neighbor_row_start:neighbor_row_stop, neighbor_col_start:neighbor_col_stop].copy()
        neighbors[local_row - neighbor_row_start, local_col - neighbor_col_start] = False
        if np.any(neighbors):
            return None

        nearest_valid_m = _nearest_valid_distance_m(
            src,
            valid_mask,
            row_start,
            col_start,
            point,
            unit_ctx,
            exclude_cell=(int(row), int(col)),
        )
        return {"reason": "surrounded_by_nodata", "nearest_valid_m": nearest_valid_m}

    nearest_valid_m = _nearest_valid_distance_m(src, valid_mask, row_start, col_start, point, unit_ctx)
    return {"reason": "on_nodata", "nearest_valid_m": nearest_valid_m}


def _segment_length_m(coord_a, coord_b, unit_ctx):
    seg = LineString([coord_a, coord_b])
    return unit_conversion.geometry_length_meters(seg, unit_ctx)


def _intersection_points(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Point):
        return [geom]
    if isinstance(geom, MultiPoint):
        return [pt for pt in geom.geoms if pt is not None and not pt.is_empty]
    if isinstance(geom, LineString):
        if geom.length <= bt_const.SMALL_BUFFER:
            return []
        return [geom.interpolate(0.5, normalized=True)]
    if isinstance(geom, MultiLineString):
        points = []
        for part in geom.geoms:
            points.extend(_intersection_points(part))
        return points
    if isinstance(geom, GeometryCollection):
        points = []
        for part in geom.geoms:
            points.extend(_intersection_points(part))
        return points
    if hasattr(geom, "representative_point"):
        return [geom.representative_point()]
    return []


def _overlap_midpoints_and_lengths(geom, unit_ctx):
    if geom is None or geom.is_empty:
        return []

    items = []
    if isinstance(geom, LineString):
        length_m = unit_conversion.geometry_length_meters(geom, unit_ctx)
        if length_m > bt_const.SMALL_BUFFER:
            items.append((geom.interpolate(0.5, normalized=True), float(length_m)))
        return items

    if isinstance(geom, MultiLineString):
        for part in geom.geoms:
            items.extend(_overlap_midpoints_and_lengths(part, unit_ctx))
        return items

    if isinstance(geom, GeometryCollection):
        for part in geom.geoms:
            items.extend(_overlap_midpoints_and_lengths(part, unit_ctx))
        return items

    return items


def _dedupe_records(records, precision=9):
    deduped = []
    seen = set()
    for rec in records:
        pt = rec["geometry"]
        key = (
            rec["issue_type"],
            int(rec["line_id"]),
            -1 if rec["line_id_2"] is None else int(rec["line_id_2"]),
            round(float(pt.x), precision),
            round(float(pt.y), precision),
            round(float(rec["value"]), 6),
            round(float(rec["threshold"]), 6),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rec)
    return deduped


def check_short_lines(gdf, min_length_m, unit_ctx):
    threshold = float(min_length_m)
    records = []
    for line_id, geom in enumerate(gdf.geometry):
        for part in _iter_line_parts(geom):
            length_m = unit_conversion.geometry_length_meters(part, unit_ctx)
            if length_m < threshold:
                records.append(
                    {
                        "issue_type": "short_line",
                        "description": f"Line length {length_m:.3f}m is below minimum {threshold:.3f}m",
                        "line_id": int(line_id),
                        "line_id_2": None,
                        "value": float(length_m),
                        "threshold": threshold,
                        "geometry": part.interpolate(0.5, normalized=True),
                    }
                )
    return _dedupe_records(records)


def check_close_vertices(gdf, close_distance_m, unit_ctx):
    threshold = float(close_distance_m)
    records = []
    for line_id, geom in enumerate(gdf.geometry):
        for part in _iter_line_parts(geom):
            coords = list(part.coords)
            if len(coords) < 2:
                continue
            for i in range(1, len(coords)):
                dist_m = _segment_length_m(coords[i - 1], coords[i], unit_ctx)
                if bt_const.SMALL_BUFFER < dist_m <= threshold:
                    records.append(
                        {
                            "issue_type": "close_vertices",
                            "description": (
                                f"Consecutive vertices are {dist_m:.3f}m apart; threshold {threshold:.3f}m"
                            ),
                            "line_id": int(line_id),
                            "line_id_2": None,
                            "value": float(dist_m),
                            "threshold": threshold,
                            "geometry": Point(coords[i]),
                        }
                    )
    return _dedupe_records(records)


def check_unsnapped_endpoints(gdf, snap_tolerance_m, unit_ctx):
    threshold = float(snap_tolerance_m)
    records = []

    endpoints = []
    for line_id, geom in enumerate(gdf.geometry):
        for part in _iter_line_parts(geom):
            coords = list(part.coords)
            if len(coords) < 2:
                continue
            endpoints.append({"line_id": int(line_id), "point": Point(coords[0])})
            endpoints.append({"line_id": int(line_id), "point": Point(coords[-1])})

    if len(endpoints) < 2:
        return records

    if unit_ctx["is_geographic"]:
        candidates = [
            (i, j)
            for i in range(len(endpoints))
            for j in range(i + 1, len(endpoints))
            if endpoints[i]["line_id"] != endpoints[j]["line_id"]
        ]
    else:
        threshold_native = unit_conversion.meters_to_native_units(threshold, unit_ctx)
        points = gpd.GeoSeries([ep["point"] for ep in endpoints], crs=gdf.crs)
        sindex = points.sindex
        candidates = []
        for i, ep in enumerate(endpoints):
            bounds = ep["point"].buffer(threshold_native).bounds
            for j in sindex.intersection(bounds):
                if j <= i:
                    continue
                if ep["line_id"] == endpoints[j]["line_id"]:
                    continue
                candidates.append((i, int(j)))

    for i, j in candidates:
        ep_a = endpoints[i]
        ep_b = endpoints[j]
        dist_m = _point_distance_m(ep_a["point"], ep_b["point"], unit_ctx)
        if dist_m <= bt_const.SMALL_BUFFER or dist_m > threshold:
            continue

        line_id_a = min(ep_a["line_id"], ep_b["line_id"])
        line_id_b = max(ep_a["line_id"], ep_b["line_id"])
        records.append(
            {
                "issue_type": "unsnapped_endpoint",
                "description": (
                    f"Endpoints are close ({dist_m:.3f}m) but not snapped (threshold {threshold:.3f}m)"
                ),
                "line_id": int(line_id_a),
                "line_id_2": int(line_id_b),
                "value": float(dist_m),
                "threshold": threshold,
                "geometry": ep_a["point"],
            }
        )

    return _dedupe_records(records)


def check_self_crossing(gdf):
    records = []
    threshold = 0.0
    for line_id, geom in enumerate(gdf.geometry):
        for part in _iter_line_parts(geom):
            if part.is_simple:
                continue

            coords = list(part.coords)
            if len(coords) < 4:
                continue

            segments = []
            for i in range(len(coords) - 1):
                seg = LineString([coords[i], coords[i + 1]])
                if seg.length > bt_const.SMALL_BUFFER:
                    segments.append((i, seg))

            seg_count = len(segments)
            for i in range(seg_count):
                idx_a, seg_a = segments[i]
                for j in range(i + 1, seg_count):
                    idx_b, seg_b = segments[j]

                    if abs(idx_a - idx_b) <= 1:
                        continue
                    if idx_a == 0 and idx_b == len(coords) - 2 and Point(coords[0]).equals(Point(coords[-1])):
                        continue

                    inter = seg_a.intersection(seg_b)
                    if inter is None or inter.is_empty:
                        continue

                    for pt in _intersection_points(inter):
                        records.append(
                            {
                                "issue_type": "self_crossing",
                                "description": "Line has self-crossing or self-touching segments",
                                "line_id": int(line_id),
                                "line_id_2": None,
                                "value": 0.0,
                                "threshold": threshold,
                                "geometry": pt,
                            }
                        )

    return _dedupe_records(records)


def check_overlapping_lines(gdf):
    records = []
    threshold = 0.0

    lines = []
    for line_id, geom in enumerate(gdf.geometry):
        for part in _iter_line_parts(geom):
            lines.append({"line_id": int(line_id), "geometry": part})

    if len(lines) < 2:
        return records

    unit_ctx = _build_unit_ctx(gdf)

    line_gdf = gpd.GeoDataFrame(lines, geometry="geometry", crs=gdf.crs)
    sindex = line_gdf.sindex

    for i, row in line_gdf.iterrows():
        geom_i = row.geometry
        for j in sindex.intersection(geom_i.bounds):
            j = int(j)
            if j <= i:
                continue
            other = line_gdf.iloc[j]
            if int(other["line_id"]) == int(row["line_id"]):
                continue

            inter = geom_i.intersection(other.geometry)
            if inter is None or inter.is_empty:
                continue

            for pt, overlap_len_m in _overlap_midpoints_and_lengths(inter, unit_ctx):
                line_id_a = min(int(row["line_id"]), int(other["line_id"]))
                line_id_b = max(int(row["line_id"]), int(other["line_id"]))
                records.append(
                    {
                        "issue_type": "overlap",
                        "description": f"Lines share an overlapping segment ({overlap_len_m:.3f}m)",
                        "line_id": line_id_a,
                        "line_id_2": line_id_b,
                        "value": float(overlap_len_m),
                        "threshold": threshold,
                        "geometry": pt,
                    }
                )

    return _dedupe_records(records)


def check_chm_nodata_vertices(
    gdf,
    in_raster,
    search_radius_m,
    unit_ctx,
    check_internal_vertices=False,
):
    records = []
    if not in_raster or rasterio is None or Window is None:
        return records

    threshold = float(search_radius_m)
    include_internal = bool(check_internal_vertices)

    with rasterio.open(in_raster) as src:
        for line_id, row in gdf.reset_index(drop=True).iterrows():
            bt_uid = row.get(bt_const.BT_UID)
            for part in _iter_line_parts(row.geometry):
                coords = list(part.coords)
                if len(coords) < 2:
                    continue

                candidates = [(0, coords[0], "start_endpoint"), (len(coords) - 1, coords[-1], "end_endpoint")]
                if include_internal and len(coords) > 2:
                    candidates.extend(
                        (idx, coord, "internal_vertex") for idx, coord in enumerate(coords[1:-1], start=1)
                    )

                for vertex_index, coord, vertex_type in candidates:
                    point = Point(coord)
                    result = _check_chm_point(src, point, threshold, unit_ctx)
                    if result is None:
                        continue

                    nearest_valid_m = result["nearest_valid_m"]
                    nearest_text = (
                        f"nearest valid CHM cell is {nearest_valid_m:.3f}m away"
                        if nearest_valid_m is not None
                        else f"no valid CHM cell found within {threshold:.3f}m"
                    )
                    uid_text = f"; BT_UID={bt_uid}" if bt_uid is not None else ""
                    reason_text = (
                        "falls on CHM NoData"
                        if result["reason"] == "on_nodata"
                        else "is surrounded by CHM NoData"
                        if result["reason"] == "surrounded_by_nodata"
                        else "falls outside the CHM raster"
                    )

                    records.append(
                        {
                            "issue_type": "chm_nodata_vertex",
                            "description": (
                                f"{vertex_type} {reason_text}; vertex_index={vertex_index}{uid_text}; "
                                f"coordinate=({point.x:.3f}, {point.y:.3f}); {nearest_text}"
                            ),
                            "line_id": int(line_id),
                            "line_id_2": None,
                            "value": -1.0 if nearest_valid_m is None else float(nearest_valid_m),
                            "threshold": threshold,
                            "geometry": point,
                        }
                    )

    return _dedupe_records(records)


def generate_qc_report(
    gdf,
    min_length_m,
    close_distance_m,
    snap_tolerance_m,
    in_raster=None,
    warn_nodata_vertices=False,
    nodata_vertex_search_radius_m=10.0,
    check_internal_vertices=False,
):
    if gdf is None:
        gdf = gpd.GeoDataFrame(geometry=[])

    gdf = gdf.reset_index(drop=True)
    if gdf.empty:
        issues_gdf = gpd.GeoDataFrame(
            {col: [] for col in ISSUE_COLUMNS if col != "geometry"},
            geometry=gpd.GeoSeries([], crs=gdf.crs),
            crs=gdf.crs,
        )
        summary = {
            "short_line": 0,
            "close_vertices": 0,
            "unsnapped_endpoint": 0,
            "self_crossing": 0,
            "overlap": 0,
            "chm_nodata_vertex": 0,
            "total": 0,
        }
        return issues_gdf, summary

    unit_ctx = _build_unit_ctx(gdf)

    short_line = check_short_lines(gdf, min_length_m=min_length_m, unit_ctx=unit_ctx)
    close_vertices = check_close_vertices(gdf, close_distance_m=close_distance_m, unit_ctx=unit_ctx)
    unsnapped_endpoint = check_unsnapped_endpoints(
        gdf,
        snap_tolerance_m=snap_tolerance_m,
        unit_ctx=unit_ctx,
    )
    self_crossing = check_self_crossing(gdf)
    overlap = check_overlapping_lines(gdf)
    chm_nodata_vertex = []
    if warn_nodata_vertices:
        chm_nodata_vertex = check_chm_nodata_vertices(
            gdf,
            in_raster=in_raster,
            search_radius_m=nodata_vertex_search_radius_m,
            unit_ctx=unit_ctx,
            check_internal_vertices=check_internal_vertices,
        )

    all_issues = short_line + close_vertices + unsnapped_endpoint + self_crossing + overlap + chm_nodata_vertex

    if all_issues:
        issues_gdf = gpd.GeoDataFrame(all_issues, columns=ISSUE_COLUMNS, geometry="geometry", crs=gdf.crs)
    else:
        issues_gdf = gpd.GeoDataFrame(
            {col: [] for col in ISSUE_COLUMNS if col != "geometry"},
            geometry=gpd.GeoSeries([], crs=gdf.crs),
            crs=gdf.crs,
        )

    summary = {
        "short_line": len(short_line),
        "close_vertices": len(close_vertices),
        "unsnapped_endpoint": len(unsnapped_endpoint),
        "self_crossing": len(self_crossing),
        "overlap": len(overlap),
        "chm_nodata_vertex": len(chm_nodata_vertex),
    }
    summary["total"] = int(sum(summary.values()))

    return issues_gdf, summary
