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

from pathlib import Path

import geopandas as gpd
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

    def __init__(self, line_obj):
        self.vertex = line_obj.get_end_vertex()
        self.search_distance = line_obj.search_distance

        self.cost_footprint = None
        self.vertex_opt = None  # optimized vertex
        self.centerlines = None
        self.anchors = None
        self.in_raster = None
        self.line_radius = None
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
                pt_start_2 = lines[remain][2]
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

                raster_clip, out_meta = sp_common.clip_raster(self.in_raster, seed_line, self.line_radius)
                raster_clip, _ = algo_cost.cost_raster(raster_clip, out_meta)
                centerline_1 = find_lc_path(raster_clip, out_meta, seed_line)
                seed_line = sh_geom.LineString(self.anchors[2:4])

                raster_clip, out_meta = sp_common.clip_raster(self.in_raster, seed_line, self.line_radius)
                raster_clip, _ = algo_cost.cost_raster(raster_clip, out_meta)
                centerline_2 = find_lc_path(raster_clip, out_meta, seed_line)

                if centerline_1 and centerline_2:
                    intersection = algo_common.intersection_of_lines(centerline_1, centerline_2)
            elif len(self.anchors) == 2:
                seed_line = sh_geom.LineString(self.anchors)

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

    def get_lines(self):
        lines = [item.line for item in self.lines]
        return lines

    def get_vertex(self):
        return self.vertex


class VertexGrouping:
    """A class used to group vertices and perform vertex optimization."""

    def __init__(
        self,
        in_line,
        in_raster,
        search_distance,
        line_radius,
        out_line,
        processes,
        verbose,
        in_layer=None,
        out_layer=None,
    ):
        self.in_line = in_line
        self.in_raster = in_raster
        self.line_radius = float(line_radius)
        self.search_distance = float(search_distance)
        self.out_line = out_line
        self.processes = processes
        self.verbose = verbose
        self.parallel_mode = bt_const.PARALLEL_MODE
        self.in_layer = in_layer
        self.out_layer = out_layer

        self.crs = None
        self.vertex_grp = []
        self.sindex = None

        self.line_list = []
        self.line_visited = None

        # calculate cost raster footprint
        self.cost_footprint = algo_common.generate_raster_footprint(self.in_raster, latlon=False)

    def set_parallel_mode(self, parallel_mode):
        self.parallel_mode = parallel_mode

    def create_vertex_group(self, line_obj):
        """
        Create a new vertex group.

        Args:
            line_obj : _SingleLine

        """
        # all end points not added will stay with this vertex
        vertex = line_obj.get_end_vertex()
        vertex_obj = _Vertex(line_obj)
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

        vertex_obj.in_raster = self.in_raster

        vertex_obj.line_radius = self.line_radius
        vertex_obj.cost_footprint = self.cost_footprint
        self.vertex_grp.append(vertex_obj)

    def create_all_vertex_groups(self):
        self.line_list = algo_common.prepare_lines_gdf(self.in_line, layer=self.in_layer, proc_segments=True)
        self.sindex = STRtree([item.geometry[0] for item in self.line_list])
        self.line_visited = [{0: False, -1: False} for _ in range(len(self.line_list))]

        i = 0
        for line_no in range(len(self.line_list)):
            if not self.line_visited[line_no][0]:
                line = _SingleLine(self.line_list[line_no], line_no, 0, self.search_distance)

                if not line.is_valid:
                    print(f"Line {line['line_no']} is invalid")
                    continue

                self.create_vertex_group(line)
                self.line_visited[line_no][0] = True
                i += 1

            if not self.line_visited[line_no][-1]:
                line = _SingleLine(self.line_list[line_no], line_no, -1, self.search_distance)

                if not line.is_valid:
                    print(f"Line {line['line_no']} is invalid")
                    continue

                self.create_vertex_group(line)
                self.line_visited[line_no][-1] = True
                i += 1

    def update_all_lines(self):
        for vertex_obj in self.vertex_grp:
            for line in vertex_obj.lines:
                if not vertex_obj.vertex_opt:
                    continue

                old_line = self.line_list[line.line_no].geometry[0]
                self.line_list[line.line_no].geometry = [
                    update_line_end_pt(old_line, line.end_no, vertex_obj.vertex_opt)
                ]

    def save_all_layers(self, line_file):
        line_file = Path(line_file)
        lines = pd.concat(self.line_list)
        lines.to_file(line_file, layer=self.out_layer)
        print(f"Saved output to: {line_file}", flush=True)

        aux_file = line_file
        if line_file.suffix == ".shp":
            file_stem = line_file.stem
            aux_file = line_file.with_stem(file_stem + "_aux").with_suffix(".gpkg")

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

        lc_paths = gpd.GeoDataFrame(geometry=lc_paths, crs=lines.crs)
        anchors = gpd.GeoDataFrame(geometry=anchors, crs=lines.crs)
        vertices = gpd.GeoDataFrame(geometry=vertices, crs=lines.crs)

        if bt_const.BT_DEBUGGING:
            lc_paths.to_file(aux_file, layer="lc_paths")
            anchors.to_file(aux_file, layer="anchors")
            vertices.to_file(aux_file, layer="vertices")

    def compute(self):
        vertex_grp = bt_base.execute_multiprocessing(
            algo_common.process_single_item,
            self.vertex_grp,
            "Vertex Optimization",
            self.processes,
            bt_const.PARALLEL_MODE.MULTIPROCESSING,
            verbose=self.verbose,
        )

        self.vertex_grp = vertex_grp
