"""Per-line vertex preclean helpers for vertex optimization."""

import math

import geopandas as gpd
import shapely.geometry as sh_geom

import beratools.core.constants as bt_const


def _point_distance(coord_a, coord_b):
    return sh_geom.Point(coord_a).distance(sh_geom.Point(coord_b))


def _is_near_collinear(coord_a, coord_b, coord_c, angle_tol_deg):
    v1x = coord_b[0] - coord_a[0]
    v1y = coord_b[1] - coord_a[1]
    v2x = coord_c[0] - coord_b[0]
    v2y = coord_c[1] - coord_b[1]

    norm1 = math.hypot(v1x, v1y)
    norm2 = math.hypot(v2x, v2y)
    if norm1 <= bt_const.SMALL_BUFFER or norm2 <= bt_const.SMALL_BUFFER:
        return True

    dot = v1x * v2x + v1y * v2y
    cos_val = max(-1.0, min(1.0, dot / (norm1 * norm2)))
    angle = math.degrees(math.acos(cos_val))

    return angle <= angle_tol_deg or abs(angle - 180.0) <= angle_tol_deg


def _dedupe_consecutive_coords(coords):
    if len(coords) <= 1:
        return coords

    out = [coords[0]]
    for coord in coords[1:]:
        if _point_distance(coord, out[-1]) > bt_const.SMALL_BUFFER:
            out.append(coord)

    return out


def _preclean_line(line, close_distance, min_segment_length, angle_tol):
    coords = list(line.coords)
    if len(coords) <= 2:
        return line

    cleaned = [coords[0]]

    for i in range(1, len(coords) - 1):
        prev_coord = cleaned[-1]
        curr_coord = coords[i]
        next_coord = coords[i + 1]

        prev_dist = _point_distance(prev_coord, curr_coord)
        next_dist = _point_distance(curr_coord, next_coord)

        if prev_dist < close_distance or next_dist < close_distance:
            continue

        if (prev_dist < min_segment_length or next_dist < min_segment_length) and _is_near_collinear(
            prev_coord, curr_coord, next_coord, angle_tol
        ):
            continue

        cleaned.append(curr_coord)

    cleaned.append(coords[-1])
    cleaned = _dedupe_consecutive_coords(cleaned)

    while len(cleaned) > 2 and _point_distance(cleaned[0], cleaned[1]) < min_segment_length:
        cleaned.pop(1)

    while len(cleaned) > 2 and _point_distance(cleaned[-2], cleaned[-1]) < min_segment_length:
        cleaned.pop(-2)

    if len(cleaned) < 2:
        return None

    if _point_distance(cleaned[0], cleaned[-1]) <= bt_const.SMALL_BUFFER:
        return None

    return sh_geom.LineString(cleaned)


def preclean_vertices(gdf, close_distance, min_segment_length, angle_tol):
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

        cleaned_geoms.append(_preclean_line(geom, close_distance, min_segment_length, angle_tol))

    out_gdf.geometry = cleaned_geoms
    out_gdf = out_gdf[~out_gdf.geometry.isna() & ~out_gdf.geometry.is_empty]
    out_gdf = out_gdf[out_gdf.geometry.length > bt_const.SMALL_BUFFER]
    out_gdf.reset_index(drop=True, inplace=True)

    return out_gdf
