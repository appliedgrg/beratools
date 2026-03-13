"""Post-processing QC checks for check_seed_line outputs."""

import geopandas as gpd
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPoint, Point

import beratools.core.constants as bt_const
import beratools.utility.unit_conversion as unit_conversion


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


def generate_qc_report(gdf, min_length_m, close_distance_m, snap_tolerance_m):
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

    all_issues = short_line + close_vertices + unsnapped_endpoint + self_crossing + overlap

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
    }
    summary["total"] = int(sum(summary.values()))

    return issues_gdf, summary
