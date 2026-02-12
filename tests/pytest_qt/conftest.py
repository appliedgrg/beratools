"""
pytest-qt GUI test fixtures for BERA Tools.

Cross-platform alternative to pywinauto-based tests in tests/gui/.
Drives Qt widgets in-process via qtbot — no subprocess, no display automation.

Requires:
    pip install pytest-qt

Run:
    pytest tests/pytest_qt/ -v -m gui_qt
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt5 import QtWidgets

sys.path.insert(0, Path(__file__).parents[2].as_posix())

from beratools.gui.bt_data import BTData
from beratools.gui.bt_gui_main import MainWindow
from beratools.gui.tool_widgets import (
    BooleanInput,
    FileSelector,
    NumericInput,
    OptionsInput,
    ToolWidgets,
)


SIGNAL_TIMEOUT = 2000


def pytest_configure(config):
    config.addinivalue_line("markers", "gui_qt: GUI tests using pytest-qt")


@pytest.fixture
def patched_file_dialog():
    with (
        patch("PyQt5.QtWidgets.QFileDialog.getOpenFileName") as mock_open,
        patch("PyQt5.QtWidgets.QFileDialog.getSaveFileName") as mock_save,
    ):
        mock_open.return_value = ("", "")
        mock_save.return_value = ("", "")
        yield {"open": mock_open, "save": mock_save}


@pytest.fixture
def patched_message_box():
    with (
        patch("PyQt5.QtWidgets.QMessageBox.question") as mock_question,
        patch("PyQt5.QtWidgets.QMessageBox.warning") as mock_warning,
    ):
        yield {"question": mock_question, "warning": mock_warning}


@pytest.fixture
def patched_browser():
    with patch("webbrowser.open_new_tab") as mock_browser:
        yield mock_browser


@pytest.fixture
def patched_layers():
    with patch("beratools.gui.tool_widgets.get_layers") as mock_layers:
        mock_layers.return_value = {}
        yield mock_layers


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def testdata_dir():
    return Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "gui_qt_output"


# ---------------------------------------------------------------------------
# BTData
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def btdata():
    return BTData()


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------


@pytest.fixture
def main_window(qtbot):
    with (
        patch("webbrowser.open_new_tab"),
        patch(
            "beratools.gui.bt_gui_main.QtWidgets.QMessageBox.question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ),
    ):
        w = MainWindow()
        qtbot.addWidget(w)
        w.show()
        yield w


@pytest.fixture
def fake_process(main_window):
    with patch.object(main_window, "process", create=True) as mock_proc:
        mock_proc.is_alive.return_value = True
        yield mock_proc


# ---------------------------------------------------------------------------
# ToolWidgets factory
# ---------------------------------------------------------------------------


@pytest.fixture
def make_tool_widget(qtbot, btdata):
    """Factory fixture: returns a function that creates ToolWidgets for a tool."""
    created = []

    def _make(tool_name, show_advanced=True):
        args = btdata.get_bera_tool_args(tool_name)
        tw = ToolWidgets(tool_name, args, show_advanced)
        qtbot.addWidget(tw)
        created.append(tw)
        return tw

    yield _make


# ---------------------------------------------------------------------------
# Individual widget factories (for unit tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def make_file_selector(qtbot):
    """Factory: create a FileSelector from a param dict."""
    import json

    def _make(param_dict):
        json_str = json.dumps(param_dict, sort_keys=True, indent=2)
        w = FileSelector(json_str)
        qtbot.addWidget(w)
        return w

    return _make


@pytest.fixture
def make_boolean_input(qtbot):
    import json

    def _make(param_dict):
        json_str = json.dumps(param_dict, sort_keys=True, indent=2)
        w = BooleanInput(json_str)
        qtbot.addWidget(w)
        return w

    return _make


@pytest.fixture
def make_options_input(qtbot):
    import json

    def _make(param_dict):
        json_str = json.dumps(param_dict, sort_keys=True, indent=2)
        w = OptionsInput(json_str)
        qtbot.addWidget(w)
        return w

    return _make


@pytest.fixture
def make_numeric_input(qtbot):
    import json

    def _make(param_dict):
        json_str = json.dumps(param_dict, sort_keys=True, indent=2)
        w = NumericInput(json_str)
        qtbot.addWidget(w)
        return w

    return _make


# ---------------------------------------------------------------------------
# Tool names list (from beratools.json)
# ---------------------------------------------------------------------------

ALL_TOOL_NAMES = [
    "Check Seed Lines",
    "Vertex Optimization",
    "Centerline",
    "Canopy Footprint (Absolute Threshold)",
    "Canopy Footprint (Relative Threshold)",
    "Ground Footprint",
    "Feature Buffer",
]
