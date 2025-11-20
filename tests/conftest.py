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
    logging.getLogger("pyogrio").setLevel(logging.ERROR)
    logging.getLogger("rasterio").setLevel(logging.ERROR)
    logging.getLogger("rasterio.env").setLevel(logging.ERROR)
    logging.getLogger("label_centerlines._src").setLevel(logging.ERROR)
    logging.getLogger("pyproj").setLevel(logging.WARNING)


# Fixture to get the path to the 'data' directory
@pytest.fixture
def testdata_dir():
    return Path(__file__).parent.joinpath("data")


@pytest.fixture(scope="session")
def available_cpu_cores():
    return os.cpu_count()


# Integration arguments: each tool uses original inputs
@pytest.fixture
def tool_arguments_integration(testdata_dir, available_cpu_cores):
    return {
        "args_check_seed_line": {
            "in_line": f"{testdata_dir.joinpath('integration.gpkg').as_posix()}|seed_lines",
            "out_line": f"{testdata_dir.joinpath('integration_inter.gpkg').as_posix()}|seed_lines_checked",
        },
        "args_vertex_optimization": {
            "in_line": f"{testdata_dir.joinpath('integration.gpkg').as_posix()}|seed_lines_checked",
            "in_raster": testdata_dir.joinpath("chm.tif").as_posix(),
            "search_distance": 5.0,
            "line_radius": 15,
            "out_line": f"{testdata_dir.joinpath('integration_inter.gpkg').as_posix()}|seed_lines_vo",
        },
        "args_centerline": {
            "in_line": f"{testdata_dir.joinpath('integration.gpkg').as_posix()}|seed_lines_vo",
            "in_raster": testdata_dir.joinpath("chm.tif").as_posix(),
            "line_radius": 15,
            "proc_segments": True,
            "out_line": f"{testdata_dir.joinpath('integration_inter.gpkg').as_posix()}|centerline",
        },
        "args_footprint_abs": {
            "in_line": f"{testdata_dir.joinpath('integration.gpkg').as_posix()}|centerline",
            "in_chm": testdata_dir.joinpath("chm.tif").as_posix(),
            "corridor_thresh": 3.0,
            "max_ln_width": 32.0,
            "exp_shk_cell": 0,
            "out_footprint": f"{testdata_dir.joinpath('integration_inter.gpkg').as_posix()}|footprint_abs",
        },
        "args_footprint_exp": {
            "in_line": f"{testdata_dir.joinpath('integration.gpkg').as_posix()}|centerline",
            "in_chm": testdata_dir.joinpath("chm.tif").as_posix(),
            "out_footprint": f"{testdata_dir.joinpath('integration_inter.gpkg').as_posix()}|footprint_exp",
            "max_ln_width": 32,
            "tree_radius": 1.5,
            "max_line_dist": 1.5,
            "canopy_avoidance": 0.0,
            "exponent": 0,
            "canopy_thresh_percentage": 50,
        },
        "args_ground_footprint": {
            "in_line": f"{testdata_dir.joinpath('integration.gpkg').as_posix()}|centerline",
            "in_footprint": f"{testdata_dir.joinpath('integration.gpkg').as_posix()}|footprint_exp",
            "n_samples": 15,
            "offset": 30,
            "max_width": True,
            "out_footprint": f"{testdata_dir.joinpath('integration_inter.gpkg').as_posix()}|footprint_ground",
        },
        "arg_main_canopy_threshold_relative": {
            'in_line':f"{testdata_dir.joinpath('integration_inter.gpkg').as_posix()}|centerline",
            'in_chm': testdata_dir.joinpath('chm.tif').as_posix(),
            'canopy_percentile': 90,
            'canopy_thresh_percentage': 50,
            'full_step': 'True',
            'processes': available_cpu_cores,
            'verbose': False,
            'out_DynCenterline': f"{testdata_dir.joinpath('DynCanTh_integration_inter.gpkg').as_posix()}|centerline",
        },
        "arg_main_line_footprint_relative": {
            'in_line': f"{testdata_dir.joinpath('DynCanTh_integration_inter.gpkg').as_posix()}|centerline",
            'in_chm': f"{testdata_dir.joinpath('chm.tif').as_posix()}",
            'max_ln_width': 32,
            'out_footprint': f"{testdata_dir.joinpath('footprint_rel.gpkg').as_posix()}|footprint_rel",
            'out_centerline': f"{testdata_dir.joinpath('smooth_centerline.gpkg').as_posix()}|smooth_centerline",
            'exp_shk_cell':5,
            'tree_radius': 1.5,
            'max_line_dist': 1.5,
            'canopy_avoidance': 1.0,
            'exponent': 1,
            'full_step': 'True',
            'canopy_thresh_percentage': 50,
            'processes': available_cpu_cores,
            'verbose': False,
            'debug_mode':False,
        },
    }


# Workflow arguments: chained outputs
@pytest.fixture
def tool_arguments_workflow(testdata_dir, available_cpu_cores):
    return {
        "args_check_seed_line": {
            "in_line": f"{testdata_dir.joinpath('seed_lines.gpkg').as_posix()}|seed_lines",
            "out_line": f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|seed_lines_checked",
        },
        "args_vertex_optimization": {
            "in_line": f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|seed_lines_checked",
            "in_raster": testdata_dir.joinpath("chm.tif").as_posix(),
            "search_distance": 5.0,
            "line_radius": 15,
            "out_line": f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|seed_lines_vo",
        },
        "args_centerline": {
            "in_line": f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|seed_lines_vo",
            "in_raster": testdata_dir.joinpath("chm.tif").as_posix(),
            "line_radius": 15,
            "proc_segments": True,
            "out_line": f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|centerline",
        },
        "args_footprint_abs": {
            "in_line": f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|centerline",
            "in_chm": testdata_dir.joinpath("chm.tif").as_posix(),
            "corridor_thresh": 3.0,
            "max_ln_width": 32.0,
            "exp_shk_cell": 0,
            "out_footprint": f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|footprint_abs",
        },
        "args_footprint_exp": {
            "in_line": f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|centerline",
            "in_chm": testdata_dir.joinpath("chm.tif").as_posix(),
            "out_footprint": f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|footprint_exp",
            "max_ln_width": 32,
            "tree_radius": 1.5,
            "max_line_dist": 1.5,
            "canopy_avoidance": 0.0,
            "exponent": 0,
            "canopy_thresh_percentage": 50,
        },
        "args_ground_footprint": {
            "in_line": f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|centerline",
            "in_footprint": f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|footprint_abs",
            "n_samples": 15,
            "offset": 30,
            "max_width": True,
            "out_footprint": f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|footprint_ground",
        },
        "arg_main_canopy_threshold_relative": {
            'in_line':f"{testdata_dir.joinpath('workflow.gpkg').as_posix()}|centerline",
            'in_chm': testdata_dir.joinpath('chm.tif').as_posix(),
            'canopy_percentile': 90,
            'canopy_thresh_percentage': 50,
            'full_step': 'True',
            'processes': available_cpu_cores,
            'verbose': False,
            'out_DynCenterline': f"{testdata_dir.joinpath('DynCanTh_workflow.gpkg').as_posix()}|centerline",
        },
        "arg_main_line_footprint_relative": {
            'in_line': f"{testdata_dir.joinpath('DynCanTh_workflow.gpkg').as_posix()}|centerline",
            'in_chm': f"{testdata_dir.joinpath('chm.tif').as_posix()}",
            'max_ln_width': 32,
            'out_footprint': f"{testdata_dir.joinpath('footprint_rel.gpkg').as_posix()}|footprint_rel",
            'out_centerline': f"{testdata_dir.joinpath('smooth_centerline.gpkg').as_posix()}|smooth_centerline",
            'exp_shk_cell':5,
            'tree_radius': 1.5,
            'max_line_dist': 1.5,
            'canopy_avoidance': 1.0,
            'exponent': 1,
            'full_step': 'True',
            'canopy_thresh_percentage': 50,
            'processes': available_cpu_cores,
            'verbose': False,
            'debug_mode':False,
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
        testdata_dir.joinpath('line_percentile_rel.gpkg'),
        testdata_dir.joinpath('DynCanTh_centerline.gpkg'),
        testdata_dir.joinpath('DynCanTh_workflow.gpkg'),
        testdata_dir.joinpath('DynCanTh_integration_inter.gpkg'),
        testdata_dir.joinpath('DynCanTh_integration.gpkg'),
        testdata_dir.joinpath('smooth_centerline.gpkg'),
        testdata_dir.joinpath('smooth_centerline_poly.gpkg'),
        testdata_dir.joinpath("workflow.gpkg"),
        testdata_dir.joinpath("integration_inter.gpkg"),
        testdata_dir.joinpath("workflow_aux.gpkg"),
        testdata_dir.joinpath("integration_inter_aux.gpkg"),
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
