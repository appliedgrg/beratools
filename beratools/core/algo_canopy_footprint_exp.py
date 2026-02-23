"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng, Maverick Fong

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide main interface for experimental canopy footprint tool.
    The tool is used to generate the canopy footprint of a line based on relative threshold.
"""

import math
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
import beratools.utility.spatial_common as sp_common


class Side(Enum):
    """Constants for left and right side."""

    left = "left"
    right = "right"


class FootprintCanopy:
    """Relative canopy footprint class."""

    def __init__(
        self,
        in_geom,
        in_chm,
        max_line_width=32,
        tree_radius=1.5,
        max_line_dist=1.5,
        canopy_avoidance=0.0,
        exponent=1.0,
        canopy_thresh_percentage=50,
    ):
        in_file, in_layer = sp_common.decode_file_layer(in_geom)
        data = algo_common.read_geospatial_file(in_file, layer=in_layer)
        if data is None:
            data = gpd.GeoDataFrame()
        self.lines = []

        for idx in data.index:
            line = LineInfo(
                data.loc[[idx]].copy(),
                in_chm,
                max_line_width=max_line_width,
                tree_radius=tree_radius,
                max_line_dist=max_line_dist,
                canopy_avoidance=canopy_avoidance,
                exponent=exponent,
                canopy_thresh_percentage=canopy_thresh_percentage,
            )
            self.lines.append(line)

    def compute(self, processes):
        result = bt_base.execute_multiprocessing(
            algo_common.process_single_item,
            self.lines,
            "Canopy Footprint",
            processes,
        )

        footprint_list = []
        percentile = []
        try:
            for item in result:
                if item.footprint is not None:
                    footprint_list.append(item.footprint)
                else:
                    print("Footprint is None for one of the lines.")

                if item.lines_percentile is not None:
                    percentile.append(item.lines_percentile)
                else:
                    print("lines_percentile is None for one of the lines.")

            self.footprints = pd.concat(footprint_list, ignore_index=True) if footprint_list else None
            self.lines_percentile = pd.concat(percentile, ignore_index=True) if percentile else None

            if self.footprints is None:
                print("No valid footprints to save.")
            if self.lines_percentile is None:
                print("No valid lines_percentile to save.")
        except Exception as e:
            print(f"Error during processing: {e}")

    def save_footprint(self, out_footprint, layer=None):
        if self.footprints is not None and isinstance(self.footprints, gpd.GeoDataFrame):
            self.footprints = algo_common.clean_geometries(
                self.footprints,
                stage="output",
                out_file=out_footprint,
                layer="rejected_output_canopy_footprint_exp",
            )
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


class LineInfo:
    """Class to store line information."""

    def __init__(
        self,
        line_gdf,
        in_chm,
        max_line_width=32,
        tree_radius=1.5,
        max_line_dist=1.5,
        canopy_avoidance=0.0,
        exponent=1.0,
        canopy_thresh_percentage=50,
    ):
        self.line = line_gdf
        self.in_chm = in_chm
        self.line_simplified = self.line.geometry.simplify(tolerance=0.5, preserve_topology=True)

        self.buffer_rings = []

        self.left_cut_height = np.nan
        self.right_cut_height = np.nan
        self.right_cut_dist = np.nan
        self.left_cut_dist = np.nan

        self.canopy_thresh_percentage = canopy_thresh_percentage
        self.canopy_avoidance = canopy_avoidance
        self.exponent = exponent
        self.max_line_width = max_line_width
        self.max_line_dist = max_line_dist
        self.tree_radius = tree_radius

        self.buffer_left = None
        self.buffer_right = None
        self.footprint = None

        self.lines_percentile = None

    def compute(self):
        self.prepare_ring_buffer()

        ring_list = []
        for item in self.buffer_rings:
            ring = self.calc_ring_percentile(item)
            if ring is not None:
                ring_list.append(ring)
            else:
                # TODO: handle None rings appropriately
                pass

        self.buffer_rings = ring_list

        # Aggregate percentiles and geometries for lines_percentile
        percentile_records = []
        for ring in self.buffer_rings:
            percentile_records.append(
                {"geometry": ring.geometry, "percentile": ring.percentile, "side": ring.side.value}
            )
        if percentile_records:
            self.lines_percentile = gpd.GeoDataFrame(percentile_records, geometry="geometry")
            if self.line.crs:
                self.lines_percentile = self.lines_percentile.set_crs(self.line.crs, allow_override=True)
        else:
            self.lines_percentile = None

        self.rate_of_change(self.get_percentile_array(Side.left), Side.left)
        self.rate_of_change(self.get_percentile_array(Side.right), Side.right)

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

            fp_combined = pd.concat([fp_left, fp_right], ignore_index=True)

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
        for ring_step, ring_max_dist, side in [(1, 15, Side.left), (-1, -15, Side.right)]:
            ring_list = self.multi_ring_buffer(self.line_simplified, ring_step, ring_max_dist)
            for ring_poly in ring_list:
                self.buffer_rings.append(BufferRing(ring_poly, side))

    def calc_ring_percentile(self, ring):
        line_buffer = None
        try:
            line_buffer = ring.geometry
            if line_buffer.is_empty or shapely.is_missing(line_buffer):
                return None
            if line_buffer.has_z:
                line_buffer = sh_ops.transform(lambda x, y, z=None: (x, y), line_buffer)

        except Exception as e:
            print(f"calc_ring_percentile: {e}")
            return None

        # TODO: temporary workaround for exception causing not percentile defined
        try:
            clipped_raster, _ = sp_common.clip_raster(self.in_chm, line_buffer, 0)
            clipped_raster = np.squeeze(clipped_raster, axis=0)

            # mask all -9999 (nodata) value cells
            masked_raster = np.ma.masked_where(clipped_raster == bt_const.BT_NODATA, clipped_raster)
            filled_raster = np.ma.filled(masked_raster, np.nan)

            # Calculate the percentile
            ring.percentile = np.nanpercentile(filled_raster, 50)
        except Exception as e:
            print(e)
            print("Default values are used.")

        return ring

    def get_percentile_array(self, side):
        return [ring.percentile for ring in self.buffer_rings if ring.side == side]

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
        rate_change = np.insert(diff, 0, 0)
        # test the rate of change is > than 150% (1.5), if it is
        # no result found then lower to 140% (1.4) until 110% (1.1)
        try:
            while not found and changes >= 1.1:
                for idx in range(0, len(rate_change) - 1):
                    if percentile_array[idx] >= 0.5:
                        if (rate_change[idx]) >= changes:
                            cut_dist = idx + 1
                            cut_percentile = math.floor(percentile_array[idx])

                            if 0.5 >= cut_percentile:
                                if cut_dist > 5:
                                    cut_percentile = 2
                                    # @<0.5  found and modified
                            elif 15 < cut_percentile:
                                if cut_dist > 4:
                                    cut_percentile = 15.5
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
                cut_dist = 4
                cut_percentile = 0.5
            elif 0.5 < median_percentile <= 5.0:
                cut_dist = 4.5
                cut_percentile = math.floor(median_percentile)
            elif 5.0 < median_percentile <= 10.0:
                cut_dist = 5.5
                cut_percentile = math.floor(median_percentile)
            elif 10.0 < median_percentile <= 15:
                cut_dist = 6
                cut_percentile = math.floor(median_percentile)
            elif 15 < median_percentile:
                cut_dist = 5
                cut_percentile = 15.5

        if side == Side.right:
            self.right_cut_dist = cut_dist
            self.right_cut_height = float(cut_percentile)
        elif side == Side.left:
            self.left_cut_dist = cut_dist
            self.left_cut_height = float(cut_percentile)

    def multi_ring_buffer(self, df, ring_step, ring_max_dist):
        """
        Buffers an input DataFrames geometry with concentric rings.

        Compute with a distance between rings of ring_step and returns
        a list of non overlapping buffers
        """
        rings = []
        line = df.geometry.iloc[0]
        for ring in np.arange(0, ring_max_dist, ring_step):
            big_ring = line.buffer(ring_step + ring, single_sided=True, cap_style="flat")
            small_ring = line.buffer(ring, single_sided=True, cap_style="flat")
            the_ring = big_ring.difference(small_ring)
            if not shapely.is_empty(the_ring) and not shapely.is_missing(the_ring) and the_ring.area > 0:
                if isinstance(the_ring, (sh_geom.MultiPolygon, shapely.Polygon)):
                    rings.append(the_ring)
                elif isinstance(the_ring, shapely.GeometryCollection):
                    for geom in the_ring.geoms:
                        if not isinstance(geom, shapely.LineString):
                            rings.append(geom)

        return rings

    def prepare_line_buffer(self):
        line = self.line.geometry.iloc[0]
        buffer_left_1 = line.buffer(
            distance=self.max_line_width + 1,
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
            distance=-self.max_line_width - 1,
            cap_style=3,
            single_sided=True,
        )
        buffer_right_2 = line.buffer(distance=1, cap_style=3, single_sided=True)

        self.buffer_right = sh_ops.unary_union([buffer_right_1, buffer_right_2])

    def dyn_canopy_cost_raster(self, side):
        canopy_thresh_ratio = self.canopy_thresh_percentage / 100

        if side == Side.left:
            canopy_height_thresh = self.left_cut_height * canopy_thresh_ratio
            cut_dist = self.left_cut_dist
            line_buffer = self.buffer_left
        elif side == Side.right:
            canopy_height_thresh = self.right_cut_height * canopy_thresh_ratio
            cut_dist = self.right_cut_dist
            line_buffer = self.buffer_right
        else:
            raise ValueError(f"Unsupported side: {side}")

        canopy_height_thresh = float(canopy_height_thresh)
        if canopy_height_thresh <= 0:
            canopy_height_thresh = 0.5

        try:
            clipped_raster, out_meta = sp_common.clip_raster(self.in_chm, line_buffer, 0)
            negative_cost_clip, dyn_canopy_ndarray = algo_cost.cost_raster(
                clipped_raster,
                out_meta,
                self.tree_radius,
                canopy_height_thresh,
                self.max_line_dist,
                self.canopy_avoidance,
                self.exponent,
            )

            return dyn_canopy_ndarray, negative_cost_clip, out_meta, cut_dist

        except Exception as e:
            print(f"dyn_canopy_cost_raster: {e}")
            return None

    def _extract_coords(self, feat):
        """Extract coordinate list from a geometry (single or multi)."""
        coords = []
        if hasattr(feat, "geoms"):
            for geom in feat.geoms:
                coords.extend(geom.coords)
        else:
            coords.extend(feat.coords)
        return coords

    def process_single_footprint(self, side):
        result = self.dyn_canopy_cost_raster(side)
        if result is None:
            return None
        canopy_raster, cost_raster, in_meta, cut_dist = result

        if canopy_raster is None or cost_raster is None or in_meta is None or cut_dist is None:
            return None

        if np.isnan(canopy_raster).all():
            print("Canopy raster empty")
            return None

        if np.isnan(cost_raster).all():
            print("Cost raster empty")
            return None

        in_transform = in_meta["transform"]
        cell_size_x = in_transform[0]
        cell_size_y = -in_transform[4]

        feat = self.line.geometry.iloc[0]
        segment_list = self._extract_coords(feat)

        # Work out the corridor from both end of the centerline
        try:
            if len(cost_raster.shape) > 2:
                cost_raster = np.squeeze(cost_raster, axis=0)

            algo_cost.remove_nan_from_array_refactor(cost_raster)
            cost_raster[cost_raster == bt_const.BT_NODATA] = np.inf

            # generate 1m interval points along line
            distances = np.arange(0, feat.length, 1)
            multipoint_along_line = [feat.interpolate(d) for d in distances]
            multipoint_along_line.append(sh_geom.Point(segment_list[-1]))

            # Rasterize points along line
            rasterized_points = ras_feat.rasterize(
                multipoint_along_line,
                out_shape=cost_raster.shape,
                transform=in_transform,
                fill=0,
                all_touched=True,
                default_value=1,
            )
            points_along_line = np.transpose(np.nonzero(rasterized_points))

            # Find minimum cost paths through an N-d costs array.
            mcp = MCP_Flexible(cost_raster, sampling=(cell_size_x, cell_size_y), fully_connected=True)
            mcp_cost_surface, _ = mcp.find_costs(starts=points_along_line)

            # Generate corridor
            corridor = np.ma.masked_invalid(mcp_cost_surface)

            # Calculate minimum value of corridor raster
            corridor_min = float(np.ma.min(corridor)) if np.ma.min(corridor) is not None else 0.5

            # normalize corridor raster by deducting corridor_min
            corridor_norm = corridor - corridor_min

            # Set minimum as zero and save minimum file
            corridor_threshold = cut_dist / cell_size_x
            if corridor_threshold < 0:  # if no threshold found, use default value
                corridor_threshold = bt_const.FP_CORRIDOR_THRESHOLD / cell_size_x

            corridor_thresh = np.ma.where(corridor_norm >= corridor_threshold, 1.0, 0.0)
            clean_raster = algo_common.morph_raster(
                corridor_thresh, canopy_raster, self.exponent, cell_size_x
            )

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

            poly = sh_geom.MultiPolygon(multi_polygon)

            # create GeoDataFrame directly from dictionary
            footprint_gdf = gpd.GeoDataFrame(
                {"corridor_thresh": [corridor_threshold], "geometry": [poly]},
                geometry="geometry",
            )
            if self.line.crs:
                footprint_gdf = footprint_gdf.set_crs(self.line.crs, allow_override=True)

            if footprint_gdf.empty or footprint_gdf.geometry.isnull().all():
                print("Empty GeoDataFrame from process_single_footprint.")
                return None

            return footprint_gdf

        except Exception as e:
            print("Exception: {}".format(e))
            return None
