"""Test script for the tools in the beratools package."""
from pprint import pprint

from utils import check_file_exists

from beratools.core.algo_canopy_footprint_exp import line_footprint_exp
from beratools.core.canopy_threshold_relative import main_canopy_threshold_relative
from beratools.core.line_footprint_functions import main_line_footprint_relative
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

def test_footprint_exp_tool_e2e(tool_arguments):
    """E2E test for the FootprintCanopy tool."""
    args_footprint_exp = tool_arguments["args_footprint_exp"]
    pprint(args_footprint_exp)

    line_footprint_exp(**args_footprint_exp)

    assert check_file_exists(args_footprint_exp["out_footprint"]), (
        "Footprint Rel output file was not created!"
    )

def test_rel_footprint_tool_e2e(tool_arguments):
    args_centerline = tool_arguments["args_centerline"]
    pprint(args_centerline)

    # Call the actual centerline tool (no mocks)
    centerline(**args_centerline)
    assert check_file_exists(args_centerline["out_line"]), (
        "Centerline output file was not created!"
    )

    """E2E test for the main_canopy_threshold_relative tool."""
    if check_file_exists(args_centerline["out_line"]):
        arg_main_canopy_threshold_relative = tool_arguments["arg_main_canopy_threshold_relative"]
        arg_main_canopy_threshold_relative['in_line'] = args_centerline["out_line"]
        pprint(arg_main_canopy_threshold_relative)

        main_canopy_threshold_relative(**arg_main_canopy_threshold_relative)

        assert check_file_exists(arg_main_canopy_threshold_relative["out_DynCenterline"]), (
        "Dynamic Centerline output file was not created!"
        )
        if check_file_exists(arg_main_canopy_threshold_relative["out_DynCenterline"]):
            arg_main_line_footprint_relative = tool_arguments["arg_main_line_footprint_relative"]
            arg_main_line_footprint_relative['in_line'] = arg_main_canopy_threshold_relative["out_DynCenterline"]
            pprint(arg_main_line_footprint_relative)

            main_line_footprint_relative(**arg_main_line_footprint_relative)

            assert check_file_exists(arg_main_canopy_threshold_relative["out_DynCenterline"]), (
            "Dynamic FP output file was not created!"
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