"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng, Maverick Fong

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    This file hosts code to deal with line grouping and merging, cleanups.
"""

import enum
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import chain
from typing import Optional, Union

import networkit as nk
import numpy as np
import shapely
import shapely.geometry as sh_geom

import beratools.core.algo_common as algo_common
import beratools.core.algo_merge_lines as algo_merge_lines
import beratools.core.constants as bt_const

TRIMMING_DISTANCE = 75  # meters
SMALL_BUFFER = 1


@enum.unique
class VertexClass(enum.IntEnum):
    """Enum class for vertex class."""

    TWO_WAY_ZERO_PRIMARY_LINE = 1
    THREE_WAY_ZERO_PRIMARY_LINE = 2
    THREE_WAY_ONE_PRIMARY_LINE = 3
    FOUR_WAY_ZERO_PRIMARY_LINE = 4
    FOUR_WAY_ONE_PRIMARY_LINE = 5
    FOUR_WAY_TWO_PRIMARY_LINE = 6
    FIVE_WAY_ZERO_PRIMARY_LINE = 7
    FIVE_WAY_ONE_PRIMARY_LINE = 8
    FIVE_WAY_TWO_PRIMARY_LINE = 9
    SINGLE_WAY = 10


CONCERN_CLASSES = (
    VertexClass.FIVE_WAY_ZERO_PRIMARY_LINE,
    VertexClass.FIVE_WAY_ONE_PRIMARY_LINE,
    VertexClass.FIVE_WAY_TWO_PRIMARY_LINE,
    VertexClass.FOUR_WAY_ZERO_PRIMARY_LINE,
    VertexClass.FOUR_WAY_ONE_PRIMARY_LINE,
    VertexClass.FOUR_WAY_TWO_PRIMARY_LINE,
    VertexClass.THREE_WAY_ZERO_PRIMARY_LINE,
    VertexClass.THREE_WAY_ONE_PRIMARY_LINE,
    VertexClass.TWO_WAY_ZERO_PRIMARY_LINE,
    VertexClass.SINGLE_WAY,
)

ANGLE_TOLERANCE = np.pi / 10
TURN_ANGLE_TOLERANCE = np.pi * 0.5  # (little bigger than right angle)
TRIM_THRESHOLD = 0.15
TRANSECT_LENGTH = 40


def points_in_line(line):
    """Get point list of line."""
    point_list = []
    try:
        for point in list(line.coords):  # loops through every point in a line
            # loops through every vertex of every segment
            if point:  # adds all the vertices to segment_list, which creates an array
                point_list.append(sh_geom.Point(point[0], point[1]))
    except Exception as e:
        print(e)

    return point_list


def get_angle(line, end_index):
    """
    Calculate the angle of the first or last segment.

    Args:
    line: sh_geom.LineString
    end_index: 0 or -1 of the line vertices. Consider the multipart.

    """
    pts = points_in_line(line)

    if end_index == 0:
        pt_1 = pts[0]
        pt_2 = pts[1]
    elif end_index == -1:
        pt_1 = pts[-1]
        pt_2 = pts[-2]

    delta_x = pt_2.x - pt_1.x
    delta_y = pt_2.y - pt_1.y
    angle = np.arctan2(delta_y, delta_x)

    return angle


@dataclass
class SingleLine:
    """Class to store line and its simplified line."""

    line_id: int = field(default=0)
    line: Union[sh_geom.LineString, sh_geom.MultiLineString] = field(default=None)
    sim_line: Union[sh_geom.LineString, sh_geom.MultiLineString] = field(default=None)
    vertex_index: int = field(default=0)
    group: int = field(default=0)

    def get_angle_for_line(self):
        return get_angle(self.sim_line, self.vertex_index)

    def end_transect(self):
        coords = self.sim_line.coords
        end_seg = None
        if self.vertex_index == 0:
            end_seg = sh_geom.LineString([coords[0], coords[1]])
        elif self.vertex_index == -1:
            end_seg = sh_geom.LineString([coords[-1], coords[-2]])

        l_left = end_seg.offset_curve(TRANSECT_LENGTH)
        l_right = end_seg.offset_curve(-TRANSECT_LENGTH)

        return sh_geom.LineString([l_left.coords[0], l_right.coords[0]])

    def midpoint(self):
        return shapely.force_2d(self.line.interpolate(0.5, normalized=True))

    def update_line(self, line):
        self.line = line


class VertexNode:
    """Class to store vertex and lines connected to it."""

    def __init__(self, line_id, line, sim_line, vertex_index, group=None) -> None:
        self.vertex = None
        self.line_list = []
        self.line_connected = []  # pairs of lines connected
        self.line_not_connected = []
        self.vertex_class = None

        if line:
            self.add_line(SingleLine(line_id, line, sim_line, vertex_index, group))

    def set_vertex(self, line, vertex_index):
        """Set vertex coordinates."""
        self.vertex = shapely.force_2d(shapely.get_point(line, vertex_index))

    def add_line(self, line_class):
        """Add line when creating or merging other VertexNode."""
        self.line_list.append(line_class)
        self.set_vertex(line_class.line, line_class.vertex_index)

    def get_line(self, line_id):
        for line in self.line_list:
            if line.line_id == line_id:
                return line.line

    def get_line_obj(self, line_id):
        for line in self.line_list:
            if line.line_id == line_id:
                return line

    def get_line_geom(self, line_id):
        return self.get_line_obj(line_id).line

    def get_all_line_ids(self):
        all_line_ids = {i.line_id for i in self.line_list}
        return all_line_ids

    def update_line(self, line_id, line):
        for i in self.line_list:
            if i.line_id == line_id:
                i.update_line(line)

    def merge(self, vertex):
        """Merge other VertexNode if they have same vertex coords."""
        self.add_line(vertex.line_list[0])

    def get_trim_transect(self, poly, line_indices):
        if not poly:
            return None

        internal_line = None
        for line_idx in line_indices:
            line = self.get_line_obj(line_idx)
            if poly.contains(line.midpoint()):
                internal_line = line

        if not internal_line:
            # print("No line is retrieved")
            return
        return internal_line.end_transect()

    def _trim_polygon(self, poly, trim_transect):
        if not poly or not trim_transect:
            return

        split_poly = shapely.ops.split(poly, trim_transect)

        if len(split_poly.geoms) != 2:
            return

        # check geom_type
        none_poly = False
        for geom in split_poly.geoms:
            if geom.geom_type != "Polygon":
                none_poly = True

        if none_poly:
            return

        # only two polygons in split_poly
        if split_poly.geoms[0].area > split_poly.geoms[1].area:
            poly = split_poly.geoms[0]
        else:
            poly = split_poly.geoms[1]

        return poly

    def trim_end_all(self, polys):
        """
        Trim all unconnected lines in the vertex.

        Args:
        polys: list of polygons returned by sindex.query

        """
        polys = polys.geometry
        new_polys = []
        for idx, poly in polys.items():
            out_poly = self.trim_end(poly)
            if out_poly:
                new_polys.append((idx, out_poly))

        return new_polys

    def trim_end(self, poly):
        transect = self.get_trim_transect(poly, self.line_not_connected)
        if not transect:
            return

        poly = self._trim_polygon(poly, transect)
        return poly
        # Helper to get the neighbor coordinate based on vertex_index.

    @staticmethod
    def get_vertex(line_obj, index):
        coords = list(line_obj.sim_line.coords)
        # Normalize negative indices.
        if index < 0:
            index += len(coords)
        if 0 <= index < len(coords):
            return sh_geom.Point(coords[index])

    @staticmethod
    def get_neighbor(line_obj):
        index = 0

        if line_obj.vertex_index == 0:
            index = 1
        elif line_obj.vertex_index == -1:
            index = -2

        return VertexNode.get_vertex(line_obj, index)

    @staticmethod
    def parallel_line_centered(p1, p2, center, length):
        """Generate a parallel line."""
        # Compute the direction vector.
        dx = p2.x - p1.x
        dy = p2.y - p1.y

        # Normalize the direction vector.
        magnitude = (dx**2 + dy**2) ** 0.5
        if magnitude == 0:
            return None
        dx /= magnitude
        dy /= magnitude

        # Compute half-length shifts.
        half_dx = (dx * length) / 2
        half_dy = (dy * length) / 2

        # Compute the endpoints of the new parallel line.
        new_p1 = sh_geom.Point(center.x - half_dx, center.y - half_dy)
        new_p2 = sh_geom.Point(center.x + half_dx, center.y + half_dy)

        return sh_geom.LineString([new_p1, new_p2])

    def get_transect_for_primary(self):
        """
        Get a transect line from two primary connected lines.

        This method calculates a transect line that is perpendicular to the line segment
        formed by the next vertex neighbors of these two lines and the current vertex.

        Return:
            A transect line object if the conditions are met, otherwise None.

        """
        if not self.line_connected or len(self.line_connected[0]) != 2:
            return None

        # Retrieve the two connected line objects from the first connectivity group.
        line_ids = self.line_connected[0]
        pt1 = None
        pt1 = None
        if line_ids[0] == line_ids[1]:  # line ring
            # TODO: check line ring when merging vertex nodes.
            # TODO: change one end index to -1
            line_id = line_ids[0]
            pt1 = self.get_vertex(self.get_line_obj(line_id), 1)
            pt2 = self.get_vertex(self.get_line_obj(line_id), -2)
        else:  # two different lines
            line_obj1 = self.get_line_obj(line_ids[0])
            line_obj2 = self.get_line_obj(line_ids[1])

            pt1 = self.get_neighbor(line_obj1)
            pt2 = self.get_neighbor(line_obj2)

        if pt1 is None or pt2 is None:
            return None

        transect = algo_common.generate_perpendicular_line_precise([pt1, self.vertex, pt2], offset=40)
        return transect

    def get_transect_for_primary_second(self):
        """
        Get a transect line from the second primary connected line.

        For the second primary line, this method retrieves the neighbor point from
        two lines in the second connectivity group, creates a reference line through the
        vertex by mirroring the neighbor point about the vertex, and then generates a
        parallel line centered at the vertex.

        Returns:
            A LineString representing the transect if available, otherwise None.

        """
        # Ensure there is a second connectivity group.
        if not self.line_connected or len(self.line_connected) < 2:
            return None

        # Use the first line of the second connectivity group.
        second_primary = self.line_connected[1]
        line_obj1 = self.get_line_obj(second_primary[0])
        line_obj2 = self.get_line_obj(second_primary[1])
        if not line_obj1 or not line_obj2:
            return None

        pt1 = self.get_neighbor(line_obj1)
        pt2 = self.get_neighbor(line_obj2)

        if pt1 is None or pt2 is None:
            return None

        center = self.vertex
        transect = self.parallel_line_centered(pt1, pt2, center, TRANSECT_LENGTH)
        return transect

    def trim_primary_end(self, polys):
        """
        Trim first primary line in the vertex.

        Args:
        polys: list of polygons returned by sindex.query

        """
        if len(self.line_connected) == 0:
            return

        new_polys = []
        line = self.line_connected[0]

        # use the first line to get transect
        # transect = self.get_line_obj(line[0]).end_transect()
        # if len(self.line_connected) == 1:
        transect = self.get_transect_for_primary()
        # elif len(self.line_connected) > 1:
        #     transect = self.get_transect_for_primary_second()

        idx_1 = line[0]
        poly_1 = None
        idx_1 = line[1]
        poly_2 = None

        for idx, poly in polys.items():
            # TODO: no polygons
            if not poly:
                continue

            if poly.buffer(SMALL_BUFFER).contains(self.get_line_geom(line[0])):
                poly_1 = poly
                idx_1 = idx
            elif poly.buffer(SMALL_BUFFER).contains(self.get_line_geom(line[1])):
                poly_2 = poly
                idx_2 = idx

        if poly_1:
            poly_1 = self._trim_polygon(poly_1, transect)
            new_polys.append([idx_1, poly_1])
        if poly_2:
            poly_2 = self._trim_polygon(poly_2, transect)
            new_polys.append([idx_2, poly_2])

        return new_polys

    def trim_intersection(self, polys, merge_group=True):
        """
        Trim intersection of lines and polygons.

        TODO: there are polygons of 0 zero.

        """

        def get_poly_with_info(line, polys):
            if polys.empty:
                return None, None, None

            for idx, row in polys.iterrows():
                poly = row.geometry
                if not poly:  # TODO: no polygon
                    continue

                if poly.buffer(SMALL_BUFFER).contains(line):
                    return idx, poly, row["max_width"]

            return None, None, None

        poly_trim_list = []
        primary_lines = []
        p_primary_list = []

        # retrieve primary lines
        if len(self.line_connected) > 0:
            for idx in self.line_connected[0]:  # only one connected line is used
                primary_lines.append(self.get_line(idx))
                _, poly, _ = get_poly_with_info(self.get_line(idx), polys)

                if poly:
                    p_primary_list.append(poly.buffer(bt_const.SMALL_BUFFER))
                else:
                    print("trim_intersection: No primary polygon found.")

        line_idx_to_trim = self.line_not_connected
        poly_list = []
        if not merge_group:  # add all remaining primary lines for trimming
            if len(self.line_connected) > 1:
                for line in self.line_connected[1:]:
                    line_idx_to_trim.extend(line)

            # sort line index to by footprint area
            for line_idx in line_idx_to_trim:
                line = self.get_line_geom(line_idx)
                poly_idx, poly, max_width = get_poly_with_info(line, polys)
                if poly_idx:
                    poly_list.append((line_idx, poly_idx, max_width))

            poly_list = sorted(poly_list, key=lambda x: x[2])

        # create PolygonTrimming object and trim all by primary line
        for i, indices in enumerate(poly_list):
            line_idx = indices[0]
            poly_idx = indices[1]
            line_cleanup = self.get_line(line_idx)
            poly_cleanup = polys.loc[poly_idx].geometry
            poly_trim = PolygonTrimming(
                line_index=line_idx,
                line_cleanup=line_cleanup,
                poly_index=poly_idx,
                poly_cleanup=poly_cleanup,
            )

            poly_trim_list.append(poly_trim)
            if p_primary_list:
                poly_trim.process(p_primary_list, self.vertex)

            # use poly_trim.poly_cleanup to update polys gdf's geometry
            polys.at[poly_trim.poly_index, "geometry"] = poly_trim.poly_cleanup

        # further trimming overlaps by non-primary lines
        # poly_list and poly_trim_list have same index
        for i, indices in enumerate(poly_list):
            p_list = []
            for p in poly_list[i + 1 :]:
                p_list.append(polys.loc[p[1]].geometry)

            poly_trim = poly_trim_list[i]
            poly_trim.process(p_list, self.vertex)

        return poly_trim_list

    def assign_vertex_class(self):
        if len(self.line_list) == 5:
            if len(self.line_connected) == 0:
                self.vertex_class = VertexClass.FIVE_WAY_ZERO_PRIMARY_LINE
            if len(self.line_connected) == 1:
                self.vertex_class = VertexClass.FIVE_WAY_ONE_PRIMARY_LINE
            if len(self.line_connected) == 2:
                self.vertex_class = VertexClass.FIVE_WAY_TWO_PRIMARY_LINE
        elif len(self.line_list) == 4:
            if len(self.line_connected) == 0:
                self.vertex_class = VertexClass.FOUR_WAY_ZERO_PRIMARY_LINE
            if len(self.line_connected) == 1:
                self.vertex_class = VertexClass.FOUR_WAY_ONE_PRIMARY_LINE
            if len(self.line_connected) == 2:
                self.vertex_class = VertexClass.FOUR_WAY_TWO_PRIMARY_LINE
        elif len(self.line_list) == 3:
            if len(self.line_connected) == 0:
                self.vertex_class = VertexClass.THREE_WAY_ZERO_PRIMARY_LINE
            if len(self.line_connected) == 1:
                self.vertex_class = VertexClass.THREE_WAY_ONE_PRIMARY_LINE
        elif len(self.line_list) == 2:
            if len(self.line_connected) == 0:
                self.vertex_class = VertexClass.TWO_WAY_ZERO_PRIMARY_LINE
        elif len(self.line_list) == 1:
            self.vertex_class = VertexClass.SINGLE_WAY

    def all_has_valid_group_attr(self):
        """If all values in group list are valid value, return True."""
        # TODO: if some line has no group, give advice
        for i in self.line_list:
            if i.group is None:
                return False

        return True

    def need_regrouping(self):
        pass

    def check_connectivity(self, use_angle_grouping=True):
        # Fill missing group with -1
        for line in self.line_list:
            if line.group is None:
                line.group = -1

        if self.need_regrouping():
            self.group_regroup()

        if use_angle_grouping:
            self.group_line_by_angle()
        else:
            self.update_connectivity_by_group()

        # record line not connected
        all_line_ids = self.get_all_line_ids()
        self.line_not_connected = list(all_line_ids - set(chain(*self.line_connected)))

        self.assign_vertex_class()

    def group_regroup(self):
        pass

    def update_connectivity_by_group(self):
        group_line = defaultdict(list)
        for i in self.line_list:
            group_line[i.group].append(i.line_id)

        for value in group_line.values():
            if len(value) > 1:
                self.line_connected.append(value)

    def group_line_by_angle(self):
        """Generate connectivity of all lines."""
        if len(self.line_list) == 1:
            return

        # if there are 2 and more lines
        new_angles = [i.get_angle_for_line() for i in self.line_list]
        angle_visited = [False] * len(new_angles)

        if len(self.line_list) == 2:
            angle_diff = abs(new_angles[0] - new_angles[1])
            angle_diff = angle_diff if angle_diff <= np.pi else angle_diff - np.pi

            # if angle_diff >= TURN_ANGLE_TOLERANCE:
            self.line_connected.append(
                (
                    self.line_list[0].line_id,
                    self.line_list[1].line_id,
                )
            )
            return

        # three and more lines
        for i, angle_1 in enumerate(new_angles):
            for j, angle_2 in enumerate(new_angles[i + 1 :]):
                if not angle_visited[i + j + 1]:
                    angle_diff = abs(angle_1 - angle_2)
                    angle_diff = angle_diff if angle_diff <= np.pi else angle_diff - np.pi
                    if (
                        angle_diff < ANGLE_TOLERANCE
                        or np.pi - ANGLE_TOLERANCE < abs(angle_1 - angle_2) < np.pi + ANGLE_TOLERANCE
                    ):
                        angle_visited[j + i + 1] = True  # tenth of PI
                        self.line_connected.append(
                            (
                                self.line_list[i].line_id,
                                self.line_list[i + j + 1].line_id,
                            )
                        )


class LineGrouping:
    """Class to group lines and merge them."""

    def __init__(self, in_line_gdf, merge_group=True, use_angle_grouping=True) -> None:
        if in_line_gdf is None:
            raise ValueError("Line GeoDataFrame cannot be None")
        self.use_angle_grouping = use_angle_grouping

        if in_line_gdf.empty:
            raise ValueError("Line GeoDataFrame cannot be empty")

        self.lines = algo_common.clean_line_geometries(in_line_gdf)
        self.lines.reset_index(inplace=True, drop=True)
        self.merge_group = merge_group

        self.sim_geom = self.lines.simplify(1)

        self.G = nk.Graph(len(self.lines))
        self.merged_vertex_list = []
        self.has_group_attr = False
        self.need_regrouping = False
        self.groups = [None] * len(self.lines)
        self.merged_lines_trimmed = None  # merged trimmed lines

        self.vertex_list = []
        self.vertex_of_concern = []
        self.v_index = None  # sindex of all vertices for vertex_list

        self.polys = None

        # invalid geoms in final geom list
        self.valid_lines = None
        self.valid_polys = None
        self.invalid_lines = None
        self.invalid_polys = None

    def create_vertex_list(self):
        # check if data has group column
        if bt_const.BT_GROUP in self.lines.keys():
            self.groups = self.lines[bt_const.BT_GROUP]
            self.has_group_attr = True
            if self.groups.hasnans:  # Todo: check for other invalid values
                self.need_regrouping = True

        for idx, s_geom, geom, group in zip(*zip(*self.sim_geom.items()), self.lines.geometry, self.groups):
            self.vertex_list.append(VertexNode(idx, geom, s_geom, 0, group))
            self.vertex_list.append(VertexNode(idx, geom, s_geom, -1, group))

        v_points = []
        for i in self.vertex_list:
            if i.vertex is None:
                print("Vertex is None, skipping.")
                continue

            v_points.append(i.vertex.buffer(SMALL_BUFFER))  # small polygon

        # Spatial index of all vertices
        self.v_index = shapely.STRtree(v_points)

        vertex_visited = [False] * len(self.vertex_list)
        for i, pt in enumerate(v_points):
            if vertex_visited[i]:
                continue

            s_list = self.v_index.query(pt)
            vertex = self.vertex_list[i]
            if len(s_list) > 1:
                for j in s_list:
                    if j != i:
                        # some short line will be very close to each other
                        if vertex.vertex.distance(self.vertex_list[j].vertex) > bt_const.SMALL_BUFFER:
                            continue

                        vertex.merge(self.vertex_list[j])
                        vertex_visited[j] = True

            self.merged_vertex_list.append(vertex)
            vertex_visited[i] = True

        for i in self.merged_vertex_list:
            i.check_connectivity(self.use_angle_grouping)

        for i in self.merged_vertex_list:
            if i.line_connected:
                for edge in i.line_connected:
                    self.G.addEdge(edge[0], edge[1])

    def group_lines(self):
        cc = nk.components.ConnectedComponents(self.G)
        cc.run()
        # print("number of components ", cc.numberOfComponents())

        group = 0
        for i in range(cc.numberOfComponents()):
            component = cc.getComponents()[i]
            for id in component:
                self.groups[id] = group

            group += 1

    def update_line_in_vertex_node(self, line_id, line):
        """Update line in VertexNode after trimming."""
        idx = self.v_index.query(line)
        for i in idx:
            v = self.vertex_list[i]
            v.update_line(line_id, line)

    def run_line_merge(self):
        return algo_merge_lines.run_line_merge(self.lines, self.merge_group)

    def find_vertex_for_poly_trimming(self):
        self.vertex_of_concern = [i for i in self.merged_vertex_list if i.vertex_class in CONCERN_CLASSES]

    def line_and_poly_cleanup(self):
        sindex_poly = self.polys.sindex

        for vertex in self.vertex_of_concern:
            s_idx = sindex_poly.query(vertex.vertex, predicate="within")
            if len(s_idx) == 0:
                continue

            #  Trim intersections of primary lines
            polys = self.polys.loc[s_idx].geometry
            if not self.merge_group:
                if (
                    vertex.vertex_class == VertexClass.FIVE_WAY_TWO_PRIMARY_LINE
                    or vertex.vertex_class == VertexClass.FIVE_WAY_ONE_PRIMARY_LINE
                    or vertex.vertex_class == VertexClass.FOUR_WAY_ONE_PRIMARY_LINE
                    or vertex.vertex_class == VertexClass.FOUR_WAY_TWO_PRIMARY_LINE
                    or vertex.vertex_class == VertexClass.THREE_WAY_ONE_PRIMARY_LINE
                ):
                    out_polys = vertex.trim_primary_end(polys)
                    if len(out_polys) == 0:
                        continue

                    # update polygon DataFrame
                    for idx, out_poly in out_polys:
                        if out_poly:
                            self.polys.at[idx, "geometry"] = out_poly

            # retrieve polygons again. Some polygons may be updated
            polys = self.polys.loc[s_idx]
            if (
                vertex.vertex_class == VertexClass.SINGLE_WAY
                or vertex.vertex_class == VertexClass.TWO_WAY_ZERO_PRIMARY_LINE
                or vertex.vertex_class == VertexClass.THREE_WAY_ZERO_PRIMARY_LINE
                or vertex.vertex_class == VertexClass.FOUR_WAY_ZERO_PRIMARY_LINE
                or vertex.vertex_class == VertexClass.FIVE_WAY_ZERO_PRIMARY_LINE
            ):
                if vertex.vertex_class == VertexClass.THREE_WAY_ZERO_PRIMARY_LINE:
                    pass

                out_polys = vertex.trim_end_all(polys)
                if len(out_polys) == 0:
                    continue

                # update polygon DataFrame
                for idx, out_poly in out_polys:
                    self.polys.at[idx, "geometry"] = out_poly

            polys = self.polys.loc[s_idx]
            if vertex.vertex_class != VertexClass.SINGLE_WAY:
                poly_trim_list = vertex.trim_intersection(polys, self.merge_group)
                for p_trim in poly_trim_list:
                    # update main line and polygon DataFrame
                    self.polys.at[p_trim.poly_index, "geometry"] = p_trim.poly_cleanup
                    self.lines.at[p_trim.line_index, "geometry"] = p_trim.line_cleanup

                    # update VertexNode's line
                    self.update_line_in_vertex_node(p_trim.line_index, p_trim.line_cleanup)

    def get_merged_lines_original(self):
        return self.lines.dissolve(by=bt_const.BT_GROUP)

    def run_grouping(self):
        self.create_vertex_list()
        if not self.has_group_attr:
            self.group_lines()

        self.find_vertex_for_poly_trimming()
        self.lines[bt_const.BT_GROUP] = self.groups  # assign group attribute

    def run_regrouping(self):
        """
        Run this when new lines are added to grouped file.

        Some new lines has empty group attributes
        """
        pass

    def run_cleanup(self, in_polys):
        self.polys = in_polys.copy()
        self.line_and_poly_cleanup()
        self.run_line_merge_trimmed()
        self.check_geom_validity()

    def run_line_merge_trimmed(self):
        self.merged_lines_trimmed = self.run_line_merge()

    def check_geom_validity(self):
        """
        Check MultiLineString and MultiPolygon in line and polygon dataframe.

        Save to separate layers for user to double check
        """
        #  remove null geometry
        # TODO make sure lines and polygons match in pairs
        # they should have same amount and spatial coverage
        self.valid_polys = self.polys[~self.polys.geometry.isna() & ~self.polys.geometry.is_empty]

        # save sh_geom.MultiLineString and sh_geom.MultiPolygon
        self.invalid_polys = self.polys[(self.polys.geometry.geom_type == "MultiPolygon")]

        # check lines
        self.valid_lines = self.merged_lines_trimmed[
            ~self.merged_lines_trimmed.geometry.isna() & ~self.merged_lines_trimmed.geometry.is_empty
        ]
        self.valid_lines.reset_index(inplace=True, drop=True)

        self.invalid_lines = self.merged_lines_trimmed[
            (self.merged_lines_trimmed.geometry.geom_type == "MultiLineString")
        ]
        self.invalid_lines.reset_index(inplace=True, drop=True)

    def save_file(self, out_file):
        if not self.valid_lines.empty:
            self.valid_lines["length"] = self.valid_lines.length
            self.valid_lines.to_file(out_file, layer="merged_lines")

        if not self.valid_polys.empty:
            if "length" in self.valid_polys.columns:
                self.valid_polys.drop(columns=["length"], inplace=True)

            self.valid_polys["area"] = self.valid_polys.area
            self.valid_polys.to_file(out_file, layer="clean_footprint")

        if not self.invalid_lines.empty:
            self.invalid_lines.to_file(out_file, layer="invalid_lines")

        if not self.invalid_polys.empty:
            self.invalid_polys.to_file(out_file, layer="invalid_polygons")


@dataclass
class PolygonTrimming:
    """Store polygon and line to trim. Primary polygon is used to trim both."""

    poly_primary: Optional[sh_geom.MultiPolygon] = None
    poly_index: int = field(default=-1)
    poly_cleanup: Optional[sh_geom.Polygon] = None
    line_index: int = field(default=-1)
    line_cleanup: Optional[sh_geom.LineString] = None

    def process(self, primary_poly_list=None, vertex=None):
        # prepare primary polygon
        poly_primary = shapely.union_all(primary_poly_list)
        trim_distance = TRIMMING_DISTANCE

        if self.line_cleanup.length < 100.0:
            trim_distance = 50.0

        poly_primary = poly_primary.intersection(vertex.buffer(trim_distance))

        self.poly_primary = poly_primary

        # TODO: check why there is such cases
        if self.poly_cleanup is None:
            print("No polygon to trim.")
            return

        midpoint = self.line_cleanup.interpolate(0.5, normalized=True)
        if self.poly_primary is None or self.poly_primary.is_empty:
            print("Warning: No valid primary polygon for trimming; skipping difference operation.")
            return
        diff = self.poly_cleanup.difference(self.poly_primary)
        if diff.geom_type == "Polygon":
            self.poly_cleanup = diff
        elif diff.geom_type == "MultiPolygon":
            # area = self.poly_cleanup.area
            reserved = []
            for i in diff.geoms:
                # if i.area > TRIM_THRESHOLD * area:  # small part
                #     reserved.append(i)
                if i.contains(midpoint):
                    reserved.append(i)

            if len(reserved) == 0:
                pass
            elif len(reserved) == 1:
                self.poly_cleanup = sh_geom.Polygon(*reserved)
            else:
                # TODO output all MultiPolygons which should be dealt with
                # self.poly_cleanup = sh_geom.MultiPolygon(reserved)
                print("trim: MultiPolygon detected, please check")

        diff = self.line_cleanup.intersection(self.poly_cleanup)
        if diff.geom_type == "GeometryCollection":
            geoms = []
            for item in diff.geoms:
                if item.geom_type == "LineString":
                    geoms.append(item)
                elif item.geom_type == "MultiLineString":
                    print("trim: sh_geom.MultiLineString detected, please check")
            if len(geoms) == 0:
                return
            elif len(geoms) == 1:
                diff = geoms[0]
            else:
                diff = sh_geom.MultiLineString(geoms)

        if diff.geom_type == "LineString":
            self.line_cleanup = diff
        elif diff.geom_type == "MultiLineString":
            length = self.line_cleanup.length
            reserved = []
            for i in diff.geoms:
                if i.length > TRIM_THRESHOLD * length:  # small part
                    reserved.append(i)

            if len(reserved) == 0:
                pass
            elif len(reserved) == 1:
                self.line_cleanup = sh_geom.LineString(*reserved)
            else:
                # TODO output all MultiPolygons which should be dealt with
                self.poly_cleanup = sh_geom.MultiLineString(reserved)
