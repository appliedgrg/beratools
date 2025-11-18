"""Test functions and command lines."""

import geopandas as gpd
import pytest
from label_centerlines import get_centerline


# Fixture to load the 'alps.geojson' shape using geopandas
@pytest.fixture
def footprint_shape(testdata_dir):
    # Read the GeoJSON file using geopandas
    gdf = gpd.read_file(testdata_dir.joinpath("footprint.geojson"))

    # Return the first geometry from the GeoDataFrame
    return gdf.geometry.iloc[0]

# Test the centerline functionality
def test_centerline(footprint_shape):
    cl = get_centerline(footprint_shape)
    assert cl.is_valid
    assert cl.geom_type == "MultiLineString"