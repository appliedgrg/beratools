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
from datetime import datetime, timezone
from dataclasses import dataclass

import geopandas as gpd
import pyproj
from shapely import ops as sh_ops
from shapely.geometry import LineString, Point

import beratools.core.constants as bt_const
import beratools.core.algo_common as algo_common
import beratools.utility.spatial_common as sp_common
from beratools.core.logger import Logger
from beratools.utility.tool_args import CallMode

log = Logger("check_seed_line", file_level=logging.INFO)
logger = log.get_logger()
print = log.print


@dataclass
class SeedLineQCConfig:
    chm_footprint_shrink: float = 15.0
    clip_to_chm_footprint: bool = True
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


def _step_timer():
    return time.perf_counter()


def _elapsed(start_t):
    return time.perf_counter() - start_t


def check_seed_line(
    in_line,
    in_raster,
    out_line,
    chm_footprint_shrink=15.0,
    clip_to_chm_footprint=True,
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

    config = SeedLineQCConfig(
        chm_footprint_shrink=float(chm_footprint_shrink),
        clip_to_chm_footprint=_to_bool(clip_to_chm_footprint),
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
    aux_file = algo_common.get_aux_path(out_file)

    qc_manifest = {
        "qc_removed_input_cleanup": {
            "layer_name": "qc_removed_input_cleanup",
            "step": 0,
            "step_name": "input cleanup",
            "reason": "Invalid, null, or empty geometries removed during input hygiene",
            "feature_count": 0,
            "written": 0,
            "notes": "not triggered",
        },
        "qc_removed_cleanup": {
            "layer_name": "qc_removed_cleanup",
            "step": 2,
            "step_name": "geometry cleanup",
            "reason": "Null, empty, or too-short lines removed in cleanup",
            "feature_count": 0,
            "written": 0,
            "notes": "not triggered",
        },
        "qc_removed_short": {
            "layer_name": "qc_removed_short",
            "step": 3,
            "step_name": "short line removal",
            "reason": "Lines below user minimum length",
            "feature_count": 0,
            "written": 0,
            "notes": "disabled",
        },
        "qc_removed_clipped": {
            "layer_name": "qc_removed_clipped",
            "step": 4,
            "step_name": "CHM footprint clipping",
            "reason": "Lines outside shrunken CHM footprint",
            "feature_count": 0,
            "written": 0,
            "notes": "not triggered",
        },
        "chm_footprint": {
            "layer_name": "chm_footprint",
            "step": 4,
            "step_name": "CHM footprint clipping",
            "reason": "Shrunken CHM footprint used for clipping",
            "feature_count": 0,
            "written": 0,
            "notes": "not triggered",
        },
        "qc_removed_post_clip": {
            "layer_name": "qc_removed_post_clip",
            "step": 5,
            "step_name": "post-clip normalize + cleanup",
            "reason": "Fragments removed after clipping and normalization",
            "feature_count": 0,
            "written": 0,
            "notes": "not triggered",
        },
        "qc_removed_final": {
            "layer_name": "qc_removed_final",
            "step": 11,
            "step_name": "final cleanup",
            "reason": "Remaining invalid/empty/too-short lines",
            "feature_count": 0,
            "written": 0,
            "notes": "not triggered",
        },
    }

    def _mark_layer(layer_name, layer_gdf, notes=None):
        if layer_name not in qc_manifest:
            return
        count = 0 if layer_gdf is None else len(layer_gdf)
        qc_manifest[layer_name]["feature_count"] = int(count)
        qc_manifest[layer_name]["written"] = 1 if count > 0 else 0
        qc_manifest[layer_name]["notes"] = notes or ("written" if count > 0 else "empty")
        if count > 0:
            algo_common.save_aux_layer(layer_gdf, out_file, layer_name)

    def _has_rows(layer_gdf):
        return layer_gdf is not None and hasattr(layer_gdf, "empty") and not layer_gdf.empty

    def _ensure_gdf(obj, fallback_crs):
        if isinstance(obj, gpd.GeoDataFrame):
            return obj
        return gpd.GeoDataFrame(obj, crs=fallback_crs)

    def _persist_qc_tables(input_count, output_count):
        manifest_rows = [qc_manifest[key] for key in qc_manifest.keys()]
        algo_common.save_aux_table(manifest_rows, out_file, "qc_manifest", overwrite=True)
        summary_row = {
            "tool_name": "check_seed_line",
            "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "input_line": in_line,
            "input_raster": in_raster,
            "output_line": out_line,
            "aux_gpkg": aux_file,
            "clip_to_chm_footprint": int(config.clip_to_chm_footprint),
            "chm_footprint_shrink_m": float(config.chm_footprint_shrink),
            "remove_short_lines": int(config.remove_short_lines),
            "minimum_line_length_m": float(config.minimum_line_length),
            "snap_close_endpoints": int(config.snap_close_endpoints),
            "snap_tolerance_m": float(config.snap_tolerance),
            "group_lines": int(config.group_lines),
            "merge_by_group": int(config.merge_by_group),
            "densify_long_lines": int(config.densify_long_lines),
            "max_segment_length_m": float(config.max_segment_length),
            "input_feature_count": int(input_count),
            "output_feature_count": int(output_count),
        }
        algo_common.save_aux_table([summary_row], out_file, "qc_run_summary", overwrite=True)

    if config.clip_to_chm_footprint and in_raster:
        if not sp_common.compare_crs(sp_common.vector_crs(in_file), sp_common.raster_crs(in_raster)):
            raise ValueError("Input line and raster CRS do not match.")

    gdf = gpd.read_file(in_file, layer=in_layer)
    if "fid" in gdf.columns:
        gdf = gdf.rename(columns={"fid": "orig_fid"})
    input_count = len(gdf)
    gdf = algo_common.clean_geometries(
        gdf,
        stage="input",
        out_file=out_file,
        layer="qc_removed_input_cleanup",
    ).reset_index(drop=True)
    input_cleanup_removed_count = input_count - len(gdf)
    qc_manifest["qc_removed_input_cleanup"]["feature_count"] = int(max(input_cleanup_removed_count, 0))
    qc_manifest["qc_removed_input_cleanup"]["written"] = 1 if input_cleanup_removed_count > 0 else 0
    qc_manifest["qc_removed_input_cleanup"]["notes"] = (
        "written" if input_cleanup_removed_count > 0 else "empty"
    )

    logger.info(
        "Seed line QC start: %s feature(s), input cleanup removed %s feature(s)",
        len(gdf),
        input_cleanup_removed_count,
    )

    step_name = "qc_merge_multilinestring"
    in_count = len(gdf)
    t0 = _step_timer()
    gdf = qc_merge_multilinestring(gdf)
    _log_step(1, step_name, in_count, len(gdf), _elapsed(t0))
    if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
        _persist_qc_tables(input_count, 0)
        return

    step_name = "geometry cleanup"
    in_count = len(gdf)
    t0 = _step_timer()
    gdf, removed_gdf = _clean_line_geometries_min_length_m(gdf, bt_const.SMALL_BUFFER)
    gdf = gdf.reset_index(drop=True)
    _mark_layer("qc_removed_cleanup", removed_gdf, notes="written" if _has_rows(removed_gdf) else "empty")
    _log_step(2, step_name, in_count, len(gdf), _elapsed(t0))
    if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
        _persist_qc_tables(input_count, 0)
        return

    step_name = "short line removal"
    in_count = len(gdf)
    if config.remove_short_lines:
        t0 = _step_timer()
        gdf, removed_gdf = _clean_line_geometries_min_length_m(gdf, config.minimum_line_length)
        gdf = gdf.reset_index(drop=True)
        _mark_layer("qc_removed_short", removed_gdf, notes="written" if _has_rows(removed_gdf) else "empty")
        _log_step(3, step_name, in_count, len(gdf), _elapsed(t0))
        if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
            _persist_qc_tables(input_count, 0)
            return
    else:
        qc_manifest["qc_removed_short"]["notes"] = "disabled"
        _log_step(3, step_name, in_count, in_count, skipped_reason="disabled")

    step_name = "CHM footprint clipping"
    in_count = len(gdf)
    if config.clip_to_chm_footprint:
        if in_raster:
            t0 = _step_timer()
            gdf, removed_gdf, footprint = _clip_to_chm_footprint(gdf, in_raster, config.chm_footprint_shrink)
            _mark_layer(
                "qc_removed_clipped", removed_gdf, notes="written" if _has_rows(removed_gdf) else "empty"
            )
            footprint_gdf = gpd.GeoDataFrame(
                [{"source": "chm_footprint_shrunken"}], geometry=[footprint], crs=gdf.crs
            )
            _mark_layer("chm_footprint", footprint_gdf, notes="written")
            _log_step(4, step_name, in_count, len(gdf), _elapsed(t0))
            if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
                _persist_qc_tables(input_count, 0)
                return
        else:
            qc_manifest["qc_removed_clipped"]["notes"] = "enabled but missing in_raster"
            qc_manifest["chm_footprint"]["notes"] = "enabled but missing in_raster"
            logger.error(
                "CHM footprint clipping enabled but 'in_raster' is missing; continuing without footprint clip."
            )
            _log_step(4, step_name, in_count, in_count, skipped_reason="enabled but missing in_raster")
    else:
        qc_manifest["qc_removed_clipped"]["notes"] = "disabled"
        qc_manifest["chm_footprint"]["notes"] = "disabled"
        _log_step(4, step_name, in_count, in_count, skipped_reason="disabled")

    step_name = "post-clip normalize + cleanup"
    in_count = len(gdf)
    t0 = _step_timer()
    gdf = _normalize_to_lines(gdf)
    gdf, removed_gdf = _clean_line_geometries_min_length_m(gdf, bt_const.SMALL_BUFFER)
    gdf = gdf.reset_index(drop=True)
    _mark_layer("qc_removed_post_clip", removed_gdf, notes="written" if _has_rows(removed_gdf) else "empty")
    _log_step(5, step_name, in_count, len(gdf), _elapsed(t0))
    if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
        _persist_qc_tables(input_count, 0)
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
            _persist_qc_tables(input_count, 0)
            return
    else:
        _log_step(6, step_name, in_count, in_count, skipped_reason="disabled")

    step_name = "qc_split_lines_at_intersections"
    in_count = len(gdf)
    t0 = _step_timer()
    prev_crs = gdf.crs
    split_out = qc_split_lines_at_intersections(gdf)
    gdf = _ensure_gdf(split_out, prev_crs)
    gdf, removed_gdf = _clean_line_geometries_min_length_m(gdf, config.minimum_line_length)
    gdf = gdf.reset_index(drop=True)
    _log_step(7, step_name, in_count, len(gdf), _elapsed(t0))
    if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
        _persist_qc_tables(input_count, 0)
        return

    step_name = "LineGrouping"
    in_count = len(gdf)
    if config.group_lines:
        t0 = _step_timer()
        lg = LineGrouping(gdf, use_angle_grouping=config.use_angle_grouping)
        lg.run_grouping()
        gdf = _ensure_gdf(lg.lines, gdf.crs).reset_index(drop=True)
        _log_step(8, step_name, in_count, len(gdf), _elapsed(t0))
        if _bail_if_empty(gdf, step_name, out_file, out_layer, in_count):
            _persist_qc_tables(input_count, 0)
            return
    else:
        gdf = _ensure_gdf(gdf, gdf.crs).reset_index(drop=True)
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
            _persist_qc_tables(input_count, 0)
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
            _persist_qc_tables(input_count, 0)
            return
    else:
        _log_step(10, step_name, in_count, in_count, skipped_reason="disabled")

    gdf, removed_gdf = _clean_line_geometries_min_length_m(gdf, bt_const.SMALL_BUFFER)
    gdf = gdf.reset_index(drop=True)
    _mark_layer("qc_removed_final", removed_gdf, notes="written" if _has_rows(removed_gdf) else "empty")

    _write_output(gdf, out_file, out_layer)
    _persist_qc_tables(input_count, len(gdf))
    print(f"Output saved to file: {out_file}, layer: {out_layer}")


if __name__ == "__main__":
    from beratools.utility.tool_args import compose_tool_kwargs

    start_time = time.time()
    kwargs = compose_tool_kwargs("check_seed_line")
    check_seed_line(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))
