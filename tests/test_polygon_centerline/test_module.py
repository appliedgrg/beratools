import logging

import pytest
from shapely.geometry import Point

from beratools.external.polygon_centerline import get_centerline
from beratools.external.polygon_centerline.exceptions import CenterlineError
import beratools.external.polygon_centerline._src as src_module


def test_centerline(alps_shape):
    cl = get_centerline(alps_shape)
    assert cl.is_valid
    assert cl.geom_type == "LineString"


def test_alps_endpoint_points_are_inside_and_off_centerline(
    alps_shape, alps_endpoint_points
):
    centerline = get_centerline(alps_shape)
    src_pt, dst_pt = alps_endpoint_points

    assert alps_shape.contains(src_pt)
    assert alps_shape.contains(dst_pt)

    assert centerline.distance(src_pt) > 0.05
    assert centerline.distance(dst_pt) > 0.05


def test_centerline_strict_endpoint_guidance(alps_shape, alps_endpoint_points):
    src_pt, dst_pt = alps_endpoint_points
    centerline = get_centerline(
        alps_shape,
        src_geom=src_pt,
        dst_geom=dst_pt,
    )

    assert Point(centerline.coords[0]).distance(src_pt) < 1e-9
    assert Point(centerline.coords[-1]).distance(dst_pt) < 1e-9


def test_centerline_guided_strategy_main_route(alps_shape, alps_endpoint_points):
    src_pt, dst_pt = alps_endpoint_points
    centerline = get_centerline(
        alps_shape,
        src_geom=src_pt,
        dst_geom=dst_pt,
        guided_strategy="main_route",
    )
    assert centerline.is_valid
    assert centerline.geom_type == "LineString"


def test_centerline_guided_strategy_virtual(alps_shape, alps_endpoint_points):
    src_pt, dst_pt = alps_endpoint_points
    centerline = get_centerline(
        alps_shape,
        src_geom=src_pt,
        dst_geom=dst_pt,
        guided_strategy="virtual",
    )
    assert Point(centerline.coords[0]).distance(src_pt) < 1e-9
    assert Point(centerline.coords[-1]).distance(dst_pt) < 1e-9


def test_centerline_guided_strategy_candidate(alps_shape):
    src_pt = alps_shape.representative_point()
    dst_pt = alps_shape.centroid
    centerline = get_centerline(
        alps_shape,
        src_geom=src_pt,
        dst_geom=dst_pt,
        guided_strategy="candidate",
    )
    assert centerline.is_valid
    assert centerline.geom_type == "LineString"


def test_centerline_guided_strategy_candidate_strict_anchors(alps_shape):
    src_pt = alps_shape.representative_point()
    dst_pt = alps_shape.centroid
    centerline = get_centerline(
        alps_shape,
        src_geom=src_pt,
        dst_geom=dst_pt,
        guided_strategy="candidate",
    )
    assert Point(centerline.coords[0]).distance(src_pt) < 1e-9
    assert Point(centerline.coords[-1]).distance(dst_pt) < 1e-9


def test_centerline_guided_failure_raises_in_strict_mode(alps_shape, monkeypatch):
    src_pt = alps_shape.representative_point()
    dst_pt = alps_shape.centroid

    monkeypatch.setattr(
        src_module, "_get_guided_path_virtual", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(src_module, "_get_guided_path", lambda *args, **kwargs: None)

    with pytest.raises(CenterlineError, match="endpoint-guided extraction failed"):
        get_centerline(
            alps_shape,
            src_geom=src_pt,
            dst_geom=dst_pt,
            guided_strategy="virtual",
            endpoint_mode="strict",
        )


def test_centerline_guided_failure_soft_mode_warns_and_falls_back(
    alps_shape, monkeypatch, caplog
):
    src_pt = alps_shape.representative_point()
    dst_pt = alps_shape.centroid

    monkeypatch.setattr(
        src_module, "_get_guided_path_virtual", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(src_module, "_get_guided_path", lambda *args, **kwargs: None)

    with caplog.at_level(logging.WARNING, logger=src_module.__name__):
        centerline = get_centerline(
            alps_shape,
            src_geom=src_pt,
            dst_geom=dst_pt,
            guided_strategy="virtual",
            endpoint_mode="soft",
        )

    assert centerline.is_valid
    assert centerline.geom_type == "LineString"
    assert any(
        "endpoint-guided extraction failed in soft mode" in record.message
        for record in caplog.records
    )


def test_centerline_guided_strategy_invalid(alps_shape):
    with pytest.raises(ValueError):
        get_centerline(alps_shape, guided_strategy="unknown")


def test_centerline_upstream_kwargs_regression(alps_shape, alps_endpoint_areas):
    src_geom, dst_geom = alps_endpoint_areas
    centerline = get_centerline(
        alps_shape,
        guided_strategy="virtual",
        endpoint_mode="strict",
        src_geom=src_geom,
        dst_geom=dst_geom,
    )

    src_pt = src_geom.representative_point()
    dst_pt = dst_geom.representative_point()
    assert Point(centerline.coords[0]).distance(src_pt) < 1e-9
    assert Point(centerline.coords[-1]).distance(dst_pt) < 1e-9
