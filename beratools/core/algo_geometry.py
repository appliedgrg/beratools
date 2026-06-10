"""Reusable vector geometry post-processing helpers."""

from __future__ import annotations

from shapely.geometry import LineString, MultiPolygon, Polygon


def chaikin_smooth_line(line: LineString, *, iterations: int) -> LineString:
    if line is None or line.is_empty or iterations <= 0 or len(line.coords) < 3:
        return line

    points = [(float(x), float(y)) for x, y, *_ in line.coords]
    for _ in range(iterations):
        smoothed = [points[0]]
        for point, next_point in zip(points, points[1:]):
            smoothed.append((0.75 * point[0] + 0.25 * next_point[0], 0.75 * point[1] + 0.25 * next_point[1]))
            smoothed.append((0.25 * point[0] + 0.75 * next_point[0], 0.25 * point[1] + 0.75 * next_point[1]))
        smoothed.append(points[-1])
        points = smoothed
    return LineString(points)


def chaikin_smooth_polygon(geometry, *, iterations: int):
    if geometry is None or geometry.is_empty or iterations <= 0:
        return geometry
    if geometry.geom_type == "Polygon":
        exterior = _chaikin_smooth_ring(geometry.exterior.coords, iterations=iterations)
        interiors = [_chaikin_smooth_ring(interior.coords, iterations=iterations) for interior in geometry.interiors]
        return Polygon(exterior, interiors)
    if geometry.geom_type == "MultiPolygon":
        return MultiPolygon([chaikin_smooth_polygon(part, iterations=iterations) for part in geometry.geoms])
    return geometry


def process_corridor_polygon(
    polygon,
    *,
    delete_holes=False,
    simplify=False,
    simplify_length=0.0,
    smooth=False,
    smooth_iterations=0,
):
    """Apply stage-8 style polygon cleanup, simplification, and smoothing."""

    if polygon is None or polygon.is_empty:
        return polygon

    processed = polygon
    if delete_holes:
        processed = _delete_polygon_holes(processed)
    if simplify and float(simplify_length) > 0:
        processed = processed.simplify(float(simplify_length), preserve_topology=True)
    if smooth and int(smooth_iterations) > 0:
        processed = chaikin_smooth_polygon(processed, iterations=int(smooth_iterations))
    if processed is not None and not processed.is_valid:
        processed = processed.buffer(0)
    return processed


def _delete_polygon_holes(geometry):
    if geometry.geom_type == "Polygon":
        return Polygon(geometry.exterior)
    if geometry.geom_type == "MultiPolygon":
        return MultiPolygon([Polygon(poly.exterior) for poly in geometry.geoms])
    return geometry


def _chaikin_smooth_ring(coords, *, iterations: int) -> list[tuple[float, float]]:
    points = [(float(x), float(y)) for x, y, *_ in coords]
    if len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    if len(points) < 3 or iterations <= 0:
        return points + points[:1]

    for _ in range(iterations):
        smoothed = []
        for index, point in enumerate(points):
            next_point = points[(index + 1) % len(points)]
            smoothed.append((0.75 * point[0] + 0.25 * next_point[0], 0.75 * point[1] + 0.25 * next_point[1]))
            smoothed.append((0.25 * point[0] + 0.75 * next_point[0], 0.25 * point[1] + 0.75 * next_point[1]))
        points = smoothed
    return points + points[:1]
