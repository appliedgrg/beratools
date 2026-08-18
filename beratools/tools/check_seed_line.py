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
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

import geopandas as gpd

import beratools.core.constants as bt_const
import beratools.core.algo_common as algo_common
from beratools.core.algo_check_seed_line import (
    _choose_anchor,
    _clean_line_geometries_min_length_m,
    _clip_to_chm_footprint,
    _default_close_distance_m,
    _densify_linestring,
    _densify_long_lines,
    _geometry_length_meters,
    _interp_coord,
    _iter_line_parts,
    _normalize_to_lines,
    _parse_line_id,
    _preclean_lines_full,
    _snap_close_endpoints,
    qc_merge_multilinestring,
    qc_split_lines_at_intersections,
)
import beratools.utility.spatial_common as sp_common
import beratools.utility.unit_conversion as unit_conversion
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
    preclean_vertices: bool = True
    preclean_close_distance: Optional[float] = None
    preclean_angle_tolerance: float = 10.0
    snap_close_endpoints: bool = False
    snap_tolerance: float = 5.0
    group_lines: bool = False
    densify_long_lines: bool = False
    max_segment_length: float = bt_const.LP_SEGMENT_LENGTH
    use_angle_grouping: bool = True
    apply_seed_line_correction: bool = False
    slc_search_distance: float = 5.0
    slc_line_radius: float = 15.0
    slc_optimize_internal_vertices: bool = False


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
    verbose=False,
    skipped_steps=None,
):
    label = step_name.ljust(34)

    if skipped_reason:
        if verbose:
            print(f"↷ {label} {in_count} -> {out_count}")
        elif skipped_steps is not None:
            _record_skipped_step(skipped_steps, step_idx, step_name, skipped_reason)
        logger.debug(
            "Step %s - %s skipped (%s): %s -> %s",
            step_idx,
            step_name,
            skipped_reason,
            in_count,
            out_count,
        )
        return

    if elapsed is None:
        print(f"✓ {label} {in_count} -> {out_count}")
        return

    print(f"✓ {label} {in_count} -> {out_count} {elapsed:.3f}s")


def _print_skipped_summary(skipped_steps):
    if not skipped_steps:
        return

    option_order = {
        "Clip to CHM footprint": 0,
        "Remove short lines": 1,
        "Preclean vertices": 2,
        "Snap close endpoints": 3,
        "Group lines": 4,
        "Densify long lines": 5,
        "Apply Seed Line Correction": 6,
    }
    skipped_steps = sorted(
        skipped_steps,
        key=lambda item: (option_order.get(item[1], 99), item[0]),
    )

    lines = []
    for _, step_name, _ in skipped_steps:
        label = step_name.ljust(34)
        lines.append(f"↷ {label} skipped")
    print("\n".join(lines))


def _print_qc_summary(qc_summary, aux_file):
    if qc_summary["total"] > 0:
        print("QC Report Summary:")
        print(f"  Short lines:           {qc_summary['short_line']} issues")
        print(f"  Close vertices:        {qc_summary['close_vertices']} issues")
        print(f"  Unsnapped endpoints:   {qc_summary['unsnapped_endpoint']} issues")
        print(f"  Self-crossing:         {qc_summary['self_crossing']} issues")
        print(f"  Overlapping lines:     {qc_summary['overlap']} issues")
        print(f"  {'-' * 35}")
        print(f"  Total issues:          {qc_summary['total']}")
        print(f"  Details saved to: {aux_file} (layer: qc_report_issues)")
    else:
        print("QC Report: No issues found.")


def _record_skipped_step(skipped_steps, step_idx, step_name, reason):
    if skipped_steps is None:
        return

    if any(existing_step_name == step_name for _, existing_step_name, _ in skipped_steps):
        return

    skipped_steps.append((step_idx, step_name, reason))


def _bail_if_empty(gdf, step_name, out_file, out_layer, in_count, skipped_steps=None):
    if not gdf.empty:
        return False

    if skipped_steps:
        _print_skipped_summary(skipped_steps)

    logger.warning(
        "Seed line QC early return after '%s' produced empty output (%s -> 0).",
        step_name,
        in_count,
    )
    print("QC Report skipped: output became empty before Step 12.")
    _write_output(gdf.iloc[0:0].copy(), out_file, out_layer)
    return True


def _step_timer():
    return time.perf_counter()


def _elapsed(start_t):
    return time.perf_counter() - start_t


def _convert_slc_meter_params_to_native_units(lines_gdf, search_distance_m, line_radius_m):
    """Convert SLC meter parameters to source CRS linear units."""
    search_distance_native = unit_conversion.convert_meters_param_projected(
        lines_gdf,
        search_distance_m,
        "Apply Seed Line Correction search distance (m)",
        min_value=bt_const.SMALL_BUFFER,
    )
    line_radius_native = unit_conversion.convert_meters_param_projected(
        lines_gdf,
        line_radius_m,
        "Apply Seed Line Correction line radius (m)",
        min_value=bt_const.SMALL_BUFFER,
    )
    return search_distance_native, line_radius_native


def check_seed_line(
    in_line,
    in_raster,
    out_line,
    chm_footprint_shrink=15.0,
    clip_to_chm_footprint=True,
    remove_short_lines=False,
    minimum_line_length=5.0,
    preclean_vertices=True,
    preclean_close_distance=None,
    preclean_angle_tolerance=10.0,
    snap_close_endpoints=False,
    snap_tolerance=5.0,
    group_lines=False,
    densify_long_lines=False,
    max_segment_length=bt_const.LP_SEGMENT_LENGTH,
    use_angle_grouping=True,
    apply_seed_line_correction=False,
    slc_search_distance=5.0,
    slc_line_radius=15.0,
    slc_optimize_internal_vertices=False,
    processes=0,
    call_mode=CallMode.CLI,
    log_level="INFO",
):
    from beratools.core.algo_line_grouping import LineGrouping

    level_name = str(log_level).upper()
    level_value = getattr(logging, level_name, logging.INFO)
    verbose_steps = level_value <= logging.DEBUG
    logger.setLevel(level_value)
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(level_value)

    config = SeedLineQCConfig(
        chm_footprint_shrink=float(chm_footprint_shrink),
        clip_to_chm_footprint=_to_bool(clip_to_chm_footprint),
        remove_short_lines=_to_bool(remove_short_lines),
        minimum_line_length=float(minimum_line_length),
        preclean_vertices=_to_bool(preclean_vertices),
        preclean_close_distance=None
        if preclean_close_distance in (None, "", "none")
        else float(preclean_close_distance),
        preclean_angle_tolerance=float(preclean_angle_tolerance),
        snap_close_endpoints=_to_bool(snap_close_endpoints),
        snap_tolerance=float(snap_tolerance),
        group_lines=_to_bool(group_lines),
        densify_long_lines=_to_bool(densify_long_lines),
        max_segment_length=max(float(max_segment_length),bt_const.LP_SEGMENT_LENGTH),
        use_angle_grouping=_to_bool(use_angle_grouping),
        apply_seed_line_correction=_to_bool(apply_seed_line_correction),
        slc_search_distance=float(slc_search_distance),
        slc_line_radius=float(slc_line_radius),
        slc_optimize_internal_vertices=_to_bool(slc_optimize_internal_vertices),
    )

    skipped_steps = []

    in_file, in_layer = sp_common.decode_file_layer(in_line)
    out_file, out_layer = sp_common.decode_file_layer(out_line)
    aux_file = algo_common.get_aux_path(out_file)
    effective_preclean_close_distance = (
        _default_close_distance_m(in_raster)
        if config.preclean_close_distance is None
        else float(config.preclean_close_distance)
    )

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
            "step": 4,
            "step_name": "short line removal",
            "reason": "Lines below user minimum length",
            "feature_count": 0,
            "written": 0,
            "notes": "disabled",
        },
        "qc_removed_clipped": {
            "layer_name": "qc_removed_clipped",
            "step": 3,
            "step_name": "CHM footprint clipping",
            "reason": "Lines outside shrunken CHM footprint",
            "feature_count": 0,
            "written": 0,
            "notes": "not triggered",
        },
        "chm_footprint": {
            "layer_name": "chm_footprint",
            "step": 3,
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
        "qc_removed_preclean": {
            "layer_name": "qc_removed_preclean",
            "step": 6,
            "step_name": "preclean vertices",
            "reason": "Removes near-duplicate endpoint vertices and simplifies close interior vertices with angle-aware bend preservation.",
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
        "qc_report_issues": {
            "layer_name": "qc_report_issues",
            "step": 12,
            "step_name": "QC report",
            "reason": "Post-processing QC check results (using 2x thresholds)",
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
            "preclean_vertices": int(config.preclean_vertices),
            "preclean_mode": "full",
            "preclean_close_distance_m": float(effective_preclean_close_distance),
            "preclean_angle_tolerance_deg": float(config.preclean_angle_tolerance),
            "snap_close_endpoints": int(config.snap_close_endpoints),
            "snap_tolerance_m": float(config.snap_tolerance),
            "group_lines": int(config.group_lines),
            "densify_long_lines": int(config.densify_long_lines),
            "max_segment_length_m": float(config.max_segment_length),
            "apply_seed_line_correction": int(config.apply_seed_line_correction),
            "slc_search_distance": float(config.slc_search_distance),
            "slc_line_radius": float(config.slc_line_radius),
            "slc_optimize_internal_vertices": int(config.slc_optimize_internal_vertices),
            "input_feature_count": int(input_count),
            "output_feature_count": int(output_count),
        }
        algo_common.save_aux_table([summary_row], out_file, "qc_run_summary", overwrite=True)

    if in_raster:
        if not sp_common.compare_crs(
            sp_common.vector_crs(in_file, in_layer), sp_common.raster_crs(in_raster)
        ):
            raise ValueError("Input line and raster CRS do not match.")

    gdf = gpd.read_file(in_file, layer=in_layer)
    if (
        config.clip_to_chm_footprint
        and in_raster
        and not sp_common.seedlines_within_chm_footprint(gdf, in_raster)
    ):
        raise ValueError("Input line(s) do not overlap input raster.")
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

    step_name = "Normalize multiline seed lines"
    in_count = len(gdf)
    t0 = _step_timer()
    gdf = qc_merge_multilinestring(gdf)
    _log_step(
        1, step_name, in_count, len(gdf), _elapsed(t0), verbose=verbose_steps, skipped_steps=skipped_steps
    )
    if _bail_if_empty(
        gdf,
        step_name,
        out_file,
        out_layer,
        in_count,
        skipped_steps=skipped_steps,
    ):
        _persist_qc_tables(input_count, 0)
        return

    step_name = "Geometry cleanup"
    in_count = len(gdf)
    t0 = _step_timer()
    gdf, removed_gdf = _clean_line_geometries_min_length_m(gdf, bt_const.SMALL_BUFFER)
    gdf = gdf.reset_index(drop=True)
    _mark_layer("qc_removed_cleanup", removed_gdf, notes="written" if _has_rows(removed_gdf) else "empty")
    _log_step(
        2, step_name, in_count, len(gdf), _elapsed(t0), verbose=verbose_steps, skipped_steps=skipped_steps
    )
    if _bail_if_empty(
        gdf,
        step_name,
        out_file,
        out_layer,
        in_count,
        skipped_steps=skipped_steps,
    ):
        _persist_qc_tables(input_count, 0)
        return

    step_name = "Clip to CHM footprint"
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
            _log_step(
                3,
                step_name,
                in_count,
                len(gdf),
                _elapsed(t0),
                verbose=verbose_steps,
                skipped_steps=skipped_steps,
            )
            if _bail_if_empty(
                gdf,
                step_name,
                out_file,
                out_layer,
                in_count,
                skipped_steps=skipped_steps,
            ):
                _persist_qc_tables(input_count, 0)
                return
        else:
            qc_manifest["qc_removed_clipped"]["notes"] = "enabled but missing in_raster"
            qc_manifest["chm_footprint"]["notes"] = "enabled but missing in_raster"
            logger.error(
                "CHM footprint clipping enabled but 'in_raster' is missing; continuing without footprint clip."
            )
            _log_step(
                3,
                step_name,
                in_count,
                in_count,
                skipped_reason="enabled but missing in_raster",
                verbose=verbose_steps,
                skipped_steps=skipped_steps,
            )
    else:
        qc_manifest["qc_removed_clipped"]["notes"] = "disabled"
        qc_manifest["chm_footprint"]["notes"] = "disabled"
        _log_step(
            3,
            step_name,
            in_count,
            in_count,
            skipped_reason="disabled",
            verbose=verbose_steps,
            skipped_steps=skipped_steps,
        )

    step_name = "Remove short lines"
    in_count = len(gdf)
    if config.remove_short_lines:
        t0 = _step_timer()
        gdf, removed_gdf = _clean_line_geometries_min_length_m(gdf, config.minimum_line_length)
        gdf = gdf.reset_index(drop=True)
        _mark_layer("qc_removed_short", removed_gdf, notes="written" if _has_rows(removed_gdf) else "empty")
        _log_step(
            4, step_name, in_count, len(gdf), _elapsed(t0), verbose=verbose_steps, skipped_steps=skipped_steps
        )
        if _bail_if_empty(
            gdf,
            step_name,
            out_file,
            out_layer,
            in_count,
            skipped_steps=skipped_steps,
        ):
            _persist_qc_tables(input_count, 0)
            return
    else:
        qc_manifest["qc_removed_short"]["notes"] = "disabled"
        _log_step(
            4,
            step_name,
            in_count,
            in_count,
            skipped_reason="disabled",
            verbose=verbose_steps,
            skipped_steps=skipped_steps,
        )

    step_name = "Post-clip cleanup"
    in_count = len(gdf)
    t0 = _step_timer()
    gdf = _normalize_to_lines(gdf)
    gdf, removed_gdf = _clean_line_geometries_min_length_m(gdf, bt_const.SMALL_BUFFER)
    gdf = gdf.reset_index(drop=True)
    _mark_layer("qc_removed_post_clip", removed_gdf, notes="written" if _has_rows(removed_gdf) else "empty")
    _log_step(
        5, step_name, in_count, len(gdf), _elapsed(t0), verbose=verbose_steps, skipped_steps=skipped_steps
    )
    if _bail_if_empty(
        gdf,
        step_name,
        out_file,
        out_layer,
        in_count,
        skipped_steps=skipped_steps,
    ):
        _persist_qc_tables(input_count, 0)
        return

    step_name = "Preclean vertices"
    in_count = len(gdf)
    if config.preclean_vertices:
        t0 = _step_timer()
        gdf, removed_gdf = _preclean_lines_full(
            gdf,
            close_distance_m=effective_preclean_close_distance,
            angle_tol_deg=config.preclean_angle_tolerance,
        )
        gdf = gdf.reset_index(drop=True)
        _mark_layer(
            "qc_removed_preclean", removed_gdf, notes="written" if _has_rows(removed_gdf) else "empty"
        )
        _log_step(
            6, step_name, in_count, len(gdf), _elapsed(t0), verbose=verbose_steps, skipped_steps=skipped_steps
        )
        if _bail_if_empty(
            gdf,
            step_name,
            out_file,
            out_layer,
            in_count,
            skipped_steps=skipped_steps,
        ):
            _persist_qc_tables(input_count, 0)
            return
    else:
        qc_manifest["qc_removed_preclean"]["notes"] = "disabled"
        _log_step(
            6,
            step_name,
            in_count,
            in_count,
            skipped_reason="disabled",
            verbose=verbose_steps,
            skipped_steps=skipped_steps,
        )

    step_name = "Snap close endpoints"
    in_count = len(gdf)
    if config.snap_close_endpoints:
        t0 = _step_timer()
        effective_tolerance = config.snap_tolerance
        if config.remove_short_lines:
            effective_tolerance = max(effective_tolerance, config.minimum_line_length)
        gdf = _snap_close_endpoints(gdf, effective_tolerance).reset_index(drop=True)
        _log_step(
            7, step_name, in_count, len(gdf), _elapsed(t0), verbose=verbose_steps, skipped_steps=skipped_steps
        )
        if _bail_if_empty(
            gdf,
            step_name,
            out_file,
            out_layer,
            in_count,
            skipped_steps=skipped_steps,
        ):
            _persist_qc_tables(input_count, 0)
            return
    else:
        _log_step(
            7,
            step_name,
            in_count,
            in_count,
            skipped_reason="disabled",
            verbose=verbose_steps,
            skipped_steps=skipped_steps,
        )

    step_name = "Split lines at intersections"
    in_count = len(gdf)
    t0 = _step_timer()
    prev_crs = gdf.crs
    split_out = qc_split_lines_at_intersections(gdf)
    gdf = _ensure_gdf(split_out, prev_crs)
    split_min_length = config.minimum_line_length if config.remove_short_lines else bt_const.SMALL_BUFFER
    gdf, removed_gdf = _clean_line_geometries_min_length_m(gdf, split_min_length)
    gdf = gdf.reset_index(drop=True)
    _log_step(
        8, step_name, in_count, len(gdf), _elapsed(t0), verbose=verbose_steps, skipped_steps=skipped_steps
    )
    if _bail_if_empty(
        gdf,
        step_name,
        out_file,
        out_layer,
        in_count,
        skipped_steps=skipped_steps,
    ):
        _persist_qc_tables(input_count, 0)
        return

    step_name = "Group lines"
    in_count = len(gdf)
    if config.group_lines:
        t0 = _step_timer()
        lg = LineGrouping(gdf, use_angle_grouping=config.use_angle_grouping)
        lg.run_grouping()
        gdf = _ensure_gdf(lg.lines, gdf.crs).reset_index(drop=True)
        _log_step(
            9, step_name, in_count, len(gdf), _elapsed(t0), verbose=verbose_steps, skipped_steps=skipped_steps
        )
        if _bail_if_empty(
            gdf,
            step_name,
            out_file,
            out_layer,
            in_count,
            skipped_steps=skipped_steps,
        ):
            _persist_qc_tables(input_count, 0)
            return
    else:
        gdf = _ensure_gdf(gdf, gdf.crs).reset_index(drop=True)
        gdf[bt_const.BT_GROUP] = list(range(len(gdf)))
        _log_step(
            9,
            step_name,
            in_count,
            len(gdf),
            skipped_reason="disabled; assigned unique BT_GROUP",
            verbose=verbose_steps,
            skipped_steps=skipped_steps,
        )

    step_name = "Densify long lines"
    in_count = len(gdf)
    if config.densify_long_lines:
        t0 = _step_timer()
        gdf = _densify_long_lines(gdf, config.max_segment_length).reset_index(drop=True)
        _log_step(
            10,
            step_name,
            in_count,
            len(gdf),
            _elapsed(t0),
            verbose=verbose_steps,
            skipped_steps=skipped_steps,
        )
        if _bail_if_empty(
            gdf,
            step_name,
            out_file,
            out_layer,
            in_count,
            skipped_steps=skipped_steps,
        ):
            _persist_qc_tables(input_count, 0)
            return
    else:
        _log_step(
            10,
            step_name,
            in_count,
            in_count,
            skipped_reason="disabled",
            verbose=verbose_steps,
            skipped_steps=skipped_steps,
        )

    step_name = "Apply Seed Line Correction"
    in_count = len(gdf)
    if config.apply_seed_line_correction:
        from beratools.core.algo_seed_line_correction import SeedLineCorrection

        print("Starting Seed Line Correction...", flush=True)

        slc_search_distance_native, slc_line_radius_native = _convert_slc_meter_params_to_native_units(
            gdf,
            config.slc_search_distance,
            config.slc_line_radius,
        )

        t0 = _step_timer()
        try:
            slc = SeedLineCorrection(
                in_file,
                in_raster,
                slc_search_distance_native,
                slc_line_radius_native,
                processes,
                call_mode,
                layer=in_layer,
                optimize_internal_vertices=config.slc_optimize_internal_vertices,
            )
            slc.prepare_lines(lines_gdf=gdf)
            slc.group_vertices()
            gdf = _ensure_gdf(slc.optimize(), gdf.crs).reset_index(drop=True)
            debug_layers = slc.get_debug_layers()
            algo_common.save_aux_layer(debug_layers.get("lc_paths"), out_file, "lc_paths")
            algo_common.save_aux_layer(debug_layers.get("anchors"), out_file, "anchors")
            algo_common.save_aux_layer(debug_layers.get("vertices"), out_file, "vertices")
        except Exception:
            logger.exception("Apply Seed Line Correction failed; QC report step was not reached.")
            raise
        _log_step(
            11,
            step_name,
            in_count,
            len(gdf),
            _elapsed(t0),
            verbose=verbose_steps,
            skipped_steps=skipped_steps,
        )
        if _bail_if_empty(
            gdf,
            step_name,
            out_file,
            out_layer,
            in_count,
            skipped_steps=skipped_steps,
        ):
            _persist_qc_tables(input_count, 0)
            return
    else:
        _log_step(
            11,
            step_name,
            in_count,
            in_count,
            skipped_reason="disabled",
            verbose=verbose_steps,
            skipped_steps=skipped_steps,
        )

    gdf, removed_gdf = _clean_line_geometries_min_length_m(gdf, bt_const.SMALL_BUFFER)
    gdf = gdf.reset_index(drop=True)
    _mark_layer("qc_removed_final", removed_gdf, notes="written" if _has_rows(removed_gdf) else "empty")

    step_name = "Generate QC Report"
    from beratools.core.algo_check_seed_line_validate import generate_qc_report

    print("Running final validation pass to detect remaining issues after all previous steps...")
    t0 = _step_timer()
    qc_issues_gdf, qc_summary = generate_qc_report(
        gdf,
        min_length_m=config.minimum_line_length * 2.0,
        close_distance_m=effective_preclean_close_distance * 2.0,
        snap_tolerance_m=config.snap_tolerance * 2.0,
    )
    _mark_layer("qc_report_issues", qc_issues_gdf)
    _log_step(
        12,
        step_name,
        len(gdf),
        qc_summary["total"],
        _elapsed(t0),
        verbose=verbose_steps,
        skipped_steps=skipped_steps,
    )
    _print_qc_summary(qc_summary, aux_file)

    if not verbose_steps and skipped_steps:
        _print_skipped_summary(skipped_steps)

    _write_output(gdf, out_file, out_layer)
    _persist_qc_tables(input_count, len(gdf))
    print(f"Output saved to file: {out_file}, layer: {out_layer}")


if __name__ == "__main__":
    from beratools.utility.tool_args import compose_tool_kwargs

    start_time = time.time()
    kwargs = compose_tool_kwargs("check_seed_line")
    check_seed_line(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))
