# GUI Tests (pytest-qt)

Cross-platform GUI tests for BERA Tools using [pytest-qt](https://pytest-qt.readthedocs.io/).
Drives Qt widgets in-process via `qtbot` — no subprocess, no display automation required.

## Requirements

```bash
pip install pytest pytest-qt
# or install all dev dependencies:
pip install -e ".[dev]"
```

## Running Tests

```bash
# Headless (recommended for CI)
# Windows cmd:
set QT_QPA_PLATFORM=offscreen && python -m pytest tests/pytest_qt/ -v -m gui_qt

# PowerShell:
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/pytest_qt/ -v -m gui_qt

# Run all pytest-qt GUI tests (non-headless local run)
python -m pytest tests/pytest_qt/ -v -m gui_qt

# Run only widget unit tests
python -m pytest tests/pytest_qt/test_tool_widgets.py -v -m gui_qt

# Run only MainWindow tests
python -m pytest tests/pytest_qt/test_main_window.py -v -m gui_qt

# Run only per-tool form round-trip tests
python -m pytest tests/pytest_qt/test_tool_forms.py -v -m gui_qt

# Run a specific test class or method
python -m pytest tests/pytest_qt/test_tool_widgets.py::TestKeyboardInput -v -m gui_qt
python -m pytest tests/pytest_qt/test_tool_forms.py::TestCenterline::test_round_trip -v -m gui_qt
```

## Usage Notes

- Tests use marker `gui_qt` (registered in `conftest.py`), so use `-m gui_qt` for this suite.
- Use `SIGNAL_TIMEOUT` from `conftest.py` for `qtbot.waitSignal`/`qtbot.waitUntil` in new tests.
- Prefer user-visible assertions first (text, button state, visibility, progress), then internal call assertions.
- Avoid `time.sleep()` in GUI tests; use `waitSignal`/`waitUntil`.

## Test Structure

| File | Description |
|---|---|
| `conftest.py` | Shared fixtures and constants (`SIGNAL_TIMEOUT`, patched dialogs/browser/layers, widget factories, `main_window`) |
| `test_tool_widgets.py` | Widget-level tests: NumericInput/BooleanInput/OptionsInput/FileSelector, dialog interaction, layer-combo behavior, signal payloads, keyboard input |
| `test_main_window.py` | MainWindow interaction tests: button clicks, tree/search, keyboard search, process signals, error/edge UI paths, slider behavior, tool history/persistence |
| `test_tool_forms.py` | Per-tool form construction and `get_widgets_arguments()` round-trip checks across tool configs |

## Test Files (Brief)

- `tests/pytest_qt/conftest.py`: central fixtures, factories, marker registration, and shared timeout.
- `tests/pytest_qt/test_tool_widgets.py`: focused widget behavior and signal tests, including FileSelector browse/cancel/vector-layer cases.
- `tests/pytest_qt/test_main_window.py`: end-user interaction flows on `MainWindow` (run/cancel/exit/help/defaults/advanced), process and progress behavior, slider, and persistence.
- `tests/pytest_qt/test_tool_forms.py`: tool-form smoke/round-trip coverage for configured BERA tools.

## Notes

- Skip this suite with: `python -m pytest tests/ --ignore=tests/pytest_qt`
- FileSelector vector-layer tests patch `beratools.gui.tool_widgets.get_layers`; no real geodata files are required.
- MainWindow help/open-url behavior is patched in tests to avoid real browser launches.
