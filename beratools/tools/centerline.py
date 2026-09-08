"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide main interface for centerline tool.
"""

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio
import beratools.core.algo_centerline as algo_centerline
import beratools.core.algo_common as algo_common
import beratools.core.constants as bt_const
import beratools.core.tool_geo_simplify as tool_geo_simplify
import beratools.utility.spatial_common as sp_common
import beratools.utility.unit_conversion as unit_conversion
from beratools.core.logger import Logger
from beratools.core.tool_base import execute_multiprocessing
from beratools.utility.tool_args import CallMode

LOGGER_NAME="centerline"
log = Logger(LOGGER_NAME, file_level=logging.DEBUG,console_level=logging.INFO)
logger = log.get_logger()
print = log.print


def _to_bool(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False

    return bool(value)


def generate_line_class_list(
    in_vector,
    in_raster,
    line_radius,
    layer=None,
    proc_segments=True,
    guided_strategy=bt_const.CENTERLINE_GUIDED_STRATEGY.value,
    centerline_method=bt_const.CENTERLINE_METHOD.value,
    lcp_simplify_enabled=False,
    lcp_simplify_diameter=10.0,
    lcp_smooth_enabled=False,
    lcp_smooth_iterations=1,
    chm_mode=bt_const.CENTERLINE_CHM_MODE.value,
    chm_buffer_width=5.0,
    chm_buffer_multiplier=0.5,
    astar_corridor_line_bias_weight=0.1,
    astar_corridor_distance_penalty_weight=0.2,
    corridor_simplify_polygon=False,
    corridor_simplify_length=0.5,
    corridor_smooth_polygon=False,
    corridor_polygon_smooth_iterations=1,
) -> list:
    line_classes = []
    line_list = algo_common.prepare_lines_gdf(in_vector, layer, proc_segments)

    for item in line_list:
        line_classes.append(
            algo_centerline.SeedLine(
                item,
                in_raster,
                proc_segments,
                line_radius,
                guided_strategy=guided_strategy,
                centerline_method=centerline_method,
                lcp_simplify_enabled=lcp_simplify_enabled,
                lcp_simplify_diameter=lcp_simplify_diameter,
                lcp_smooth_enabled=lcp_smooth_enabled,
                lcp_smooth_iterations=lcp_smooth_iterations,
                chm_mode=chm_mode,
                chm_buffer_width=chm_buffer_width,
                chm_buffer_multiplier=chm_buffer_multiplier,
                astar_corridor_line_bias_weight=astar_corridor_line_bias_weight,
                astar_corridor_distance_penalty_weight=astar_corridor_distance_penalty_weight,
                corridor_simplify_polygon=corridor_simplify_polygon,
                corridor_simplify_length=corridor_simplify_length,
                corridor_smooth_polygon=corridor_smooth_polygon,
                corridor_polygon_smooth_iterations=corridor_polygon_smooth_iterations,
            )
        )

    return line_classes


def process_single_line_class(seed_line):
    seed_line.compute()
    return seed_line


def centerline(
    in_line,
    in_raster,
    line_radius,
    proc_segments,
    out_line,
    centerline_method=bt_const.CENTERLINE_METHOD.value,
    guided_strategy=bt_const.CENTERLINE_GUIDED_STRATEGY.value,
    simplify_centerline=False,
    simplify_diameter=10.0,
    lcp_simplify_enabled=False,
    lcp_simplify_diameter=10.0,
    lcp_smooth_enabled=False,
    lcp_smooth_iterations=1,
    chm_mode=bt_const.CENTERLINE_CHM_MODE.value,
    chm_buffer_width=5.0,
    chm_buffer_multiplier=0.5,
    astar_corridor_line_bias_weight=0.1,
    astar_corridor_distance_penalty_weight=0.2,
    corridor_simplify_polygon=False,
    corridor_simplify_length=0.5,
    corridor_smooth_polygon=False,
    corridor_polygon_smooth_iterations=1,
    use_angle_grouping=True,
    processes=0,
    call_mode=CallMode.CLI,
    log_level="INFO",
):
    """Run centerline extraction.

    guided_strategy modes:
    - MAIN_ROUTE: unguided main-route extraction.
    - PAIRWISE: endpoint-guided search over endpoint node pairs.
    - VIRTUAL_NODES: endpoint-guided search using virtual source/destination graph nodes.
    - DIRECT_INSERT: endpoint-guided search by inserting endpoints directly into the Voronoi graph.
    """
    if isinstance(guided_strategy, str):
        guided_strategy = bt_const.CenterlineStrategy(guided_strategy)
    if isinstance(centerline_method, str):
        centerline_method = bt_const.CenterlineMethod(centerline_method)
    if isinstance(chm_mode, str):
        chm_mode = bt_const.CenterlineChmMode(chm_mode)

    guided_strategy_value = guided_strategy.value
    centerline_method_value = centerline_method.value
    chm_mode_value = chm_mode.value
    proc_segments = _to_bool(proc_segments)

    in_file, in_layer = sp_common.decode_file_layer(in_line)
    out_file, out_layer = sp_common.decode_file_layer(out_line)
    simplify_enabled = _to_bool(simplify_centerline)
    diameter = tool_geo_simplify.validate_diameter(simplify_diameter)
    line_radius_m = float(line_radius)

    vec_crs_osr = sp_common.vector_crs(in_file, in_layer)
    line_radius_native = unit_conversion.convert_meters_param_projected_from_osr(
        vec_crs_osr,
        line_radius_m,
        "Line Processing Radius (m)",
    )
    chm_buffer_width_native = unit_conversion.convert_meters_param_projected_from_osr(
        vec_crs_osr,
        float(chm_buffer_width),
        "CHM Buffer Width (m)",
    )

    if not sp_common.compare_crs(vec_crs_osr, sp_common.raster_crs(in_raster)):
        print("Line and CHM have different spatial references, please check.")
        return

    with rasterio.open(in_raster) as src:
        cell_size = max(abs(float(src.transform.a)), abs(float(src.transform.e)), )

    if not sp_common.check_vector_raster_extent_overlap(in_file, in_layer, in_raster):
        print("Input line extent does not overlap input raster extent.")
        return

    line_gdf = gpd.read_file(in_file, layer=in_layer)
    if not sp_common.check_vector_raster_overlap(line_gdf, in_raster):
        print("Input line(s) do not overlap input raster.")
        return

    line_class_list = generate_line_class_list(
        in_file,
        in_raster,
        line_radius=line_radius_native,
        layer=in_layer,
        proc_segments=proc_segments,
        guided_strategy=guided_strategy_value,
        centerline_method=centerline_method_value,
        lcp_simplify_enabled=_to_bool(lcp_simplify_enabled),
        lcp_simplify_diameter=tool_geo_simplify.validate_diameter(lcp_simplify_diameter),
        lcp_smooth_enabled=_to_bool(lcp_smooth_enabled),
        lcp_smooth_iterations=int(lcp_smooth_iterations),
        chm_mode=chm_mode_value,
        chm_buffer_width=chm_buffer_width_native,
        chm_buffer_multiplier=float(chm_buffer_multiplier),
        astar_corridor_line_bias_weight=float(astar_corridor_line_bias_weight),
        astar_corridor_distance_penalty_weight=float(astar_corridor_distance_penalty_weight),
        corridor_simplify_polygon=_to_bool(corridor_simplify_polygon),
        corridor_simplify_length=float(corridor_simplify_length),
        corridor_smooth_polygon=_to_bool(corridor_smooth_polygon),
        corridor_polygon_smooth_iterations=int(corridor_polygon_smooth_iterations),
    )

    print("{} lines to be processed.".format(len(line_class_list)))

    lc_path_list = []
    centerline_list = []
    corridor_poly_list = []
    result = execute_multiprocessing(
        process_single_line_class,
        line_class_list,
        "Centerline",
        processes,
        call_mode,
        logger_name = LOGGER_NAME)
    if not result:
        print("No centerlines found.")
        return 1

    for item in result:
        lc_path_list.append(item.lc_path)
        centerline_list.append(item.centerline)
        corridor_poly_list.append(item.corridor_poly_gpd)

    # Concatenate the lists of GeoDataFrames into single GeoDataFrames
    if len(lc_path_list) == 0 or len(centerline_list) == 0 or len(corridor_poly_list) == 0:
        print("No centerline generated.")
        return 1

    lc_path_list = pd.concat(lc_path_list, ignore_index=True)
    centerline_list = pd.concat(centerline_list, ignore_index=True)
    corridor_polys = pd.concat(corridor_poly_list, ignore_index=True)

    # Make sure they remain GeoDataFrames:
    lc_path_gdf = gpd.GeoDataFrame(lc_path_list,
        geometry="geometry",crs=line_gdf.crs,)

    centerline_gdf = gpd.GeoDataFrame(centerline_list,
        geometry="geometry",crs=line_gdf.crs,)

    corridor_gdf = gpd.GeoDataFrame(corridor_polys,
        geometry="geometry",crs=line_gdf.crs,)

    # Save the concatenated GeoDataFrames to the shapefile/gpkg
    logger.info("Clean geometries....")
    centerline_gdf = algo_common.clean_geometries(
        centerline_gdf,
        stage="output",
        out_file=out_file,
        layer="rejected_output_centerlines",)

    lc_path_gdf = algo_common.clean_geometries(
        lc_path_gdf,
        stage="lcp_segments",
        out_file=out_file,
        layer="rejected_lcp_segments",
    )

    corridor_gdf = algo_common.clean_geometries(
        corridor_gdf,
        stage="corridor_segments",
        out_file=out_file,
        layer="rejected_corridor_segments",
    )
    logger.info("Clean geometries....Done")

    dissolved_cl_orig=centerline_gdf
    dissolved_lcp_orig=lc_path_gdf
    dissolved_corridor_orig=corridor_gdf
    aux_file = algo_common.get_aux_path(out_file)
    if proc_segments:
        logger.info("Dissolving segments...")

        dissolved_cl = (
            algo_common.merge_lines_by_original_id(
                line_gdf=dissolved_cl_orig,
                group_field="OLnFID",
                order_field="OLnSEG",
                max_bridge_gap=max(
                    cell_size * 1.5,
                    0.5,
                ),
                geometry_count_field=(
                    "merged_centerline_part_count"
                ),
            )
        )
        # for fid in [232]:
        #
        #     rows = dissolved_cl[
        #         dissolved_cl["OLnFID"] == fid
        #         ]
        #
        #     if len(rows):
        #         logger.file_only(
        #             f"POST_MERGE {fid}: "
        #             f"merge_status={rows.iloc[0]['merge_status']} "
        #             f"type={rows.geometry.iloc[0].geom_type} "
        #             f"length={rows.geometry.iloc[0].length:.2f}"
        #         )


        dissolved_cl = algo_common.clean_geometries(
            dissolved_cl,
            stage="merged_centerlines",
            out_file=out_file,
            layer="rejected_merged_centerline_geometry",
        )
        # for fid in [232]:
        #
        #     rows = dissolved_cl[
        #         dissolved_cl["OLnFID"] == fid
        #         ]
        #
        #     if len(rows):
        #         geom = rows.geometry.iloc[0]
        #
        #         logger.file_only(
        #             f"PRE_QC {fid}: "
        #             f"type={geom.geom_type} "
        #             f"length={geom.length:.2f}"
        #         )

        dissolved_lcp = (
            algo_common.merge_lines_by_original_id(
                line_gdf=dissolved_lcp_orig,
                group_field="OLnFID",
                order_field="OLnSEG",
                max_bridge_gap=max(
                    cell_size * 0.75,
                    0.05,
                ),
                geometry_count_field=(
                    "merged_lcp_part_count"
                ),
            )
        )

        dissolved_corridor = (
            algo_common.merge_corridors_by_original_id(
                dissolved_corridor_orig,
                group_field="OLnFID",
                order_field="OLnSEG",
            )
        )


        if dissolved_cl is None or dissolved_cl.empty:
            print("No centerlines remained after merging.")
            return 1

        # for fid in [232]:
        #
        #     rows = dissolved_cl[
        #         dissolved_cl["OLnFID"] == fid
        #         ]
        #
        #     if len(rows):
        #         geom = rows.geometry.iloc[0]
        #
        #         logger.file_only(
        #             f"PRE_QC {fid}: "
        #             f"type={geom.geom_type} "
        #             f"length={geom.length:.2f}"
        #         )

        valid_mask = dissolved_cl.geometry.apply(
            lambda geom: not algo_common._is_degenerate_line(
                geom,
                min_length=max(cell_size, 1.0),
                endpoint_tolerance=max(
                    cell_size * 0.01,
                    1e-6,
                ),
                min_straightness=0.10,
                stage="final",
            )
        )

        rejected_final = dissolved_cl.loc[~valid_mask].copy()

        dissolved_cl = dissolved_cl.loc[valid_mask].copy()

        # for fid in [232]:
        #
        #     if (
        #             rejected_final["OLnFID"] == fid
        #     ).any():
        #         logger.file_only(
        #             f"FINAL_QC_REJECTED {fid}"
        #         )

        if not rejected_final.empty:
            rejected_final["BT_REJECT_REASON"] = (
                "degenerate_after_merge"
            )

            rejected_final.to_file(
                aux_file,
                layer="rejected_merged_centerlines",
            )

        if dissolved_cl.empty:
            print(
                "All merged centerlines failed final QC."
            )
            return 1

        logger.info("Dissolving segments...Done")

    # for fid in [232]:
    #     rows = dissolved_cl[
    #         dissolved_cl["OLnFID"] == fid
    #         ]
    #
    #     logger.file_only(
    #         f"PRE_SAVE {fid}: count={len(rows)}"
    #     )

    if simplify_enabled and diameter > 0:
        temp_file = tool_geo_simplify.build_temp_output_same_folder(
            out_file,
            prefix=f"{Path(out_file).stem}_centerline_tmp_",
        )
        temp_layer = "centerline_temp"
        try:
            dissolved_cl.to_file(temp_file.as_posix(), layer=temp_layer)
            tool_geo_simplify.run_reduce_bend(
                input_file=temp_file,
                in_layer=temp_layer,
                output_file=out_file,
                out_layer=out_layer,
                diameter=diameter,
                smooth_line=True,
            )
        finally:
            if temp_file.exists():
                temp_file.unlink()
    else:
        if simplify_enabled and diameter == 0:
            print("Centerline simplify enabled with diameter 0; skipping simplify step.")
        dissolved_cl.to_file(out_file, layer=out_layer)

    print(f"Saved centerlines to: {out_file}")

    aux_file = algo_common.get_aux_path(out_file)
    print(f"Saved auxiliary data to: {aux_file}")

    # Save lc_path_list and corridor_polys to the new GeoPackage with '_aux' suffix
    if proc_segments:
        centerline_gdf.to_file(aux_file,layer="centerline_segments",)
        lc_path_gdf.to_file(aux_file,layer="least_cost_path_segments",)
        corridor_gdf.to_file(aux_file,layer="corridor_polygon_segments",)

    dissolved_lcp.to_file(aux_file, layer="dissolved_lcp")
    dissolved_corridor.to_file(aux_file, layer="dissolved_corridor")

    return 0


if __name__ == "__main__":
    import time

    from beratools.utility.tool_args import compose_tool_kwargs

    start_time = time.time()
    kwargs = compose_tool_kwargs("centerline")
    centerline(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))
