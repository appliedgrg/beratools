"""Test script for the tools in the beratools package."""

from pprint import pprint

from utils import check_file_exists

from beratools.core.canopy_threshold_relative import main_canopy_threshold_relative
from beratools.core.line_footprint_functions import main_line_footprint_relative
from beratools.tools.canopy_footprint_absolute import canopy_footprint_abs
from beratools.tools.canopy_footprint_exp import line_footprint_exp
from beratools.tools.centerline import centerline
from beratools.tools.check_seed_line import check_seed_line
from beratools.tools.ground_footprint import ground_footprint
from beratools.tools.vertex_optimization import vertex_optimization
from beratools.utility.spatial_common import decode_file_layer


# Integration TESTS
def test_check_seed_line_tool(tool_arguments_integration):
    """Test for the check_seed_line tool."""
    args_check_seed_line = tool_arguments_integration["args_check_seed_line"]
    pprint(args_check_seed_line)
    check_seed_line(**args_check_seed_line)
    out_file, layer = decode_file_layer(args_check_seed_line["out_line"])
    assert check_file_exists(out_file, layer), "Check Seed Line no output!"


def test_vertex_optimization_tool(tool_arguments_integration):
    """Test for the vertex_optimization tool."""
    args_vertex_optimization = tool_arguments_integration["args_vertex_optimization"]
    pprint(args_vertex_optimization)
    vertex_optimization(**args_vertex_optimization)
    out_file, layer = decode_file_layer(args_vertex_optimization["out_line"])
    assert check_file_exists(out_file, layer), "Vertex Optimization no output!"


def test_centerline_tool(tool_arguments_integration):
    """Test for the centerline tool."""
    args_centerline = tool_arguments_integration["args_centerline"]
    pprint(args_centerline)

    # Call the actual centerline tool (no mocks)
    centerline(**args_centerline)

    # Check if the output file is created
    in_file, layer = decode_file_layer(args_centerline["in_line"])
    assert check_file_exists(in_file, layer), "Centerline no output!"


def test_centerline_tool_candidate_mode(tool_arguments_integration):
    """Test centerline tool with candidate guided strategy."""
    args_centerline = tool_arguments_integration["args_centerline_candidate"]
    pprint(args_centerline)

    centerline(**args_centerline)

    out_file, layer = decode_file_layer(args_centerline["out_line"])
    assert check_file_exists(out_file, layer), "Centerline candidate mode no output!"


def test_canopy_footprint_abs_tool(tool_arguments_integration):
    """Test for the canopy_footprint_abs tool."""
    args_footprint_abs = tool_arguments_integration["args_footprint_abs"]
    pprint(args_footprint_abs)
    canopy_footprint_abs(**args_footprint_abs)

    out_file, layer = decode_file_layer(args_footprint_abs["out_footprint"])
    assert check_file_exists(out_file, layer), "Footprint Abs no output!"


def test_rel_footprint_tool(tool_arguments_integration):
    """Test for the main_canopy_threshold_relative tool."""
    arg_main_canopy_threshold_relative = tool_arguments_integration["arg_main_canopy_threshold_relative"]
    pprint(arg_main_canopy_threshold_relative)

    out_dyncl_file = main_canopy_threshold_relative(**arg_main_canopy_threshold_relative)
    out_file, layer = decode_file_layer(out_dyncl_file)
    assert check_file_exists(out_file, layer=layer), "Dynamic Centerline output file was not created!"

    arg_main_line_footprint_relative = tool_arguments_integration["arg_main_line_footprint_relative"]
    pprint(arg_main_line_footprint_relative)

    main_line_footprint_relative(**arg_main_line_footprint_relative)
    out_file, layer = decode_file_layer(arg_main_line_footprint_relative["out_footprint"])
    assert check_file_exists(out_file, layer=layer), "Dynamic FP output file was not created!"


def test_footprint_exp_tool(tool_arguments_integration):
    """Test for the FootprintCanopy tool."""
    args_footprint_exp = tool_arguments_integration["args_footprint_exp"]
    pprint(args_footprint_exp)

    line_footprint_exp(**args_footprint_exp)

    out_file, layer = decode_file_layer(args_footprint_exp["out_footprint"])
    assert check_file_exists(out_file, layer), "Footprint Rel no output!"


def test_ground_footprint_tool(tool_arguments_integration):
    """Test for the ground_footprint tool."""
    args_ground_footprint = tool_arguments_integration["args_ground_footprint"]
    ground_footprint(**args_ground_footprint)
    pprint(args_ground_footprint)

    out_file, layer = decode_file_layer(args_ground_footprint["out_footprint"])
    assert check_file_exists(out_file, layer), "Ground footprint no output!"


# CLEANUP TESTS
def test_cleanup_output_files(cleanup_output_files):
    # Your test code goes here
    # The cleanup will automatically run after the test finishes
    pass
