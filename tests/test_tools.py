"""Test script for the tools in the beratools package."""
from pprint import pprint

from utils import check_file_exists

from beratools.core.algo_footprint_rel import line_footprint_rel
from beratools.tools.centerline import centerline
from beratools.tools.line_footprint_absolute import line_footprint_abs
from beratools.tools.line_footprint_fixed import line_footprint_fixed


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

def test_line_footprint_abs_tool_e2e(tool_arguments):
    """E2E test for the line_footprint_abs tool."""
    args_footprint_abs = tool_arguments["args_footprint_abs"]
    pprint(args_footprint_abs)
    line_footprint_abs(**args_footprint_abs)

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


def test_line_footprint_fixed_tool_e2e(tool_arguments):
    """E2E test for the line_footprint_fixed tool."""
    args_line_footprint_fixed = tool_arguments["args_line_footprint_fixed"]
    line_footprint_fixed(**args_line_footprint_fixed)
    pprint(args_line_footprint_fixed)

    assert check_file_exists(args_line_footprint_fixed["out_footprint"]), (
        "Line footprint fixed output file was not created!"
    )

# CLEANUP TESTS
# def test_cleanup_output_files(cleanup_output_files):
#     # Your test code goes here
#     # The cleanup will automatically run after the test finishes
#     pass