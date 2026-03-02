"""Test script for the tools in the beratools package."""

from utils import check_file_exists

from beratools.core.canopy_threshold_relative import main_canopy_threshold_relative
from beratools.core.line_footprint_functions import main_line_footprint_relative
from beratools.tools.canopy_footprint_absolute import canopy_footprint_abs
from beratools.tools.centerline import centerline
from beratools.tools.check_seed_line import check_seed_line
from beratools.tools.ground_footprint import ground_footprint
from beratools.tools.vertex_optimization import vertex_optimization
from beratools.utility.spatial_common import decode_file_layer


# E2E test for the entire workflow
def test_full_workflow(tool_arguments_workflow):
    """
    Full E2E test running the entire workflow.

    with real data, ensuring that each tool integrates properly with the next.
    """
    # 1. Test the check_seed_line tool
    args_check_seed_line = tool_arguments_workflow["args_check_seed_line"]
    check_seed_line(**args_check_seed_line)
    out_file, layer = decode_file_layer(args_check_seed_line["out_line"])
    assert check_file_exists(out_file, layer=layer), "Check Seed Line output file was not created!"

    # 2. Test the vertex_optimization tool
    args_vertex_optimization = tool_arguments_workflow["args_vertex_optimization"]
    vertex_optimization(**args_vertex_optimization)
    out_file, layer = decode_file_layer(args_vertex_optimization["out_line"])
    assert check_file_exists(out_file, layer=layer), "Vertex Optimization output file was not created!"

    # 3. Test the centerline tool
    args_centerline = tool_arguments_workflow["args_centerline"]
    centerline(**args_centerline)
    out_file, layer = decode_file_layer(args_centerline["out_line"])
    assert check_file_exists(out_file, layer=layer), "Centerline output file was not created!"

    # 4. Test the canopy_footprint_abs tool
    args_footprint_abs = tool_arguments_workflow["args_footprint_abs"]
    canopy_footprint_abs(**args_footprint_abs)
    out_file, layer = decode_file_layer(args_footprint_abs["out_footprint"])
    assert check_file_exists(out_file, layer=layer), "Footprint Abs output file was not created!"

    # 5. Test the line_footprint_rel tool
    arg_main_canopy_threshold_relative = tool_arguments_workflow["arg_main_canopy_threshold_relative"]
    main_canopy_threshold_relative(**arg_main_canopy_threshold_relative)
    out_file, layer = decode_file_layer(arg_main_canopy_threshold_relative["out_dyn_centerline"])
    assert check_file_exists(out_file, layer=layer), "Dynamic Centerline output file was not created!"

    arg_main_line_footprint_relative = tool_arguments_workflow["arg_main_line_footprint_relative"]

    main_line_footprint_relative(**arg_main_line_footprint_relative)
    out_file, layer = decode_file_layer(arg_main_line_footprint_relative["out_footprint"])
    assert check_file_exists(out_file, layer=layer), "Dynamic FP output file was not created!"

    # 6. Test adaptive mode through canopy_footprint_abs tool
    args_footprint_exp = tool_arguments_workflow["args_footprint_exp"]
    args_footprint_exp["footprint_mode"] = "adaptive"
    canopy_footprint_abs(**args_footprint_exp)
    out_file, layer = decode_file_layer(args_footprint_exp["out_footprint"])
    assert check_file_exists(out_file, layer=layer), "Footprint exp output file was not created!"

    # 7. Test the ground_footprint tool
    args_ground_footprint = tool_arguments_workflow["args_ground_footprint"]
    ground_footprint(**args_ground_footprint)
    out_file, layer = decode_file_layer(args_ground_footprint["out_footprint"])
    assert check_file_exists(out_file, layer=layer), "Line footprint fixed output file was not created!"


# CLEANUP TESTS
def test_cleanup_output_files(cleanup_output_files):
    # Your test code goes here
    # The cleanup will automatically run after the test finishes
    pass
