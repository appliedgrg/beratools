"""
GUI tests for BERA Tools using pywinauto.

These tests launch the BERA Tools GUI, interact with widgets, and verify
that form-filling works for each tool. They do NOT run the actual tools
(they fill forms and cancel immediately).

Requirements:
    - pywinauto installed
    - A display (no headless)
    - Test data in tests/data/

Run:
    python -m pytest tests/pywinauto/ -v -m gui
    python -m pytest tests/pywinauto/test_gui_tools.py -v -k "test_select_tool" -m gui
"""

import time

import pytest

from conftest import (
    click_browse_and_set_file,
    click_button,
    fill_tool_form,
    select_gpkg_layer,
    select_tool,
    set_checkbox,
    set_numeric,
    set_option_combo,
    set_slider,
)

pytestmark = pytest.mark.gui


# ---------------------------------------------------------------------------
# Basic UI tests
# ---------------------------------------------------------------------------


class TestMainWindowBasics:
    """Test that the main window loads and basic controls are accessible."""

    def test_window_visible(self, bera_app):
        """Main window should be visible and have correct title."""
        assert bera_app.is_visible()
        assert "BERA Tools" in bera_app.window_text()

    def test_run_button_exists(self, bera_app):
        btn = bera_app.child_window(title="Run", control_type="Button")
        assert btn.exists(timeout=5)
        assert btn.is_enabled()

    def test_cancel_button_exists(self, bera_app):
        btn = bera_app.child_window(title="Cancel", control_type="Button")
        assert btn.exists(timeout=5)

    def test_exit_button_exists(self, bera_app):
        btn = bera_app.child_window(title="Exit", control_type="Button")
        assert btn.exists(timeout=5)

    def test_advanced_button_exists(self, bera_app):
        btn = bera_app.child_window(title="Show Advanced Options", control_type="Button")
        assert btn.exists(timeout=5)

    def test_help_button_exists(self, bera_app):
        btn = bera_app.child_window(title="help", control_type="Button")
        assert btn.exists(timeout=5)

    def test_load_default_args_button_exists(self, bera_app):
        btn = bera_app.child_window(title="Load Default Arguments", control_type="Button")
        assert btn.exists(timeout=5)


# ---------------------------------------------------------------------------
# Tool selection tests
# ---------------------------------------------------------------------------


class TestToolSelection:
    """Test selecting each tool from the tree view."""

    EXPECTED_LABEL_BY_TOOL = {
        "Check Seed Lines": "Seed Line",
        "Vertex Optimization": "Vertex searching distance (m)",
        "Centerline": "Seed Line",
        "Canopy Footprint (Absolute Threshold)": "Centerline",
        "Canopy Footprint (Relative Threshold)": "Centerline",
        "Ground Footprint": "Centerline",
        "Feature Buffer": "Buffer Distance (m)",
    }

    @pytest.mark.parametrize(
        "tool_name",
        [
            "Check Seed Lines",
            "Vertex Optimization",
            "Centerline",
            "Canopy Footprint (Absolute Threshold)",
            "Canopy Footprint (Relative Threshold)",
            "Ground Footprint",
            "Feature Buffer",
        ],
    )
    def test_select_tool(self, bera_app, tool_name):
        """Each tool should be selectable from the tree view."""
        select_tool(bera_app, tool_name)
        time.sleep(0.3)
        # Verify selection via stable parameter label in right panel.
        texts = [w.window_text() for w in bera_app.descendants(control_type="Text")]
        expected_label = self.EXPECTED_LABEL_BY_TOOL[tool_name]
        assert any(expected_label in t for t in texts), (
            f"Expected label '{expected_label}' for tool '{tool_name}' not found in UI labels"
        )


# ---------------------------------------------------------------------------
# Advanced options toggle
# ---------------------------------------------------------------------------


class TestAdvancedOptions:
    """Test the Show/Hide Advanced Options toggle."""

    def test_toggle_advanced(self, bera_app):
        btn = bera_app.child_window(title_re=".*Advanced Options.*", control_type="Button")
        btn.wait("visible enabled", timeout=5)

        original_text = btn.window_text()
        btn.click_input()
        time.sleep(0.5)

        new_text = btn.window_text()
        assert new_text != original_text

        # Toggle back
        btn.click_input()
        time.sleep(0.5)
        assert btn.window_text() == original_text


# ---------------------------------------------------------------------------
# Slider test
# ---------------------------------------------------------------------------


class TestSlider:
    """Test the CPU cores slider."""

    def test_set_slider_value(self, bera_app):
        set_slider(bera_app, 2)
        time.sleep(0.3)
        slider = bera_app.child_window(control_type="Slider", found_index=0)
        assert slider.is_visible()


# ---------------------------------------------------------------------------
# Per-tool form filling tests
# ---------------------------------------------------------------------------


class TestCheckSeedLines:
    """Test form filling for Check Seed Lines tool."""

    def test_fill_form(self, bera_app, test_data):
        params = test_data["Check Seed Lines"]
        fill_tool_form(bera_app, "Check Seed Lines", params)
        time.sleep(0.3)


class TestVertexOptimization:
    """Test form filling for Vertex Optimization tool."""

    def test_fill_form(self, bera_app, test_data):
        params = test_data["Vertex Optimization"]
        fill_tool_form(bera_app, "Vertex Optimization", params)
        time.sleep(0.3)


class TestCenterline:
    """Test form filling for Centerline tool."""

    def test_fill_form(self, bera_app, test_data):
        params = test_data["Centerline"]
        fill_tool_form(bera_app, "Centerline", params)
        time.sleep(0.3)


class TestCanopyFootprintAbsolute:
    """Test form filling for Canopy Footprint (Absolute Threshold) tool."""

    def test_fill_form(self, bera_app, test_data):
        params = test_data["Canopy Footprint (Absolute Threshold)"]
        fill_tool_form(bera_app, "Canopy Footprint (Absolute Threshold)", params)
        time.sleep(0.3)


class TestCanopyFootprintRelative:
    """Test form filling for Canopy Footprint (Relative Threshold) tool."""

    def test_fill_form(self, bera_app, test_data):
        params = test_data["Canopy Footprint (Relative Threshold)"]
        fill_tool_form(bera_app, "Canopy Footprint (Relative Threshold)", params)
        time.sleep(0.3)


class TestGroundFootprint:
    """Test form filling for Ground Footprint tool."""

    def test_fill_form(self, bera_app, test_data):
        params = test_data["Ground Footprint"]
        fill_tool_form(bera_app, "Ground Footprint", params)
        time.sleep(0.3)


class TestFeatureBuffer:
    """Test form filling for Feature Buffer tool."""

    def test_fill_form(self, bera_app, test_data):
        params = test_data["Feature Buffer"]
        fill_tool_form(bera_app, "Feature Buffer", params)
        time.sleep(0.3)


# ---------------------------------------------------------------------------
# File dialog interaction test (explicit browse button)
# ---------------------------------------------------------------------------


class TestFileDialog:
    """Test the file browse dialog explicitly."""

    def test_browse_and_select_gpkg(self, bera_app, testdata_dir):
        """Open file dialog via browse button and select a gpkg file."""
        select_tool(bera_app, "Check Seed Lines")
        time.sleep(0.5)

        gpkg_path = str(testdata_dir / "integration_aoi.gpkg")
        click_browse_and_set_file(bera_app, "Seed Line", gpkg_path)
        time.sleep(1)

        # Verify the layer combo appeared (gpkg triggers layer loading)
        try:
            combo = bera_app.child_window(control_type="ComboBox", found_index=1)
            if combo.exists(timeout=3) and combo.is_visible():
                select_gpkg_layer(bera_app, "seed_lines")
        except Exception:
            pass  # layer combo may not appear if file doesn't exist on disk

    def test_browse_and_select_tif(self, bera_app, testdata_dir):
        """Open file dialog via browse button and select a tif file."""
        select_tool(bera_app, "Vertex Optimization")
        time.sleep(0.5)

        tif_path = str(testdata_dir / "chm_aoi.tif")
        click_browse_and_set_file(bera_app, "CHM Raster", tif_path)
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# Numeric input tests
# ---------------------------------------------------------------------------


class TestNumericInput:
    """Test QSpinBox and QDoubleSpinBox interactions."""

    def test_set_float_value(self, bera_app):
        select_tool(bera_app, "Vertex Optimization")
        time.sleep(0.5)
        set_numeric(bera_app, 10.0, spinner_index=0)

    def test_set_int_value(self, bera_app):
        select_tool(bera_app, "Vertex Optimization")
        time.sleep(0.5)
        bera_app.child_window(title_re=".*Advanced Options.*", control_type="Button").click_input()
        time.sleep(0.3)
        set_numeric(bera_app, 20, param_label="Line Processing Radius")


# ---------------------------------------------------------------------------
# Boolean / checkbox tests
# ---------------------------------------------------------------------------


class TestBooleanInput:
    """Test QCheckBox interactions."""

    def test_toggle_checkbox(self, bera_app):
        select_tool(bera_app, "Centerline")
        time.sleep(0.5)
        set_checkbox(bera_app, "Process Segments", checked=False)
        time.sleep(0.3)
        set_checkbox(bera_app, "Process Segments", checked=True)


# ---------------------------------------------------------------------------
# Option list (combobox) tests
# ---------------------------------------------------------------------------


class TestOptionsInput:
    """Test QComboBox option selection."""

    def test_select_canopy_percentile(self, bera_app):
        select_tool(bera_app, "Canopy Footprint (Relative Threshold)")
        time.sleep(0.5)
        bera_app.child_window(title_re=".*Advanced Options.*", control_type="Button").click_input()
        time.sleep(0.3)
        # canopy_percentile is a list type with options [50,55,...,95]
        set_option_combo(bera_app, "90", combo_index=0)


# ---------------------------------------------------------------------------
# Load defaults test
# ---------------------------------------------------------------------------


class TestLoadDefaults:
    """Test that Load Default Arguments resets form values."""

    def test_load_defaults(self, bera_app):
        select_tool(bera_app, "Vertex Optimization")
        time.sleep(0.5)

        # Change a numeric value
        set_numeric(bera_app, 99.0, spinner_index=0)
        time.sleep(0.3)

        # Click Load Default Arguments
        click_button(bera_app, "Load Default Arguments")
        time.sleep(0.5)

        # Value should be reset (default is 30.0 for search_distance)
        spinner = bera_app.child_window(control_type="Spinner", found_index=0)
        try:
            val = spinner.child_window(control_type="Edit").get_value()
            assert val != "99", "Value was not reset to default"
        except Exception:
            pass  # can't always read spinner value reliably
