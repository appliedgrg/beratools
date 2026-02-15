"""
GUI test fixtures: app launch/teardown and helper functions.

Requires:
    - pywinauto: pip install pywinauto
    - A display (cannot run headless)
    - Test data in tests/data/ (integration_aoi.gpkg, chm_aoi.tif)

Run with:
    python -m pytest tests/pywinauto/ -v -m gui
Skip with:
    python -m pytest tests/ --ignore=tests/pywinauto
"""

import os
import subprocess
import sys
import time
import importlib
import re
from pathlib import Path

import pytest


def _import_pywinauto():
    """Import real pywinauto package without local test-path shadowing."""
    tests_dir = Path(__file__).resolve().parents[1]
    removed_entries = []

    for idx, entry in enumerate(list(sys.path)):
        try:
            if Path(entry).resolve() == tests_dir:
                removed_entries.append((idx, entry))
        except Exception:
            continue

    for _, entry in removed_entries:
        while entry in sys.path:
            sys.path.remove(entry)

    pwa_pkg = None
    pwa_app = None
    pwa_keyboard = None

    try:
        pwa_pkg = importlib.import_module("pywinauto")
        pwa_app = importlib.import_module("pywinauto.application")
        pwa_keyboard = importlib.import_module("pywinauto.keyboard")
    except ModuleNotFoundError as exc:
        raise ImportError(
            "pywinauto is required for tests/pywinauto. Install it with: pip install pywinauto"
        ) from exc
    finally:
        for idx, entry in sorted(removed_entries, key=lambda x: x[0]):
            sys.path.insert(idx, entry)

    assert pwa_pkg is not None and pwa_app is not None and pwa_keyboard is not None
    return pwa_app.Application, pwa_pkg.Desktop, pwa_pkg.timings, pwa_keyboard.send_keys


Application, Desktop, timings, send_keys = _import_pywinauto()

from gui_test_config import PARAM_TYPES, TOOL_PARAM_LABELS, make_test_data

timings.Timings.window_find_timeout = 15
timings.Timings.app_start_timeout = 20


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def output_dir(tmp_path_factory):
    """Temporary directory for GUI test output files."""
    return tmp_path_factory.mktemp("gui_output")


@pytest.fixture(scope="session")
def testdata_dir():
    return Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="session")
def test_data(testdata_dir, output_dir):
    """Test data dict for all tools."""
    return make_test_data(testdata_dir, output_dir)


@pytest.fixture(scope="session")
def bera_app():
    """Launch BERA Tools GUI and return the main window wrapper.

    The app is started as a subprocess and connected via pywinauto UIA backend.
    Killed automatically after the test session ends.
    """
    ready_flag = Path(os.getenv("TEMP", ".")) / "bera_gui_test_ready.flag"
    if ready_flag.exists():
        ready_flag.unlink()

    env = os.environ.copy()
    env["BERA_SPLASH_READY"] = str(ready_flag)

    proc = subprocess.Popen(
        [sys.executable, "-c", "from beratools.gui.bt_gui_main import runner; runner()"],
        env=env,
    )

    # Wait for the app to signal readiness
    for _ in range(300):
        if ready_flag.exists():
            break
        time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("BERA Tools GUI did not start within 30 seconds")

    app = Application(backend="uia").connect(process=proc.pid)
    main = app.window(title="BERA Tools")
    main.wait("visible enabled", timeout=20)
    main.set_focus()

    yield main

    # Teardown: close gracefully, then force-kill
    try:
        main.close()
        # Handle the "Are you sure" confirmation dialog
        time.sleep(0.5)
        try:
            confirm = app.window(title="Confirmation:")
            if confirm.exists(timeout=2):
                confirm.child_window(title="Yes", control_type="Button").click_input()
        except Exception:
            pass
    except Exception:
        pass
    finally:
        proc.kill()
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Helper functions for widget interaction
# ---------------------------------------------------------------------------


def select_tool(main, tool_name: str):
    """Select a tool from the tree view using the search box."""
    search = main.child_window(control_type="Edit", found_index=0)
    search.wait("visible enabled", timeout=10)
    search.set_edit_text("")
    time.sleep(0.3)
    search.set_edit_text(tool_name)
    time.sleep(0.5)

    tree = main.child_window(control_type="Tree", found_index=0)
    tree.wait("visible enabled", timeout=10)
    item = tree.child_window(title=tool_name, control_type="TreeItem")
    item.wait("visible", timeout=10)
    item.click_input()
    time.sleep(0.5)

    # Clear search to restore full tree
    search.set_edit_text("")
    time.sleep(0.3)


def _first_visible_enabled(widgets):
    for widget in widgets:
        try:
            if widget.is_visible() and widget.is_enabled():
                return widget
        except Exception:
            continue
    return widgets[0] if widgets else None


def _find_row_by_label(main, param_label: str):
    try:
        label = main.child_window(title=param_label, control_type="Text")
        label.wait("visible", timeout=3)
        return label.parent()
    except Exception:
        pass

    escaped = re.escape(param_label)
    label = main.child_window(title_re=rf".*{escaped}.*", control_type="Text")
    label.wait("visible", timeout=5)
    return label.parent()


def _visible_descendants(parent, control_type: str):
    try:
        widgets = parent.descendants(control_type=control_type)
    except Exception:
        return []

    visible = []
    for widget in widgets:
        try:
            if widget.is_visible() and widget.is_enabled():
                visible.append(widget)
        except Exception:
            continue
    return visible


def _wait_visible_enabled(ctrl, timeout: float = 5.0):
    """Wait for a control to become visible and enabled."""
    if hasattr(ctrl, "wait"):
        ctrl.wait("visible enabled", timeout=timeout)
        return

    end = time.time() + timeout
    while time.time() < end:
        try:
            if ctrl.is_visible() and ctrl.is_enabled():
                return
        except Exception:
            pass
        time.sleep(0.1)

    raise TimeoutError("Control did not become visible and enabled")


def _ensure_advanced_options_visible(main):
    """Show advanced options if currently hidden."""
    try:
        btn = main.child_window(title_re=".*Advanced Options.*", control_type="Button")
        btn.wait("visible enabled", timeout=3)
        if btn.window_text().strip().lower().startswith("show"):
            btn.click_input()
            time.sleep(0.4)
    except Exception:
        pass


def click_browse_and_set_file(main, param_label: str, file_path: str):
    """Click the '...' browse button next to a label and set a file path.

    Handles both native Windows (#32770) and Qt non-native file dialogs.
    Types the full absolute path into the filename edit — no folder navigation.
    """
    btn = None

    try:
        parent = _find_row_by_label(main, param_label)
        row_buttons = _visible_descendants(parent, "Button")
        for candidate in row_buttons:
            if candidate.window_text().strip() == "...":
                btn = candidate
                break
    except Exception:
        btn = None

    if btn is None:
        all_buttons = _visible_descendants(main, "Button")
        for candidate in all_buttons:
            if candidate.window_text().strip() == "...":
                btn = candidate
                break

    if btn is None:
        raise RuntimeError(f"Could not find browse button for label: {param_label}")

    btn.click_input()
    time.sleep(0.5)

    _handle_file_dialog(file_path)


def _handle_file_dialog(file_path: str):
    """Type a full file path into a file dialog and confirm."""
    # Try native Windows dialog first
    try:
        dlg = Desktop(backend="uia").window(class_name="#32770")
        dlg.wait("visible", timeout=5)
        dlg.set_focus()

        # File name edit (auto_id 1148 on English Windows)
        try:
            filename_edit = dlg.child_window(auto_id="1148", control_type="Edit")
            filename_edit.wait("visible", timeout=3)
            filename_edit.set_edit_text(file_path)
        except Exception:
            # Fallback: type path via keyboard
            send_keys(file_path, with_spaces=True)

        time.sleep(0.3)

        # Click Open or press Enter
        try:
            open_btn = dlg.child_window(title="Open", control_type="Button")
            open_btn.click_input()
        except Exception:
            try:
                save_btn = dlg.child_window(title="Save", control_type="Button")
                save_btn.click_input()
            except Exception:
                send_keys("{ENTER}")
        time.sleep(0.5)
        return
    except Exception:
        pass

    # Fallback: Qt non-native dialog
    try:
        dlg = Desktop(backend="uia").window(title_re="Open|Save|Select")
        dlg.wait("visible", timeout=5)
        dlg.set_focus()
        edits = dlg.descendants(control_type="Edit")
        if edits:
            edits[-1].set_edit_text(file_path)
        else:
            send_keys(file_path, with_spaces=True)

        try:
            dlg.child_window(title="Open", control_type="Button").click_input()
        except Exception:
            send_keys("{ENTER}")
        time.sleep(0.5)
    except Exception:
        # Last resort: just type and press enter
        send_keys(file_path, with_spaces=True)
        send_keys("{ENTER}")
        time.sleep(0.5)


def select_gpkg_layer(main, layer_name: str, combo_index: int = 1):
    """Select a layer from the gpkg layer combobox.

    The combo items are formatted as 'layer_name (geometry_type)'.
    Matches by layer_name substring.
    """
    visible_combos = _visible_descendants(main, "ComboBox")
    for combo in visible_combos:
        try:
            items = combo.texts()
            for item_text in items:
                if layer_name in item_text:
                    combo.select(item_text)
                    return
        except Exception:
            continue

    combo = main.child_window(control_type="ComboBox", found_index=combo_index)
    combo.wait("visible enabled", timeout=10)

    # Fallback: click and type
    combo.click_input()
    send_keys(layer_name, with_spaces=True)
    send_keys("{ENTER}")


def set_checkbox(main, name_substring: str, checked: bool):
    """Set a QCheckBox by matching part of its title text."""
    cb = None
    try:
        parent = _find_row_by_label(main, name_substring)
        cb = _first_visible_enabled(parent.descendants(control_type="CheckBox"))
    except Exception:
        cb = None

    if cb is None:
        cb = main.child_window(title_re=f".*{name_substring}.*", control_type="CheckBox")

    _wait_visible_enabled(cb, timeout=5)
    current = cb.get_toggle_state()  # 0=unchecked, 1=checked
    if (current == 1) != checked:
        cb.toggle()


def set_option_combo(main, option_text: str, combo_index: int = 0, param_label: str | None = None):
    """Select an item from a QComboBox dropdown."""
    combo = None

    if param_label:
        try:
            parent = _find_row_by_label(main, param_label)
            combo = _first_visible_enabled(parent.descendants(control_type="ComboBox"))
        except Exception:
            combo = None

    if combo is None:
        visible_combos = _visible_descendants(main, "ComboBox")
        if combo_index < len(visible_combos):
            combo = visible_combos[combo_index]
        else:
            combo = main.child_window(control_type="ComboBox", found_index=combo_index)

    _wait_visible_enabled(combo, timeout=5)
    try:
        combo.select(str(option_text))
    except Exception:
        combo.click_input()
        send_keys(str(option_text), with_spaces=True)
        send_keys("{ENTER}")


def set_numeric(main, value, spinner_index: int = 0, param_label: str | None = None):
    """Set a QSpinBox or QDoubleSpinBox value."""
    spinner = None
    edit = None

    if param_label:
        try:
            parent = _find_row_by_label(main, param_label)
            edit = _first_visible_enabled(parent.descendants(control_type="Edit"))
            spinner = _first_visible_enabled(parent.descendants(control_type="Spinner"))
        except Exception:
            edit = None
            spinner = None

    if edit is not None:
        edit.set_edit_text(str(value))
        send_keys("{ENTER}")
        return

    if spinner is None:
        visible_spinners = _visible_descendants(main, "Spinner")
        if spinner_index < len(visible_spinners):
            spinner = visible_spinners[spinner_index]
        else:
            raise AssertionError(f"Spinner index {spinner_index} not available among visible controls")

    _wait_visible_enabled(spinner, timeout=5)
    try:
        spinner.set_value(value)
    except Exception:
        spinner.click_input()
        send_keys("^a{BACKSPACE}" + str(value) + "{ENTER}", with_spaces=True)


def set_slider(main, value: int):
    """Set the CPU cores slider."""
    slider = main.child_window(control_type="Slider", found_index=0)
    slider.wait("visible enabled", timeout=5)
    try:
        slider.set_value(value)
    except Exception:
        slider.click_input()
        send_keys("{HOME}")
        for _ in range(value - 1):
            send_keys("{RIGHT}")


def click_button(main, title: str):
    """Click a button by its title text."""
    btn = main.child_window(title=title, control_type="Button")
    btn.wait("visible enabled", timeout=5)
    btn.click_input()


def fill_tool_form(main, tool_name: str, params: dict):
    """Generic form filler: select a tool and fill all its parameter widgets.

    Args:
        main: pywinauto main window wrapper.
        tool_name: Tool name as shown in the tree view.
        params: Dict of variable -> value. File params use
                {"path": "...", "layer": "..."} dicts.
    """
    select_tool(main, tool_name)
    _ensure_advanced_options_visible(main)

    spinner_idx = 0
    combo_idx = 0

    for variable, value in params.items():
        ptype_info = PARAM_TYPES.get(variable)
        if ptype_info is None:
            continue

        param_label = str(TOOL_PARAM_LABELS.get(tool_name, {}).get(variable, variable))

        ptype = ptype_info["type"]
        subtype = ptype_info.get("subtype", "")

        if ptype == "file":
            # value is {"path": "...", "layer": "..."} or {"path": "..."}
            if isinstance(value, dict):
                file_path = value["path"]
                layer = value.get("layer", "")
            else:
                file_path = str(value)
                layer = ""

            # Find label for this variable from beratools.json mapping
            # For now, use the browse button approach with known labels
            # This will be refined when objectNames are added
            _set_file_by_variable(main, variable, file_path, layer, param_label=param_label)

        elif ptype == "number":
            set_numeric(main, value, spinner_index=spinner_idx, param_label=param_label)
            spinner_idx += 1

        elif ptype == "list" and subtype == "bool":
            set_checkbox(main, param_label, bool(value))

        elif ptype == "list":
            set_option_combo(main, str(value), combo_index=combo_idx, param_label=param_label)
            combo_idx += 1


def _set_file_by_variable(
    main, variable: str, file_path: str, layer: str = "", param_label: str | None = None
):
    """Set a file path by finding the browse button for a given variable.

    Falls back to setting the QLineEdit text directly if the browse
    button approach fails.
    """
    # Prefer setting by UI label row to avoid index/order fragility.
    if param_label:
        try:
            parent = _find_row_by_label(main, param_label)
            edit = _first_visible_enabled(parent.descendants(control_type="Edit"))
            if edit is not None:
                edit.set_edit_text(file_path)
                if layer and file_path.lower().endswith(".gpkg"):
                    time.sleep(0.5)
                    select_gpkg_layer(main, layer)
                return
        except Exception:
            pass

    # Try setting the QLineEdit directly (faster, no dialog needed)
    try:
        edits = main.descendants(control_type="Edit")
        for edit in edits:
            try:
                name = edit.element_info.automation_id
                if variable in str(name):
                    edit.set_edit_text(file_path)
                    if layer and file_path.lower().endswith(".gpkg"):
                        time.sleep(0.5)
                        select_gpkg_layer(main, layer)
                    return
            except Exception:
                continue
    except Exception:
        pass

    # Fallback: try all Edit controls and match by position
    # This is a last resort — adding objectNames to widgets is strongly recommended
    edits = main.descendants(control_type="Edit")
    for edit in edits:
        try:
            current_text = edit.get_value()
            if current_text == "" or file_path in current_text:
                edit.set_edit_text(file_path)
                if layer and file_path.lower().endswith(".gpkg"):
                    time.sleep(0.5)
                    select_gpkg_layer(main, layer)
                return
        except Exception:
            continue
