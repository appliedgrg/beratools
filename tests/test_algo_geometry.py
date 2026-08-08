from shapely.geometry import LineString, Polygon

from beratools.core.algo_geometry import (
    chaikin_smooth_line,
    chaikin_smooth_polygon,
    process_corridor_polygon,
)


def test_chaikin_smooth_line_preserves_endpoints():
    line = LineString([(0, 0), (1, 1), (2, 0)])

    smoothed = chaikin_smooth_line(line, iterations=1)

    assert smoothed.coords[0] == line.coords[0]
    assert smoothed.coords[-1] == line.coords[-1]
    assert len(smoothed.coords) > len(line.coords)


def test_chaikin_smooth_polygon_returns_closed_valid_polygon():
    polygon = Polygon([(0, 0), (4, 0), (4, 2), (0, 2), (0, 0)])

    smoothed = chaikin_smooth_polygon(polygon, iterations=1)

    assert smoothed.is_valid
    assert smoothed.exterior.coords[0] == smoothed.exterior.coords[-1]
    assert len(smoothed.exterior.coords) > len(polygon.exterior.coords)


def test_process_corridor_polygon_deletes_holes_simplifies_and_smooths():
    polygon = Polygon(
        [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)],
        holes=[[(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)]],
    )

    processed = process_corridor_polygon(
        polygon,
        delete_holes=True,
        simplify=True,
        simplify_length=0.1,
        smooth=True,
        smooth_iterations=1,
    )

    assert processed.is_valid
    assert len(processed.interiors) == 0
    assert len(processed.exterior.coords) > len(Polygon(polygon.exterior).exterior.coords)
