import os

import geopandas as gpd
import pytest

TEST_DIR = os.path.dirname(os.path.realpath(__file__))
TESTDATA_DIR = os.path.join(TEST_DIR, "testdata")


@pytest.fixture
def footprint_shape():
    gdf = gpd.read_file(os.path.join(TESTDATA_DIR, "footprint.geojson"))
    return gdf.geometry.iloc[0]


@pytest.fixture
def footprint_endpoint_points():
    gdf = gpd.read_file(os.path.join(TESTDATA_DIR, "footprint_endpoints.geojson"))
    return gdf.geometry.iloc[0], gdf.geometry.iloc[1]


@pytest.fixture
def footprint_endpoint_areas(footprint_endpoint_points):
    src_pt, dst_pt = footprint_endpoint_points
    return src_pt.buffer(5.0), dst_pt.buffer(5.0)


@pytest.fixture
def multi_footprint_shape():
    gdf = gpd.read_file(os.path.join(TESTDATA_DIR, "footprint_multi.geojson"))
    return gdf.geometry.iloc[0]


@pytest.fixture
def multi_footprint_endpoint_points():
    gdf = gpd.read_file(
        os.path.join(TESTDATA_DIR, "footprint_multi_endpoints.geojson")
    )
    src1 = gdf.loc[gdf["role"] == "src"].iloc[0].geometry
    dst1 = gdf.loc[gdf["role"] == "dst"].iloc[0].geometry
    src2 = gdf.loc[gdf["role"] == "src"].iloc[1].geometry
    dst2 = gdf.loc[gdf["role"] == "dst"].iloc[1].geometry
    return (src1, dst1), (src2, dst2)
