"""Test script for the tools in the beratools package."""
from pprint import pprint

from utils import check_file_exists

from beratools.core.algo_canopy_footprint_exp import line_footprint_rel
from beratools.tools.canopy_footprint_absolute import canopy_footprint_abs
from beratools.tools.centerline import centerline
from beratools.tools.ground_footprint import ground_footprint


# E2E TESTS
def test_centerline_tool_e2e(tool_arguments):
    """E2E test for the centerline tool."""
    args_centerline = tool_arguments["args_centerline"]
    pprint(args_centerline)

    # Call the actual centerline tool (no mocks)
    centerline(**args_centerline)

    # Check if the output file is created
    assert check_file_exists(args_centerline["out_line"]), (
        "Centerline output file was not created!"
    )

def test_canopy_footprint_abs_tool_e2e(tool_arguments):
    """E2E test for the canopy_footprint_abs tool."""
    args_footprint_abs = tool_arguments["args_footprint_abs"]
    pprint(args_footprint_abs)
    canopy_footprint_abs(**args_footprint_abs)

    assert check_file_exists(args_footprint_abs["out_footprint"]), (
        "Footprint Abs output file was not created!"
    )

def test_footprint_rel_tool_e2e(tool_arguments):
    """E2E test for the FootprintCanopy tool."""
    args_footprint_rel = tool_arguments["args_footprint_rel"]
    pprint(args_footprint_rel)

    line_footprint_rel(**args_footprint_rel)

    assert check_file_exists(args_footprint_rel["out_footprint"]), (
        "Footprint Rel output file was not created!"
    )


def test_ground_footprint_tool_e2e(tool_arguments):
    """E2E test for the ground_footprint tool."""
    args_ground_footprint = tool_arguments["args_ground_footprint"]
    ground_footprint(**args_ground_footprint)
    pprint(args_ground_footprint)

    assert check_file_exists(args_ground_footprint["out_footprint"]), (
        "Line footprint fixed output file was not created!"
    )

# CLEANUP TESTS
def test_cleanup_output_files(cleanup_output_files):
    # Your test code goes here
    # The cleanup will automatically run after the test finishes
    pass