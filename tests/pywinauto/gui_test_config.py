"""
GUI test configuration: test data paths and tool parameter values.

All file paths point to existing test data in tests/data/.
Output files go to a temporary directory created per test session.
"""

from pathlib import Path

TESTDATA_DIR = Path(__file__).resolve().parents[1] / "data"


def make_test_data(testdata_dir, output_dir):
    """Build TEST_DATA dict with resolved paths.

    Args:
        testdata_dir: Path to tests/data/ with existing .gpkg and .tif files.
        output_dir: Path to a temporary output directory for test results.
    """
    return {
        "Check Seed Lines": {
            "in_line": {
                "path": str(testdata_dir / "integration_aoi.gpkg"),
                "layer": "seed_lines_checked",
            },
            "in_raster": {
                "path": str(testdata_dir / "chm_aoi.tif"),
            },
            "chm_footprint_shrink": 15.0,
            "clip_to_chm_footprint": True,
            "out_line": {
                "path": str(output_dir / "gui_test_output.gpkg"),
                "layer": "seed_lines_checked",
            },
            "remove_short_lines": False,
            "minimum_line_length": 5.0,
            "snap_close_endpoints": False,
            "snap_tolerance": 5.0,
            "group_lines": False,
            "merge_by_group": False,
            "densify_long_lines": False,
            "max_segment_length": 500.0,
        },
        "Vertex Optimization": {
            "in_line": {
                "path": str(testdata_dir / "integration_aoi.gpkg"),
                "layer": "seed_lines_checked",
            },
            "in_raster": {
                "path": str(testdata_dir / "chm_aoi.tif"),
            },
            "search_distance": 5.0,
            "line_radius": 15,
            "out_line": {
                "path": str(output_dir / "gui_test_output.gpkg"),
                "layer": "seed_lines_vo",
            },
        },
        "Centerline": {
            "in_line": {
                "path": str(testdata_dir / "integration_aoi.gpkg"),
                "layer": "seed_lines_checked",
            },
            "in_raster": {
                "path": str(testdata_dir / "chm_aoi.tif"),
            },
            "line_radius": 15.0,
            "proc_segments": True,
            "out_line": {
                "path": str(output_dir / "gui_test_output.gpkg"),
                "layer": "centerline",
            },
        },
        "Canopy Footprint (Absolute Threshold)": {
            "in_line": {
                "path": str(testdata_dir / "integration_aoi.gpkg"),
                "layer": "centerline",
            },
            "in_chm": {
                "path": str(testdata_dir / "chm_aoi.tif"),
            },
            "corridor_thresh": 3.0,
            "max_ln_width": 32.0,
            "exp_shk_cell": 0,
            "out_footprint": {
                "path": str(output_dir / "gui_test_output.gpkg"),
                "layer": "footprint_abs",
            },
        },
        "Canopy Footprint (Relative Threshold)": {
            "in_line": {
                "path": str(testdata_dir / "integration_aoi.gpkg"),
                "layer": "centerline",
            },
            "in_chm": {
                "path": str(testdata_dir / "chm_aoi.tif"),
            },
            "max_ln_width": 32.0,
            "exp_shk_cell": 0,
            "out_footprint": {
                "path": str(output_dir / "gui_test_output.gpkg"),
                "layer": "footprint_rel",
            },
            "out_centerline": {
                "path": str(output_dir / "gui_test_output.gpkg"),
                "layer": "smooth_centerline",
            },
            "off_ln_dist": 10.0,
            "canopy_percentile": 90,
            "canopy_thresh_percentage": 50.0,
            "tree_radius": 1.5,
            "max_line_dist": 1.5,
            "canopy_avoidance": 0.0,
            "exponent": 1,
        },
        "Ground Footprint": {
            "in_line": {
                "path": str(testdata_dir / "integration_aoi.gpkg"),
                "layer": "centerline",
            },
            "in_footprint": {
                "path": str(testdata_dir / "integration_aoi.gpkg"),
                "layer": "footprint_exp",
            },
            "n_samples": 15,
            "offset": 30.0,
            "max_width": True,
            "out_footprint": {
                "path": str(output_dir / "gui_test_output.gpkg"),
                "layer": "footprint_ground",
            },
        },
        "Feature Buffer": {
            "in_feature": {
                "path": str(testdata_dir / "integration_aoi.gpkg"),
                "layer": "seed_lines_checked",
            },
            "buffer_dist": 10.0,
            "out_feature": {
                "path": str(output_dir / "gui_test_output.gpkg"),
                "layer": "buffered",
            },
        },
    }


# Parameter type lookup from beratools.json (variable -> type info)
PARAM_TYPES = {
    # Check Seed Lines
    "in_line": {"type": "file", "subtype": "vector"},
    "in_raster": {"type": "file", "subtype": "raster"},
    "chm_footprint_shrink": {"type": "number", "subtype": "float"},
    "clip_to_chm_footprint": {"type": "list", "subtype": "bool"},
    "out_line": {"type": "file", "subtype": "vector"},
    "remove_short_lines": {"type": "list", "subtype": "bool"},
    "minimum_line_length": {"type": "number", "subtype": "float"},
    "snap_close_endpoints": {"type": "list", "subtype": "bool"},
    "snap_tolerance": {"type": "number", "subtype": "float"},
    "group_lines": {"type": "list", "subtype": "bool"},
    "merge_by_group": {"type": "list", "subtype": "bool"},
    "densify_long_lines": {"type": "list", "subtype": "bool"},
    "max_segment_length": {"type": "number", "subtype": "float"},
    # Vertex Optimization
    "search_distance": {"type": "number", "subtype": "float"},
    "line_radius": {"type": "number", "subtype": "int"},
    "optimize_internal_vertices": {"type": "list", "subtype": "bool"},
    # Centerline
    "proc_segments": {"type": "list", "subtype": "bool"},
    # Canopy Footprint (Absolute)
    "in_chm": {"type": "file", "subtype": "raster"},
    "corridor_thresh": {"type": "number", "subtype": "float"},
    "max_ln_width": {"type": "number", "subtype": "float"},
    "exp_shk_cell": {"type": "number", "subtype": "int"},
    "out_footprint": {"type": "file", "subtype": "vector"},
    # Canopy Footprint (Relative)
    "out_centerline": {"type": "file", "subtype": "vector"},
    "off_ln_dist": {"type": "number", "subtype": "float"},
    "canopy_percentile": {"type": "list", "subtype": "int"},
    "canopy_thresh_percentage": {"type": "number", "subtype": "float"},
    "tree_radius": {"type": "number", "subtype": "float"},
    "max_line_dist": {"type": "number", "subtype": "float"},
    "canopy_avoidance": {"type": "number", "subtype": "float"},
    "exponent": {"type": "number", "subtype": "int"},
    # Ground Footprint
    "in_footprint": {"type": "file", "subtype": "vector"},
    "n_samples": {"type": "number", "subtype": "int"},
    "offset": {"type": "number", "subtype": "float"},
    "max_width": {"type": "list", "subtype": "bool"},
    # Feature Buffer
    "in_feature": {"type": "file", "subtype": "vector"},
    "buffer_dist": {"type": "number", "subtype": "float"},
    "out_feature": {"type": "file", "subtype": "vector"},
}


# Tool-specific parameter labels from beratools.json
TOOL_PARAM_LABELS = {
    "Check Seed Lines": {
        "in_line": "Seed Line",
        "in_raster": "CHM Raster",
        "chm_footprint_shrink": "CHM footprint shrink (m)",
        "clip_to_chm_footprint": "Clip to CHM footprint",
        "out_line": "Output Seed Line",
        "remove_short_lines": "Remove short lines",
        "minimum_line_length": "Minimum line length (m)",
        "snap_close_endpoints": "Snap close endpoints",
        "snap_tolerance": "Snap tolerance (m)",
        "group_lines": "Group lines",
        "merge_by_group": "Merge by group",
        "densify_long_lines": "Densify long lines",
        "max_segment_length": "Max segment length (m)",
    },
    "Vertex Optimization": {
        "in_line": "Input Line",
        "in_raster": "CHM Raster",
        "search_distance": "Vertex searching distance (m)",
        "line_radius": "Line Processing Radius",
        "optimize_internal_vertices": "Optimize Internal Vertices",
        "out_line": "Optimized Line",
    },
    "Centerline": {
        "in_line": "Seed Line",
        "in_raster": "CHM Raster",
        "line_radius": "Line Processing Radius",
        "proc_segments": "Process Segments",
        "out_line": "Output Centerline",
    },
    "Canopy Footprint (Absolute Threshold)": {
        "in_line": "Centerline",
        "in_chm": "CHM Raster",
        "corridor_thresh": "Corridor Threshold",
        "max_ln_width": "Maximum Line Width",
        "exp_shk_cell": "Expand And Shrink Cell Range",
        "out_footprint": "Output Footprint",
    },
    "Canopy Footprint (Relative Threshold)": {
        "in_line": "Centerline",
        "in_chm": "CHM Raster",
        "max_ln_width": "Maximum Line Width",
        "exp_shk_cell": "Expand And Shrink Cell Range",
        "out_footprint": "Output Footprint",
        "out_centerline": "Output Centerline",
        "off_ln_dist": "Offset Line Distance",
        "canopy_percentile": "Canopy Percentile",
        "canopy_thresh_percentage": "Canopy Threshold Percentage",
        "tree_radius": "Tree Search Radius",
        "max_line_dist": "Maximum Line Distance",
        "canopy_avoidance": "Canopy Avoidance",
        "exponent": "Cost Raster Exponent",
    },
    "Ground Footprint": {
        "in_line": "Centerline",
        "in_footprint": "Input Footprint",
        "n_samples": "Sampling number",
        "offset": "Perpendicular line length",
        "max_width": "Use maximum width",
        "out_footprint": "Output Ground Footprint",
    },
    "Feature Buffer": {
        "in_feature": "Input Feature Class",
        "buffer_dist": "Buffer Distance (m)",
        "out_feature": "Output Buffered Features",
    },
}
