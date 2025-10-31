"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng, Maverick Fong

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide main interface for canopy footprint tool.
    The tool is used to generate the footprint of a line based on relative threshold.
"""

import math
import time
from enum import Enum

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio.features as ras_feat
import shapely
import shapely.geometry as sh_geom
import shapely.ops as sh_ops
from skimage.graph import MCP_Flexible

import beratools.core.algo_common as algo_common
import beratools.core.algo_cost as algo_cost
import beratools.core.constants as bt_const
import beratools.core.tool_base as bt_base
import beratools.tools.common as bt_common
import beratools.utility.spatial_common as sp_common


class Side(Enum):
    """Constants for left and right side."""

    left = "left"
    right = "right"


class FootprintCanopy:
    """Relative canopy footprint class."""

    def __init__(self, in_geom, in_chm, in_layer=None):
        data = gpd.read_file(in_geom, layer=in_layer)
        self.lines = []

        for idx in data.index:
            line = LineInfo(data.iloc[[idx]], in_chm)
            self.lines.append(line)

    def compute(self, processes, parallel_mode=bt_const.ParallelMode.MULTIPROCESSING):
        result = bt_base.execute_multiprocessing(
            algo_common.process_single_item,
            self.lines,
            "Canopy Footprint",
            processes,
            parallel_mode,
        )

        fp = []
        percentile = []
        try:
            for item in result:
                if item.footprint is not None:
                    fp.append(item.footprint)
                else:
                    print("Footprint is None for one of the lines.")
                    continue  # Skip failed line

            if fp:
                self.footprints = pd.concat(fp)
            else:
                print("No valid footprints to save.")
                self.footprints = None

            for item in result:
                if item.lines_percentile is not None:
                    percentile.append(item.lines_percentile)
                else:
                    print("lines_percentile is None for one of the lines.")
                    continue  # Skip failed line

            if percentile:
                self.lines_percentile = pd.concat(percentile)
            else:
                print("No valid lines_percentile to save.")
                self.lines_percentile = None
        except Exception as e:
            print(f"Error during processing: {e}")

    def save_footprint(self, out_footprint, layer=None):
        if self.footprints is not None and isinstance(self.footprints, gpd.GeoDataFrame):
            self.footprints.to_file(out_footprint, layer=layer)
        else:
            print("No footprints to save (None or not a GeoDataFrame).")

    def save_line_percentile(self, out_percentile):
        if self.lines_percentile is not None and isinstance(self.lines_percentile, gpd.GeoDataFrame):
            self.lines_percentile.to_file(out_percentile)
        else:
            print("No lines_percentile to save (None or not a GeoDataFrame).")


class BufferRing:
    """Buffer ring class."""

    def __init__(self, ring_poly, side):
        self.geometry = ring_poly
        self.side = side
        self.percentile = 0.5
        self.Dyn_Canopy_Threshold = 0.05


class LineInfo:
    """Class to store line information."""

    def __init__(
        self,
        line_gdf,
        in_chm,
        max_ln_width=32,
        tree_radius=1.5,
        max_line_dist=1.5,
        canopy_avoidance=0.0,
        exponent=1.0,
        canopy_thresh_percentage=50,
    ):
        self.line = line_gdf
        self.in_chm = in_chm
        self.line_simp = self.line.geometry.simplify(tolerance=0.5, preserve_topology=True)

        self.canopy_percentile = 50
        self.DynCanTh = np.nan

        self.buffer_rings = []

        self.CL_CutHt = np.nan
        self.CR_CutHt = np.nan
        self.RDist_Cut = np.nan
        self.LDist_Cut = np.nan

        self.canopy_thresh_percentage = canopy_thresh_percentage
        self.canopy_avoidance = canopy_avoidance
        self.exponent = exponent
        self.max_ln_width = max_ln_width
        self.max_line_dist = max_line_dist
        self.tree_radius = tree_radius

        self.nodata = -9999
        self.dyn_canopy_ndarray = None
        self.negative_cost_clip = None
        self.out_meta = None

        self.buffer_left = None
        self.buffer_right = None
        self.footprint = None

        self.lines_percentile = None

    def compute(self):
        self.prepare_ring_buffer()

        ring_list = []
        for item in self.buffer_rings:
            ring = self.cal_percentileRing(item)
            if ring is not None:
                ring_list.append(ring)
            else:
                # print("Skipping invalid ring.")
                # TODO: handle None rings appropriately
                pass

        self.buffer_rings = ring_list

        # Aggregate percentiles and geometries for lines_percentile
        percentile_records = []
        for ring in self.buffer_rings:
            if ring is not None and hasattr(ring, "geometry") and hasattr(ring, "percentile"):
                percentile_records.append(
                    {"geometry": ring.geometry, "percentile": ring.percentile, "side": ring.side.value}
                )
        if percentile_records:
            self.lines_percentile = gpd.GeoDataFrame(percentile_records)
            self.lines_percentile.set_geometry("geometry", inplace=True)
            if self.line.crs:
                self.lines_percentile = self.lines_percentile.set_crs(self.line.crs, allow_override=True)
        else:
            self.lines_percentile = None

        self.rate_of_change(self.get_percentile_array(Side.left), Side.left)
        self.rate_of_change(self.get_percentile_array(Side.right), Side.right)

        self.line["CL_CutHt"] = self.CL_CutHt
        self.line["CR_CutHt"] = self.CR_CutHt
        self.line["RDist_Cut"] = self.RDist_Cut
        self.line["LDist_Cut"] = self.LDist_Cut

        self.DynCanTh = (self.CL_CutHt + self.CR_CutHt) / 2
        self.line["DynCanTh"] = self.DynCanTh

        self.prepare_line_buffer()

        fp_left = self.process_single_footprint(Side.left)
        fp_right = self.process_single_footprint(Side.right)

        # Check if footprints are valid
        if fp_left is None or fp_right is None:
            print("One or both footprints are None in LineInfo.")
            self.footprint = None
            return

        try:
            # Buffer cleanup for validity
            fp_left.geometry = fp_left.geometry.buffer(0)
            fp_right.geometry = fp_right.geometry.buffer(0)

            fp_combined = pd.concat([fp_left, fp_right])

            if fp_combined.empty or not isinstance(fp_combined, gpd.GeoDataFrame):
                print("Combined footprint is invalid or empty.")
                self.footprint = None
                return

            fp_combined = fp_combined.dissolve()
            fp_combined.geometry = fp_combined.geometry.buffer(-0.005)

            self.footprint = fp_combined
        except Exception as e:
            print(f"Error combining footprints: {e}")
            self.footprint = None
            return

        # Transfer group value to footprint if present
        if bt_const.BT_GROUP in self.line.columns:
            self.footprint[bt_const.BT_GROUP] = self.line[bt_const.BT_GROUP].iloc[0]

    def prepare_ring_buffer(self):
        nrings = 1
        ringdist = 15
        ring_list = self.multi_ring_buffer(self.line_simp, nrings, ringdist)
        for i in ring_list:
            if BufferRing(i, Side.left):
                self.buffer_rings.append(BufferRing(i, Side.left))
            else:
                print("Empty buffer ring")

        nrings = -1
        ringdist = -15
        ring_list = self.multi_ring_buffer(self.line_simp, nrings, ringdist)
        for i in ring_list:
            if BufferRing(i, Side.right):
                self.buffer_rings.append(BufferRing(i, Side.right))
            else:
                print("Empty buffer ring")

    def cal_percentileRing(self, ring):
        line_buffer = None
        try:
            line_buffer = ring.geometry
            if line_buffer.is_empty or shapely.is_missing(line_buffer):
                return None
            if line_buffer.has_z:
                line_buffer = sh_ops.transform(lambda x, y, z=None: (x, y), line_buffer)

        except Exception as e:
            print(f"cal_percentileRing: {e}")
            return None

        # TODO: temporary workaround for exception causing not percentile defined
        try:
            clipped_raster, _ = sp_common.clip_raster(self.in_chm, line_buffer, 0)
            clipped_raster = np.squeeze(clipped_raster, axis=0)

            # mask all -9999 (nodata) value cells
            masked_raster = np.ma.masked_where(clipped_raster == bt_const.BT_NODATA, clipped_raster)
            filled_raster = np.ma.filled(masked_raster, np.nan)

            # Calculate the percentile
            percentile = np.nanpercentile(filled_raster, 50)

            if percentile > 1:
                ring.Dyn_Canopy_Threshold = percentile * (0.3)
            else:
                ring.Dyn_Canopy_Threshold = 1

            ring.percentile = percentile
        except Exception as e:
            print(e)
            print("Default values are used.")

        return ring

    def get_percentile_array(self, side):
        per_array = []
        for item in self.buffer_rings:
            try:
                if item.side == side:
                    per_array.append(item.percentile)
            except Exception as e:
                print(e)

        return per_array

    def rate_of_change(self, percentile_array, side):
        # Since the x interval is 1 unit, the array 'diff' is the rate of change (slope)
        diff = np.ediff1d(percentile_array)
        cut_dist = len(percentile_array) / 5

        median_percentile = np.nanmedian(percentile_array)
        if not np.isnan(median_percentile):
            cut_percentile = float(math.floor(median_percentile))
        else:
            cut_percentile = 0.5

        found = False
        changes = 1.50
        Change = np.insert(diff, 0, 0)
        scale_down = 1.0

        # test the rate of change is > than 150% (1.5), if it is
        # no result found then lower to 140% (1.4) until 110% (1.1)
        try:
            while not found and changes >= 1.1:
                for ii in range(0, len(Change) - 1):
                    if percentile_array[ii] >= 0.5:
                        if (Change[ii]) >= changes:
                            cut_dist = (ii + 1) * scale_down
                            cut_percentile = math.floor(percentile_array[ii])

                            if 0.5 >= cut_percentile:
                                if cut_dist > 5:
                                    cut_percentile = 2
                                    cut_dist = cut_dist * scale_down**3
                                    # @<0.5  found and modified
                            elif 0.5 < cut_percentile <= 5.0:
                                if cut_dist > 6:
                                    cut_dist = cut_dist * scale_down**3  # 4.0
                                    # @0.5-5.0  found and modified
                            elif 5.0 < cut_percentile <= 10.0:
                                if cut_dist > 8:  # 5
                                    cut_dist = cut_dist * scale_down**3
                                    # @5-10  found and modified
                            elif 10.0 < cut_percentile <= 15:
                                if cut_dist > 5:
                                    cut_dist = cut_dist * scale_down**3  # 5.5
                                    #  @10-15  found and modified
                            elif 15 < cut_percentile:
                                if cut_dist > 4:
                                    cut_dist = cut_dist * scale_down**2
                                    cut_percentile = 15.5
                                    #  @>15  found and modified
                            found = True
                            # rate of change found
                            break
                changes = changes - 0.1

        except IndexError:
            pass

        # if still no result found, lower to 10% (1.1),
        # if no result found then default is used
        if not found:
            if 0.5 >= median_percentile:
                cut_dist = 4 * scale_down  # 3
                cut_percentile = 0.5
            elif 0.5 < median_percentile <= 5.0:
                cut_dist = 4.5 * scale_down  # 4.0
                cut_percentile = math.floor(median_percentile)
            elif 5.0 < median_percentile <= 10.0:
                cut_dist = 5.5 * scale_down  # 5
                cut_percentile = math.floor(median_percentile)
            elif 10.0 < median_percentile <= 15:
                cut_dist = 6 * scale_down  # 5.5
                cut_percentile = math.floor(median_percentile)
            elif 15 < median_percentile:
                cut_dist = 5 * scale_down  # 5
                cut_percentile = 15.5

        if side == Side.right:
            self.RDist_Cut = cut_dist
            self.CR_CutHt = float(cut_percentile)
        elif side == Side.left:
            self.LDist_Cut = cut_dist
            self.CL_CutHt = float(cut_percentile)

    def multi_ring_buffer(self, df, nrings, ringdist):
        """
        Buffers an input DataFrames geometry nring (number of rings) times.

        Compute with a distance between rings of ringdist and returns
        a list of non overlapping buffers
        """
        rings = []  # A list to hold the individual buffers
        line = df.geometry.iloc[0]
        # For each ring (1, 2, 3, ..., nrings)
        for ring in np.arange(0, ringdist, nrings):
            big_ring = line.buffer(
                nrings + ring, single_sided=True, cap_style="flat"
            )  # Create one big buffer
            small_ring = line.buffer(ring, single_sided=True, cap_style="flat")  # Create one smaller one
            the_ring = big_ring.difference(small_ring)  # Difference the big with the small to create a ring
            if (
                ~shapely.is_empty(the_ring)
                or ~shapely.is_missing(the_ring)
                or not None
                or ~the_ring.area == 0
            ):
                if isinstance(the_ring, sh_geom.MultiPolygon) or isinstance(the_ring, shapely.Polygon):
                    rings.append(the_ring)  # Append the ring to the rings list
                else:
                    if isinstance(the_ring, shapely.GeometryCollection):
                        for i in range(0, len(the_ring.geoms)):
                            if not isinstance(the_ring.geoms[i], shapely.LineString):
                                rings.append(the_ring.geoms[i])

        return rings  # return the list

    def prepare_line_buffer(self):
        line = self.line.geometry.iloc[0]
        buffer_left_1 = line.buffer(
            distance=self.max_ln_width + 1,
            cap_style=3,
            single_sided=True,
        )

        buffer_left_2 = line.buffer(
            distance=-1,
            cap_style=3,
            single_sided=True,
        )

        self.buffer_left = sh_ops.unary_union([buffer_left_1, buffer_left_2])

        buffer_right_1 = line.buffer(
            distance=-self.max_ln_width - 1,
            cap_style=3,
            single_sided=True,
        )
        buffer_right_2 = line.buffer(distance=1, cap_style=3, single_sided=True)

        self.buffer_right = sh_ops.unary_union([buffer_right_1, buffer_right_2])

    def dyn_canopy_cost_raster(self, side):
        in_chm_raster = self.in_chm
        # tree_radius = self.tree_radius
        # max_line_dist = self.max_line_dist
        # canopy_avoid = self.canopy_avoidance
        # exponent = self.exponent
        line_df = self.line
        out_meta = self.out_meta

        canopy_thresh_percentage = self.canopy_thresh_percentage / 100

        Cut_Dist = None
        line_buffer = None
        if side == Side.left:
            canopy_ht_threshold = line_df.CL_CutHt * canopy_thresh_percentage
            Cut_Dist = self.LDist_Cut
            line_buffer = self.buffer_left
        elif side == Side.right:
            canopy_ht_threshold = line_df.CR_CutHt * canopy_thresh_percentage
            Cut_Dist = self.RDist_Cut
            line_buffer = self.buffer_right
        else:
            canopy_ht_threshold = 0.5
            Cut_Dist = 1.0
            line_buffer = None

        canopy_ht_threshold = float(canopy_ht_threshold)
        if canopy_ht_threshold <= 0:
            canopy_ht_threshold = 0.5

        # get the round up integer number for tree search radius
        # tree_radius = float(tree_radius)
        # max_line_dist = float(max_line_dist)
        # canopy_avoid = float(canopy_avoid)
        # cost_raster_exponent = float(exponent)

        try:
            clipped_rasterC, out_meta = sp_common.clip_raster(in_chm_raster, line_buffer, 0)
            negative_cost_clip, dyn_canopy_ndarray = algo_cost.cost_raster(
                clipped_rasterC,
                out_meta,
                self.tree_radius,
                canopy_ht_threshold,
                self.max_line_dist,
                self.canopy_avoidance,
                self.exponent,
            )

            return dyn_canopy_ndarray, negative_cost_clip, out_meta, Cut_Dist

        except Exception as e:
            print(f"dyn_canopy_cost_raster: {e}")
            return None

    def process_single_footprint(self, side):
        # this will change segment content, and parameters will be changed
        in_canopy_r, in_cost_r, in_meta, Cut_Dist = self.dyn_canopy_cost_raster(side)

        if np.isnan(in_canopy_r).all():
            print("Canopy raster empty")

        if np.isnan(in_cost_r).all():
            print("Cost raster empty")

        exp_shk_cell = self.exponent  # TODO: duplicate vars
        no_data = self.nodata

        shapefile_proj = self.line.crs
        in_transform = in_meta["transform"]

        segment_list = []

        feat = self.line.geometry.iloc[0]
        if hasattr(feat, "geoms"):
            for geom in feat.geoms:
                for coord in geom.coords:
                    segment_list.append(coord)
        else:
            for coord in feat.coords:
                segment_list.append(coord)

        cell_size_x = in_transform[0]
        cell_size_y = -in_transform[4]

        # Work out the corridor from both end of the centerline
        try:
            if len(in_cost_r.shape) > 2:
                in_cost_r = np.squeeze(in_cost_r, axis=0)

            algo_cost.remove_nan_from_array_refactor(in_cost_r)
            in_cost_r[in_cost_r == no_data] = np.inf

            # generate 1m interval points along line
            distance_delta = 1
            distances = np.arange(0, feat.length, distance_delta)
            multipoint_along_line = [feat.interpolate(distance) for distance in distances]
            multipoint_along_line.append(sh_geom.Point(segment_list[-1]))
            # Rasterize points along line
            rasterized_points_Alongln = ras_feat.rasterize(
                multipoint_along_line,
                out_shape=in_cost_r.shape,
                transform=in_transform,
                fill=0,
                all_touched=True,
                default_value=1,
            )
            points_Alongln = np.transpose(np.nonzero(rasterized_points_Alongln))

            # Find minimum cost paths through an N-d costs array.
            mcp_flexible1 = MCP_Flexible(in_cost_r, sampling=(cell_size_x, cell_size_y), fully_connected=True)
            flex_cost_alongLn, flex_back_alongLn = mcp_flexible1.find_costs(starts=points_Alongln)

            # Generate corridor
            corridor = flex_cost_alongLn
            corridor = np.ma.masked_invalid(corridor)

            # Calculate minimum value of corridor raster
            if np.ma.min(corridor) is not None:
                corr_min = float(np.ma.min(corridor))
            else:
                corr_min = 0.5

            # normalize corridor raster by deducting corr_min
            corridor_norm = corridor - corr_min

            # Set minimum as zero and save minimum file
            corridor_th_value = Cut_Dist / cell_size_x
            if corridor_th_value < 0:  # if no threshold found, use default value
                corridor_th_value = bt_const.FP_CORRIDOR_THRESHOLD / cell_size_x

            corridor_thresh = np.ma.where(corridor_norm >= corridor_th_value, 1.0, 0.0)
            clean_raster = algo_common.morph_raster(corridor_thresh, in_canopy_r, exp_shk_cell, cell_size_x)

            # create mask for non-polygon area
            mask = np.where(clean_raster == 1, True, False)
            if clean_raster.dtype == np.int64:
                clean_raster = clean_raster.astype(np.int32)

            # Process: ndarray to shapely Polygon
            out_polygon = ras_feat.shapes(clean_raster, mask=mask, transform=in_transform)

            # create a shapely MultiPolygon
            multi_polygon = []
            if out_polygon is not None:
                try:
                    for poly, value in out_polygon:
                        multi_polygon.append(sh_geom.shape(poly))
                except TypeError:
                    pass

            if not multi_polygon:
                print("No polygons generated from raster. Returning None.")
                return None

            poly = sh_geom.MultiPolygon(multi_polygon) if multi_polygon else None

            # create GeoDataFrame directly from dictionary
            out_gdata = gpd.GeoDataFrame({"CorriThresh": [corridor_th_value], "geometry": [poly]})
            out_gdata.set_geometry("geometry", inplace=True)
            if shapefile_proj:
                out_gdata = out_gdata.set_crs(shapefile_proj, allow_override=True)

            if out_gdata is None or out_gdata.empty or out_gdata.geometry.isnull().all():
                print("Empty GeoDataFrame from process_single_footprint.")
                return None

            return out_gdata

        except Exception as e:
            print("Exception: {}".format(e))


def line_footprint_rel(
    in_line,
    in_chm,
    out_footprint,
    processes,
    verbose=True,
    in_layer=None,
    out_layer=None,
    max_ln_width=32,
    tree_radius=1.5,
    max_line_dist=1.5,
    canopy_avoidance=0.0,
    exponent=1.0,
    canopy_thresh_percentage=50,
    parallel_mode=bt_const.ParallelMode.MULTIPROCESSING,
):
    """Safe version of relative canopy footprint tool."""
    try:
        footprint = FootprintCanopy(in_line, in_chm, in_layer=in_layer)
    except Exception as e:
        print(f"Failed to initialize FootprintCanopy: {e}")
        return

    try:
        footprint.compute(processes, parallel_mode)
    except Exception as e:
        print(f"Error in compute(): {e}")
        import traceback

        traceback.print_exc()
        return

    # Save only if footprints were actually generated
    if (
        hasattr(footprint, "footprints")
        and footprint.footprints is not None
        and hasattr(footprint.footprints, "empty")
        and not footprint.footprints.empty
    ):
        try:
            footprint.save_footprint(out_footprint, out_layer)
            if verbose:
                print(f"Footprint saved to {out_footprint} layer={out_layer}")
        except Exception as e:
            print(f"Failed to save footprint: {e}")
    else:
        print("No valid footprints to save.")

    # Optionally save percentile lines (if needed)
    if (
        hasattr(footprint, "lines_percentile")
        and footprint.lines_percentile is not None
        and hasattr(footprint.lines_percentile, "empty")
        and not footprint.lines_percentile.empty
    ):
        out_percentile = out_footprint.replace("footprint", "line_percentile")
        try:
            footprint.save_line_percentile(out_percentile)
            if verbose:
                print(f"Line percentile saved to {out_percentile}")
        except Exception as e:
            print(f"Failed to save line percentile: {e}")


if __name__ == "__main__":
    """This part is to be another version of relative canopy footprint tool."""
    in_args, in_verbose = sp_common.check_arguments()
    start_time = time.time()
    line_footprint_rel(**in_args.input, processes=int(in_args.processes), verbose=in_verbose)

    print("Elapsed time: {}".format(time.time() - start_time))
