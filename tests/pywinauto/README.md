# GUI Tests (pywinauto)

Windows-only GUI tests for BERA Tools using [pywinauto](https://pywinauto.readthedocs.io/).
Launches the app as a subprocess and interacts via the Windows UIA automation backend.

> For cross-platform tests, see `tests/pytest_qt/` which uses pytest-qt instead.

## Requirements

- **Windows only** (pywinauto uses Windows UI Automation)
- A display (cannot run headless)
- Test data in `tests/data/` (`integration_aoi.gpkg`, `chm_aoi.tif`)

```bash
pip install pywinauto
```

## Running Tests

```bash
# Run all pywinauto GUI tests
python -m pytest tests/pywinauto/ -v -m gui

# Run only tool selection tests
python -m pytest tests/pywinauto/test_gui_tools.py -v -k "test_select_tool" -m gui

# Run only form-filling tests
python -m pytest tests/pywinauto/test_gui_tools.py -v -k "test_fill_form" -m gui

# Skip pywinauto GUI tests when running the full suite
python -m pytest tests/ --ignore=tests/pywinauto
```

## Test Structure

| File | Description |
|---|---|
| `conftest.py` | Fixtures: `bera_app` (subprocess launch + pywinauto connect), helper functions for widget interaction |
| `gui_test_config.py` | Test data paths, parameter type lookup, `make_test_data()` factory |
| `test_gui_tools.py` | Window basics, tool selection, form filling per tool, file dialog, numeric/boolean/option inputs, slider, load defaults |

## How It Works

1. `bera_app` fixture launches BERA Tools GUI as a subprocess
2. Connects via `pywinauto.Application(backend="uia")`
3. Helper functions (`select_tool`, `fill_tool_form`, `set_numeric`, etc.) interact with widgets through the UIA control tree
4. Tests fill forms and verify UI state — they do **not** run actual tools
5. On teardown, the app is closed gracefully (handling the confirmation dialog) then force-killed

## Notes

- Tests use the `gui` pytest marker.
- The app signals readiness via a temp file flag (`BERA_SPLASH_READY` env var).
- File dialog handling supports both native Windows (`#32770`) and Qt non-native dialogs.
- Widget identification relies on control type and index; adding `objectName` to widgets would improve reliability.
