"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide main interface for line grouping tool.
"""

import logging
import math
import time
from dataclasses import dataclass

import geopandas as gpd
import pyproj
from shapely import ops as sh_ops
from shapely.geometry import LineString, Point

import beratools.core.constants as bt_const
import beratools.utility.spatial_common as sp_common
from beratools.core.algo_common import generate_raster_footprint
from beratools.core.logger import Logger
from beratools.utility.tool_args import CallMode

log = Logger("check_seed_line", file_level=logging.INFO)
logger = log.get_logger()
print = log.print


@dataclass
class SeedLineQCConfig:
    chm_footprint_shrink: float = 15.0
    remove_short_lines: bool = False
    minimum_line_length: float = 5.0
    snap_close_endpoints: bool = False
    snap_tolerance: float = 5.0
    group_lines: bool = False
    merge_by_group: bool = False
    densify_long_lines: bool = False
    max_segment_length: float = bt_const.LP_SEGMENT_LENGTH
    use_angle_grouping: bool = True


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "on"}
    return bool(value)


def _write_output(gdf, out_file, out_layer):
    to_file_kwargs = {}
    if out_layer:
        to_file_kwargs["layer"] = out_layer
    gdf.to_file(out_file, **to_file_kwargs)


def _log_step(
    step_idx,
    step_name,
    in_count,
    out_count,
    elapsed=None,
    skipped_reason=None,
):
    if skipped_reason:
        logger.info(
            "Step %s - %s skipped (%s): %s -> %s",
            step_idx,
            step_name,
            skipped_reason,
            in_count,
            out_count,
        )
        return

    if elapsed is None:
        logger.info("Step %s - %s: %s -> %s", step_idx, step_name, in_count, out_count)
        return

    logger.info(
        "Step %s - %s: %s -> %s (%.3fs)",
        step_idx,
        step_name,
        in_count,
        out_count,
        elapsed,
    )


def _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
    if not gdf.empty:
        return False

    logger.warning(
        "Seed line QC early return after '%s' produced empty output (%s -> 0).",
        step_name,
        in_count,
    )
    _write_output(gdf.iloc[0:0].copy(), out_file, out_layer)
    return True


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


def _clean_line_geometries_min_length_m(line_gdf, min_length_m):
    if line_gdf is None:
        return line_gdf
    if line_gdf.empty:
        return line_gdf

    out = line_gdf[~line_gdf.geometry.isna() & ~line_gdf.geometry.is_empty]
    crs = _require_crs(out, "Minimum line length (m)")

    reference_geom = out.unary_union.envelope
    unit_ctx = _build_linear_unit_context(crs, reference_geom)
    min_len_m = max(float(min_length_m), bt_const.SMALL_BUFFER)

    if unit_ctx["is_geographic"]:
        mask = out.geometry.apply(lambda geom: _geometry_length_meters(geom, unit_ctx) > min_len_m)
        return out[mask]

    min_len_native = max(_meters_to_native_units(min_len_m, unit_ctx), bt_const.SMALL_BUFFER)
    return out[out.geometry.length > min_len_native]


def _clip_to_chm_footprint(gdf, in_raster, shrink_m):
    footprint = generate_raster_footprint(in_raster, latlon=False)
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

    records = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        clipped = geom.intersection(shrunken)
        if clipped is None or clipped.is_empty:
            continue

        rec = row.to_dict()
        rec["geometry"] = clipped
        records.append(rec)

    return gpd.GeoDataFrame(records, columns=gdf.columns, crs=gdf.crs)


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
        -endpoint_a["line_length"],
        0 if line_id_a is not None else 1,
        line_id_a if line_id_a is not None else float("inf"),
        endpoint_a["discovery_order"],
    )
    score_b = (
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

    candidate_pairs = []
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
                candidate_pairs.append((dist, ep_i, ep_j))

    candidate_pairs.sort(
        key=lambda x: (
            x[0],
            min(x[1]["discovery_order"], x[2]["discovery_order"]),
            max(x[1]["discovery_order"], x[2]["discovery_order"]),
        )
    )

    updates = {}
    moved_keys = set()
    anchor_locked_keys = set()
    for _, ep_i, ep_j in candidate_pairs:
        anchor, mover = _choose_anchor(ep_i, ep_j)
        anchor_key = (anchor["gdf_index"], anchor["endpoint_idx"])
        mover_key = (mover["gdf_index"], mover["endpoint_idx"])

        if mover_key in moved_keys:
            continue
        if mover_key in anchor_locked_keys:
            continue
        if anchor_key in moved_keys:
            continue

        updates[mover_key] = tuple(anchor["point"].coords[0])
        moved_keys.add(mover_key)
        anchor_locked_keys.add(anchor_key)

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

    out = gdf.copy()
    for idx, row in out.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty or geom.geom_type != "LineString":
            continue
        if geom.length <= float(max_segment_length):
            continue
        out.at[idx, "geometry"] = _densify_linestring(geom, max_segment_length)
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


def _step_timer():
    return time.perf_counter()


def _elapsed(start_t):
    return time.perf_counter() - start_t


def check_seed_line(
    in_line,
    in_raster,
    out_line,
    chm_footprint_shrink=15.0,
    remove_short_lines=False,
    minimum_line_length=5.0,
    snap_close_endpoints=False,
    snap_tolerance=5.0,
    group_lines=False,
    merge_by_group=False,
    densify_long_lines=False,
    max_segment_length=bt_const.LP_SEGMENT_LENGTH,
    use_angle_grouping=True,
    processes=0,
    call_mode=CallMode.CLI,
    log_level="INFO",
):
    from beratools.core.algo_line_grouping import LineGrouping

    del processes, call_mode, log_level

    if not in_raster:
        raise ValueError("Parameter 'in_raster' is required for Check Seed Lines.")

    config = SeedLineQCConfig(
        chm_footprint_shrink=float(chm_footprint_shrink),
        remove_short_lines=_to_bool(remove_short_lines),
        minimum_line_length=float(minimum_line_length),
        snap_close_endpoints=_to_bool(snap_close_endpoints),
        snap_tolerance=float(snap_tolerance),
        group_lines=_to_bool(group_lines),
        merge_by_group=_to_bool(merge_by_group),
        densify_long_lines=_to_bool(densify_long_lines),
        max_segment_length=float(max_segment_length),
        use_angle_grouping=_to_bool(use_angle_grouping),
    )

    in_file, in_layer = sp_common.decode_file_layer(in_line)
    out_file, out_layer = sp_common.decode_file_layer(out_line)

    if not sp_common.compare_crs(sp_common.vector_crs(in_file), sp_common.raster_crs(in_raster)):
        raise ValueError("Input line and raster CRS do not match.")

    gdf = gpd.read_file(in_file, layer=in_layer)
    logger.info("Seed line QC start: %s feature(s)", len(gdf))

    step_name = "qc_merge_multilinestring"
    in_count = len(gdf)
    t0 = _step_timer()
    gdf = qc_merge_multilinestring(gdf)
    _log_step(1, step_name, in_count, len(gdf), _elapsed(t0))
    if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
        return

    step_name = "geometry cleanup"
    in_count = len(gdf)
    t0 = _step_timer()
    gdf = _clean_line_geometries_min_length_m(gdf, bt_const.SMALL_BUFFER).reset_index(drop=True)
    _log_step(2, step_name, in_count, len(gdf), _elapsed(t0))
    if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
        return

    step_name = "short line removal"
    in_count = len(gdf)
    if config.remove_short_lines:
        t0 = _step_timer()
        gdf = _clean_line_geometries_min_length_m(gdf, config.minimum_line_length).reset_index(drop=True)
        _log_step(3, step_name, in_count, len(gdf), _elapsed(t0))
        if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
            return
    else:
        _log_step(3, step_name, in_count, in_count, skipped_reason="disabled")

    step_name = "CHM footprint clipping"
    in_count = len(gdf)
    t0 = _step_timer()
    gdf = _clip_to_chm_footprint(gdf, in_raster, config.chm_footprint_shrink)
    _log_step(4, step_name, in_count, len(gdf), _elapsed(t0))
    if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
        return

    step_name = "post-clip normalize + cleanup"
    in_count = len(gdf)
    t0 = _step_timer()
    gdf = _normalize_to_lines(gdf)
    gdf = _clean_line_geometries_min_length_m(gdf, bt_const.SMALL_BUFFER).reset_index(drop=True)
    _log_step(5, step_name, in_count, len(gdf), _elapsed(t0))
    if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
        return

    step_name = "endpoint snapping"
    in_count = len(gdf)
    if config.snap_close_endpoints:
        t0 = _step_timer()
        effective_tolerance = config.snap_tolerance
        if config.remove_short_lines:
            effective_tolerance = max(effective_tolerance, config.minimum_line_length)
        gdf = _snap_close_endpoints(gdf, effective_tolerance).reset_index(drop=True)
        _log_step(6, step_name, in_count, len(gdf), _elapsed(t0))
        if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
            return
    else:
        _log_step(6, step_name, in_count, in_count, skipped_reason="disabled")

    step_name = "qc_split_lines_at_intersections"
    in_count = len(gdf)
    t0 = _step_timer()
    gdf = qc_split_lines_at_intersections(gdf)
    _log_step(7, step_name, in_count, len(gdf), _elapsed(t0))
    if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
        return

    step_name = "LineGrouping"
    in_count = len(gdf)
    if config.group_lines:
        t0 = _step_timer()
        lg = LineGrouping(gdf, use_angle_grouping=config.use_angle_grouping)
        lg.run_grouping()
        gdf = lg.lines.reset_index(drop=True)
        _log_step(8, step_name, in_count, len(gdf), _elapsed(t0))
        if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
            return
    else:
        gdf = gdf.reset_index(drop=True)
        gdf[bt_const.BT_GROUP] = list(range(len(gdf)))
        _log_step(8, step_name, in_count, len(gdf), skipped_reason="disabled; assigned unique BT_GROUP")

    step_name = "merge by group"
    in_count = len(gdf)
    if config.merge_by_group and config.group_lines:
        t0 = _step_timer()
        gdf = gdf.dissolve(by=bt_const.BT_GROUP, as_index=False, aggfunc="first")
        gdf = qc_merge_multilinestring(gdf).reset_index(drop=True)
        _log_step(9, step_name, in_count, len(gdf), _elapsed(t0))
        if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
            return
    else:
        reason = "disabled"
        if config.merge_by_group and not config.group_lines:
            reason = "guarded because group_lines=false"
        _log_step(9, step_name, in_count, in_count, skipped_reason=reason)

    step_name = "long line densification"
    in_count = len(gdf)
    if config.densify_long_lines:
        t0 = _step_timer()
        gdf = _densify_long_lines(gdf, config.max_segment_length).reset_index(drop=True)
        _log_step(10, step_name, in_count, len(gdf), _elapsed(t0))
        if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
            return
    else:
        _log_step(10, step_name, in_count, in_count, skipped_reason="disabled")

    gdf = _clean_line_geometries_min_length_m(gdf, bt_const.SMALL_BUFFER).reset_index(drop=True)
    _write_output(gdf, out_file, out_layer)
    print(f"Output saved to file: {out_file}, layer: {out_layer}")


if __name__ == "__main__":
    from beratools.utility.tool_args import compose_tool_kwargs

    start_time = time.time()
    kwargs = compose_tool_kwargs("check_seed_line")
    check_seed_line(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))
