"""Per-line vertex preclean helpers for line optimization workflows."""

import math

import geopandas as gpd
import shapely.geometry as sh_geom

import beratools.core.constants as bt_const


class VertexPrecleaner:
    VALID_MODES = {"full", "endpoint_only"}

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

    def _dedupe_consecutive_coords(self, coords):
        if not coords:
            return []

        work_coords = [coords[0]]
        for coord in coords[1:]:
            if self._point_distance(work_coords[-1], coord) > bt_const.SMALL_BUFFER:
                work_coords.append(coord)

        return work_coords

    def _finalize_line(self, coords, original_line):
        if len(coords) < 2:
            return None

        if self._point_distance(coords[0], coords[-1]) <= bt_const.SMALL_BUFFER:
            return None

        if len(coords) == len(original_line.coords):
            return original_line

        return sh_geom.LineString(coords)

    def _cleanup_endpoint_only(self, coords):
        while len(coords) > 2 and self._point_distance(coords[0], coords[1]) < self.close_distance:
            coords.pop(1)

        while len(coords) > 2 and self._point_distance(coords[-2], coords[-1]) < self.close_distance:
            coords.pop(-2)

        return coords

    def cleanup_line(self, line, mode="full"):
        if mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported vertex cleanup mode: {mode}")

        coords = [tuple(coord) for coord in line.coords]
        if len(coords) <= 2:
            return line

        work_coords = self._dedupe_consecutive_coords(coords)
        if len(work_coords) <= 2:
            return self._finalize_line(work_coords, line)

        work_coords = self._cleanup_endpoint_only(work_coords)
        if mode == "endpoint_only":
            return self._finalize_line(work_coords, line)

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
                remove_index = i if remove_left_loss <= remove_right_loss else i + 1

            work_coords.pop(remove_index)
            if i > 1:
                i -= 1

        return self._finalize_line(work_coords, line)

    def remove_close_vertices(self, gdf, mode="full"):
        if mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported vertex cleanup mode: {mode}")

        if gdf is None or gdf.empty:
            return gdf

        if isinstance(gdf, gpd.GeoSeries):
            gdf = gpd.GeoDataFrame(geometry=gdf)

        out_gdf = gdf.copy()

        if any(getattr(geom, "geom_type", None) == "MultiLineString" for geom in out_gdf.geometry):
            out_gdf = out_gdf.explode(index_parts=False)

        cleaned_geoms = []
        for geom in out_gdf.geometry:
            if geom is None or geom.is_empty:
                cleaned_geoms.append(None)
                continue

            if geom.geom_type != "LineString":
                cleaned_geoms.append(geom)
                continue

            cleaned_geoms.append(self.cleanup_line(geom, mode=mode))

        geom_series = gpd.GeoSeries(cleaned_geoms, index=out_gdf.index, crs=out_gdf.crs)
        valid_mask = geom_series.notna() & ~geom_series.is_empty
        out_gdf = out_gdf.loc[valid_mask].copy()
        out_gdf.set_geometry(geom_series.loc[valid_mask], inplace=True)
        out_gdf = out_gdf[out_gdf.geometry.length > bt_const.SMALL_BUFFER]
        out_gdf = gpd.GeoDataFrame(out_gdf, crs=gdf.crs)
        out_gdf.reset_index(drop=True, inplace=True)

        return out_gdf

