import logging

import pytest
from shapely.geometry import Point

from beratools.external.polygon_centerline import get_centerline
from beratools.external.polygon_centerline.exceptions import CenterlineError
import beratools.external.polygon_centerline._src as src_module


def test_centerline(footprint_shape):
    cl = get_centerline(footprint_shape)
    assert cl.is_valid
    assert cl.geom_type in ("LineString", "MultiLineString")


def test_endpoint_points_are_inside_and_off_centerline(
    footprint_shape, footprint_endpoint_points
):
    centerline = get_centerline(footprint_shape)
    src_pt, dst_pt = footprint_endpoint_points

    assert footprint_shape.contains(src_pt)
    assert footprint_shape.contains(dst_pt)

    assert centerline.distance(src_pt) > 0.05
    assert centerline.distance(dst_pt) > 0.05


def test_centerline_strict_endpoint_guidance(
    footprint_shape, footprint_endpoint_points
):
    src_pt, dst_pt = footprint_endpoint_points
    centerline = get_centerline(
        footprint_shape,
        src_geom=src_pt,
        dst_geom=dst_pt,
    )

    assert Point(centerline.coords[0]).distance(src_pt) < 1e-9
    assert Point(centerline.coords[-1]).distance(dst_pt) < 1e-9


def test_centerline_guided_strategy_main_route(
    footprint_shape, footprint_endpoint_points
):
    src_pt, dst_pt = footprint_endpoint_points
    centerline = get_centerline(
        footprint_shape,
        src_geom=src_pt,
        dst_geom=dst_pt,
        guided_strategy="main_route",
    )
    assert centerline.is_valid


def test_centerline_guided_strategy_virtual(
    footprint_shape, footprint_endpoint_points
):
    src_pt, dst_pt = footprint_endpoint_points
    centerline = get_centerline(
        footprint_shape,
        src_geom=src_pt,
        dst_geom=dst_pt,
        guided_strategy="virtual",
    )
    assert Point(centerline.coords[0]).distance(src_pt) < 1e-9
    assert Point(centerline.coords[-1]).distance(dst_pt) < 1e-9


def test_centerline_guided_strategy_candidate(footprint_shape):
    src_pt = footprint_shape.representative_point()
    dst_pt = footprint_shape.centroid
    centerline = get_centerline(
        footprint_shape,
        src_geom=src_pt,
        dst_geom=dst_pt,
        guided_strategy="candidate",
    )
    assert centerline.is_valid


def test_centerline_guided_strategy_candidate_strict_anchors(footprint_shape):
    src_pt = footprint_shape.representative_point()
    dst_pt = footprint_shape.centroid
    centerline = get_centerline(
        footprint_shape,
        src_geom=src_pt,
        dst_geom=dst_pt,
        guided_strategy="candidate",
    )
    assert Point(centerline.coords[0]).distance(src_pt) < 1e-9
    assert Point(centerline.coords[-1]).distance(dst_pt) < 1e-9


def test_centerline_guided_failure_raises_in_strict_mode(
    footprint_shape, monkeypatch
):
    src_pt = footprint_shape.representative_point()
    dst_pt = footprint_shape.centroid

    monkeypatch.setattr(
        src_module, "_get_guided_path_virtual", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(src_module, "_get_guided_path", lambda *args, **kwargs: None)

    with pytest.raises(CenterlineError, match="endpoint-guided extraction failed"):
        get_centerline(
            footprint_shape,
            src_geom=src_pt,
            dst_geom=dst_pt,
            guided_strategy="virtual",
            endpoint_mode="strict",
        )


def test_centerline_guided_failure_soft_mode_warns_and_falls_back(
    footprint_shape, monkeypatch, caplog
):
    src_pt = footprint_shape.representative_point()
    dst_pt = footprint_shape.centroid

    monkeypatch.setattr(
        src_module, "_get_guided_path_virtual", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(src_module, "_get_guided_path", lambda *args, **kwargs: None)

    with caplog.at_level(logging.WARNING, logger=src_module.__name__):
        centerline = get_centerline(
            footprint_shape,
            src_geom=src_pt,
            dst_geom=dst_pt,
            guided_strategy="virtual",
            endpoint_mode="soft",
        )

    assert centerline.is_valid
    assert any(
        "endpoint-guided extraction failed in soft mode" in record.message
        for record in caplog.records
    )


def test_centerline_guided_strategy_invalid(footprint_shape):
    with pytest.raises(ValueError):
        get_centerline(footprint_shape, guided_strategy="unknown")


def test_centerline_upstream_kwargs_regression(
    footprint_shape, footprint_endpoint_areas
):
    src_geom, dst_geom = footprint_endpoint_areas
    centerline = get_centerline(
        footprint_shape,
        guided_strategy="virtual",
        endpoint_mode="strict",
        src_geom=src_geom,
        dst_geom=dst_geom,
    )

    src_pt = src_geom.representative_point()
    dst_pt = dst_geom.representative_point()
    assert Point(centerline.coords[0]).distance(src_pt) < 1e-9
    assert Point(centerline.coords[-1]).distance(dst_pt) < 1e-9


# ---------- MultiPolygon tests ----------


def test_multi_centerline(multi_footprint_shape):
    cl = get_centerline(multi_footprint_shape)
    assert cl.is_valid
    assert cl.geom_type == "MultiLineString"
    assert len(cl.geoms) == 2


def test_multi_centerline_main_route(multi_footprint_shape):
    cl = get_centerline(multi_footprint_shape, guided_strategy="main_route")
    assert cl.is_valid
    assert cl.geom_type == "MultiLineString"
    assert len(cl.geoms) == 2


def test_multi_centerline_ignores_endpoint_guidance(
    multi_footprint_shape, multi_footprint_endpoint_points
):
    """MultiPolygon branch does not use endpoint guidance; result is still MultiLineString."""
    (src1, dst1), (src2, dst2) = multi_footprint_endpoint_points
    cl = get_centerline(
        multi_footprint_shape,
        src_geom=src1,
        dst_geom=dst1,
        guided_strategy="virtual",
    )
    assert cl.is_valid
    assert cl.geom_type == "MultiLineString"
    assert len(cl.geoms) == 2


def test_multi_each_sub_polygon_valid(multi_footprint_shape):
    """Each sub-polygon should produce a valid centerline independently."""
    for sub_geom in multi_footprint_shape.geoms:
        cl = get_centerline(sub_geom)
        assert cl.is_valid
        assert cl.geom_type == "LineString"


def test_multi_sub_polygon_with_endpoints(
    multi_footprint_shape, multi_footprint_endpoint_points
):
    """Guided extraction works when applied to individual sub-polygons."""
    for i, sub_geom in enumerate(multi_footprint_shape.geoms):
        src_pt, dst_pt = multi_footprint_endpoint_points[i]
        cl = get_centerline(
            sub_geom,
            src_geom=src_pt,
            dst_geom=dst_pt,
            guided_strategy="candidate",
        )
        assert cl.is_valid
        assert cl.geom_type == "LineString"
        assert Point(cl.coords[0]).distance(src_pt) < 1e-9
        assert Point(cl.coords[-1]).distance(dst_pt) < 1e-9
