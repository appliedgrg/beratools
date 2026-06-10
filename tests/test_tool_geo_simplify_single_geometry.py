from shapely.geometry import LineString


def test_simplify_line_reduce_bend_returns_input_when_diameter_zero():
    from beratools.core.tool_geo_simplify import simplify_line_reduce_bend

    line = LineString([(0, 0), (1, 1), (2, 0)])


    assert simplify_line_reduce_bend(line, crs="EPSG:3857", diameter=0) is line
