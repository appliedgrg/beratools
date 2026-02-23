import os

import fiona
import pytest
from shapely.geometry import shape

TEST_DIR = os.path.dirname(os.path.realpath(__file__))
TESTDATA_DIR = os.path.join(TEST_DIR, "testdata")


@pytest.fixture
def alps_shape():
    with fiona.open(os.path.join(TESTDATA_DIR, "alps.geojson"), "r") as src:
        return shape(next(iter(src))["geometry"])


@pytest.fixture
def alps_endpoint_points():
    with fiona.open(os.path.join(TESTDATA_DIR, "alps_endpoints.geojson"), "r") as src:
        features = list(src)
    src_pt = shape(features[0]["geometry"])
    dst_pt = shape(features[1]["geometry"])
    return src_pt, dst_pt


@pytest.fixture
def alps_endpoint_areas(alps_endpoint_points):
    src_pt, dst_pt = alps_endpoint_points
    return src_pt.buffer(0.25), dst_pt.buffer(0.25)
