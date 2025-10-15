"""Test script for the tools in the beratools package."""
import time

from utils import check_file_exists

from beratools.core.algo_footprint_rel import line_footprint_rel
from beratools.tools.centerline import centerline
from beratools.tools.line_footprint_absolute import line_footprint_abs
from beratools.tools.line_footprint_fixed import line_footprint_fixed


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
    
    # 2. Test the line_footprint_abs tool
    args_footprint_abs = tool_arguments["args_footprint_abs"]
    line_footprint_abs(**args_footprint_abs)
    assert check_file_exists(args_footprint_abs["out_footprint"]), (
        "Footprint Abs output file was not created!"
    )
    
    # 3. Test the line_footprint_rel tool
    args_footprint_rel = tool_arguments["args_footprint_rel"]
    line_footprint_rel(**args_footprint_rel)
    assert check_file_exists(args_footprint_rel["out_footprint"]), (
        "Footprint Rel output file was not created!"
    )
    
    # 4. Test the line_footprint_fixed tool
    args_line_footprint_fixed = tool_arguments["args_line_footprint_fixed"]
    line_footprint_fixed(**args_line_footprint_fixed)
    assert check_file_exists(args_line_footprint_fixed["out_footprint"]), (
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