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

import geopandas as gpd

import beratools.utility.spatial_common as sp_common
from beratools.core.algo_line_grouping import LineGrouping
from beratools.core.algo_split_with_lines import LineSplitter
from beratools.core.logger import Logger


def qc_merge_multilinestring(gdf):
    """
    QC step: Merge MultiLineStrings if possible, else split into LineStrings.

    Args:
        gdf (GeoDataFrame): Input GeoDataFrame.

    Returns:
        GeoDataFrame: Cleaned GeoDataFrame with only LineStrings.
    """
    records = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        # Try to merge MultiLineString
        if geom.geom_type == "MultiLineString":
            merged = custom_line_merge(geom)
            if merged.geom_type == "MultiLineString":
                # Could not merge, split into LineStrings
                for part in merged.geoms:
                    new_row = row.copy()
                    new_row.geometry = part
                    records.append(new_row)
            elif merged.geom_type == "LineString":
                new_row = row.copy()
                new_row.geometry = merged
                records.append(new_row)
            else:
                # Unexpected geometry, keep as is
                new_row = row.copy()
                new_row.geometry = merged
                records.append(new_row)
        elif geom.geom_type == "LineString":
            records.append(row)
        else:
            # Keep other geometry types unchanged
            records.append(row)
    # Build new GeoDataFrame
    out_gdf = gpd.GeoDataFrame(records, columns=gdf.columns, crs=gdf.crs)
    out_gdf = out_gdf[out_gdf.geometry.type == "LineString"].reset_index(drop=True)
    return out_gdf

def qc_split_lines_at_intersections(gdf):
    """
    QC step: Split lines at intersections so each segment becomes a separate line object.

    Args:
        gdf (GeoDataFrame): Input GeoDataFrame of LineStrings.

    Returns:
        GeoDataFrame: New GeoDataFrame with lines split at all intersection points.
    """
    splitter = LineSplitter(gdf)
    splitter.process()
    if splitter.split_lines_gdf is not None:
        return splitter.split_lines_gdf.reset_index(drop=True)
    else:
        return gdf.reset_index(drop=True)

def check_seed_line(
    in_line, out_line, verbose, processes=-1, in_layer=None, out_layer=None, use_angle_grouping=True
):
    print("check_seed_line started")
    in_line_gdf = gpd.read_file(in_line, layer=in_layer)
    in_line_gdf = qc_merge_multilinestring(in_line_gdf)
    in_line_gdf = qc_split_lines_at_intersections(in_line_gdf)
    lg = LineGrouping(in_line_gdf, use_angle_grouping=use_angle_grouping)
    lg.run_grouping()
    lg.lines.to_file(out_line, layer=out_layer)


log = Logger("check_seed_line", file_level=logging.INFO)
logger = log.get_logger()
print = log.print

if __name__ == "__main__":
    in_args, in_verbose = sp_common.check_arguments()
    start_time = time.time()
    check_seed_line(**in_args.input, processes=int(in_args.processes), verbose=in_verbose)

    print("Elapsed time: {}".format(time.time() - start_time))
