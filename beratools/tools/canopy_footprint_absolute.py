"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide main interface for canopy footprint tool.
    The tool is used to generate the footprint of a line based on absolute threshold.
"""

import time

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from shapely.geometry import shape, MultiPolygon, Polygon
from rasterio.transform import rowcol

import beratools.core.algo_centerline as algo_cl
import beratools.core.algo_common as algo_common
import beratools.core.algo_cost as algo_cost
import beratools.core.constants as bt_const
import beratools.core.tool_base as bt_base
import beratools.utility.spatial_common as sp_common


class FootprintAbsolute:
    """Class to compute the footprint of a line based on absolute threshold."""

    def __init__(
        self,
        line_seg,
        in_chm,
        corridor_thresh,
        max_ln_width,
        exp_shk_cell,
    ):
        self.line_seg = line_seg
        self.in_chm = in_chm
        self.corridor_thresh = corridor_thresh
        self.max_ln_width = max_ln_width
        self.exp_shk_cell = exp_shk_cell

        self.footprint = None
        self.corridor_poly_gpd = None
        self.centerline = None

    def compute(self):
        """Generate line footprint."""
        in_chm = self.in_chm
        corridor_thresh = self.corridor_thresh
        line_gpd = self.line_seg
        max_ln_width = self.max_ln_width
        exp_shk_cell = self.exp_shk_cell

        try:
            print("FootprintAbsolute.compute: started")
            corridor_thresh = float(corridor_thresh)
            if corridor_thresh < 0.0:
                corridor_thresh = 3.0
        except ValueError as e:
            print(f"FootprintAbsolute.compute: ValueError {e}")
            corridor_thresh = 3.0
        except Exception as e:
            print(f"FootprintAbsolute.compute: exception {e}")

        segment_list = []
        feat = self.line_seg.geometry[0]
        for coord in feat.coords:
            segment_list.append(coord)

        # Find origin and destination coordinates
        x1, y1 = segment_list[0][0], segment_list[0][1]
        x2, y2 = segment_list[-1][0], segment_list[-1][1]

        # Buffer around line and clip cost raster and canopy raster
        # TODO: deal with NODATA
        clip_cost, out_meta = sp_common.clip_raster(in_chm, feat, max_ln_width)
        out_transform = out_meta["transform"]
        cell_size_x = out_transform[0]
        cell_size_y = -out_transform[4]

        clip_cost, clip_canopy = algo_cost.cost_raster(clip_cost, out_meta)

        # Work out the corridor from both end of the centerline
        if len(clip_canopy.shape) > 2:
            clip_canopy = np.squeeze(clip_canopy, axis=0)

        source = [rowcol(out_transform, x1, y1)]
        destination = [rowcol(out_transform, x2, y2)]

        corridor_thresh = algo_common.corridor_raster(
            clip_cost,
            out_meta,
            source,
            destination,
            (cell_size_x, cell_size_y),
            corridor_thresh,
        )

        clean_raster = algo_common.morph_raster(corridor_thresh, clip_canopy, exp_shk_cell, cell_size_x)

        # create mask for non-polygon area
        msk = np.where(clean_raster == 1, True, False)
        if clean_raster.dtype == np.int64:
            clean_raster = clean_raster.astype(np.int32)

        # Process: ndarray to shapely Polygon
        out_polygon = features.shapes(clean_raster, mask=msk, transform=out_transform)

        # create a shapely multipolygon
        multi_polygon = []
        for shp, value in out_polygon:
            multi_polygon.append(shape(shp))
        poly = MultiPolygon(multi_polygon)

        # create a pandas dataframe for the footprint
        # Ensure CRS is a string
        crs_str = None
        if hasattr(self.line_seg, "crs") and self.line_seg.crs:
            if hasattr(self.line_seg.crs, "to_string"):
                crs_str = self.line_seg.crs.to_string()
            else:
                crs_str = str(self.line_seg.crs)
        else:
            crs_str = "EPSG:4326"
        # Ensure poly is a valid shapely geometry
        if not isinstance(poly, (Polygon, MultiPolygon)):
            poly = MultiPolygon([poly]) if poly else None

        # Fallback CRS if invalid
        if not crs_str or not isinstance(crs_str, str) or not crs_str.startswith("EPSG"):
            crs_str = "EPSG:4326"

        # Only create GeoDataFrame if poly is not None
        if poly is not None and isinstance(poly, (Polygon, MultiPolygon)):
            geometry_list = [poly]
        else:
            geometry_list = []

        import pandas as pd
        self.footprint = gpd.GeoDataFrame({"geometry": geometry_list})
        self.footprint.set_crs(crs_str, inplace=True)

        # find contiguous corridor polygon for centerline
        corridor_poly_gpd = algo_cl.find_corridor_polygon(corridor_thresh, out_transform, line_gpd)
        centerline, status = algo_cl.find_centerline(corridor_poly_gpd.geometry.iloc[0], feat)

        self.corridor_poly_gpd = corridor_poly_gpd
        self.centerline = centerline


def process_single_line(line_footprint):
    print("process_single_line: started")
    try:
        line_footprint.compute()
        print("process_single_line: finished compute")
    except Exception as e:
        print(f"process_single_line: exception {e}")
    return line_footprint


def generate_line_class_list(
    in_line,
    in_chm,
    corridor_thresh,
    max_ln_width,
    exp_shk_cell,
    in_layer=None,
):
    line_classes = []
    line_list = algo_common.prepare_lines_gdf(in_line, in_layer, proc_segments=False)

    for line in line_list:
        line_classes.append(FootprintAbsolute(line, in_chm, corridor_thresh, max_ln_width, exp_shk_cell))

    return line_classes


def canopy_footprint_abs(
    in_line,
    in_chm,
    corridor_thresh,
    max_ln_width,
    exp_shk_cell,
    out_footprint,
    processes,
    verbose,
    in_layer=None,
    out_layer=None,
    parallel_mode=bt_const.ParallelMode.MULTIPROCESSING,
):
    max_ln_width = float(max_ln_width)
    exp_shk_cell = int(exp_shk_cell)

    footprint_list = []
    poly_list = []

    line_class_list = generate_line_class_list(
        in_line, in_chm, corridor_thresh, max_ln_width, exp_shk_cell, in_layer
    )

    feat_list = bt_base.execute_multiprocessing(
        process_single_line,
        line_class_list,
        "Line footprint",
        processes,
        parallel_mode,
        verbose=verbose,
    )

    if feat_list:
        for i in feat_list:
            if i.footprint is not None:
                footprint_list.append(i.footprint)
            if i.corridor_poly_gpd is not None:
                poly_list.append(i.corridor_poly_gpd)

    if footprint_list:
        results = gpd.GeoDataFrame(pd.concat(footprint_list))
        results = results.reset_index(drop=True)
        results.to_file(out_footprint, layer=out_layer)
    else:
        print("Warning: No footprints generated. Output file not written.")


if __name__ == "__main__":
    start_time = time.time()
    print("Footprint processing started")

    in_args, in_verbose = sp_common.check_arguments()
    canopy_footprint_abs(**in_args.input, processes=int(in_args.processes), verbose=in_verbose)
    print("Elapsed time: {}".format(time.time() - start_time))
