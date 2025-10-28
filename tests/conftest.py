"""Test configuration file for the BERA Tools package."""

import logging
import os
import sys
import time
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, Path(__file__).parents[1].as_posix())

def pytest_configure(config):
    # Ignore the FutureWarning for the specific warning from osgeo.osr
    warnings.simplefilter("ignore", category=FutureWarning)
    warnings.simplefilter("ignore", category=DeprecationWarning)  # networkit

    # Set the global logging level to ERROR to suppress DEBUG and INFO logs
    logging.basicConfig(level=logging.ERROR)

    # Set logger to ERROR to suppress debug logs
    logging.getLogger('pyogrio').setLevel(logging.WARNING)
    logging.getLogger('rasterio').setLevel(logging.ERROR)
    logging.getLogger('rasterio.env').setLevel(logging.ERROR)
    logging.getLogger('label_centerlines._src').setLevel(logging.ERROR)
    logging.getLogger("pyproj").setLevel(logging.WARNING)
    
# Fixture to get the path to the 'data' directory
@pytest.fixture
def testdata_dir():
    return Path(__file__).parent.joinpath("data")

@pytest.fixture(scope="session")
def available_cpu_cores():
    return os.cpu_count()

# Shared arguments for all tools, now using the `testdata_dir` fixture
@pytest.fixture
def tool_arguments(testdata_dir, available_cpu_cores):
    return {
        "args_centerline": {
            'in_line': testdata_dir.joinpath('seed_lines.gpkg').as_posix(),
             'in_layer': 'seed_lines',
            'in_raster': testdata_dir.joinpath('chm.tif').as_posix(),
            'line_radius': 15,
            'proc_segments': True,
            'out_line': testdata_dir.joinpath('centerline.gpkg').as_posix(),
            'out_layer': 'centerline',
            'processes': available_cpu_cores,
            'verbose': False
        },
        "args_footprint_abs": {
            'in_line': testdata_dir.joinpath('centerline.gpkg').as_posix(),
            'in_chm': testdata_dir.joinpath('chm.tif').as_posix(),
            'in_layer': 'centerline',
            'corridor_thresh': 3.0,
            'max_ln_width': 32.0,
            'exp_shk_cell': 0,
            'out_footprint': testdata_dir.joinpath('footprint_abs.gpkg').as_posix(),
            'out_layer': 'footprint_abs',
            'processes': available_cpu_cores,
            'verbose': False
        },
        "args_footprint_rel": {
            'in_line': testdata_dir.joinpath('centerline.gpkg').as_posix(),
            'in_chm': testdata_dir.joinpath('chm.tif').as_posix(),
            'out_footprint': testdata_dir.joinpath('footprint_rel.gpkg').as_posix(),
            'in_layer': 'centerline',
            'out_layer': 'footprint_rel',
            'max_ln_width': 32,
            'tree_radius': 1.5,
            'max_line_dist': 1.5,
            'canopy_avoidance': 0.0,
            'exponent': 0,
            'canopy_thresh_percentage': 50,
            'processes': available_cpu_cores,
            'verbose': False
        },
        "args_ground_footprint": {
            'in_line': testdata_dir.joinpath('centerline.gpkg').as_posix(),
            'in_footprint': testdata_dir.joinpath('footprint_rel.gpkg').as_posix(),
            'in_layer': 'centerline',
            'in_layer_fp': 'footprint_rel',
            'n_samples': 15,
            'offset': 30,
            'max_width': True,
            'out_footprint': testdata_dir.joinpath('footprint_final.gpkg').as_posix(),
            'out_layer': 'footprint_fixed',
            'processes': available_cpu_cores,
            'verbose': False
        }
    }

# A test for cleaning up test output files
@pytest.fixture
def test_output_files(testdata_dir):
    return [
        testdata_dir.joinpath('centerline.gpkg'),
        testdata_dir.joinpath('footprint_abs.gpkg'),
        testdata_dir.joinpath('footprint_rel.gpkg'),
        testdata_dir.joinpath('footprint_final.gpkg'),
        testdata_dir.joinpath('footprint_final_aux.gpkg'),
        testdata_dir.joinpath('line_percentile_rel.gpkg')
    ]

@pytest.fixture
def cleanup_output_files(test_output_files):
    """Fixture to clean up generated output files after the test."""
    yield  # Yield here allows the test to run first
    time.sleep(1)  # Wait a little to allow file system operations to complete
    for file_path in test_output_files:
        if file_path.exists():
            file_path.unlink()
            assert not file_path.exists(), f"Failed to remove {file_path}"
