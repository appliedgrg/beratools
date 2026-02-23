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

import logging
import time

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio import features
from rasterio.transform import rowcol
from shapely.geometry import MultiPolygon, Polygon, shape

import beratools.core.algo_centerline as algo_cl
import beratools.core.algo_common as algo_common
import beratools.core.algo_cost as algo_cost
import beratools.core.tool_base as bt_base
import beratools.utility.spatial_common as sp_common
from beratools.core.logger import Logger
from beratools.utility.tool_args import CallMode

log = Logger("canopy_footprint_abs", file_level=logging.INFO)
logger = log.get_logger()
print = log.print


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
        prep = self.prepare_inputs()
        raster = self.compute_cost_surface(prep["feat"])

        corridor_thresh = algo_common.corridor_raster(
            raster["clip_cost"],
            raster["out_meta"],
            raster["source"],
            raster["destination"],
            (raster["cell_size_x"], raster["cell_size_y"]),
            prep["corridor_thresh"],
        )

        clean_raster = algo_common.morph_raster(
            corridor_thresh, raster["clip_canopy"], self.exp_shk_cell, raster["cell_size_x"]
        )
        self.footprint = self.build_candidate_polygon(clean_raster, raster["out_transform"])
        self.postprocess_output(corridor_thresh, raster["out_transform"], prep["line_gpd"], prep["feat"])

    def prepare_inputs(self):
        corridor_thresh = self.corridor_thresh
        try:
            corridor_thresh = float(corridor_thresh)
            if corridor_thresh < 0.0:
                corridor_thresh = 3.0
        except ValueError as e:
            print(f"FootprintAbsolute.compute: ValueError {e}")
            corridor_thresh = 3.0
        except Exception as e:
            print(f"FootprintAbsolute.compute: exception {e}")

        feat = self.line_seg.geometry[0]
        return {
            "line_gpd": self.line_seg,
            "corridor_thresh": corridor_thresh,
            "feat": feat,
        }

    def compute_cost_surface(self, feat):
        # Buffer around line and clip cost raster and canopy raster
        # TODO: deal with NODATA
        clip_cost, out_meta = sp_common.clip_raster(self.in_chm, feat, self.max_ln_width)
        out_transform = out_meta["transform"]
        cell_size_x = out_transform[0]
        cell_size_y = -out_transform[4]

        clip_cost, clip_canopy = algo_cost.cost_raster(clip_cost, out_meta)
        if len(clip_canopy.shape) > 2:
            clip_canopy = np.squeeze(clip_canopy, axis=0)

        source = [rowcol(out_transform, feat.coords[0][0], feat.coords[0][1])]
        destination = [rowcol(out_transform, feat.coords[-1][0], feat.coords[-1][1])]

        return {
            "clip_cost": clip_cost,
            "clip_canopy": clip_canopy,
            "out_meta": out_meta,
            "out_transform": out_transform,
            "cell_size_x": cell_size_x,
            "cell_size_y": cell_size_y,
            "source": source,
            "destination": destination,
        }

    def build_candidate_polygon(self, clean_raster, out_transform):
        msk = np.where(clean_raster == 1, True, False)
        if clean_raster.dtype == np.int64:
            clean_raster = clean_raster.astype(np.int32)

        out_polygon = features.shapes(clean_raster, mask=msk, transform=out_transform)

        multi_polygon = []
        for shp, value in out_polygon:
            multi_polygon.append(shape(shp))
        poly = MultiPolygon(multi_polygon)

        crs_str = None
        if hasattr(self.line_seg, "crs") and self.line_seg.crs:
            if hasattr(self.line_seg.crs, "to_string"):
                crs_str = self.line_seg.crs.to_string()
            else:
                crs_str = str(self.line_seg.crs)
        else:
            crs_str = "EPSG:4326"

        if not isinstance(poly, (Polygon, MultiPolygon)):
            poly = MultiPolygon([poly]) if poly else None

        if not crs_str or not isinstance(crs_str, str) or not crs_str.startswith("EPSG"):
            crs_str = "EPSG:4326"

        if poly is not None and isinstance(poly, (Polygon, MultiPolygon)):
            geometry_list = [poly]
        else:
            geometry_list = []

        footprint = gpd.GeoDataFrame({"geometry": geometry_list})
        footprint.set_crs(crs_str, inplace=True)
        return footprint

    def postprocess_output(self, corridor_thresh, out_transform, line_gpd, feat):
        corridor_poly_gpd = algo_cl.find_corridor_polygon(corridor_thresh, out_transform, line_gpd)
        centerline, _status = algo_cl.find_centerline(corridor_poly_gpd.geometry.iloc[0], feat)

        self.corridor_poly_gpd = corridor_poly_gpd
        self.centerline = centerline


def process_single_line(line_footprint):
    try:
        line_footprint.compute()
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
    processes=0,
    call_mode=CallMode.CLI,
    log_level="INFO",
):
    in_file, in_layer = sp_common.decode_file_layer(in_line)
    out_file, out_layer = sp_common.decode_file_layer(out_footprint)

    max_ln_width = float(max_ln_width)
    exp_shk_cell = int(exp_shk_cell)

    footprint_list = []
    poly_list = []

    line_class_list = generate_line_class_list(
        in_file, in_chm, corridor_thresh, max_ln_width, exp_shk_cell, in_layer
    )

    feat_list = bt_base.execute_multiprocessing(
        process_single_line, line_class_list, "Line footprint", processes, call_mode
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
        layer_name = out_layer if out_layer else "canopy_footprint"
        results = algo_common.clean_geometries(
            results,
            stage="output",
            out_file=out_file,
            layer="rejected_output_canopy_footprint_absolute",
        )
        results.to_file(out_file, layer=layer_name)
        print(f"Saved footprint to {out_file}, layer: {layer_name}")
    else:
        print("Warning: No footprints generated. Output file not written.")


if __name__ == "__main__":
    from beratools.utility.tool_args import compose_tool_kwargs

    start_time = time.time()
    print("Footprint processing started")
    kwargs = compose_tool_kwargs("canopy_footprint_absolute")
    canopy_footprint_abs(**kwargs)
    print("Elapsed time: {}".format(time.time() - start_time))
