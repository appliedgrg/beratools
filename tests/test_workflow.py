"""Test script for the tools in the beratools package."""
import time

from utils import check_file_exists

from beratools.core.algo_canopy_footprint_exp import line_footprint_exp
from beratools.core.canopy_threshold_relative import main_canopy_threshold_relative
from beratools.core.line_footprint_functions import main_line_footprint_relative
from beratools.tools.canopy_footprint_absolute import canopy_footprint_abs
from beratools.tools.centerline import centerline
from beratools.tools.ground_footprint import ground_footprint


# Integration test for the entire workflow
def test_full_workflow(tool_arguments):
    """
    Full integration test (actually an E2E test) running the entire workflow.

    with real data, ensuring that each tool integrates properly with the next.
    """
    # 1. Test the centerline tool
    args_centerline = tool_arguments["args_centerline"]
    centerline(**args_centerline)
    assert check_file_exists(args_centerline["out_line"]), (
        "Centerline output file was not created!"
    )
    
    # 2. Test the canopy_footprint_abs tool
    args_footprint_abs = tool_arguments["args_footprint_abs"]
    canopy_footprint_abs(**args_footprint_abs)
    assert check_file_exists(args_footprint_abs["out_footprint"]), (
        "Footprint Abs output file was not created!"
    )
    
    # 3. Test the line_footprint_rel tool

    if check_file_exists(args_centerline["out_line"]):
        arg_main_canopy_threshold_relative = tool_arguments["arg_main_canopy_threshold_relative"]
        arg_main_canopy_threshold_relative['in_line'] = args_centerline["out_line"]

        main_canopy_threshold_relative(**arg_main_canopy_threshold_relative)

        assert check_file_exists(arg_main_canopy_threshold_relative["out_DynCenterline"]), (
            "Dynamic Centerline output file was not created!"
        )
        if check_file_exists(arg_main_canopy_threshold_relative["out_DynCenterline"]):
            arg_main_line_footprint_relative = tool_arguments["arg_main_line_footprint_relative"]
            arg_main_line_footprint_relative['in_line'] = arg_main_canopy_threshold_relative["out_DynCenterline"]

            main_line_footprint_relative(**arg_main_line_footprint_relative)

            assert check_file_exists(arg_main_canopy_threshold_relative["out_DynCenterline"]), (
                "Dynamic FP output file was not created!"
            )
    # args_footprint_exp = tool_arguments["args_footprint_exp"]
    # line_footprint_exp(**args_footprint_exp)
    # assert check_file_exists(args_footprint_exp["out_footprint"]), (
    #     "Footprint Rel output file was not created!"
    # )
    
    # 4. Test the ground_footprint tool
    args_ground_footprint = tool_arguments["args_ground_footprint"]
    ground_footprint(**args_ground_footprint)
    assert check_file_exists(args_ground_footprint["out_footprint"]), (
        "Line footprint fixed output file was not created!"
    )

# clean up files for workflow
def test_cleanup_output_files_workflow(test_output_files):
    """Test to clean up generated output files after the test."""
    time.sleep(1)  # Wait a little to allow file system operations to complete
    for file_path in test_output_files:
        if file_path.exists():
            file_path.unlink()
            assert not file_path.exists(), f"Failed to remove {file_path}"

# CLEANUP TESTS
def test_cleanup_output_files(cleanup_output_files):
    # Your test code goes here
    # The cleanup will automatically run after the test finishes
    pass