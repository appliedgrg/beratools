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

import geopandas as gpd

import beratools.utility.spatial_common as sp_common
from beratools.core.logger import Logger
from beratools.utility.tool_args import CallMode

log = Logger("check_seed_line", file_level=logging.INFO)
logger = log.get_logger()
print = log.print


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
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        row_dict = row.to_dict()
        # Try to merge MultiLineString
        if geom.geom_type == "MultiLineString":
            merged = custom_line_merge(geom)
            if merged.geom_type == "MultiLineString":
                # Could not merge, split into LineStrings
                for part in merged.geoms:
                    new_row = row_dict.copy()
                    new_row["geometry"] = part
                    if part.geom_type == "LineString":
                        records.append(new_row)
            elif merged.geom_type == "LineString":
                new_row = row_dict.copy()
                new_row["geometry"] = merged
                records.append(new_row)
            else:
                # Unexpected geometry, keep as is
                new_row = row_dict.copy()
                new_row["geometry"] = merged
                if hasattr(merged, "geom_type") and merged.geom_type == "LineString":
                    records.append(new_row)
        elif geom.geom_type == "LineString":
            records.append(row_dict)
        # else: skip non-LineString geometries

    # Build new GeoDataFrame
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
        else:
            return splitter.split_lines_gdf
    else:
        return gdf.reset_index(drop=True)


def check_seed_line(in_line, out_line, use_angle_grouping=True, 
                    processes=0, call_mode=CallMode.CLI, log_level="INFO"):
    from beratools.core.algo_line_grouping import LineGrouping
    
    in_file, in_layer = sp_common.decode_file_layer(in_line)
    print(f"Input file: {in_file}, layer: {in_layer}")
    out_file, out_layer = sp_common.decode_file_layer(out_line)

    in_line_gdf = gpd.read_file(in_file, layer=in_layer)
    in_line_gdf = qc_merge_multilinestring(in_line_gdf)
    in_line_gdf = qc_split_lines_at_intersections(in_line_gdf)
    lg = LineGrouping(in_line_gdf, use_angle_grouping=use_angle_grouping)
    lg.run_grouping()
    lg.lines.to_file(out_file, layer=out_layer)
    print(f"Output saved to file: {out_file}, layer: {out_layer}")


if __name__ == "__main__":
    import time

    import beratools.utility.tool_args as tool_args
    start_time = time.time()
    kwargs = tool_args.compose_tool_kwargs("check_seed_line")
    check_seed_line(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))
