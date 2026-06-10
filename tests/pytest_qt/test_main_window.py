"""
MainWindow-level tests using pytest-qt.

Tests window setup, button presence, tree view navigation,
tool switching, slider, and advanced options toggle.
"""

from unittest.mock import patch

import pytest
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox, QPushButton

from beratools.gui import bt_data

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
# Window basics
# ---------------------------------------------------------------------------


class TestMainWindowBasics:
    def test_window_title(self, main_window):
        assert main_window.windowTitle() == "BERA Tools"

    def test_window_visible(self, main_window):
        assert main_window.isVisible()

    def test_stale_recent_tool_falls_back_to_centerline(self, qtbot, monkeypatch):
        from beratools.gui import bt_gui_main

        monkeypatch.setattr(bt_gui_main.bt, "recent_tool", "Missing Tool")

        window = bt_gui_main.MainWindow()
        qtbot.addWidget(window)

        assert window.recent_tool is None
        assert window.tool_name == "Centerline"

    def test_run_button_exists(self, main_window):
        assert main_window.btn_run is not None
        assert main_window.btn_run.text() == "Run"
        assert main_window.btn_run.isEnabled()

    def test_text_edit_readonly(self, main_window):
        assert main_window.text_edit.isReadOnly()

    def test_text_edit_uses_custom_context_menu(self, main_window):
        assert main_window.text_edit.contextMenuPolicy() == Qt.CustomContextMenu

    def test_progress_bar_exists(self, main_window):
        assert main_window.progress_bar is not None
        assert main_window.progress_bar.value() in (-1, 0)


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------


class TestButtons:
    @pytest.mark.parametrize(
        "btn_text",
        [
            "Run",
            "Cancel",
            "Exit",
            "Show Advanced Options",
            "Tool Help",
            "Load Default Arguments",
        ],
    )
    def test_button_findable(self, main_window, btn_text):
        buttons = main_window.findChildren(QPushButton)
        texts = [b.text() for b in buttons]
        assert btn_text in texts, f"Button '{btn_text}' not found. Available: {texts}"


def _get_button_by_text(main_window, text):
    for button in main_window.findChildren(QPushButton):
        if button.text() == text:
            return button
    raise AssertionError(f"Button '{text}' not found")


class _FakeSignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)


class _FakeProcess:
    def __init__(self):
        self.readyReadStandardOutput = _FakeSignal()
        self.readyReadStandardError = _FakeSignal()
        self.stateChanged = _FakeSignal()
        self.finished = _FakeSignal()
        self.killed = False
        self.started = None

    def start(self, tool_type, tool_args):
        self.started = (tool_type, tool_args)

    def kill(self):
        self.killed = True

    def terminate(self):
        self.killed = True


class _ProcessEmitter(QtCore.QObject):
    stateChanged = QtCore.pyqtSignal(int)
    finished = QtCore.pyqtSignal()


class _FakeMenu:
    def __init__(self):
        self.actions = []

    def addSeparator(self):
        return None

    def addAction(self, text):
        self.actions.append(text)
        return text

    def exec_(self, pos):
        return self.actions[-1] if self.actions else None


class TestButtonInteractions:
    def test_run_click_with_empty_args_does_not_start_process(self, main_window, qtbot):
        run_btn = _get_button_by_text(main_window, "Run")
        start_text = main_window.text_edit.toPlainText()
        start_progress = main_window.progress_bar.value()

        with patch.object(main_window.tool_widget, "get_widgets_arguments", return_value=None):
            qtbot.mouseClick(run_btn, Qt.LeftButton)

        assert main_window.process is None
        assert main_window.btn_run.isEnabled()
        assert main_window.progress_bar.value() == start_progress
        assert main_window.text_edit.toPlainText() == start_text

    def test_run_click_with_args_starts_process(self, main_window, qtbot):
        run_btn = _get_button_by_text(main_window, "Run")
        fake_process = _FakeProcess()

        with (
            patch.object(
                main_window.tool_widget,
                "get_widgets_arguments",
                return_value={"in_raster": "in_raster.tif"},
            ),
            patch.object(main_window, "save_tool_parameter"),
            patch("beratools.gui.bt_gui_main.bt.prepare_tool_run", return_value=("fake_tool", ["--arg"])),
            patch("beratools.gui.bt_gui_main.QtCore.QProcess", return_value=fake_process),
        ):
            qtbot.mouseClick(run_btn, Qt.LeftButton)

        assert main_window.process is fake_process
        assert fake_process.started == ("fake_tool", ["--arg"])
        assert "Starting tool" in main_window.text_edit.toPlainText()

    def test_cancel_click_kills_running_process(self, main_window, qtbot):
        cancel_btn = _get_button_by_text(main_window, "Cancel")
        fake_process = _FakeProcess()
        main_window.process = fake_process

        qtbot.mouseClick(cancel_btn, Qt.LeftButton)

        assert main_window.cancel_op is True
        assert fake_process.killed is True
        assert "terminating" in main_window.text_edit.toPlainText()

    def test_exit_click_accept_closes_window(self, main_window, qtbot):
        exit_btn = _get_button_by_text(main_window, "Exit")
        with patch(
            "beratools.gui.bt_gui_main.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            qtbot.mouseClick(exit_btn, Qt.LeftButton)
            qtbot.waitUntil(lambda: not main_window.isVisible(), timeout=SIGNAL_TIMEOUT)

        assert not main_window.isVisible()

    def test_exit_click_reject_keeps_window_open(self, main_window, qtbot):
        exit_btn = _get_button_by_text(main_window, "Exit")
        with patch(
            "beratools.gui.bt_gui_main.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ):
            qtbot.mouseClick(exit_btn, Qt.LeftButton)

        assert main_window.isVisible()

    def test_help_click_opens_current_tool_url(self, main_window, qtbot):
        help_btn = _get_button_by_text(main_window, "Tool Help")
        tech_link = main_window.get_current_tool_parameters()["tech_link"]
        if isinstance(tech_link, list):
            expected_url = str(tech_link[0]) if tech_link else ""
        else:
            expected_url = str(tech_link)

        with patch("webbrowser.open_new_tab") as mock_open:
            qtbot.mouseClick(help_btn, Qt.LeftButton)

        mock_open.assert_called_once_with(expected_url)


class TestHelpMenu:
    def test_help_menu_exists_with_actions(self, main_window):
        assert main_window.help_menu is not None
        action_texts = [action.text() for action in main_window.help_menu.actions()]
        assert "BERA Tools Guide" in action_texts
        assert "About BERA Tools" in action_texts

    def test_guide_action_opens_global_url(self, main_window):
        expected_url = bt_data.get_global_docs_url()
        with patch("webbrowser.open_new_tab") as mock_open:
            main_window.action_bera_tools_guide.trigger()

        mock_open.assert_called_once_with(expected_url)

    def test_about_action_opens_dialog_with_version_info(self, main_window):
        with patch("beratools.gui.bt_gui_main.QtWidgets.QMessageBox.about") as mock_about:
            main_window.action_about_bera_tools.trigger()

        assert mock_about.called
        message_text = mock_about.call_args.args[2]
        assert "BERA Tools" in message_text
        assert "Version:" in message_text
        assert "Python:" in message_text

        version_part = message_text.split("Version:", 1)[1].splitlines()[0].strip()
        assert version_part != ""

    def test_load_default_button_resets_widget_values(self, main_window, qtbot):
        from beratools.gui.tool_widgets import NumericInput

        main_window.set_tool("Vertex Optimization")
        numerics = [w for w in main_window.tool_widget.widget_list if isinstance(w, NumericInput)]
        assert numerics
        target = numerics[0]
        target.set_value(999)

        load_defaults_btn = _get_button_by_text(main_window, "Load Default Arguments")
        qtbot.mouseClick(load_defaults_btn, Qt.LeftButton)

        assert target.data_input.value() != 999
        if isinstance(target.default_value, float):
            assert target.data_input.value() == pytest.approx(target.default_value)
        else:
            assert target.data_input.value() == target.default_value

    def test_advanced_toggle_click_changes_text_and_visibility(self, main_window, qtbot):
        main_window.set_tool("Vertex Optimization")
        advanced_btn = main_window.btn_advanced
        optional_widgets = [w for w in main_window.tool_widget.widget_list if w.optional]
        assert optional_widgets

        assert advanced_btn.text() == "Show Advanced Options"
        assert all(w.isHidden() for w in optional_widgets)

        qtbot.mouseClick(advanced_btn, Qt.LeftButton)
        qtbot.waitUntil(lambda: advanced_btn.text() == "Hide Advanced Options", timeout=SIGNAL_TIMEOUT)
        optional_widgets = [w for w in main_window.tool_widget.widget_list if w.optional]
        assert all(not w.isHidden() for w in optional_widgets)

        qtbot.mouseClick(advanced_btn, Qt.LeftButton)
        qtbot.waitUntil(lambda: advanced_btn.text() == "Show Advanced Options", timeout=SIGNAL_TIMEOUT)
        optional_widgets = [w for w in main_window.tool_widget.widget_list if w.optional]
        assert all(w.isHidden() for w in optional_widgets)


# ---------------------------------------------------------------------------
# Tree view
# ---------------------------------------------------------------------------


class TestTreeView:
    def test_tree_view_exists(self, main_window):
        assert main_window.tree_view is not None

    def test_category_count(self, main_window):
        model = main_window.tree_view.tree_model
        assert model.rowCount() == 2  # Mapping + Templates

    def test_tool_count(self, main_window):
        model = main_window.tree_view.tree_model
        total = 0
        for row in range(model.rowCount()):
            parent = model.item(row)
            total += parent.rowCount()
        assert total == 7

    @pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
    def test_select_tool_by_name(self, main_window, qtbot, tool_name):
        if main_window.tool_name == tool_name:
            alt = next((name for name in ALL_TOOL_NAMES if name != tool_name), None)
            if alt:
                main_window.tree_view.select_tool_by_name(alt)

        with qtbot.waitSignal(main_window.tree_view.tool_changed, timeout=SIGNAL_TIMEOUT):
            main_window.tree_view.select_tool_by_name(tool_name)

    def test_tool_changed_signal_payload(self, main_window, qtbot):
        target_tool = "Centerline"
        if main_window.tool_name == target_tool:
            main_window.tree_view.select_tool_by_name("Feature Buffer")

        with qtbot.waitSignal(main_window.tree_view.tool_changed, timeout=SIGNAL_TIMEOUT) as blocker:
            main_window.tree_view.select_tool_by_name(target_tool)

        assert blocker.args == [target_tool]

    def test_search_filters_tree(self, main_window):
        search = main_window.tree_view.tool_search
        proxy = main_window.tree_view.tags_model

        search.setText("Center")
        assert proxy.rowCount() > 0

        search.setText("xyznonexistent")
        assert proxy.rowCount() == 0

        search.setText("")

    def test_stale_recent_tool_falls_back_to_centerline(self, qtbot, monkeypatch):
        from beratools.gui import bt_gui_main

        monkeypatch.setattr(bt_gui_main.bt, "recent_tool", "Missing Tool")

        tree_view = bt_gui_main.BTTreeView()
        qtbot.addWidget(tree_view)

        index = tree_view.tree_sel_model.currentIndex()
        source_index = tree_view.tags_model.mapToSource(index)
        item = tree_view.tree_model.itemFromIndex(source_index)

        assert item is not None
        assert item.text() == "Centerline"


class TestKeyboardInput:
    def test_search_box_key_clicks_filters_and_clears(self, main_window, qtbot):
        search = main_window.tree_view.tool_search
        proxy = main_window.tree_view.tags_model

        search.setFocus()
        qtbot.keyClicks(search, "Center")
        qtbot.waitUntil(lambda: proxy.rowCount() > 0, timeout=SIGNAL_TIMEOUT)

        qtbot.keyClick(search, Qt.Key_A, Qt.ControlModifier)
        qtbot.keyClick(search, Qt.Key_Delete)
        qtbot.keyClicks(search, "xyznonexistent")
        qtbot.waitUntil(lambda: proxy.rowCount() == 0, timeout=SIGNAL_TIMEOUT)

        qtbot.keyClick(search, Qt.Key_A, Qt.ControlModifier)
        qtbot.keyClick(search, Qt.Key_Delete)
        qtbot.waitUntil(lambda: search.text() == "", timeout=SIGNAL_TIMEOUT)
        assert proxy.rowCount() > 0


# ---------------------------------------------------------------------------
# Tool switching
# ---------------------------------------------------------------------------


class TestToolSwitching:
    @pytest.mark.parametrize("tool_name", ALL_TOOL_NAMES)
    def test_set_tool_updates_widget(self, main_window, tool_name):
        main_window.set_tool(tool_name)
        assert main_window.tool_name == tool_name
        assert main_window.tool_widget is not None
        assert len(main_window.tool_widget.widget_list) > 0

    def test_set_tool_updates_label(self, main_window):
        main_window.set_tool("Feature Buffer")
        label_widget = main_window.btn_layout_top.itemAt(0).widget()
        assert "Feature Buffer" in label_widget.text()


# ---------------------------------------------------------------------------
# Advanced options toggle
# ---------------------------------------------------------------------------


class TestAdvancedOptions:
    def test_toggle_shows_optional(self, main_window):
        main_window.set_tool("Vertex Optimization")

        from beratools.gui.bt_data import BTData

        bt = BTData()
        bt.show_advanced = False
        main_window.btn_advanced.setText("Show Advanced Options")

        main_window.show_advanced()
        assert main_window.btn_advanced.text() == "Hide Advanced Options"

        main_window.show_advanced()
        assert main_window.btn_advanced.text() == "Show Advanced Options"

    def test_internal_vertex_checkbox_appears_when_advanced_enabled(self, main_window, qtbot):
        main_window.set_tool("Vertex Optimization")
        advanced_btn = main_window.btn_advanced

        internal_widget = next(
            w for w in main_window.tool_widget.widget_list if w.variable == "optimize_internal_vertices"
        )
        assert internal_widget.optional is True
        assert internal_widget.isHidden()

        qtbot.mouseClick(advanced_btn, Qt.LeftButton)
        qtbot.waitUntil(lambda: advanced_btn.text() == "Hide Advanced Options", timeout=SIGNAL_TIMEOUT)
        assert not internal_widget.isHidden()


# ---------------------------------------------------------------------------
# Slider
# ---------------------------------------------------------------------------


class TestSlider:
    def test_slider_exists(self, main_window):
        from beratools.gui.bt_gui_main import BTSlider

        sliders = main_window.findChildren(BTSlider)
        assert len(sliders) == 1

    def test_slider_set_value(self, main_window):
        from beratools.gui.bt_gui_main import BTSlider

        slider_widget = main_window.findChildren(BTSlider)[0]
        slider_widget.slider.setValue(2)
        slider_widget.slider_moved(2)
        assert slider_widget.slider.value() == 2
        assert "2" in slider_widget.label.text()

    def test_slider_move_updates_cpu_setting(self, main_window):
        from beratools.gui.bt_gui_main import BTSlider

        slider_widget = main_window.findChildren(BTSlider)[0]
        with patch("beratools.gui.bt_gui_main.bt.set_selected_cpu_cores") as mock_set_cores:
            slider_widget.slider.setValue(3)
            slider_widget.slider_moved(3)

        mock_set_cores.assert_called_with(3)
        assert "3" in slider_widget.label.text()

    def test_slider_boundary_values_update_label(self, main_window):
        from beratools.gui.bt_gui_main import BTSlider

        slider_widget = main_window.findChildren(BTSlider)[0]
        low = slider_widget.slider.minimum()
        high = slider_widget.slider.maximum()

        slider_widget.slider_moved(low)
        assert str(low) in slider_widget.label.text()
        slider_widget.slider_moved(high)
        assert str(high) in slider_widget.label.text()

    def test_update_procs_sets_selected_cores(self, main_window):
        with patch("beratools.gui.bt_gui_main.bt.set_selected_cpu_cores") as mock_set_cores:
            main_window.update_procs(4)

        mock_set_cores.assert_called_once_with(4)


# ---------------------------------------------------------------------------
# Load default arguments
# ---------------------------------------------------------------------------


class TestLoadDefaults:
    def test_load_defaults_resets_numeric(self, main_window):
        main_window.set_tool("Vertex Optimization")
        tw = main_window.tool_widget

        from beratools.gui.tool_widgets import NumericInput

        numerics = [w for w in tw.widget_list if isinstance(w, NumericInput)]
        if numerics:
            numerics[0].set_value(999)
            main_window.load_default_args()
            assert numerics[0].data_input.value() != 999
            if isinstance(numerics[0].default_value, float):
                assert numerics[0].data_input.value() == pytest.approx(numerics[0].default_value)
            else:
                assert numerics[0].data_input.value() == numerics[0].default_value


class TestProcessSignals:
    def test_state_changed_signal_disables_run(self, main_window, qtbot):
        emitter = _ProcessEmitter()
        emitter.stateChanged.connect(main_window.handle_state)
        main_window.btn_run.setEnabled(True)

        with qtbot.waitSignal(emitter.stateChanged, timeout=SIGNAL_TIMEOUT) as blocker:
            emitter.stateChanged.emit(QtCore.QProcess.Starting)

        assert blocker.args == [QtCore.QProcess.Starting]
        assert not main_window.btn_run.isEnabled()

    def test_finished_signal_resets_progress(self, main_window, qtbot):
        emitter = _ProcessEmitter()
        emitter.finished.connect(main_window.process_finished)
        main_window.process = object()
        main_window.progress_bar.setValue(67)
        main_window.progress_label.setText("Running")

        with qtbot.waitSignal(emitter.finished, timeout=SIGNAL_TIMEOUT):
            emitter.finished.emit()

        assert main_window.process is None
        assert main_window.progress_bar.value() == 0
        assert main_window.progress_label.text() == ""


class TestToolHistoryPersistence:
    def test_save_tool_parameter_updates_history_list(self, main_window):
        main_window.set_tool("Centerline")
        params = {"in_line": "input.gpkg|layername=centerline"}

        def _set_history():
            from beratools.gui.bt_gui_main import bt

            bt.tool_history = ["Centerline", "Feature Buffer"]

        with (
            patch.object(main_window.tool_widget, "get_widgets_arguments", return_value=params),
            patch("beratools.gui.bt_gui_main.bt.add_tool_history") as mock_add_history,
            patch("beratools.gui.bt_gui_main.bt.save_tool_info") as mock_save_info,
            patch("beratools.gui.bt_gui_main.bt.get_tool_history", side_effect=_set_history),
        ):
            main_window.save_tool_parameter()

        mock_add_history.assert_called_once_with(main_window.tool_api, params)
        mock_save_info.assert_called_once()
        assert main_window.tool_history.list_model.stringList() == ["Centerline", "Feature Buffer"]

    def test_switch_away_and_back_restores_saved_parameter(self, main_window):
        from beratools.gui.bt_gui_main import bt
        from beratools.gui.tool_widgets import NumericInput

        saved_history = {}

        def _add_tool_history(tool_api, params):
            saved_history[tool_api] = dict(params)

        def _get_saved(self, tool_api, variable=None):
            tool_params = saved_history.get(tool_api, {})
            if variable is None:
                return tool_params
            return tool_params.get(variable)

        main_window.set_tool("Vertex Optimization")
        numerics = [w for w in main_window.tool_widget.widget_list if isinstance(w, NumericInput)]
        assert numerics
        target = numerics[0]
        saved_value = 42 if isinstance(target.default_value, int) else 42.0
        target.set_value(saved_value)

        with (
            patch("beratools.gui.bt_gui_main.bt.add_tool_history", side_effect=_add_tool_history),
            patch("beratools.gui.bt_gui_main.bt.save_tool_info"),
            patch.object(bt_data.BTData, "get_saved_tool_params", autospec=True, side_effect=_get_saved),
        ):
            main_window.save_tool_parameter()
            main_window.set_tool("Centerline")
            main_window.set_tool("Vertex Optimization")

        restored = [w for w in main_window.tool_widget.widget_list if isinstance(w, NumericInput)]
        restored_target = next((w for w in restored if w.variable == target.variable), restored[0])
        if isinstance(saved_value, float):
            assert restored_target.data_input.value() == pytest.approx(saved_value)
        else:
            assert restored_target.data_input.value() == saved_value


class TestErrorEdgeUi:
    def test_close_during_run_accept_kills_process(self, main_window, qtbot):
        exit_btn = _get_button_by_text(main_window, "Exit")
        fake_process = _FakeProcess()
        main_window.process = fake_process

        with patch(
            "beratools.gui.bt_gui_main.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ) as mock_question:
            qtbot.mouseClick(exit_btn, Qt.LeftButton)
            qtbot.waitUntil(lambda: not main_window.isVisible(), timeout=SIGNAL_TIMEOUT)

        assert fake_process.killed is True
        assert mock_question.called
        assert "Work in progress" in str(mock_question.call_args.args[2])

    def test_close_during_run_reject_keeps_open_and_does_not_kill(self, main_window, qtbot):
        exit_btn = _get_button_by_text(main_window, "Exit")
        fake_process = _FakeProcess()
        main_window.process = fake_process

        with patch(
            "beratools.gui.bt_gui_main.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ) as mock_question:
            qtbot.mouseClick(exit_btn, Qt.LeftButton)

        assert main_window.isVisible()
        assert fake_process.killed is False
        assert mock_question.called

    def test_custom_callback_updates_progress_and_log_text(self, main_window):
        main_window.custom_callback("57% finished tile")

        assert main_window.progress_bar.value() == 57
        assert "finished tile" in main_window.text_edit.toPlainText()

    def test_custom_callback_updates_progress_label(self, main_window):
        main_window.custom_callback("PROGRESS_LABELRunning centerline")

        assert main_window.progress_label.text() == "Running"

    def test_text_edit_remains_read_only_during_operations(self, main_window):
        assert main_window.text_edit.isReadOnly()
        main_window.custom_callback("10% working")
        main_window.process_finished()
        assert main_window.text_edit.isReadOnly()

    def test_clear_log_messages_empties_output(self, main_window):
        main_window.print_line_to_output("line one")
        main_window.print_line_to_output("line two")
        assert "line one" in main_window.text_edit.toPlainText()

        main_window.clear_log_messages()

        assert main_window.text_edit.toPlainText() == ""
        assert main_window.text_edit.isReadOnly()

    def test_log_context_menu_clear_action_clears_output(self, main_window):
        fake_menu = _FakeMenu()
        main_window.print_line_to_output("line one")

        with patch.object(main_window.text_edit, "createStandardContextMenu", return_value=fake_menu):
            main_window._show_log_context_menu(QtCore.QPoint(0, 0))

        assert "Clear Messages" in fake_menu.actions
        assert main_window.text_edit.toPlainText() == ""
