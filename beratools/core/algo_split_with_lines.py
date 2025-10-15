"""Split lines at intersections using a class-based approach."""

from itertools import combinations

import geopandas as gpd
from shapely import STRtree, snap
from shapely.geometry import LineString, MultiPoint, Point

import beratools.core.algo_common as algo_common

EPSILON = 1e-5
INTER_STATUS_COL = "INTER_STATUS"


def min_distance_in_multipoint(multipoint):
    points = list(multipoint.geoms)
    min_dist = float("inf")
    for p1, p2 in combinations(points, 2):
        dist = p1.distance(p2)
        if dist < min_dist:
            min_dist = dist
    return min_dist


class LineSplitter:
    """Split lines at intersections."""

    def __init__(self, line_gdf):
        """
        Initialize the LineSplitter with the input GeoPackage and layer name.

        Args:
        input_gpkg (str): Path to the input GeoPackage file.
        layer_name (str): Name of the layer to read from the GeoPackage.

        """
        # Explode if needed for multi-part geometries
        self.line_gdf = line_gdf.explode()
        self.line_gdf[INTER_STATUS_COL] = 1  # record line intersection status
        self.inter_status = {}
        self.sindex = self.line_gdf.sindex  # Spatial index for faster operations

        self.intersection_gdf = []
        self.split_lines_gdf = None

    def cut_line_by_points(self, line, points):
        """
        Cuts a LineString into segments based on the given points.

        Args:
        line: A shapely LineString to be cut.
        points: A list of Point objects where the LineString needs to be cut.

        Return:
        A list of LineString segments after the cuts.

        """
        # Create a spatial index for the coordinates of the LineString
        line_coords = [Point(x, y) for x, y in line.coords]
        sindex = STRtree(line_coords)

        # Sort points based on their projected position along the line
        sorted_points = sorted(points, key=lambda p: line.project(p))
        segments = []

        # Process each point, inserting it into the correct location
        start_idx = 0
        start_pt = None
        end_pt = None

        for point in sorted_points:
            # Find the closest segment on the line using the spatial index
            nearest_pt_idx = sindex.nearest(point)
            end_idx = nearest_pt_idx
            end_pt = point

            dist1 = line.project(point)
            dist2 = line.project(line_coords[nearest_pt_idx])

            if dist1 > dist2:
                end_idx = nearest_pt_idx + 1

            # Create a new segment
            new_coords = line_coords[start_idx:end_idx]
            if start_pt:  # Append start point
                new_coords = [start_pt] + new_coords

            if end_pt:  # Append end point
                new_coords = new_coords + [end_pt]

            nearest_segment = LineString(new_coords)
            start_idx = end_idx
            start_pt = end_pt

            segments.append(nearest_segment)

        # Add remaining part of the line after the last point
        if start_idx < len(line_coords):
            # If last point is not close to end point of line
            if start_pt.distance(line_coords[-1]) > EPSILON:
                remaining_part = LineString([start_pt] + line_coords[end_idx:])
                segments.append(remaining_part)

        return segments

    def find_intersections(self):
        """
        Find intersections between lines in the GeoDataFrame.

        Return:
        List of Point geometries where the lines intersect.

        """
        visited_pairs = set()
        intersection_points = []

        # Iterate through each line geometry to find intersections
        for idx, line1 in enumerate(self.line_gdf.geometry):
            # Use spatial index to find candidates for intersection
            indices = list(self.sindex.intersection(line1.bounds))
            indices.remove(idx)  # Remove the current index from the list

            for match_idx in indices:
                line2 = self.line_gdf.iloc[match_idx].geometry

                # Create an index pair where the smaller index comes first
                pair = tuple(sorted([idx, match_idx]))

                # Skip if this pair has already been visited
                if pair in visited_pairs:
                    continue

                # Mark the pair as visited
                visited_pairs.add(pair)

                # Only check lines that are different and intersect
                line1 = snap(line1, line2, tolerance=EPSILON)
                if line1.intersects(line2):
                    # Find intersection points (can be multiple)
                    intersections = line1.intersection(line2)

                    if intersections.is_empty:
                        continue

                    # Intersection can be Point, MultiPoint, LineString
                    # or GeometryCollection
                    if isinstance(intersections, Point):
                        intersection_points.append(intersections)
                    else:
                        # record for further inspection
                        # GeometryCollection, MultiLineString
                        if isinstance(intersections, MultiPoint):
                            intersection_points.extend(intersections.geoms)
                        elif isinstance(intersections, LineString):
                            intersection_points.append(intersections.interpolate(0.5, normalized=True))

                        # if minimum distance between points is greater than threshold
                        # mark line as valid
                        if isinstance(intersections, MultiPoint):
                            if min_distance_in_multipoint(intersections) > algo_common.DISTANCE_THRESHOLD:
                                continue
                        # if intersection is a line, mark line as valid
                        if isinstance(intersections, LineString):
                            continue

                        for item in pair:
                            self.inter_status[item] = 0

        self.intersection_gdf = gpd.GeoDataFrame(geometry=intersection_points, crs=self.line_gdf.crs)

    def split_lines_at_intersections(self):
        """
        Split lines at the given intersection points.

        Args:
        intersection_points: List of Point geometries where the lines should be split.

        Returns:
        A GeoDataFrame with the split lines.

        """
        # Create a spatial index for faster point-line intersection checks
        sindex = self.intersection_gdf.sindex

        # List to hold the new split line segments
        new_rows = []

        # Iterate through each intersection point to split lines at that point
        for row in self.line_gdf.itertuples():
            if not isinstance(row.geometry, LineString):
                continue

            # Use spatial index to find possible line candidates for intersection
            possible_matches = sindex.query(row.geometry.buffer(EPSILON))
            end_pts = MultiPoint([row.geometry.coords[0], row.geometry.coords[-1]])

            pt_list = []
            new_segments = [row.geometry]

            for idx in possible_matches:
                point = self.intersection_gdf.loc[idx].geometry
                # Check if the point is on the line
                if row.geometry.distance(point) < EPSILON:
                    if end_pts.distance(point) < EPSILON:
                        continue
                    else:
                        pt_list.append(point)

            if len(pt_list) > 0:
                # Split the line at the intersection
                new_segments = self.cut_line_by_points(row.geometry, pt_list)

            # If the line was split into multiple segments, create new rows
            for segment in new_segments:
                new_row = row._asdict()  # Convert the original row into a dictionary
                new_row["geometry"] = segment  # Update the geometry with the split one
                new_rows.append(new_row)

        self.split_lines_gdf = gpd.GeoDataFrame(
            new_rows, columns=self.line_gdf.columns, crs=self.line_gdf.crs
        )

        self.split_lines_gdf = algo_common.clean_line_geometries(self.split_lines_gdf)

        # Debugging: print how many segments were created
        print(f"Total new line segments created: {len(new_rows)}")

    def save_to_geopackage(
        self,
        input_gpkg,
        line_layer="split_lines",
        intersection_layer=None,
        invalid_layer=None,
    ):
        """
        Save the split lines and intersection points to the GeoPackage.

        Args:
        line_layer: split lines layer name in the GeoPackage.
        intersection_layer: layer name for intersection points in the GeoPackage.

        """
        # Save intersection points and split lines to the GeoPackage
        if self.split_lines_gdf is not None and intersection_layer:
            if len(self.intersection_gdf) > 0:
                self.intersection_gdf.to_file(input_gpkg, layer=intersection_layer, driver="GPKG")

        if self.split_lines_gdf is not None and line_layer:
            if len(self.split_lines_gdf) > 0:
                self.split_lines_gdf["length"] = self.split_lines_gdf.geometry.length
                self.split_lines_gdf.to_file(input_gpkg, layer=line_layer, driver="GPKG")

        # save invalid splits
        invalid_splits = self.line_gdf.loc[self.line_gdf[INTER_STATUS_COL] == 0]
        if not invalid_splits.empty and invalid_layer:
            if len(invalid_splits) > 0:
                invalid_splits.to_file(input_gpkg, layer=invalid_layer, driver="GPKG")

    def process(self, intersection_gdf=None):
        """
        Find intersection points, split lines at intersections.

        Args:
        intersection_gdf: external GeoDataFrame with intersection points.

        """
        if intersection_gdf is not None:
            self.intersection_gdf = intersection_gdf
        else:
            self.find_intersections()

        if self.inter_status:
            for idx in self.inter_status.keys():
                self.line_gdf.loc[idx, INTER_STATUS_COL] = self.inter_status[idx]

        if not self.intersection_gdf.empty:
            # Split the lines at intersection points
            self.split_lines_at_intersections()
        else:
            print("No intersection points found, no lines to split.")


def split_with_lines(input_gpkg, layer_name):
    splitter = LineSplitter(input_gpkg, layer_name)
    splitter.process()
    splitter.save_to_geopackage()


if __name__ == "__main__":
    input_gpkg = r"I:\Temp\footprint_final.gpkg"
    layer_name = "merged_lines_original"

    gdf = gpd.read_file(input_gpkg, layer=layer_name)
    splitter = LineSplitter(gdf)
    splitter.process()
    splitter.save_to_geopackage(input_gpkg)
