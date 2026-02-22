"""
Unit tests for individual widget types using pytest-qt.

Tests NumericInput, BooleanInput, OptionsInput, and FileSelector
in isolation — each widget is constructed with a minimal param dict
and exercised via set_value / get_value round-trips.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt5.QtCore import Qt

from beratools.gui.tool_widgets import ToolWidgets

pytestmark = pytest.mark.gui_qt

SIGNAL_TIMEOUT = 2000
ALL_TOOL_NAMES = [
    "Check Seed Lines",
    "Vertex Optimization",
    "Centerline",
    "Canopy Footprint (Absolute Threshold)",
    "Canopy Footprint (Relative Threshold)",
    "Ground Footprint",
    "Feature Buffer",
]


# ---------------------------------------------------------------------------
# NumericInput
# ---------------------------------------------------------------------------


class TestNumericInputInt:
    PARAM = {
        "name": "Line Processing Radius",
        "description": "Max processing distance.",
        "variable": "line_radius",
        "parameter_type": ["int"],
        "optional": True,
        "default_value": 35,
    }

    def test_default_value(self, make_numeric_input):
        w = make_numeric_input(self.PARAM)
        assert w.data_input.value() == 35

    def test_set_and_get(self, make_numeric_input):
        w = make_numeric_input(self.PARAM)
        w.set_value(20)
        assert w.data_input.value() == 20
        assert w.get_value() == {"line_radius": 20}

    def test_set_default_value(self, make_numeric_input):
        w = make_numeric_input(self.PARAM)
        w.set_value(99)
        w.set_default_value()
        assert w.data_input.value() == 35

    def test_spinbox_type(self, make_numeric_input):
        from PyQt5.QtWidgets import QSpinBox

        w = make_numeric_input(self.PARAM)
        assert isinstance(w.data_input, QSpinBox)


class TestNumericInputFloat:
    PARAM = {
        "name": "Search Distance",
        "description": "Searching distance.",
        "variable": "search_distance",
        "parameter_type": ["float"],
        "optional": False,
        "default_value": 30.0,
    }

    def test_default_value(self, make_numeric_input):
        w = make_numeric_input(self.PARAM)
        assert w.data_input.value() == pytest.approx(30.0)

    def test_set_and_get(self, make_numeric_input):
        w = make_numeric_input(self.PARAM)
        w.set_value(5.5)
        assert w.data_input.value() == pytest.approx(5.5)
        result = w.get_value()
        assert result["search_distance"] == pytest.approx(5.5)

    def test_spinbox_type(self, make_numeric_input):
        from PyQt5.QtWidgets import QDoubleSpinBox

        w = make_numeric_input(self.PARAM)
        assert isinstance(w.data_input, QDoubleSpinBox)

    def test_spinbox_decimals(self, make_numeric_input):
        w = make_numeric_input(self.PARAM)
        assert w.data_input.decimals() == 2


# ---------------------------------------------------------------------------
# BooleanInput
# ---------------------------------------------------------------------------


class TestBooleanInputPure:
    PARAM = {
        "name": "Process Segments",
        "description": "Process each segment separately.",
        "variable": "proc_segments",
        "parameter_type": "Boolean",
        "optional": False,
        "default_value": True,
    }

    def test_default_checked(self, make_boolean_input):
        w = make_boolean_input(self.PARAM)
        assert w.checkbox.isChecked() is True

    def test_set_false(self, make_boolean_input):
        w = make_boolean_input(self.PARAM)
        w.set_value(False)
        assert w.checkbox.isChecked() is False
        assert w.get_value() == {"proc_segments": False}

    def test_set_true_from_string(self, make_boolean_input):
        w = make_boolean_input(self.PARAM)
        w.set_value("true")
        assert w.checkbox.isChecked() is True

    def test_set_default_value(self, make_boolean_input):
        w = make_boolean_input(self.PARAM)
        w.set_value(False)
        w.set_default_value()
        assert w.checkbox.isChecked() is True

    def test_label_format(self, make_boolean_input):
        w = make_boolean_input(self.PARAM)
        assert "Process Segments" in w.checkbox.text()
        assert "Process each segment separately" in w.checkbox.text()


class TestBooleanInputFromOptionList:
    PARAM = {
        "name": "Use Maximum Width",
        "description": "Use maximum sampled width.",
        "variable": "max_width",
        "parameter_type": {"OptionList": [True, False]},
        "optional": True,
        "default_value": True,
    }

    def test_default_checked(self, make_boolean_input):
        w = make_boolean_input(self.PARAM)
        assert w.checkbox.isChecked() is True

    def test_toggle(self, make_boolean_input):
        w = make_boolean_input(self.PARAM)
        w.set_value(False)
        assert w.get_value() == {"max_width": False}
        w.set_value(True)
        assert w.get_value() == {"max_width": True}


# ---------------------------------------------------------------------------
# OptionsInput
# ---------------------------------------------------------------------------


class TestOptionsInput:
    PARAM = {
        "name": "Canopy Percentile",
        "description": "The Nth percentile.",
        "variable": "canopy_percentile",
        "parameter_type": {"OptionList": [50, 55, 60, 65, 70, 75, 80, 85, 90, 95]},
        "optional": True,
        "default_value": 90,
        "data_type": ["int"],
    }

    def test_default_selection(self, make_options_input):
        w = make_options_input(self.PARAM)
        assert w.combobox.currentText() == "90"

    def test_set_value(self, make_options_input):
        w = make_options_input(self.PARAM)
        w.set_value("75")
        assert w.combobox.currentText() == "75"

    def test_get_value(self, make_options_input):
        w = make_options_input(self.PARAM)
        w.set_value("60")
        assert w.get_value() == {"canopy_percentile": "60"}

    def test_option_count(self, make_options_input):
        w = make_options_input(self.PARAM)
        assert w.combobox.count() == 10

    def test_set_default_value(self, make_options_input):
        w = make_options_input(self.PARAM)
        w.set_value("50")
        w.set_default_value()
        assert w.combobox.currentText() == "90"

    def test_selection_change_signal(self, make_options_input, qtbot):
        w = make_options_input(self.PARAM)
        w.combobox.setCurrentIndex(0)
        assert w.value == "50"


class TestWidgetSignals:
    def test_numeric_value_changed_signal_payload(self, make_numeric_input, qtbot):
        w = make_numeric_input(TestNumericInputInt.PARAM)

        with qtbot.waitSignal(w.data_input.valueChanged, timeout=SIGNAL_TIMEOUT) as blocker:
            w.data_input.setValue(44)

        assert blocker.args == [44]
        assert w.get_value() == {"line_radius": 44}

    def test_boolean_state_changed_signal_payload(self, make_boolean_input, qtbot):
        w = make_boolean_input(TestBooleanInputPure.PARAM)

        with qtbot.waitSignal(w.checkbox.stateChanged, timeout=SIGNAL_TIMEOUT) as blocker:
            w.checkbox.setChecked(False)

        assert blocker.args == [0]
        assert w.get_value() == {"proc_segments": False}

    def test_options_index_changed_signal_payload(self, make_options_input, qtbot):
        w = make_options_input(TestOptionsInput.PARAM)

        with qtbot.waitSignal(w.combobox.currentIndexChanged, timeout=SIGNAL_TIMEOUT) as blocker:
            w.combobox.setCurrentIndex(0)

        assert blocker.args == [0]
        assert w.get_value() == {"canopy_percentile": "50"}

    def test_file_selector_text_changed_signal_payload(self, make_file_selector, qtbot):
        w = make_file_selector(TestFileSelectorRaster.PARAM)
        updated = "updated.tif"

        with qtbot.waitSignal(w.in_file.textChanged, timeout=SIGNAL_TIMEOUT) as blocker:
            w.in_file.setText(updated)

        assert blocker.args == [updated]
        assert w.get_value() == {"in_raster": updated}


class TestKeyboardInput:
    @pytest.mark.parametrize("typed, expected", [("0", 0), ("1", 1), ("99", 99)])
    def test_numeric_int_key_clicks_boundary_values(self, make_numeric_input, qtbot, typed, expected):
        w = make_numeric_input(TestNumericInputInt.PARAM)
        editor = w.data_input.lineEdit()

        with qtbot.waitSignal(w.data_input.valueChanged, timeout=SIGNAL_TIMEOUT):
            editor.setFocus()
            qtbot.keyClick(editor, Qt.Key_A, Qt.ControlModifier)
            qtbot.keyClick(editor, Qt.Key_Delete)
            qtbot.keyClicks(editor, typed)
            qtbot.keyClick(editor, Qt.Key_Enter)

        assert w.data_input.value() == expected
        assert w.get_value() == {"line_radius": expected}

    @pytest.mark.parametrize("typed, expected", [("0.0", 0.0), ("0.1", 0.1), ("99.9", 99.9)])
    def test_numeric_float_key_clicks_boundary_values(self, make_numeric_input, qtbot, typed, expected):
        w = make_numeric_input(TestNumericInputFloat.PARAM)
        editor = w.data_input.lineEdit()

        with qtbot.waitSignal(w.data_input.valueChanged, timeout=SIGNAL_TIMEOUT):
            editor.setFocus()
            qtbot.keyClick(editor, Qt.Key_A, Qt.ControlModifier)
            qtbot.keyClick(editor, Qt.Key_Delete)
            qtbot.keyClicks(editor, typed)
            qtbot.keyClick(editor, Qt.Key_Enter)

        assert w.data_input.value() == pytest.approx(expected)
        assert w.get_value()["search_distance"] == pytest.approx(expected)

    def test_file_selector_path_key_clicks_updates_value(self, make_file_selector, qtbot):
        w = make_file_selector(TestFileSelectorRaster.PARAM)
        w.in_file.setFocus()

        with qtbot.waitSignal(w.in_file.textChanged, timeout=SIGNAL_TIMEOUT):
            qtbot.keyClicks(w.in_file, "C:/tmp/in_file.tif")

        assert w.in_file.text() == "C:/tmp/in_file.tif"
        assert w.get_value() == {"in_raster": "C:/tmp/in_file.tif"}


# ---------------------------------------------------------------------------
# FileSelector — raster (non-vector)
# ---------------------------------------------------------------------------


class TestFileSelectorRaster:
    PARAM = {
        "name": "CHM Raster",
        "description": "Input CHM raster.",
        "variable": "in_raster",
        "parameter_type": {"ExistingFile": ["raster"]},
        "optional": False,
        "default_value": "",
        "output": False,
    }

    def test_set_and_get_path(self, make_file_selector, testdata_dir):
        raster = str(testdata_dir / "chm_aoi.tif")
        w = make_file_selector(self.PARAM)
        w.set_value(raster)
        assert w.in_file.text() == raster
        assert w.get_value() == {"in_raster": raster}

    def test_layer_combo_hidden_for_raster(self, make_file_selector, testdata_dir):
        raster = str(testdata_dir / "chm_aoi.tif")
        w = make_file_selector(self.PARAM)
        w.set_value(raster)
        assert not w.layer_combo.isVisible()

    def test_empty_default(self, make_file_selector):
        w = make_file_selector(self.PARAM)
        assert w.in_file.text() == ""


# ---------------------------------------------------------------------------
# FileSelector — vector (gpkg)
# ---------------------------------------------------------------------------


class TestFileSelectorVector:
    PARAM = {
        "name": "Seed Line",
        "description": "Input seed line file.",
        "variable": "in_line",
        "parameter_type": {"ExistingFile": ["vector"]},
        "optional": False,
        "default_value": "",
        "output": False,
    }

    def test_set_dict_value(self, make_file_selector, testdata_dir):
        gpkg = str(testdata_dir / "seed_lines_aoi.gpkg")
        w = make_file_selector(self.PARAM)
        with patch("beratools.gui.tool_widgets.get_layers") as mock_layers:
            mock_layers.return_value = {"seed_lines": "MultiLineString", "centerline": "MultiLineString"}
            w.set_value({"path": gpkg, "layer": "seed_lines"})

        assert w.in_file.text() == gpkg
        assert w.value["layer"] == "seed_lines"

    def test_set_pipe_string(self, make_file_selector, testdata_dir):
        gpkg = str(testdata_dir / "seed_lines_aoi.gpkg")
        w = make_file_selector(self.PARAM)
        with patch("beratools.gui.tool_widgets.get_layers") as mock_layers:
            mock_layers.return_value = {"seed_lines": "MultiLineString"}
            w.set_value(f"{gpkg}|seed_lines")

        assert w.value["path"] == gpkg
        assert w.value["layer"] == "seed_lines"

    def test_get_value_encodes_pipe(self, make_file_selector, testdata_dir):
        gpkg = str(testdata_dir / "seed_lines_aoi.gpkg")
        w = make_file_selector(self.PARAM)
        with patch("beratools.gui.tool_widgets.get_layers") as mock_layers:
            mock_layers.return_value = {"seed_lines": "MultiLineString"}
            w.set_value({"path": gpkg, "layer": "seed_lines"})

        result = w.get_value()
        assert result["in_line"] == f"{gpkg}|seed_lines"

    def test_is_vector_flag(self, make_file_selector):
        w = make_file_selector(self.PARAM)
        assert w.is_vector is True


class TestFileSelectorOutput:
    PARAM = {
        "name": "Output Centerline",
        "description": "Output centerline file.",
        "variable": "out_line",
        "parameter_type": {"NewFile": ["vector"]},
        "optional": False,
        "default_value": "",
        "output": True,
    }

    def test_output_flag(self, make_file_selector):
        w = make_file_selector(self.PARAM)
        assert w.output is True

    def test_set_output_path(self, make_file_selector, tmp_path):
        gpkg = str(tmp_path / "result.gpkg")
        w = make_file_selector(self.PARAM)
        w.set_value({"path": gpkg, "layer": "centerline"})
        result = w.get_value()
        assert result["out_line"].startswith(gpkg)
        assert "|" in result["out_line"]


class _FakeFileDialog:
    def __init__(self, file_names=None, selected_filter=""):
        self._file_names = file_names or []
        self._selected_filter = selected_filter

    def exec_(self):
        return bool(self._file_names)

    def selectedFiles(self):
        return self._file_names

    def selectedNameFilter(self):
        return self._selected_filter


class TestFileSelectorDialogInteraction:
    RASTER_PARAM = TestFileSelectorRaster.PARAM
    VECTOR_OUTPUT_PARAM = TestFileSelectorOutput.PARAM

    def test_browse_click_updates_raster_input(self, make_file_selector, qtbot, testdata_dir):
        raster = str(testdata_dir / "chm_aoi.tif")
        w = make_file_selector(self.RASTER_PARAM)
        fake_dialog = _FakeFileDialog(
            file_names=[raster],
            selected_filter="Tiff raster files (*.tif *.tiff)",
        )

        with patch.object(w, "setup_file_dialog", return_value=fake_dialog):
            qtbot.mouseClick(w.btn_select, Qt.LeftButton)

        assert w.in_file.text() == raster

    def test_browse_click_updates_output_with_selected_extension(self, make_file_selector, qtbot, tmp_path):
        w = make_file_selector(self.VECTOR_OUTPUT_PARAM)
        base_output = str(tmp_path / "centerline_output")
        fake_dialog = _FakeFileDialog(
            file_names=[base_output],
            selected_filter="GeoPackage (*.gpkg)",
        )

        with patch.object(w, "setup_file_dialog", return_value=fake_dialog):
            qtbot.mouseClick(w.btn_select, Qt.LeftButton)

        assert w.in_file.text().endswith(".gpkg")
        assert not w.layer_combo.isHidden()
        assert w.layer_combo.itemText(0) == "Result_layer"

    def test_browse_cancel_does_not_overwrite_value(self, make_file_selector, qtbot, testdata_dir):
        raster = str(testdata_dir / "chm_aoi.tif")
        w = make_file_selector(self.RASTER_PARAM)
        w.set_value(raster)
        fake_dialog = _FakeFileDialog(file_names=[], selected_filter="")

        with patch.object(w, "setup_file_dialog", return_value=fake_dialog):
            qtbot.mouseClick(w.btn_select, Qt.LeftButton)

        assert w.in_file.text() == raster
        assert w.get_value()["in_raster"] == raster


class TestFileSelectorLayerComboInteraction:
    VECTOR_PARAM = TestFileSelectorVector.PARAM
    VECTOR_LINE_PARAM = {
        "name": "Seed Line",
        "description": "Input seed line file.",
        "variable": "in_line",
        "parameter_type": {"ExistingFile": ["vector", "line"]},
        "optional": False,
        "default_value": "",
        "output": False,
    }

    def test_vector_gpkg_populates_layer_combo_and_updates_layer(
        self, make_file_selector, patched_layers, qtbot, tmp_path
    ):
        gpkg = str(tmp_path / "input.gpkg")
        Path(gpkg).write_text("", encoding="utf-8")
        patched_layers.return_value = {
            "seed_lines": "MultiLineString",
            "centerline": "MultiLineString",
        }

        w = make_file_selector(self.VECTOR_PARAM)
        w.in_file.setText(gpkg)

        qtbot.waitUntil(lambda: not w.layer_combo.isHidden(), timeout=SIGNAL_TIMEOUT)
        assert w.layer_combo.count() >= 2
        assert "seed_lines" in w.layer_combo.itemText(0)

        w.layer_combo.setCurrentText("centerline (MultiLineString)")
        assert w.value["layer"] == "centerline"

    @pytest.mark.parametrize(
        ("ext", "expected_visible"),
        [(".gpkg", True), (".shp", False)],
    )
    def test_vector_extensions_show_layer_combo(
        self, make_file_selector, patched_layers, qtbot, tmp_path, ext, expected_visible
    ):
        path = str(tmp_path / f"input{ext}")
        Path(path).write_text("", encoding="utf-8")
        patched_layers.return_value = {"seed_lines": "MultiLineString"}

        w = make_file_selector(self.VECTOR_PARAM)
        w.in_file.setText(path)

        if expected_visible:
            qtbot.waitUntil(lambda: not w.layer_combo.isHidden(), timeout=SIGNAL_TIMEOUT)
            assert w.layer_combo.count() >= 1
        else:
            assert w.layer_combo.isHidden()

    @pytest.mark.parametrize("ext", [".tif", ".tiff", ".img", ".asc"])
    def test_raster_extensions_keep_layer_combo_hidden(self, make_file_selector, ext):
        w = make_file_selector(TestFileSelectorRaster.PARAM)
        w.set_value(f"dummy{ext}")

        assert w.layer_combo.isHidden()

    def test_geojson_keeps_layer_combo_hidden_current_behavior(self, make_file_selector):
        w = make_file_selector(self.VECTOR_PARAM)
        w.in_file.setText("input.geojson")

        assert w.layer_combo.isHidden()

    def test_gpkg_filters_layers_by_restricted_geometry(
        self, make_file_selector, patched_layers, qtbot, tmp_path
    ):
        gpkg = str(tmp_path / "input.gpkg")
        Path(gpkg).write_text("", encoding="utf-8")
        patched_layers.return_value = {
            "centerline": "MultiLineString",
            "footprint": "Polygon",
        }

        w = make_file_selector(self.VECTOR_LINE_PARAM)
        w.in_file.setText(gpkg)

        qtbot.waitUntil(lambda: not w.layer_combo.isHidden(), timeout=SIGNAL_TIMEOUT)
        assert w.layer_combo.count() == 1
        assert "centerline" in w.layer_combo.itemText(0)
        assert "footprint" not in w.layer_combo.itemText(0)

    def test_gpkg_no_compatible_layers_blocks_required_input(
        self, make_file_selector, patched_layers, qtbot, tmp_path
    ):
        gpkg = str(tmp_path / "input.gpkg")
        Path(gpkg).write_text("", encoding="utf-8")
        patched_layers.return_value = {"footprint": "Polygon"}

        w = make_file_selector(self.VECTOR_LINE_PARAM)
        w.in_file.setText(gpkg)

        qtbot.waitUntil(lambda: not w.layer_combo.isHidden(), timeout=SIGNAL_TIMEOUT)
        assert w.layer_combo.itemText(0) == "(No compatible layers)"
        assert "No compatible layers" in w.input_geometry_error
        assert w.get_value()["in_line"] == ""

    def test_shapefile_geometry_mismatch_sets_warning_and_blocks(self, make_file_selector, tmp_path):
        shp = str(tmp_path / "input.shp")
        Path(shp).write_text("", encoding="utf-8")

        w = make_file_selector(self.VECTOR_LINE_PARAM)
        with patch("beratools.gui.tool_widgets.pyogrio.read_info") as mock_read_info:
            mock_read_info.return_value = {"geometry_type": "Polygon"}
            w.in_file.setText(shp)

        assert "Geometry mismatch" in w.input_geometry_error
        assert w.get_value()["in_line"] == ""

    def test_layer_popup_width_updates_for_longer_names(
        self, make_file_selector, patched_layers, qtbot, tmp_path
    ):
        short_gpkg = str(tmp_path / "short.gpkg")
        long_gpkg = str(tmp_path / "long.gpkg")
        Path(short_gpkg).write_text("", encoding="utf-8")
        Path(long_gpkg).write_text("", encoding="utf-8")

        w = make_file_selector(self.VECTOR_LINE_PARAM)

        patched_layers.return_value = {"a": "LineString"}
        w.in_file.setText(short_gpkg)
        qtbot.waitUntil(lambda: w.layer_combo.count() > 0, timeout=SIGNAL_TIMEOUT)
        short_width = w.layer_combo.view().minimumWidth()

        patched_layers.return_value = {
            "very_long_centerline_layer_name_for_testing_popup_width": "LineString"
        }
        w.in_file.setText(long_gpkg)
        qtbot.waitUntil(
            lambda: "very_long_centerline_layer_name" in w.layer_combo.itemText(0),
            timeout=SIGNAL_TIMEOUT,
        )
        long_width = w.layer_combo.view().minimumWidth()

        assert long_width > short_width


# ---------------------------------------------------------------------------
# ToolWidgets — construction and round-trip for all tools
# ---------------------------------------------------------------------------


class TestToolWidgetsConstruction:
    @pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
    def test_widget_count_matches_params(self, make_tool_widget, btdata, tool_name):
        tw = make_tool_widget(tool_name)
        expected = len(btdata.get_bera_tool_args(tool_name))
        assert len(tw.widget_list) == expected

    @pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
    def test_all_widgets_have_variable(self, make_tool_widget, tool_name):
        tw = make_tool_widget(tool_name)
        for w in tw.widget_list:
            assert hasattr(w, "variable")
            assert w.variable

    def test_load_default_args(self, make_tool_widget):
        tw = make_tool_widget("Vertex Optimization")
        for w in tw.widget_list:
            if hasattr(w, "data_input") and w.data_input and hasattr(w, "set_value"):
                w.set_value(999)
        tw.load_default_args()
        for w in tw.widget_list:
            if hasattr(w, "data_input") and w.data_input:
                assert w.data_input.value() != 999


class TestToolWidgetsAdvancedVisibility:
    def test_optional_hidden_when_advanced_off(self, qtbot, btdata):
        args = btdata.get_bera_tool_args("Vertex Optimization")
        tw = ToolWidgets("Vertex Optimization", args, show_advanced=False)
        qtbot.addWidget(tw)
        for w in tw.widget_list:
            if w.optional:
                assert w.isHidden()

    def test_optional_visible_when_advanced_on(self, make_tool_widget):
        tw = make_tool_widget("Vertex Optimization", show_advanced=True)
        for w in tw.widget_list:
            if w.optional:
                assert not w.isHidden()

    def test_missing_input_history_clears_same_output_path(self, qtbot, tmp_path):
        missing = str(tmp_path / "history_missing.gpkg")
        tool_args = [
            {
                "name": "Input line",
                "description": "Input vector",
                "variable": "in_line",
                "parameter_type": {"ExistingFile": ["vector"]},
                "optional": False,
                "default_value": "",
                "saved_value": f"{missing}|seed_lines",
                "output": False,
            },
            {
                "name": "Output line",
                "description": "Output vector",
                "variable": "out_line",
                "parameter_type": {"NewFile": ["vector"]},
                "optional": False,
                "default_value": "",
                "saved_value": f"{missing}|Result_layer",
                "output": True,
            },
        ]

        tw = ToolWidgets("History edge", tool_args, show_advanced=True)
        qtbot.addWidget(tw)

        in_widget = next(w for w in tw.widget_list if w.variable == "in_line")
        out_widget = next(w for w in tw.widget_list if w.variable == "out_line")

        assert in_widget.value["path"] == ""
        assert out_widget.value["path"] == ""
        assert out_widget.value["layer"] == ""
