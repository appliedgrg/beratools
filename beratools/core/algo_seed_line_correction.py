"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to move line vertices to the right
    seismic line courses for improved alignment and analysis in
    geospatial data processing.
"""

import geopandas as gpd
import math
import numpy as np
import pandas as pd
import shapely.geometry as sh_geom
from shapely import STRtree

import beratools.core.algo_common as algo_common
import beratools.core.algo_cost as algo_cost
import beratools.core.constants as bt_const
import beratools.core.tool_base as bt_base
import beratools.utility.spatial_common as sp_common
from beratools.core import algo_dijkstra

try:
    import rasterio
except Exception:
    rasterio = None


def update_line_end_pt(line, index, new_vertex):
    if not line:
        return None

    if index >= len(line.coords) or index < -1:
        return line

    coords = list(line.coords)
    if len(coords[index]) == 2:
        coords[index] = (new_vertex.x, new_vertex.y)
    elif len(coords[index]) == 3:
        coords[index] = (new_vertex.x, new_vertex.y, 0.0)

    return sh_geom.LineString(coords)


class VertexPrecleaner:
    def __init__(self, close_distance, angle_tol):
        self.close_distance = float(close_distance)
        self.angle_tol = float(angle_tol)

    @staticmethod
    def _point_distance(coord_a, coord_b):
        return math.hypot(coord_b[0] - coord_a[0], coord_b[1] - coord_a[1])

    def _bend_score(self, coord_a, coord_b, coord_c):
        v1x = coord_b[0] - coord_a[0]
        v1y = coord_b[1] - coord_a[1]
        v2x = coord_c[0] - coord_b[0]
        v2y = coord_c[1] - coord_b[1]

        norm1 = math.hypot(v1x, v1y)
        norm2 = math.hypot(v2x, v2y)
        if norm1 <= bt_const.SMALL_BUFFER or norm2 <= bt_const.SMALL_BUFFER:
            return 180.0

        dot = v1x * v2x + v1y * v2y
        cos_val = max(-1.0, min(1.0, dot / (norm1 * norm2)))
        return math.degrees(math.acos(cos_val))

    def _shape_loss(self, work_coords, remove_index):
        prev_coord = work_coords[remove_index - 1] if remove_index - 1 >= 0 else None
        curr_coord = work_coords[remove_index]
        next_coord = work_coords[remove_index + 1] if remove_index + 1 < len(work_coords) else None

        old_scores = []
        if prev_coord is not None and remove_index - 2 >= 0:
            old_scores.append(self._bend_score(work_coords[remove_index - 2], prev_coord, curr_coord))
        if next_coord is not None and remove_index + 2 < len(work_coords):
            old_scores.append(self._bend_score(curr_coord, next_coord, work_coords[remove_index + 2]))
        if prev_coord is not None and next_coord is not None:
            old_scores.append(self._bend_score(prev_coord, curr_coord, next_coord))

        new_scores = []
        if prev_coord is not None and next_coord is not None:
            if remove_index - 2 >= 0:
                new_scores.append(self._bend_score(work_coords[remove_index - 2], prev_coord, next_coord))
            if remove_index + 2 < len(work_coords):
                new_scores.append(self._bend_score(prev_coord, next_coord, work_coords[remove_index + 2]))

        old_peak = max(old_scores) if old_scores else 0.0
        new_peak = max(new_scores) if new_scores else 0.0
        significant_penalty = 50.0 if old_peak > self.angle_tol and new_peak <= self.angle_tol else 0.0
        return abs(old_peak - new_peak) + significant_penalty

    def _remove_close_vertices_from_line(self, line):
        coords = [tuple(coord) for coord in line.coords]
        if len(coords) <= 2:
            return line

        work_coords = [coords[0]]
        for coord in coords[1:]:
            if self._point_distance(work_coords[-1], coord) > bt_const.SMALL_BUFFER:
                work_coords.append(coord)

        while (
            len(work_coords) > 2
            and self._point_distance(work_coords[0], work_coords[1]) < self.close_distance
        ):
            work_coords.pop(1)

        while (
            len(work_coords) > 2
            and self._point_distance(work_coords[-2], work_coords[-1]) < self.close_distance
        ):
            work_coords.pop(-2)

        i = 1
        while i < len(work_coords) - 2:
            left_coord = work_coords[i]
            right_coord = work_coords[i + 1]
            if self._point_distance(left_coord, right_coord) >= self.close_distance:
                i += 1
                continue

            left_score = self._bend_score(work_coords[i - 1], left_coord, right_coord)
            right_score = self._bend_score(left_coord, right_coord, work_coords[i + 2])

            if left_score > self.angle_tol and right_score <= self.angle_tol:
                remove_index = i + 1
            elif right_score > self.angle_tol and left_score <= self.angle_tol:
                remove_index = i
            else:
                remove_left_loss = self._shape_loss(work_coords, i)
                remove_right_loss = self._shape_loss(work_coords, i + 1)
                if remove_left_loss <= remove_right_loss:
                    remove_index = i
                else:
                    remove_index = i + 1

            work_coords.pop(remove_index)
            if i > 1:
                i -= 1

        if len(work_coords) < 2:
            return None

        if self._point_distance(work_coords[0], work_coords[-1]) <= bt_const.SMALL_BUFFER:
            return None

        return sh_geom.LineString(work_coords)

    def remove_close_vertices(self, gdf):
        """Remove redundant close internal vertices on each line independently."""
        if gdf is None or gdf.empty:
            return gdf

        if isinstance(gdf, gpd.GeoSeries):
            gdf = gpd.GeoDataFrame(geometry=gdf)

        out_gdf = gdf.copy()

        if any(geom.geom_type == "MultiLineString" for geom in out_gdf.geometry):
            out_gdf = out_gdf.explode(index_parts=False)

        cleaned_geoms = []
        for geom in out_gdf.geometry:
            if geom is None or geom.is_empty:
                cleaned_geoms.append(None)
                continue

            if geom.geom_type != "LineString":
                cleaned_geoms.append(geom)
                continue

            cleaned_geoms.append(self._remove_close_vertices_from_line(geom))

        out_gdf.geometry = cleaned_geoms
        out_gdf = out_gdf[~out_gdf.geometry.isna() & ~out_gdf.geometry.is_empty]
        out_gdf = out_gdf[out_gdf.geometry.length > bt_const.SMALL_BUFFER]
        out_gdf.reset_index(drop=True, inplace=True)

        return out_gdf


class _SingleLine:
    """Single line object with anchor point."""

    def __init__(self, line_gdf, line_no, end_no, search_distance):
        self.line_gdf = line_gdf
        self.line = self.line_gdf.geometry[0]
        self.line_no = line_no
        self.end_no = end_no
        self.search_distance = search_distance
        self.anchor = None

        self.add_anchors_to_line()

    def is_valid(self):
        return self.line.is_valid

    def line_coord_list(self):
        return algo_common.line_coord_list(self.line)

    def get_end_vertex(self):
        return self.line_coord_list()[self.end_no]

    def touches_point(self, vertex):
        return algo_common.points_are_close(vertex, self.get_end_vertex())

    def get_angle(self):
        return algo_common.get_angle(self.line, self.end_no)

    def add_anchors_to_line(self):
        """
        Append new vertex to vertex group, by calculating distance to existing vertices.

        An anchor point will be added together with line
        """
        # Calculate anchor point for each vertex
        point = self.get_end_vertex()
        line_string = self.line
        index = self.end_no
        pts = algo_common.line_coord_list(line_string)

        pt_1 = None
        pt_2 = None
        if index == 0:
            pt_1 = point
            pt_2 = pts[1]
        elif index == -1:
            pt_1 = point
            pt_2 = pts[-2]

        # Calculate anchor point
        dist_pt = 0.0
        if pt_1 and pt_2:
            dist_pt = pt_1.distance(pt_2)

        # TODO: check why two points are the same
        if np.isclose(dist_pt, 0.0):
            print("Points are close, return")
            return None

        X = pt_1.x + (pt_2.x - pt_1.x) * self.search_distance / dist_pt
        Y = pt_1.y + (pt_2.y - pt_1.y) * self.search_distance / dist_pt
        self.anchor = sh_geom.Point(X, Y)  # add anchor point


class _Vertex:
    """Vertex object with multiple lines."""

    def __init__(self, line_obj, in_raster=None, line_radius=None, cost_footprint=None):
        self.vertex = line_obj.get_end_vertex()
        self.search_distance = line_obj.search_distance

        self.cost_footprint = cost_footprint
        self.vertex_opt = None  # optimized vertex
        self.centerlines = None
        self.anchors = None
        self.in_raster = in_raster
        self.line_radius = line_radius
        self.lines = []  # SingleLine objects

        self.add_line(line_obj)

    def add_line(self, line_obj):
        self.lines.append(line_obj)

    def generate_anchor_pairs(self):
        """
        Extend line following outward direction to length of search_distance.

        Use the end point as anchor point.

            vertex: input intersection with all related lines
            return:
            one or two pairs of anchors according to numbers of lines
            intersected.
            two pairs anchors return when 3 or 4 lines intersected
            one pair anchors return when 1 or 2 lines intersected.
        """
        lines = self.get_lines()
        vertex = self.get_vertex()
        slopes = []
        for line in self.lines:
            slopes.append(line.get_angle())

        index = 0  # the index of line which paired with first line.
        pt_start_1 = None
        pt_end_1 = None
        pt_start_2 = None
        pt_end_2 = None

        if len(slopes) == 4:
            # get sort order of angles
            index = np.argsort(slopes)

            # first anchor pair (first and third in the sorted array)
            pt_start_1 = self.lines[index[0]].anchor
            pt_end_1 = self.lines[index[2]].anchor

            pt_start_2 = self.lines[index[1]].anchor
            pt_end_2 = self.lines[index[3]].anchor
        elif len(slopes) == 3:
            # find the largest difference between angles
            angle_diff = [
                abs(slopes[0] - slopes[1]),
                abs(slopes[0] - slopes[2]),
                abs(slopes[1] - slopes[2]),
            ]
            angle_diff_norm = [2 * np.pi - i if i > np.pi else i for i in angle_diff]
            index = np.argmax(angle_diff_norm)
            pairs = [(0, 1), (0, 2), (1, 2)]
            pair = pairs[index]

            # first anchor pair
            pt_start_1 = self.lines[pair[0]].anchor
            pt_end_1 = self.lines[pair[1]].anchor

            # the rest one index
            remain = list({0, 1, 2} - set(pair))[0]  # the remaining index

            try:
                pt_start_2 = self.lines[remain].anchor
                # symmetry point of pt_start_2 regarding vertex["point"]
                X = vertex.x - (pt_start_2.x - vertex.x)
                Y = vertex.y - (pt_start_2.y - vertex.y)
                pt_end_2 = sh_geom.Point(X, Y)
            except Exception as e:
                print(e)

        # this scenario only use two anchors
        # and find the closest point on least cost path
        elif len(slopes) == 2:
            pt_start_1 = self.lines[0].anchor
            pt_end_1 = self.lines[1].anchor
        elif len(slopes) == 1:
            pt_start_1 = self.lines[0].anchor
            # symmetry point of pt_start_1 regarding vertex["point"]
            X = vertex.x - (pt_start_1.x - vertex.x)
            Y = vertex.y - (pt_start_1.y - vertex.y)
            pt_end_1 = sh_geom.Point(X, Y)

        if not pt_start_1 or not pt_end_1:
            print("Anchors not found")

        # if points are outside of cost footprint, set to None
        points = [pt_start_1, pt_end_1, pt_start_2, pt_end_2]
        for index, pt in enumerate(points):
            if pt:
                if not self.cost_footprint.contains(sh_geom.Point(pt)):
                    points[index] = None

        if len(slopes) == 4 or len(slopes) == 3:
            if None in points:
                return None
            else:
                return points
        elif len(slopes) == 2 or len(slopes) == 1:
            if None in (pt_start_1, pt_end_1):
                return None
            else:
                return pt_start_1, pt_end_1

    def compute(self):
        if self.cost_footprint is not None:
            try:
                if not self.cost_footprint.covers(self.get_vertex()):
                    return None
            except Exception:
                if not self.cost_footprint.contains(self.get_vertex()):
                    return None

        try:
            self.anchors = self.generate_anchor_pairs()
        except Exception as e:
            print(e)

        if not self.anchors:
            if bt_const.BT_DEBUGGING:
                print("No anchors retrieved")
            return None

        centerline_1 = None
        centerline_2 = None
        intersection = None

        if bt_const.CenterlineFlags.USE_SKIMAGE_GRAPH:
            find_lc_path = algo_dijkstra.find_least_cost_path_skimage
        else:
            find_lc_path = algo_dijkstra.find_least_cost_path

        try:
            if len(self.anchors) == 4:
                seed_line = sh_geom.LineString(self.anchors[0:2])
                if not self._should_process_seed_line(seed_line):
                    return None

                raster_clip, out_meta = sp_common.clip_raster(self.in_raster, seed_line, self.line_radius)
                raster_clip, _ = algo_cost.cost_raster(raster_clip, out_meta)
                centerline_1 = find_lc_path(raster_clip, out_meta, seed_line)
                seed_line = sh_geom.LineString(self.anchors[2:4])
                if not self._should_process_seed_line(seed_line):
                    return None

                raster_clip, out_meta = sp_common.clip_raster(self.in_raster, seed_line, self.line_radius)
                raster_clip, _ = algo_cost.cost_raster(raster_clip, out_meta)
                centerline_2 = find_lc_path(raster_clip, out_meta, seed_line)

                if centerline_1 and centerline_2:
                    intersection = algo_common.intersection_of_lines(centerline_1, centerline_2)
            elif len(self.anchors) == 2:
                seed_line = sh_geom.LineString(self.anchors)
                if not self._should_process_seed_line(seed_line):
                    return None

                raster_clip, out_meta = sp_common.clip_raster(self.in_raster, seed_line, self.line_radius)
                raster_clip, _ = algo_cost.cost_raster(raster_clip, out_meta)
                centerline_1 = find_lc_path(raster_clip, out_meta, seed_line)

                if centerline_1:
                    intersection = algo_common.closest_point_to_line(self.get_vertex(), centerline_1)
        except Exception as e:
            print(e)

        # Update vertices according to intersection, new center lines are returned
        if type(intersection) is sh_geom.MultiPoint:
            intersection = intersection.centroid

        self.centerlines = [centerline_1, centerline_2]
        self.vertex_opt = intersection

    def _should_process_seed_line(self, seed_line):
        if seed_line is None or seed_line.length <= bt_const.SMALL_BUFFER:
            return False

        if self.cost_footprint is not None:
            try:
                if not self.cost_footprint.intersects(seed_line.buffer(self.line_radius)):
                    return False
            except Exception:
                return False

        max_seed_length = max(float(self.search_distance) * 6.0, float(self.line_radius) * 10.0)
        if seed_line.length > max_seed_length:
            return False

        return True

    def get_lines(self):
        lines = [item.line for item in self.lines]
        return lines

    def get_vertex(self):
        return self.vertex


class SeedLineCorrection:
    """A class used to group vertices and perform seed line correction."""

    def __init__(
        self,
        in_line,
        in_raster,
        search_distance,
        line_radius,
        processes,
        call_mode,
        layer=None,
        optimize_internal_vertices=False,
        close_distance=None,
        min_segment_length=None,
        angle_tol=10.0,
    ):
        self.in_line = in_line
        self.in_layer = layer
        self.in_raster = in_raster
        self.line_radius = float(line_radius)
        self.search_distance = float(search_distance)
        self.processes = processes
        self.call_mode = call_mode
        self.optimize_internal_vertices = bool(optimize_internal_vertices)

        self.crs = None
        self.vertex_grp = []
        self.sindex = None

        self.line_list = []
        self.line_visited = None
        self.source_lines_gdf = None

        self.close_distance = close_distance
        self.min_segment_length = min_segment_length
        self.angle_tol = float(angle_tol)

        if self.close_distance is None:
            self.close_distance = self._default_close_distance()
        else:
            self.close_distance = float(self.close_distance)

        if self.min_segment_length is None:
            self.min_segment_length = self.close_distance
        else:
            self.min_segment_length = float(self.min_segment_length)

        # calculate cost raster footprint
        self.cost_footprint = algo_common.generate_raster_footprint(self.in_raster, latlon=False)

    def _default_close_distance(self):
        fallback = 2.0
        if rasterio is None:
            return fallback

        try:
            with rasterio.open(self.in_raster) as src:
                transform = src.transform
                cell_size = min(abs(transform.a), abs(transform.e))
                if np.isclose(cell_size, 0.0):
                    return fallback
                return float(max(2.0, 1.5 * cell_size))
        except Exception:
            return fallback

    def create_vertex_group(self, line_obj):
        """
        Create a new vertex group.

        Args:
            line_obj : _SingleLine

        """
        # all end points not added will stay with this vertex
        vertex = line_obj.get_end_vertex()
        vertex_obj = _Vertex(
            line_obj,
            in_raster=self.in_raster,
            line_radius=self.line_radius,
            cost_footprint=self.cost_footprint,
        )
        search = self.sindex.query(vertex.buffer(bt_const.SMALL_BUFFER))

        # add more vertices to the new group
        for i in search:
            line = self.line_list[i]
            if i == line_obj.line_no:
                continue

            if not self.line_visited[i][0]:
                new_line = _SingleLine(line, i, 0, self.search_distance)
                if new_line.touches_point(vertex):
                    vertex_obj.add_line(new_line)
                    self.line_visited[i][0] = True

            if not self.line_visited[i][-1]:
                new_line = _SingleLine(line, i, -1, self.search_distance)
                if new_line.touches_point(vertex):
                    vertex_obj.add_line(new_line)
                    self.line_visited[i][-1] = True

        self.vertex_grp.append(vertex_obj)

    def prepare_lines(self, lines_gdf=None):
        print(f"Preparing lines...{self.in_line}", flush=True)
        print(f"in_file: {self.in_line}, in_layer: {self.in_layer}")

        if lines_gdf is None:
            lines_gdf = algo_common.read_geospatial_file(self.in_line, layer=self.in_layer)

        if lines_gdf is None:
            self.source_lines_gdf = None
            self.line_list = []
            self.sindex = None
            self.line_visited = None
            return

        # Keep in-memory and file-based paths consistent with shared input hygiene.
        if "fid" in lines_gdf.columns:
            lines_gdf = lines_gdf.rename(columns={"fid": "orig_fid"})

        lines_gdf = algo_common.clean_geometries(lines_gdf, stage="input")
        lines_gdf = lines_gdf.reset_index(drop=True)
        if bt_const.BT_UID not in lines_gdf.columns:
            lines_gdf[bt_const.BT_UID] = range(len(lines_gdf))

        self.source_lines_gdf = lines_gdf.copy()
        lines_gdf = VertexPrecleaner(
            self.close_distance,
            self.angle_tol,
        ).remove_close_vertices(lines_gdf)

        if self.optimize_internal_vertices:
            self.line_list = algo_common.split_lines_to_segments(lines_gdf)
        else:
            self.line_list = algo_common.lines_gdf_to_list(lines_gdf)

        if not self.line_list:
            print("No lines available for seed line correction.")
            self.sindex = None
            self.line_visited = None
            return

        self.sindex = STRtree([item.geometry[0] for item in self.line_list])
        self.line_visited = [{0: False, -1: False} for _ in range(len(self.line_list))]

    def group_vertices(self):
        if not self.line_list or self.line_visited is None:
            return

        for line_no in range(len(self.line_list)):
            for end_no in [0, -1]:
                if self.line_visited[line_no][end_no]:
                    continue

                line = _SingleLine(self.line_list[line_no], line_no, end_no, self.search_distance)
                if not line.is_valid():
                    print(f"Line {line.line_no} is invalid")
                    continue

                self.create_vertex_group(line)
                self.line_visited[line_no][end_no] = True

    def create_all_vertex_groups(self):
        self.prepare_lines()
        self.group_vertices()

    def update_all_lines(self):
        for vertex_obj in self.vertex_grp:
            for line in vertex_obj.lines:
                if not vertex_obj.vertex_opt:
                    continue

                old_line = self.line_list[line.line_no].geometry[0]
                self.line_list[line.line_no].geometry = [
                    update_line_end_pt(old_line, line.end_no, vertex_obj.vertex_opt)
                ]

    def get_optimized_lines(self):
        if not self.line_list:
            if self.source_lines_gdf is None:
                return None

            lines = self.source_lines_gdf.iloc[0:0]
            return algo_common.clean_geometries(
                lines,
                stage="output",
                layer="rejected_output_vertex_optimization_lines",
            )

        lines = pd.concat(self.line_list, ignore_index=True)

        if self.optimize_internal_vertices and "BT_UID" in lines.columns:
            import beratools.core.algo_merge_lines as algo_merge_lines

            lines[bt_const.BT_GROUP] = lines["BT_UID"]
            lines = algo_merge_lines.run_line_merge(lines, merge_group=True)

        if "length" not in lines.columns:
            lines["length"] = lines.geometry.length

        return algo_common.clean_geometries(
            lines,
            stage="output",
            layer="rejected_output_vertex_optimization_lines",
        )

    def get_debug_layers(self):
        lines = self.get_optimized_lines()
        out_crs = None if lines is None else lines.crs

        lc_paths = []
        anchors = []
        vertices = []
        for item in self.vertex_grp:
            if item.centerlines:
                lc_paths.extend(item.centerlines)
            if item.anchors:
                anchors.extend(item.anchors)
            if item.vertex_opt:
                vertices.append(item.vertex_opt)

        lc_paths = [item for item in lc_paths if item is not None]
        anchors = [item for item in anchors if item is not None]
        vertices = [item for item in vertices if item is not None]

        return {
            "lc_paths": gpd.GeoDataFrame(geometry=lc_paths, crs=out_crs),
            "anchors": gpd.GeoDataFrame(geometry=anchors, crs=out_crs),
            "vertices": gpd.GeoDataFrame(geometry=vertices, crs=out_crs),
        }

    def optimize(self):
        self.compute()
        self.update_all_lines()
        return self.get_optimized_lines()

    def compute(self):
        compute_processes = self.processes
        if self.optimize_internal_vertices and (compute_processes is None or int(compute_processes) <= 0):
            compute_processes = 1

        vertex_grp = bt_base.execute_multiprocessing(
            algo_common.process_single_item,
            self.vertex_grp,
            "Vertex Optimization",
            compute_processes,
            self.call_mode,
        )

        self.vertex_grp = vertex_grp
