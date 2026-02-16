"""
Per-tool form fill and round-trip tests using pytest-qt.

For each tool: construct ToolWidgets, set all parameter values
programmatically, call get_widgets_arguments(), and verify the
returned dict matches expected values.
"""

from unittest.mock import patch

import pytest

from beratools.gui.tool_widgets import (
    BooleanInput,
    FileSelector,
    NumericInput,
    OptionsInput,
)

pytestmark = pytest.mark.gui_qt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_widget_values(tw, values):
    """Set values on ToolWidgets by variable name."""
    for widget in tw.widget_list:
        if widget.variable in values:
            widget.set_value(values[widget.variable])


def _find_widget(tw, variable):
    """Find a widget by its variable name."""
    for w in tw.widget_list:
        if w.variable == variable:
            return w
    return None


# ---------------------------------------------------------------------------
# Check Seed Lines
# ---------------------------------------------------------------------------


class TestCheckSeedLines:
    TOOL = "Check Seed Lines"

    def test_widget_types(self, make_tool_widget, btdata):
        tw = make_tool_widget(self.TOOL)
        expected = len(btdata.get_bera_tool_args(self.TOOL))
        assert len(tw.widget_list) == expected
        assert isinstance(_find_widget(tw, "in_line"), FileSelector)
        assert isinstance(_find_widget(tw, "in_raster"), FileSelector)
        assert isinstance(_find_widget(tw, "out_line"), FileSelector)
        assert isinstance(_find_widget(tw, "remove_short_lines"), BooleanInput)
        assert isinstance(_find_widget(tw, "snap_close_endpoints"), BooleanInput)
        assert isinstance(_find_widget(tw, "group_lines"), BooleanInput)
        assert isinstance(_find_widget(tw, "merge_by_group"), BooleanInput)
        assert isinstance(_find_widget(tw, "densify_long_lines"), BooleanInput)
        assert isinstance(_find_widget(tw, "chm_footprint_shrink"), NumericInput)
        assert isinstance(_find_widget(tw, "minimum_line_length"), NumericInput)
        assert isinstance(_find_widget(tw, "snap_tolerance"), NumericInput)
        assert isinstance(_find_widget(tw, "max_segment_length"), NumericInput)

    def test_round_trip(self, make_tool_widget, testdata_dir, tmp_path):
        tw = make_tool_widget(self.TOOL)
        in_path = str(testdata_dir / "seed_lines_aoi.gpkg")
        out_path = str(tmp_path / "output.gpkg")

        _set_widget_values(
            tw,
            {
                "in_line": {"path": in_path, "layer": "seed_lines"},
                "in_raster": str(testdata_dir / "chm_aoi.tif"),
                "chm_footprint_shrink": 15.0,
                "out_line": {"path": out_path, "layer": "checked"},
                "remove_short_lines": True,
                "minimum_line_length": 5.0,
                "snap_close_endpoints": True,
                "snap_tolerance": 5.0,
                "group_lines": True,
                "merge_by_group": False,
                "densify_long_lines": False,
                "max_segment_length": 500.0,
            },
        )

        args = tw.get_widgets_arguments()
        assert args is not None
        assert args["in_line"].startswith(f"{in_path}|")
        assert args["in_raster"].endswith("chm_aoi.tif")
        assert args["chm_footprint_shrink"] == pytest.approx(15.0)
        assert args["out_line"].startswith(f"{out_path}|")
        assert args["remove_short_lines"] is True
        assert args["minimum_line_length"] == pytest.approx(5.0)
        assert args["snap_close_endpoints"] is True
        assert args["snap_tolerance"] == pytest.approx(5.0)
        assert args["group_lines"] is True
        assert args["merge_by_group"] is False
        assert args["densify_long_lines"] is False
        assert args["max_segment_length"] == pytest.approx(500.0)

    def test_initial_form_hides_shrink_when_advanced_off(self, make_tool_widget):
        tw = make_tool_widget(self.TOOL, show_advanced=False)
        shrink = _find_widget(tw, "chm_footprint_shrink")
        assert shrink is not None
        assert shrink.isHidden()

    def test_advanced_form_shows_shrink_parameter(self, make_tool_widget):
        tw = make_tool_widget(self.TOOL, show_advanced=True)
        shrink = _find_widget(tw, "chm_footprint_shrink")
        assert shrink is not None
        assert not shrink.isHidden()


# ---------------------------------------------------------------------------
# Vertex Optimization
# ---------------------------------------------------------------------------


class TestVertexOptimization:
    TOOL = "Vertex Optimization"

    def test_widget_types(self, make_tool_widget):
        tw = make_tool_widget(self.TOOL)
        types = [type(w).__name__ for w in tw.widget_list]
        assert "FileSelector" in types
        assert "NumericInput" in types

    def test_round_trip(self, make_tool_widget, testdata_dir, tmp_path):
        tw = make_tool_widget(self.TOOL)
        _set_widget_values(
            tw,
            {
                "in_line": {"path": str(testdata_dir / "seed_lines_aoi.gpkg"), "layer": "seed_lines"},
                "in_raster": str(testdata_dir / "chm_aoi.tif"),
                "search_distance": 5.0,
                "line_radius": 15,
                "out_line": {"path": str(tmp_path / "out.gpkg"), "layer": "vo"},
            },
        )

        args = tw.get_widgets_arguments()
        assert args is not None
        assert args["search_distance"] == pytest.approx(5.0)
        assert args["line_radius"] == 15


# ---------------------------------------------------------------------------
# Centerline
# ---------------------------------------------------------------------------


class TestCenterline:
    TOOL = "Centerline"

    def test_has_boolean_widget(self, make_tool_widget):
        tw = make_tool_widget(self.TOOL)
        proc_seg = _find_widget(tw, "proc_segments")
        assert proc_seg is not None
        assert isinstance(proc_seg, BooleanInput)

    def test_round_trip(self, make_tool_widget, testdata_dir, tmp_path):
        tw = make_tool_widget(self.TOOL)
        _set_widget_values(
            tw,
            {
                "in_line": {"path": str(testdata_dir / "seed_lines_aoi.gpkg"), "layer": "seed_lines"},
                "in_raster": str(testdata_dir / "chm_aoi.tif"),
                "line_radius": 15.0,
                "proc_segments": False,
                "out_line": {"path": str(tmp_path / "out.gpkg"), "layer": "cl"},
            },
        )

        args = tw.get_widgets_arguments()
        assert args is not None
        assert args["proc_segments"] is False

    def test_toggle_proc_segments(self, make_tool_widget):
        tw = make_tool_widget(self.TOOL)
        w = _find_widget(tw, "proc_segments")
        w.set_value(True)
        assert w.get_value() == {"proc_segments": True}
        w.set_value(False)
        assert w.get_value() == {"proc_segments": False}


# ---------------------------------------------------------------------------
# Canopy Footprint (Absolute Threshold)
# ---------------------------------------------------------------------------


class TestCanopyFootprintAbsolute:
    TOOL = "Canopy Footprint (Absolute Threshold)"

    def test_widget_count(self, make_tool_widget, btdata):
        tw = make_tool_widget(self.TOOL)
        expected = len(btdata.get_bera_tool_args(self.TOOL))
        assert len(tw.widget_list) == expected

    def test_numeric_values(self, make_tool_widget):
        tw = make_tool_widget(self.TOOL)

        corridor = _find_widget(tw, "corridor_thresh")
        assert corridor is not None
        corridor.set_value(5.0)
        assert corridor.get_value()["corridor_thresh"] == pytest.approx(5.0)

        max_w = _find_widget(tw, "max_ln_width")
        assert max_w is not None
        max_w.set_value(40.0)
        assert max_w.get_value()["max_ln_width"] == pytest.approx(40.0)

        exp_shk = _find_widget(tw, "exp_shk_cell")
        assert exp_shk is not None
        exp_shk.set_value(2)
        assert exp_shk.get_value()["exp_shk_cell"] == 2


# ---------------------------------------------------------------------------
# Canopy Footprint (Relative Threshold)
# ---------------------------------------------------------------------------


class TestCanopyFootprintRelative:
    TOOL = "Canopy Footprint (Relative Threshold)"

    def test_has_options_input(self, make_tool_widget):
        tw = make_tool_widget(self.TOOL)
        cp = _find_widget(tw, "canopy_percentile")
        assert cp is not None
        assert isinstance(cp, OptionsInput)

    def test_canopy_percentile_options(self, make_tool_widget):
        tw = make_tool_widget(self.TOOL)
        cp = _find_widget(tw, "canopy_percentile")
        assert cp.combobox.count() == 10
        cp.set_value("75")
        assert cp.combobox.currentText() == "75"

    def test_round_trip(self, make_tool_widget, testdata_dir, tmp_path):
        tw = make_tool_widget(self.TOOL)
        _set_widget_values(
            tw,
            {
                "in_line": {"path": str(testdata_dir / "integration_aoi.gpkg"), "layer": "centerline"},
                "in_chm": str(testdata_dir / "chm_aoi.tif"),
                "max_ln_width": 32.0,
                "exp_shk_cell": 0,
                "out_footprint": {"path": str(tmp_path / "out.gpkg"), "layer": "fp"},
                "out_centerline": {"path": str(tmp_path / "out.gpkg"), "layer": "cl2"},
                "off_ln_dist": 10.0,
                "canopy_percentile": "90",
                "canopy_thresh_percentage": 50.0,
                "tree_radius": 1.5,
                "max_line_dist": 1.5,
                "canopy_avoidance": 0.0,
                "exponent": 1,
            },
        )

        args = tw.get_widgets_arguments()
        assert args is not None
        assert args["canopy_percentile"] == "90"
        assert args["tree_radius"] == pytest.approx(1.5)
        assert args["exponent"] == 1


# ---------------------------------------------------------------------------
# Ground Footprint
# ---------------------------------------------------------------------------


class TestGroundFootprint:
    TOOL = "Ground Footprint"

    def test_has_boolean_max_width(self, make_tool_widget):
        tw = make_tool_widget(self.TOOL)
        mw = _find_widget(tw, "max_width")
        assert mw is not None
        assert isinstance(mw, BooleanInput)

    def test_round_trip(self, make_tool_widget, testdata_dir, tmp_path):
        tw = make_tool_widget(self.TOOL)
        _set_widget_values(
            tw,
            {
                "in_line": {"path": str(testdata_dir / "integration_aoi.gpkg"), "layer": "centerline"},
                "in_footprint": {
                    "path": str(testdata_dir / "integration_aoi.gpkg"),
                    "layer": "footprint_rel",
                },
                "n_samples": 15,
                "offset": 30.0,
                "max_width": False,
                "out_footprint": {"path": str(tmp_path / "out.gpkg"), "layer": "gfp"},
            },
        )

        args = tw.get_widgets_arguments()
        assert args is not None
        assert args["max_width"] is False
        assert args["n_samples"] == 15
        assert args["offset"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Feature Buffer
# ---------------------------------------------------------------------------


class TestFeatureBuffer:
    TOOL = "Feature Buffer"

    def test_widget_count(self, make_tool_widget):
        tw = make_tool_widget(self.TOOL)
        assert len(tw.widget_list) == 3

    def test_round_trip(self, make_tool_widget, testdata_dir, tmp_path):
        tw = make_tool_widget(self.TOOL)
        _set_widget_values(
            tw,
            {
                "in_feature": {"path": str(testdata_dir / "seed_lines_aoi.gpkg"), "layer": "seed_lines"},
                "buffer_dist": 25.0,
                "out_feature": {"path": str(tmp_path / "out.gpkg"), "layer": "buf"},
            },
        )

        args = tw.get_widgets_arguments()
        assert args is not None
        assert args["buffer_dist"] == pytest.approx(25.0)
        assert str(testdata_dir / "seed_lines_aoi.gpkg") in args["in_feature"]


# ---------------------------------------------------------------------------
# Cross-tool: get_widgets_arguments with missing required params
# ---------------------------------------------------------------------------


class TestMissingParams:
    def test_defaults_provide_initial_arguments(self, make_tool_widget):
        tw = make_tool_widget("Check Seed Lines")
        args = tw.get_widgets_arguments()
        assert args is not None
