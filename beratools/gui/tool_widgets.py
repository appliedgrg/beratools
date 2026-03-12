"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide all kinds of widgets for tool parameters.
"""

import json
import sys
from collections import OrderedDict
from pathlib import Path

import pyogrio
from numpy import ndarray
from PyQt5 import QtCore, QtWidgets

from beratools.gui.geometry_types import (
    format_expected_families,
    get_allowed_geometry_families,
    is_geometry_compatible,
    parse_subtype_tokens,
)

BT_LABEL_MIN_WIDTH = 130


class ToolWidgets(QtWidgets.QWidget):
    """ToolWidgets class for creating widgets for tool parameters."""

    signal_save_tool_params = QtCore.pyqtSignal(object)

    def __init__(self, tool_name, tool_args, show_advanced, bt_data_obj=None, parent=None):
        super(ToolWidgets, self).__init__(parent)

        self.tool_name = tool_name
        self.show_advanced = show_advanced
        self.current_tool_api = ""
        self.bt_data = bt_data_obj
        self.widget_list = []
        self.ui_widget_list = []
        self.widgets_by_variable = {}
        self._depends_on_specs = {}
        self._inline_controllers = {}
        self.setWindowTitle("Tool widgets")

        self.create_widgets(tool_args)
        layout = QtWidgets.QVBoxLayout()

        for item in self.ui_widget_list:
            layout.addWidget(item)

        self.save_button = QtWidgets.QPushButton("Save Parameters")
        self.save_button.clicked.connect(self.save_tool_parameters)
        self.save_button.setFixedSize(200, 50)
        layout.addSpacing(20)
        self.setLayout(layout)

    def get_widgets_arguments(self):
        args = {}
        param_missing = False
        for widget in self.widget_list:
            v = widget.get_value()
            if v:
                args.update(v)
            else:
                print(f"[Missing argument]: {widget.name} not specified.", "missing")
                param_missing = True

        if param_missing:
            args = None

        return args

    def create_widgets(self, tool_args):
        valid_types = {"number", "file", "list", "text", "directory"}
        for p in tool_args:
            # Validate parameter type is not a subtype value
            sub_type = p.get("type", None)
            if sub_type and sub_type not in valid_types:
                print(f"Invalid sub type '{sub_type}' for '{p.get('label', '')}'. ")
                continue

            json_str = json.dumps(p, sort_keys=True, indent=2, separators=(",", ": "))
            pt = p["parameter_type"]
            widget = None

            if "ExistingFile" in pt or "NewFile" in pt or "Directory" in pt:
                widget = FileSelector(json_str, None, bt_data_obj=self.bt_data)
            elif "FileList" in pt:
                widget = MultiFileSelector(json_str, None)
            elif "Boolean" in pt:
                widget = BooleanInput(json_str)
            elif "OptionList" in pt:
                option_list = p["parameter_type"].get("OptionList", [])
                # Check if OptionList contains only boolean values (handle both string and bool types)
                is_bool_list = (
                    option_list == ["True", "False"]
                    or option_list == ["true", "false"]
                    or option_list == [True, False]
                    or option_list == [False, True]
                )
                if is_bool_list:
                    widget = BooleanInput(json_str)
                else:
                    widget = OptionsInput(json_str)
            elif "float" in pt or "int" in pt:
                widget = NumericInput(json_str)
            else:
                msg_box = QtWidgets.QMessageBox()
                msg_box.setIcon(QtWidgets.QMessageBox.Warning)
                msg_box.setText("Unsupported parameter type: {}.".format(pt))
                msg_box.exec()

            param_value = None
            if "saved_value" in p.keys():
                param_value = p["saved_value"]
            if param_value is None:
                param_value = p["default_value"]
            if param_value is "":
                param_value = p["default_value"]
            if param_value is not None:
                if type(widget) is OptionsInput:
                    widget.set_value(param_value)
                elif widget:
                    widget.set_value(param_value)
            else:
                print("No default value found: {}".format(p["name"]))

            # hide optional widgets
            if widget:
                self._set_widget_tooltip(widget)
                widget.depends_on = p.get("depends_on")
                widget.unit = p.get("unit", "")
                self.widgets_by_variable[widget.variable] = widget

                if widget.optional and widget.label:
                    widget.label.setStyleSheet(
                        "QtWidgets.QLabel { background-color : transparent; color : blue; }"
                    )

                if not self.show_advanced and widget.optional:
                    widget.hide()

            self.widget_list.append(widget)

        self._configure_widget_dependencies()
        self._clear_output_paths_for_missing_input_history()

    @staticmethod
    def _extract_file_selector_path(value):
        if isinstance(value, dict):
            return value.get("path", "")
        if isinstance(value, str) and "|" in value:
            return value.rsplit("|", 1)[0]
        if isinstance(value, str):
            return value
        return ""

    def _clear_output_paths_for_missing_input_history(self):
        missing_input_paths = set()

        for widget in self.widget_list:
            if not isinstance(widget, FileSelector) or widget.output:
                continue
            saved_path = self._extract_file_selector_path(widget.saved_value)
            current_path = widget.value.get("path", "") if widget.is_vector else widget.value
            if saved_path and not current_path:
                missing_input_paths.add(saved_path)

        if not missing_input_paths:
            return

        for widget in self.widget_list:
            if not isinstance(widget, FileSelector) or not widget.output:
                continue
            current_path = widget.value.get("path", "") if widget.is_vector else widget.value
            if current_path in missing_input_paths:
                if widget.is_vector:
                    widget.set_value({"path": "", "layer": ""})
                else:
                    widget.set_value("")

    def update_widgets(self, values_dict):
        for key, value in values_dict.items():
            for item in self.widget_list:
                if key == item.variable:
                    item.set_value(value)

    def save_tool_parameters(self):
        params = {}
        for item in self.widget_list:
            if item.variable:
                params[item.variable] = item.get_value()

        self.signal_save_tool_params.emit(params)

    def load_default_args(self):
        for item in self.widget_list:
            item.set_default_value()

    def _set_widget_tooltip(self, widget):
        description = getattr(widget, "description", "")
        if description:
            widget.setToolTip(description)

    def _configure_widget_dependencies(self):
        self.ui_widget_list = [widget for widget in self.widget_list if widget]
        self._depends_on_specs = {}
        self._inline_controllers = {}
        inline_controller_widgets = []

        for widget in self.widget_list:
            if not widget:
                continue

            depends_on = getattr(widget, "depends_on", None)
            if not isinstance(depends_on, dict):
                continue

            mode = depends_on.get("mode", "hide")
            controller_vars = []
            if "conditions" in depends_on:
                for condition in depends_on.get("conditions", []):
                    variable = condition.get("variable")
                    if variable:
                        controller_vars.append(variable)
            else:
                controller_var = depends_on.get("variable")
                if controller_var:
                    controller_vars.append(controller_var)

            if not controller_vars or widget.variable in controller_vars:
                print(f"[Warning] Invalid depends_on for '{widget.variable}'. Widget will remain visible.")
                continue

            controller_widgets = []
            missing_vars = []
            for controller_var in controller_vars:
                controller_widget = self.widgets_by_variable.get(controller_var)
                if controller_widget is None:
                    missing_vars.append(controller_var)
                else:
                    controller_widgets.append(controller_widget)

            if missing_vars:
                print(
                    f"[Warning] Missing depends_on controller(s) {missing_vars} for '{widget.variable}'. Widget will remain visible."
                )
                continue

            if mode == "inline":
                if "conditions" in depends_on or len(controller_vars) != 1:
                    print(
                        f"[Warning] Inline depends_on for '{widget.variable}' requires exactly one controller variable. Widget remains separate."
                    )
                elif controller_vars[0] in self._inline_controllers:
                    print(
                        f"[Warning] Multiple inline dependents for '{controller_vars[0]}' are not supported. '{widget.variable}' remains separate."
                    )
                elif self._attach_inline_widget(controller_widgets[0], widget):
                    self._inline_controllers[controller_vars[0]] = widget.variable
                    inline_controller_widgets.append(controller_widgets[0])
                    if widget in self.ui_widget_list:
                        self.ui_widget_list.remove(widget)

            self._depends_on_specs[widget.variable] = depends_on
            for controller_widget in controller_widgets:
                self._connect_widget_change_signal(controller_widget, self._update_dependency_states)

        self._align_inline_controller_checkboxes(inline_controller_widgets)
        self._update_dependency_states()

    @staticmethod
    def _align_inline_controller_checkboxes(controller_widgets):
        unique_widgets = []
        seen_ids = set()
        for widget in controller_widgets:
            widget_id = id(widget)
            if widget_id in seen_ids:
                continue
            seen_ids.add(widget_id)
            unique_widgets.append(widget)

        if not unique_widgets:
            return

        max_width = 0
        for controller in unique_widgets:
            if isinstance(controller, BooleanInput):
                max_width = max(max_width, controller.checkbox.sizeHint().width())

        if max_width <= 0:
            return

        aligned_width = max_width + 8
        for controller in unique_widgets:
            if isinstance(controller, BooleanInput):
                controller.checkbox.setMinimumWidth(aligned_width)

    def _attach_inline_widget(self, controller_widget, dependent_widget):
        controller_layout = self._get_widget_layout(controller_widget)
        if controller_layout is None:
            return False

        dependent_widget.set_inline_mode(getattr(dependent_widget, "unit", ""))
        insert_index = controller_layout.count()
        if insert_index > 0:
            last_item = controller_layout.itemAt(insert_index - 1)
            if last_item and last_item.spacerItem() is not None:
                insert_index -= 1
        controller_layout.insertWidget(insert_index, dependent_widget)
        return True

    @staticmethod
    def _get_widget_layout(widget):
        layout_obj = getattr(widget, "layout", None)
        if isinstance(layout_obj, QtWidgets.QLayout):
            return layout_obj
        if callable(layout_obj):
            return layout_obj()
        return None

    @staticmethod
    def _connect_widget_change_signal(widget, callback):
        if getattr(widget, "_depends_on_signal_connected", False):
            return

        if isinstance(widget, BooleanInput):
            widget.checkbox.stateChanged.connect(callback)
            widget._depends_on_signal_connected = True
            return

        if isinstance(widget, OptionsInput):
            widget.combobox.currentIndexChanged.connect(callback)
            widget._depends_on_signal_connected = True
            return

        if isinstance(widget, NumericInput):
            if widget.data_input is not None:
                widget.data_input.valueChanged.connect(callback)
                widget._depends_on_signal_connected = True
                return

        if isinstance(widget, FileSelector):
            widget.in_file.textChanged.connect(callback)
            widget._depends_on_signal_connected = True

    def _get_widget_value(self, variable):
        widget = self.widgets_by_variable.get(variable)
        if widget is None:
            return None
        value_dict = widget.get_value()
        if isinstance(value_dict, dict):
            return value_dict.get(variable)
        return value_dict

    @staticmethod
    def _value_matches_condition(current_value, expected_value):
        if isinstance(expected_value, bool) and isinstance(current_value, str):
            return (current_value.lower() in ("true", "1", "yes", "on")) == expected_value
        return current_value == expected_value

    def _resolve_depends_on(self, widget, depends_on):
        if "conditions" in depends_on:
            logic = depends_on.get("logic", "or").lower()
            conditions = depends_on.get("conditions", [])
            results = []
            for condition in conditions:
                variable = condition.get("variable")
                expected = condition.get("condition")
                current = self._get_widget_value(variable)
                results.append(self._value_matches_condition(current, expected))
            if logic == "and":
                return all(results)
            return any(results)

        variable = depends_on.get("variable")
        expected = depends_on.get("condition")
        current = self._get_widget_value(variable)
        return self._value_matches_condition(current, expected)

    def _update_dependency_states(self, *_):
        visibility_changed = False
        for variable, depends_on in self._depends_on_specs.items():
            widget = self.widgets_by_variable.get(variable)
            if widget is None:
                continue

            is_active = self._resolve_depends_on(widget, depends_on)
            mode = depends_on.get("mode", "hide")
            if mode == "inline":
                widget.setEnabled(is_active)
            else:
                was_visible = widget.isVisible()
                if not self.show_advanced and widget.optional:
                    widget.setVisible(False)
                else:
                    widget.setVisible(is_active)
                if was_visible != widget.isVisible():
                    visibility_changed = True

        if visibility_changed:
            current_layout = self.layout()
            if current_layout is not None:
                current_layout.invalidate()
                current_layout.activate()
            self.updateGeometry()
            self.update()


def get_layers(gpkg_file):
    try:
        # Get the list of layers and their geometry types from the GeoPackage file
        layers_info = pyogrio.list_layers(gpkg_file)

        # Check if layers_info is in the expected format
        if isinstance(layers_info, ndarray) and all(
            isinstance(layer, ndarray) and len(layer) >= 2 for layer in layers_info
        ):
            # Create a dictionary where the key is the layer name
            # and the value is the geometry type
            layers_dict = OrderedDict((layer[0], layer[1]) for layer in layers_info)
            return layers_dict
        else:
            # If the format is not correct, raise an exception with a detailed message
            raise ValueError("Expected a list of lists or tuples with layer name and geometry type.")

    except Exception as e:
        print(f"Error retrieving layers from GeoPackage '{gpkg_file}': {e}")
        raise


class FileSelector(QtWidgets.QWidget):
    """FileSelector class for creating file selection widgets."""

    VECTOR_FORMATS = {"gpkg": ["vector"], "shp": ["vector"]}
    NO_COMPATIBLE_LAYER_TEXT = "(No compatible layers)"

    @staticmethod
    def has_vector_subtype(param_type):
        if isinstance(param_type, dict):
            for v in param_type.values():
                tokens = parse_subtype_tokens(v)
                if "vector" in tokens:
                    return True
        return False

    def __init__(self, json_str, parent=None, bt_data_obj=None):
        super(FileSelector, self).__init__(parent)
        self.bt_data = bt_data_obj
        self.selected_layer = ""
        self.parse_params(json_str)
        self.initialize_values()
        self.handle_vector_io()
        self.setup_ui()

    def parse_params(self, json_str):
        params = json.loads(json_str)
        self.name = params["name"]
        self.description = params["description"]
        self.variable = params["variable"]
        self.gpkg_layers = None
        self.output = params["output"]
        self.parameter_type = params["parameter_type"]

        self.file_type = ""
        if "ExistingFile" in self.parameter_type:
            self.file_type = params["parameter_type"]["ExistingFile"]
        elif "NewFile" in self.parameter_type:
            self.file_type = params["parameter_type"]["NewFile"]

        if isinstance(self.file_type, str):
            self.file_type = [self.file_type]
        elif not isinstance(self.file_type, list):
            self.file_type = list(self.file_type)
        self.file_type = parse_subtype_tokens(self.file_type)
        self.allowed_geometry_families = get_allowed_geometry_families(self.file_type)

        self.optional = params["optional"]
        self.default_value = params["default_value"]
        self.saved_value = params.get("saved_value", None)
        self.is_vector = self.has_vector_subtype(self.parameter_type)
        self.input_geometry_error = ""
        self.filtered_gpkg_layers = OrderedDict()

    def initialize_values(self):
        # Use dict for vector values
        if self.is_vector:
            val = self.saved_value if self.saved_value is not None else self.default_value
            # Handle case where saved_value is already a dict (from previous saves)
            if isinstance(val, dict):
                self.value = val
            elif val and isinstance(val, str) and "|" in val:
                path, layer = val.rsplit("|", 1)
                self.value = {"path": path, "layer": layer}
            else:
                self.value = {"path": val if val else "", "layer": ""}
        else:
            self.value = self.saved_value if self.saved_value is not None else self.default_value

    def handle_vector_io(self):
        if not self.is_vector:
            return
        path = self.value["path"]
        layer = self.value["layer"]
        ext = Path(path).suffix.lower().replace(".", "")
        if ext not in self.VECTOR_FORMATS:
            return
        gpkg_path = Path(path)
        dir_exists = gpkg_path.parent.exists()
        file_exists = gpkg_path.exists()
        if self.output:
            # Output: preserve path/layer even if file doesn't exist
            pass
        else:
            # Input: validate file/directory existence
            if not file_exists:
                self.value = {"path": "", "layer": ""}
                print(f"[Error] Invalid Input: File does not exist: {path}")
                return
            elif not dir_exists:
                self.value = {"path": "", "layer": ""}
                print(f"[Error] Invalid Input: Directory does not exist for file: {path}")
                return
            elif ext == "gpkg":
                try:
                    layers_dict = get_layers(path)
                    if layer:
                        valid_layers = [str(k) for k in layers_dict.keys()]
                        if layer not in valid_layers:
                            self.value = {"path": "", "layer": ""}
                            print(f"[Error] Invalid Layer: Layer '{layer}' not found in file: {path}")
                except Exception:
                    self.value = {"path": "", "layer": ""}
                    print(f"[Error] Layer Error: Could not load layers from file: {path}")

    def setup_ui(self):
        self.layout = QtWidgets.QHBoxLayout()
        self.label = QtWidgets.QLabel(self.name)
        self.label.setMinimumWidth(200)
        if self.is_vector:
            self.in_file = QtWidgets.QLineEdit(self.value["path"])
        else:
            self.in_file = QtWidgets.QLineEdit(self.value)
        self.btn_select = QtWidgets.QPushButton("...")
        self.btn_select.clicked.connect(self.select_file)
        self.layer_combo = QtWidgets.QComboBox()
        self.layer_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
        self.layer_combo.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed)
        self.layer_combo.setVisible(False)
        self.layer_combo.currentTextChanged.connect(self.set_layer)
        self.label.setToolTip(self.description)
        self.in_file.setToolTip(self.description)
        self.btn_select.setToolTip(self.description)
        self.layer_combo.setToolTip(self.description)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.in_file, 1)
        self.layout.addWidget(self.layer_combo, 0)
        self.layout.addWidget(self.btn_select)
        self.setLayout(self.layout)
        # Populate combo box if vector and file exists
        if self.is_vector and self.value["path"] and Path(self.value["path"]).exists():
            try:
                layers_dict = get_layers(self.value["path"])
                self.layer_combo.clear()
                for layer_name, geometry_type in layers_dict.items():
                    self.layer_combo.addItem(f"{layer_name} ({geometry_type})")
                self.layer_combo.setVisible(True)
                if self.value["layer"]:
                    index = self.layer_combo.findText(self.value["layer"])
                    if index >= 0:
                        self.layer_combo.setCurrentIndex(index)
            except Exception:
                self.layer_combo.clear()
                self.layer_combo.setVisible(False)
        self.in_file.textChanged.connect(self.file_name_edited)
        self.update_combo_visibility()

    def set_inline_mode(self, unit=""):
        self.label.setVisible(False)
        self.layout.setContentsMargins(0, 0, 0, 0)

    def _reset_layer_state(self, clear_cache=False, visible=False, editable=False):
        self.layer_combo.clear()
        self.layer_combo.setEditable(editable)
        self.layer_combo.setVisible(visible)
        self.layer_combo.setStyleSheet("")
        self.layer_combo.setToolTip("Select layer")
        self.layer_combo.setMinimumWidth(0)
        self.layer_combo.setMaximumWidth(16777215)
        self.layer_combo.view().setMinimumWidth(0)
        QtWidgets.QToolTip.hideText()
        if clear_cache:
            self.gpkg_layers = None
            self.filtered_gpkg_layers = OrderedDict()

    def _refresh_layer_combo_popup_width(self):
        max_text_width = 0
        metrics = self.layer_combo.fontMetrics()
        for index in range(self.layer_combo.count()):
            item_text = self.layer_combo.itemText(index)
            max_text_width = max(max_text_width, metrics.horizontalAdvance(item_text))
        if self.layer_combo.isEditable():
            max_text_width = max(max_text_width, metrics.horizontalAdvance(self.layer_combo.currentText()))
        widget_padding = 36
        frame_and_scroll_padding = 48
        combo_width = max(90, max_text_width + widget_padding)
        popup_width = max(0, max_text_width + frame_and_scroll_padding)
        self.layer_combo.setFixedWidth(combo_width)
        self.layer_combo.view().setMinimumWidth(popup_width)

    def _set_input_geometry_warning(self, message):
        self.input_geometry_error = message
        self.in_file.setStyleSheet("QLineEdit { background-color: #f8d7da; }")
        self.in_file.setToolTip(message)

    def _clear_input_geometry_warning(self):
        self.input_geometry_error = ""
        self.in_file.setStyleSheet("")
        self.in_file.setToolTip(self.description)

    def _set_no_compatible_layer_placeholder(self):
        self.layer_combo.clear()
        self.layer_combo.setEditable(False)
        self.layer_combo.setVisible(True)
        self.layer_combo.addItem(self.NO_COMPATIBLE_LAYER_TEXT)
        self._refresh_layer_combo_popup_width()
        model_item = self.layer_combo.model().item(0)
        if model_item is not None:
            model_item.setEnabled(False)

    def _validate_shp_input_geometry(self, path):
        if self.output or not self.allowed_geometry_families:
            self._clear_input_geometry_warning()
            return

        file_path = Path(path)
        if not file_path.exists():
            self._clear_input_geometry_warning()
            return

        try:
            info = pyogrio.read_info(str(file_path))
            geometry_type = info.get("geometry_type")
        except Exception as exc:
            self._set_input_geometry_warning(f"Could not read shapefile geometry type: {exc}")
            return

        if is_geometry_compatible(geometry_type, self.allowed_geometry_families):
            self._clear_input_geometry_warning()
            return

        expected = format_expected_families(self.allowed_geometry_families)
        detected = geometry_type if geometry_type else "Unknown"
        self._set_input_geometry_warning(f"Geometry mismatch: expected {expected}, found {detected}")

    def _set_default_output_layer(self):
        default_name = self._unique_layer_name("Result_layer")
        self.layer_combo.addItem(default_name)

    def _on_vector_path_changed(self, path, is_output, selected_layer=""):
        is_gpkg = bool(path) and path.lower().endswith(".gpkg")
        if not is_gpkg:
            self._reset_layer_state(clear_cache=True, visible=False, editable=False)
            is_shp = bool(path) and path.lower().endswith(".shp")
            if self.is_vector and not is_output and is_shp:
                self._validate_shp_input_geometry(path)
            else:
                self._clear_input_geometry_warning()
            return

        if Path(path).exists():
            self.load_gpkg_layers(path, add_default=is_output and not selected_layer)
            if selected_layer:
                if is_output and self.layer_combo.isEditable():
                    self.layer_combo.setCurrentText(selected_layer)
                else:
                    index = self.layer_combo.findText(selected_layer)
                    if index >= 0:
                        self.layer_combo.setCurrentIndex(index)
            self.layer_combo.adjustSize()
            self._update_layer_overwrite_warning()
            if self.is_vector and not is_output:
                if self.layer_combo.currentText() == self.NO_COMPATIBLE_LAYER_TEXT:
                    expected = format_expected_families(self.allowed_geometry_families)
                    self._set_input_geometry_warning(
                        f"No compatible layers found in GeoPackage (expected {expected})"
                    )
                else:
                    self._clear_input_geometry_warning()
            return

        self._reset_layer_state(clear_cache=True, visible=bool(is_output), editable=bool(is_output))
        if is_output:
            self._set_default_output_layer()
            if selected_layer:
                self.layer_combo.setCurrentText(selected_layer)
            self.layer_combo.adjustSize()
            self._update_layer_overwrite_warning()
        else:
            self._clear_input_geometry_warning()

    def update_gpkg_combo(self, path, is_output, selected_layer):
        """Handle combo population and layer selection for vector paths."""
        self._on_vector_path_changed(path, is_output, selected_layer)

    def update_combo_visibility(self):
        # Support both string and dict for self.value
        if self.is_vector:
            path = self.value.get("path", "")
            layer = self.value.get("layer", "")
            self._on_vector_path_changed(path, self.output, layer)
        else:
            if isinstance(self.value, str) and self.value.lower().endswith(".gpkg"):
                selected_layer = getattr(self, "selected_layer", "")
                self._on_vector_path_changed(self.value, self.output, selected_layer)
            else:
                self._reset_layer_state(clear_cache=True, visible=False, editable=False)
        self.adjustSize()
        if self.parentWidget():
            self.parentWidget().layout().invalidate()
            self.parentWidget().adjustSize()
            self.parentWidget().update()

    def get_file_filters(self):
        """Return file type filter string based on self.file_type and current value."""

        def get_first_type(type_val):
            if isinstance(type_val, list):
                return type_val[0]
            return type_val

        file_types = "All files (*.*)"
        ft = get_first_type(self.file_type)
        if ft == "raster":
            file_types = """Tiff raster files (*.tif *.tiff);; 
                                Other raster files (*.dep *.bil *.flt *.sdat *.asc *grd)"""
        elif ft == "lidar":
            file_types = "LiDAR files (*.las *.zlidar *.laz *.zip)"
        elif ft == "vector":
            file_types = """GeoPackage (*.gpkg);;
                                     Shapefiles (*.shp)"""
        elif ft == "text":
            file_types = "Text files (*.txt);; all files (*.*)"
        elif ft == "csv":
            file_types = "CSV files (*.csv);; all files (*.*)"
        elif ft == "dat":
            file_types = "Binary data files (*.dat);; all files (*.*)"
        elif ft == "html":
            file_types = "HTML files (*.html)"
        elif ft == "json":
            file_types = "JSON files (*.json)"

        # Check for GeoPackage/Shapefile first in filter order by current value
        if isinstance(self.value, str) and self.value.lower().endswith(".gpkg"):
            file_types = """GeoPackage (*.gpkg);;
                               Shapefiles (*.shp);;
                               All files (*.*)"""
        elif isinstance(self.value, str) and self.value.lower().endswith(".shp"):
            file_types = """Shapefiles (*.shp);;
                               GeoPackage (*.gpkg);;
                               All files (*.*)"""
        return file_types

    def setup_file_dialog(self, file_types):
        """Initialize and configure QFileDialog."""
        dialog = QtWidgets.QFileDialog(self)
        dialog.setViewMode(QtWidgets.QFileDialog.Detail)
        # Handle both string and dict values (for vector files)
        path_value = self.value.get("path", "") if isinstance(self.value, dict) else self.value
        start_dir, start_dir_source = self._resolve_dialog_start_directory(path_value)
        if start_dir:
            dialog.setDirectory(str(start_dir))
        if path_value and start_dir_source == "path_value":
            dialog.selectFile(Path(path_value).name)
        dialog.setNameFilter(file_types)
        if "ExistingFile" in self.parameter_type:
            dialog.setFileMode(QtWidgets.QFileDialog.ExistingFiles)
        else:
            dialog.setFileMode(QtWidgets.QFileDialog.AnyFile)
        return dialog

    def _resolve_dialog_start_directory(self, path_value):
        if self.bt_data:
            last_browse_dir = self.bt_data.get_last_browse_dir()
            if last_browse_dir:
                browse_dir = Path(last_browse_dir).expanduser()
                if browse_dir.exists() and browse_dir.is_dir():
                    return browse_dir, "last_browse"

        if path_value:
            current_path = Path(path_value).expanduser()
            if current_path.exists():
                if current_path.is_dir():
                    return current_path, "path_value"
                return current_path.parent, "path_value"

            parent_dir = current_path.parent
            if parent_dir.exists() and parent_dir.is_dir():
                return parent_dir, "path_value"

        return Path.home(), "home"

    def _save_last_browse_dir(self, selected_path):
        if not self.bt_data:
            return

        selected = Path(selected_path).expanduser()
        browse_dir = selected if selected.is_dir() else selected.parent
        if browse_dir.exists() and browse_dir.is_dir():
            self.bt_data.set_last_browse_dir(str(browse_dir))

    def process_selected_file(self, result, dialog):
        """Handle file name modification, extension adding, and GeoPackage logic."""
        base_name = str(Path(result).with_suffix(""))
        selected_ext = Path(result).suffix
        selected_filter = dialog.selectedNameFilter()
        if selected_filter:
            filter_parts = selected_filter.split("(*")
            if len(filter_parts) > 1:
                extensions_str = filter_parts[1].replace(")", "")
                extensions = extensions_str.split(" ")
                if extensions:
                    preferred_ext = extensions[0].strip()
                    if not preferred_ext.startswith("."):
                        preferred_ext = "." + preferred_ext
                    if not selected_ext:
                        result = f"{base_name}{preferred_ext}"
        elif not selected_ext:
            result = f"{base_name}.txt"
        self.set_value(result)
        return result

    def handle_gpkg_selection(self, result):
        """GeoPackage-specific logic after file selection."""
        selected_layer = (
            self.value.get("layer", "") if self.is_vector else getattr(self, "selected_layer", "")
        )
        self._on_vector_path_changed(result, self.output, selected_layer)
        self.update_combo_visibility()

    def select_file(self):
        def get_first_type(type_val):
            if isinstance(type_val, list):
                return type_val[0]
            return type_val

        try:
            file_types = self.get_file_filters()
            dialog = self.setup_file_dialog(file_types)
            file_names = None
            if dialog.exec_():
                file_names = dialog.selectedFiles()
            if not file_names:
                return
            result = file_names[0]
            result = self.process_selected_file(result, dialog)
            self._save_last_browse_dir(result)
            self.handle_gpkg_selection(result)
        except Exception as e:
            print(e)
            print("[Error] Could not find the selected file.")

    def _unique_layer_name(self, base_name):
        """Return a layer name that does not conflict with existing layers in self.gpkg_layers."""
        if not self.gpkg_layers:
            return base_name
        existing = {str(k) for k in self.gpkg_layers.keys()}
        if base_name not in existing:
            return base_name
        counter = 1
        while f"{base_name}_{counter}" in existing:
            counter += 1
        return f"{base_name}_{counter}"

    def _update_layer_overwrite_warning(self):
        """Update combo style based on whether the current layer exists (A: visual warning)."""
        if not self.output or not self.gpkg_layers:
            self.layer_combo.setStyleSheet("")
            self.layer_combo.setToolTip("Select layer")
            return
        current = self.layer_combo.currentText()
        if "(" in current:
            current = current.split(" (")[0]
        existing = {str(k) for k in self.gpkg_layers.keys()}
        if current in existing:
            warning = f"Warning: layer '{current}' already exists and will be overwritten"
            self.layer_combo.setStyleSheet("QComboBox { background-color: #fff3cd; min-height: 1.4em; }")
            self.layer_combo.setToolTip(warning)
            pos = self.layer_combo.mapToGlobal(self.layer_combo.rect().bottomLeft())
            QtWidgets.QToolTip.showText(pos, warning, self.layer_combo, self.layer_combo.rect(), 5000)
        else:
            self.layer_combo.setStyleSheet("")
            self.layer_combo.setToolTip("New layer will be created")
            QtWidgets.QToolTip.hideText()

    def load_gpkg_layers(self, gpkg_file, add_default=True):
        """Load layers from a GeoPackage and populate the combo box using get_layers."""
        try:
            self.gpkg_layers = get_layers(gpkg_file)
            if not self.gpkg_layers:
                raise ValueError("No layers found in the GeoPackage.")

            self.layer_combo.clear()

            # Output: add unique default layer name to avoid overwriting existing layers
            if self.output:
                if add_default:
                    default_name = self._unique_layer_name("Result_layer")
                    self.layer_combo.addItem(default_name)
                self.layer_combo.setEditable(True)

            layers_for_combo = self.gpkg_layers
            if not self.output and self.allowed_geometry_families:
                self.filtered_gpkg_layers = OrderedDict(
                    (layer_name, geometry_type)
                    for layer_name, geometry_type in self.gpkg_layers.items()
                    if is_geometry_compatible(geometry_type, self.allowed_geometry_families)
                )
                layers_for_combo = self.filtered_gpkg_layers
            else:
                self.filtered_gpkg_layers = self.gpkg_layers

            if not self.output and not layers_for_combo and self.allowed_geometry_families:
                self._set_no_compatible_layer_placeholder()
            else:
                for layer_name, geometry_type in layers_for_combo.items():
                    self.layer_combo.addItem(f"{layer_name} ({geometry_type})")
                self._refresh_layer_combo_popup_width()

            if self.selected_layer:
                index = self.layer_combo.findText(self.selected_layer)
                if index >= 0:
                    self.layer_combo.setCurrentIndex(index)

            self.layer_combo.setToolTip("Select layer")
            self.layer_combo.setVisible(True)
            self._update_layer_overwrite_warning()

        except Exception as e:
            self.gpkg_layers = None
            print(f"[Error] Could not load layers from GeoPackage: {gpkg_file}\nDetails: {e}")

    def file_name_edited(self):
        new_value = self.in_file.text()
        if self.is_vector:
            self.value["path"] = new_value
        else:
            self.value = new_value
        # Step 2: Check if the new value ends with a supported vector extension
        ext = Path(new_value).suffix.lower().replace(".", "")
        if self.is_vector and ext in self.VECTOR_FORMATS:
            selected_layer = self.value.get("layer", "")
            self._on_vector_path_changed(new_value, self.output, selected_layer)
        else:
            self._reset_layer_state(clear_cache=True, visible=False, editable=False)
        self.update_combo_visibility()

    def set_value(self, value):
        # Accept both string and dict for compatibility
        if self.is_vector:
            if isinstance(value, dict):
                self.value = value
            elif isinstance(value, str):
                if "|" in value:
                    path, layer = value.rsplit("|", 1)
                    self.value = {"path": path, "layer": layer}
                else:
                    self.value = {"path": value, "layer": ""}
            # For input, clear if file does not exist; for output, clear if parent folder does not exist
            if self.value["path"]:
                if not self.output and not Path(self.value["path"]).exists():
                    self.value = {"path": "", "layer": ""}
                elif self.output and not Path(self.value["path"]).parent.exists():
                    self.value = {"path": "", "layer": ""}
            self.in_file.setText(self.value["path"])
            self.in_file.setToolTip(self.value["path"])
        else:
            try:  # load saved or default filepath like values
                base_name = str(Path(value).with_suffix(""))
                ext = Path(value).suffix
                if not ext:
                    if not value.endswith("."):
                        if not value.endswith(".gpkg") and not value.endswith(".shp"):
                            value = f"{base_name}.txt"
                elif value.endswith("."):
                    value = base_name
                # For input, clear if file does not exist; for output, clear if parent folder does not exist
                if value:
                    if not self.output and not Path(value).exists():
                        value = ""
                    elif self.output and not Path(value).parent.exists():
                        value = ""
                self.value = value
                self.in_file.setText(self.value)
                self.in_file.setToolTip(self.value)
            except Exception as e:
                # do nothing if first time initialize the tool with no previous values
                self.value = ""
                self.in_file.setText(self.value)
                self.in_file.setToolTip(self.value)
        self.update_combo_visibility()

    def set_layer(self, layer):
        # For vector, update dict
        if self.is_vector:
            if layer == self.NO_COMPATIBLE_LAYER_TEXT:
                self.value["layer"] = ""
                return
            # Remove geometry type if present
            if "(" in layer:
                layer = layer.split(" (")[0]
            self.value["layer"] = layer
        else:
            self.selected_layer = layer
        self._update_layer_overwrite_warning()

    def get_value(self):
        # For vector, encode from dict for compatibility
        if self.is_vector:
            path = self.value.get("path", "")
            layer = self.value.get("layer", "")
            if self.input_geometry_error and not self.output:
                return {self.variable: ""}
            # If no layer selected but combo has items, use first layer
            if not layer and self.layer_combo.count() > 0:
                first_layer = self.layer_combo.itemText(0)
                if first_layer == self.NO_COMPATIBLE_LAYER_TEXT:
                    return {self.variable: ""}
                # Remove geometry type if present
                if "(" in first_layer:
                    first_layer = first_layer.split(" (")[0]
                self.value["layer"] = first_layer
                layer = first_layer
            if self.output:
                # Output: always encode path|layer
                encoded_value = f"{path}|{layer}" if layer else path
            else:
                # Input: if path is empty, return empty
                if not path:
                    return {self.variable: ""}
                encoded_value = f"{path}|{layer}" if layer else path
            return {self.variable: encoded_value}
        else:
            return {self.variable: self.value}

    def set_default_value(self):
        default_value = self.default_value if self.default_value is not None else ""
        self.set_value(default_value)


class OptionsInput(QtWidgets.QWidget):
    """OptionsInput class for creating option selection widgets."""

    def __init__(self, json_str, parent=None):
        super(OptionsInput, self).__init__(parent)

        # first make sure that the json data has the correct fields
        params = json.loads(json_str)
        self.name = params["name"]
        self.description = params["description"]
        self.variable = params["variable"]
        self.parameter_type = params["parameter_type"]
        self.optional = params["optional"]
        self.data_type = params["data_type"]

        self.default_value = str(params["default_value"])
        self.value = self.default_value
        if "saved_value" in params.keys():
            self.value = params["saved_value"]

        self.label = QtWidgets.QLabel(self.name)
        self.label.setMinimumWidth(BT_LABEL_MIN_WIDTH)
        self.combobox = QtWidgets.QComboBox()
        self.combobox.currentIndexChanged.connect(self.selection_change)
        self.label.setToolTip(self.description)
        self.combobox.setToolTip(self.description)

        i = 1
        default_index = -1
        self.option_list = params["parameter_type"]["OptionList"]
        if self.option_list:
            # convert to strings
            self.option_list = [str(item) for item in self.option_list]

        values = ()
        for v in self.option_list:
            values += (v,)
            if v == str(self.value):
                default_index = i - 1
            i = i + 1

        self.combobox.addItems(self.option_list)
        self.combobox.setCurrentIndex(default_index)

        self.layout = QtWidgets.QHBoxLayout()
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.combobox)
        self.setLayout(self.layout)

    def set_inline_mode(self, unit=""):
        self.label.setVisible(False)
        self.layout.setContentsMargins(0, 0, 0, 0)

    def selection_change(self, i):
        self.value = self.option_list[i]

    def set_value(self, value):
        self.value = value
        for v in self.option_list:
            if value == v:
                self.combobox.setCurrentIndex(self.option_list.index(v))

    def set_default_value(self):
        self.value = self.default_value
        for v in self.option_list:
            if self.value == v:
                self.combobox.setCurrentIndex(self.option_list.index(v))

    def get_value(self):
        return {self.variable: self.value}


class NumericInput(QtWidgets.QWidget):
    """NumericInput class for creating numeric input widgets (int and float)."""

    def __init__(self, json_str, parent=None):
        super(NumericInput, self).__init__(parent)
        params = json.loads(json_str)
        self.name = params["name"]
        self.description = params["description"]
        self.variable = params["variable"]
        self.parameter_type = params["parameter_type"]
        self.optional = params["optional"]
        self.unit = params.get("unit", "")
        self.default_value = params["default_value"]
        self.value = self.default_value
        if "saved_value" in params.keys():
            self.value = params["saved_value"]
        self.label = QtWidgets.QLabel(self.name)
        self.label.setMinimumWidth(BT_LABEL_MIN_WIDTH)
        self.data_input = None
        self.unit_label = QtWidgets.QLabel(self.unit)
        self.unit_label.setVisible(bool(self.unit))
        subtypes = []
        if isinstance(self.parameter_type, list):
            subtypes = self.parameter_type
        elif isinstance(self.parameter_type, str):
            subtypes = [self.parameter_type]
        elif isinstance(self.parameter_type, dict):
            for v in self.parameter_type.values():
                if isinstance(v, list):
                    subtypes.extend(v)
                else:
                    subtypes.append(v)
        main_subtype = subtypes[0] if subtypes else None
        if main_subtype == "int":
            self.data_input = QtWidgets.QSpinBox()
            self.data_input.setRange(-2147483647, 2147483647)
        elif main_subtype == "float":
            self.data_input = QtWidgets.QDoubleSpinBox()
            self.data_input.setRange(-1e12, 1e12)
            self.data_input.setDecimals(2)
        else:
            if main_subtype is not None:
                raise ValueError(f"Unsupported parameter type: {main_subtype}")
        if self.data_input and main_subtype in ("int", "float"):
            try:
                if main_subtype == "int":
                    self.data_input.setValue(int(self.value))
                elif main_subtype == "float":
                    self.data_input.setValue(float(self.value))
            except (ValueError, TypeError):
                self.data_input.setValue(0)
            self.data_input.valueChanged.connect(self.update_value)
        self.layout = QtWidgets.QHBoxLayout()
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.data_input)
        self.layout.addWidget(self.unit_label)
        self.label.setToolTip(self.description)
        self.data_input.setToolTip(self.description)
        self.unit_label.setToolTip(self.description)
        self.setLayout(self.layout)

    def set_inline_mode(self, unit=""):
        self.label.setVisible(False)
        self.layout.setContentsMargins(0, 0, 0, 0)
        if unit:
            self.unit = unit
            self.unit_label.setText(unit)
            self.unit_label.setVisible(True)

    def update_value(self):
        if self.data_input is not None:
            self.value = self.data_input.value()

    def get_value(self):
        v = self.value
        if v is not None:
            if "int" in self.parameter_type:
                value = int(self.value)
            elif "float" in self.parameter_type:
                value = float(self.value)
            else:
                value = self.value
            return {self.variable: value}
        else:
            if not self.optional:
                msg_box = QtWidgets.QMessageBox()
                msg_box.setIcon(QtWidgets.QMessageBox.Warning)
                msg_box.setText("Unknown non-optional parameter {}.".format(self.variable))
                msg_box.exec()
        return None

    def set_value(self, value):
        if self.data_input:
            self.data_input.setValue(value)
            self.update_value()

    def set_default_value(self):
        if self.data_input:
            self.data_input.setValue(self.default_value)
            self.update_value()


class BooleanInput(QtWidgets.QWidget):
    """BooleanInput class for creating boolean checkbox widgets."""

    def __init__(self, json_str, parent=None):
        super(BooleanInput, self).__init__(parent)
        params = json.loads(json_str)
        self.name = params["name"]
        self.description = params["description"]
        self.variable = params["variable"]
        self.parameter_type = params["parameter_type"]
        self.optional = params["optional"]
        self.default_value = params["default_value"]
        # Detect if this is pure Boolean or OptionList boolean
        self._detect_boolean_source(params)
        self.value = self._convert_to_bool(self.default_value)
        if "saved_value" in params.keys():
            self.value = self._convert_to_bool(params["saved_value"])
        self.checkbox = QtWidgets.QCheckBox(self.name)
        self.checkbox.setChecked(self.value)
        self.checkbox.setToolTip(self.description)
        self.checkbox.stateChanged.connect(self.update_value)
        self.label = self.checkbox  # Reference checkbox as label for styling
        self.layout = QtWidgets.QHBoxLayout()
        self.layout.addWidget(self.checkbox)
        self.layout.addStretch()
        self.setLayout(self.layout)

    def set_inline_mode(self, unit=""):
        return

    def _detect_boolean_source(self, params):
        """Determine if this is pure Boolean or OptionList boolean."""
        pt = params["parameter_type"]

        if isinstance(pt, str) and pt == "Boolean":
            self.is_option_list = False
        elif isinstance(pt, dict) and "OptionList" in pt:
            option_list = pt["OptionList"]
            # Check if it's a boolean list (handle both string and bool types)
            is_bool_list = (
                option_list == ["True", "False"]
                or option_list == ["true", "false"]
                or option_list == [True, False]
                or option_list == [False, True]
            )
            if is_bool_list:
                self.is_option_list = True
            else:
                raise ValueError("OptionList is not boolean, use OptionsInput instead")
        else:
            raise ValueError(f"Unsupported parameter type for BooleanInput: {pt}")

    def _convert_to_bool(self, value):
        """Convert various value types to boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        if isinstance(value, (int, float)):
            return bool(value)
        return False

    def update_value(self):
        self.value = self.checkbox.isChecked()

    def set_value(self, value):
        """Set checkbox state from various value types."""
        self.value = self._convert_to_bool(value)
        self.checkbox.setChecked(self.value)

    def get_value(self):
        return {self.variable: self.checkbox.isChecked()}

    def set_default_value(self):
        self.value = self._convert_to_bool(self.default_value)
        self.checkbox.setChecked(self.value)


class DoubleSlider(QtWidgets.QSlider):
    """DoubleSlider class for creating double slider widgets."""

    # create our signal that we can connect to if necessary
    doubleValueChanged = QtCore.pyqtSignal(float)

    def __init__(self, decimals=3, *args, **kargs):
        super(DoubleSlider, self).__init__(QtCore.Qt.Horizontal)
        self._multi = 10**decimals

        self.opt = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(self.opt)

        self.valueChanged.connect(self.emit_double_value_changed)

    def emit_double_value_changed(self):
        value = float(super(DoubleSlider, self).value()) / self._multi
        self.doubleValueChanged.emit(value)

    def value(self):
        return float(super(DoubleSlider, self).value()) / self._multi

    def setMinimum(self, value):
        return super(DoubleSlider, self).setMinimum(value * self._multi)

    def setMaximum(self, value):
        return super(DoubleSlider, self).setMaximum(value * self._multi)

    def setSingleStep(self, value):
        return super(DoubleSlider, self).setSingleStep(value * self._multi)

    def singleStep(self):
        return float(super(DoubleSlider, self).singleStep()) / self._multi

    def setValue(self, value):
        super(DoubleSlider, self).setValue(int(value * self._multi))

    def sliderChange(self, change):
        if change == QtWidgets.QAbstractSlider.SliderValueChange:
            sr = self.style().subControlRect(
                QtWidgets.QStyle.CC_Slider, self.opt, QtWidgets.QStyle.SC_SliderHandle
            )
            bottom_right_corner = sr.bottomLeft()
            QtWidgets.QToolTip.showText(
                self.mapToGlobal(QtCore.QPoint(bottom_right_corner.x(), bottom_right_corner.y())),
                str(self.value()),
                self,
            )


if __name__ == "__main__":
    from bt_data import BTData

    bt = BTData()

    app = QtWidgets.QApplication(sys.argv)
    dlg = ToolWidgets(
        "Raster Line Attributes",
        bt.get_bera_tool_args("Raster Line Attributes"),
        bt.show_advanced,
    )
    dlg.show()
    sys.exit(app.exec_())
