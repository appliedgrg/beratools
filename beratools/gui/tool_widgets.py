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

BT_LABEL_MIN_WIDTH = 130


class ToolWidgets(QtWidgets.QWidget):
    """ToolWidgets class for creating widgets for tool parameters."""

    signal_save_tool_params = QtCore.pyqtSignal(object)

    def __init__(self, tool_name, tool_args, show_advanced, parent=None):
        super(ToolWidgets, self).__init__(parent)

        self.tool_name = tool_name
        self.show_advanced = show_advanced
        self.current_tool_api = ""
        self.widget_list = []
        self.setWindowTitle("Tool widgets")

        self.create_widgets(tool_args)
        layout = QtWidgets.QVBoxLayout()

        for item in self.widget_list:
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
        param_num = 0
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
                widget = FileSelector(json_str, None)
                param_num = param_num + 1
            elif "FileList" in pt:
                widget = MultiFileSelector(json_str, None)
                param_num = param_num + 1
            elif "Boolean" in pt:
                widget = BooleanInput(json_str)
                param_num = param_num + 1
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
                param_num = param_num + 1
            elif "float" in pt or "int" in pt:
                widget = NumericInput(json_str)
                param_num = param_num + 1
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
                if widget.optional and widget.label:
                    widget.label.setStyleSheet(
                        "QtWidgets.QLabel { background-color : transparent; color : blue; }"
                    )

                if not self.show_advanced and widget.optional:
                    widget.hide()

            self.widget_list.append(widget)

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

    @staticmethod
    def has_vector_subtype(param_type):
        if isinstance(param_type, dict):
            for v in param_type.values():
                if isinstance(v, list) and "vector" in v:
                    return True
        return False

    def __init__(self, json_str, parent=None):
        super(FileSelector, self).__init__(parent)
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

        self.optional = params["optional"]
        self.default_value = params["default_value"]
        self.saved_value = params.get("saved_value", None)
        self.is_vector = self.has_vector_subtype(self.parameter_type)

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
            else:
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
        self.layer_combo.setVisible(False)
        self.layer_combo.currentTextChanged.connect(self.set_layer)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.in_file)
        self.layout.addWidget(self.layer_combo)
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

    def update_gpkg_combo(self, path, is_output, selected_layer):
        """Handle combo population, and layer selection for .gpkg files."""
        self.layer_combo.setVisible(True)
        if Path(path).exists():
            if is_output:
                self.load_gpkg_layers(path, add_default=not selected_layer)
            else:
                self.layer_combo.setEditable(False)
                if self.layer_combo.count() == 0 or self.layer_combo.itemText(0) == "Result_layer":
                    self.layer_combo.clear()
                    self.load_gpkg_layers(path)
        else:
            self.layer_combo.clear()
            if is_output:
                self.layer_combo.setEditable(True)
                self.layer_combo.addItem("Result_layer")
            else:
                self.layer_combo.setVisible(False)
                return
        # Set selected layer
        if selected_layer:
            if is_output and self.layer_combo.isEditable():
                self.layer_combo.setCurrentText(selected_layer)
            else:
                index = self.layer_combo.findText(selected_layer)
                if index >= 0:
                    self.layer_combo.setCurrentIndex(index)
        self.layer_combo.adjustSize()
        self._update_layer_overwrite_warning()

    def update_combo_visibility(self):
        # Support both string and dict for self.value
        if self.is_vector:
            path = self.value.get("path", "")
            layer = self.value.get("layer", "")
            is_gpkg = path.lower().endswith(".gpkg")
            if is_gpkg:
                self.update_gpkg_combo(path, self.output, layer)
            else:
                self.layer_combo.setVisible(False)
        else:
            if isinstance(self.value, str) and self.value.lower().endswith(".gpkg"):
                selected_layer = getattr(self, "selected_layer", "")
                self.update_gpkg_combo(self.value, self.output, selected_layer)
            else:
                self.layer_combo.setVisible(False)
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
        if path_value:
            dialog.setDirectory(str(Path(path_value).parent))
            dialog.selectFile(Path(path_value).name)
        dialog.setNameFilter(file_types)
        if "ExistingFile" in self.parameter_type:
            dialog.setFileMode(QtWidgets.QFileDialog.ExistingFiles)
        else:
            dialog.setFileMode(QtWidgets.QFileDialog.AnyFile)
        return dialog

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
        if result.lower().endswith(".gpkg"):
            if not Path(result).exists():
                self.layer_combo.clear()
                if self.output:
                    self.layer_combo.addItem("Result_layer")
                else:
                    self.layer_combo.setVisible(False)
            else:
                self.load_gpkg_layers(result)
                if self.output:
                    self.layer_combo.setEditable(True)
        else:
            self.layer_combo.setVisible(False)
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

            for layer_name, geometry_type in self.gpkg_layers.items():
                self.layer_combo.addItem(f"{layer_name} ({geometry_type})")

            if self.selected_layer:
                index = self.layer_combo.findText(self.selected_layer)
                if index >= 0:
                    self.layer_combo.setCurrentIndex(index)

            self.layer_combo.setToolTip("Select layer")
            self.layer_combo.setVisible(True)
            self._update_layer_overwrite_warning()

        except Exception as e:
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
            if Path(new_value).exists():
                self.load_gpkg_layers(new_value)
                self.layer_combo.setVisible(True)
                self.update_combo_visibility()
            else:
                self.layer_combo.clear()
                if self.output:
                    self.layer_combo.addItem("Result_layer")
                    self.layer_combo.setEditable(True)
                    self.layer_combo.setVisible(True)
                else:
                    self.layer_combo.setVisible(False)
        else:
            self.layer_combo.setVisible(False)
        self.adjustSize()
        if self.parentWidget():
            self.parentWidget().layout().invalidate()
            self.parentWidget().adjustSize()
            self.parentWidget().update()

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
            # If no layer selected but combo has items, use first layer
            if not layer and self.layer_combo.count() > 0:
                first_layer = self.layer_combo.itemText(0)
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
        self.default_value = params["default_value"]
        self.value = self.default_value
        if "saved_value" in params.keys():
            self.value = params["saved_value"]
        self.label = QtWidgets.QLabel(self.name)
        self.label.setMinimumWidth(BT_LABEL_MIN_WIDTH)
        self.data_input = None
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
        elif main_subtype == "float":
            self.data_input = QtWidgets.QDoubleSpinBox()
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
        self.setLayout(self.layout)

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
        self.checkbox = QtWidgets.QCheckBox(f"{self.name} - {self.description}")
        self.checkbox.setChecked(self.value)
        self.checkbox.stateChanged.connect(self.update_value)
        self.label = self.checkbox  # Reference checkbox as label for styling
        self.layout = QtWidgets.QHBoxLayout()
        self.layout.addWidget(self.checkbox)
        self.layout.addStretch()
        self.setLayout(self.layout)

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
