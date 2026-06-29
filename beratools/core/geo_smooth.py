from __future__ import annotations

from shapely.geometry import LineString, MultiPolygon, Polygon


def chaikin_smooth_line(line: LineString, *, iterations: int) -> LineString:
    if line is None or line.is_empty or iterations <= 0 or len(line.coords) < 3:
        return line

    points = [(float(x), float(y)) for x, y, *_ in line.coords]
    for _ in range(iterations):
        smoothed = [points[0]]
        for point, next_point in zip(points, points[1:]):
            smoothed.append(
                (
                    0.75 * point[0] + 0.25 * next_point[0],
                    0.75 * point[1] + 0.25 * next_point[1],
                )
            )
            smoothed.append(
                (
                    0.25 * point[0] + 0.75 * next_point[0],
                    0.25 * point[1] + 0.75 * next_point[1],
                )
            )
        smoothed.append(points[-1])
        points = smoothed
    return LineString(points)


def chaikin_smooth_polygon(geometry, *, iterations: int):
    if geometry is None or geometry.is_empty or iterations <= 0:
        return geometry
    if geometry.geom_type == "Polygon":
        exterior = _chaikin_smooth_ring(geometry.exterior.coords, iterations=iterations)
        interiors = [
            _chaikin_smooth_ring(interior.coords, iterations=iterations)
            for interior in geometry.interiors
        ]
        return Polygon(exterior, interiors)
    if geometry.geom_type == "MultiPolygon":
        return MultiPolygon(
            [
                chaikin_smooth_polygon(part, iterations=iterations)
                for part in geometry.geoms
            ]
        )
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
            smoothed.append(
                (
                    0.75 * point[0] + 0.25 * next_point[0],
                    0.75 * point[1] + 0.25 * next_point[1],
                )
            )
            smoothed.append(
                (
                    0.25 * point[0] + 0.75 * next_point[0],
                    0.25 * point[1] + 0.75 * next_point[1],
                )
            )
        points = smoothed
    return points + points[:1]
