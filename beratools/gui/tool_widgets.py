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
import os
import sys
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pyogrio
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
        for p in tool_args:
            json_str = json.dumps(p, sort_keys=True, indent=2, separators=(",", ": "))
            pt = p["parameter_type"]
            widget = None

            if "ExistingFile" in pt or "NewFile" in pt or "directory" in pt:
                widget = FileSelector(json_str, None)
                param_num = param_num + 1
            elif "FileList" in pt:
                widget = MultiFileSelector(json_str, None)
                param_num = param_num + 1
            elif "Boolean" in pt:
                widget = BooleanInput(json_str)
                param_num = param_num + 1
            elif "OptionList" in pt:
                widget = OptionsInput(json_str)
                param_num = param_num + 1
            elif (
                "Float" in pt
                or "Integer" in pt
                or "Text" in pt
                or "String" in pt
                or "StringOrNumber" in pt
                or "StringList" in pt
                or "VectorAttributeField" in pt
            ):
                widget = DataInput(json_str)
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
            if param_value is not None:
                if type(widget) is OptionsInput:
                    widget.value = param_value
                elif widget:
                    widget.value = param_value
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
                if key == item.flag:
                    item.set_value(value)

    def save_tool_parameters(self):
        params = {}
        for item in self.widget_list:
            if item.flag:
                params[item.flag] = item.get_value()

        self.signal_save_tool_params.emit(params)

    def load_default_args(self):
        for item in self.widget_list:
            item.set_default_value()


def get_layers(gpkg_file):
    try:
        # Get the list of layers and their geometry types from the GeoPackage file
        layers_info = pyogrio.list_layers(gpkg_file)

        # Check if layers_info is in the expected format
        if isinstance(layers_info, np.ndarray) and all(
            isinstance(layer, np.ndarray) and len(layer) >= 2 for layer in layers_info
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

    def __init__(self, json_str, parent=None):
        super(FileSelector, self).__init__(parent)

        # Parsing the JSON data
        params = json.loads(json_str)
        self.name = params["name"]
        self.description = params["description"]
        self.flag = params["flag"]
        self.layer_flag = None
        self.saved_layer = ""
        if "layer" in params.keys():
            self.layer_flag = params["layer"]["layer_name"]
            self.saved_layer = params["layer"]["layer_value"]

        self.gpkg_layers = None
        self.output = params["output"]  # Ensure output flag is read
        self.parameter_type = params["parameter_type"]
        self.file_type = ""
        if "ExistingFile" in self.parameter_type:
            self.file_type = params["parameter_type"]["ExistingFile"]
        elif "NewFile" in self.parameter_type:
            self.file_type = params["parameter_type"]["NewFile"]
        self.optional = params["optional"]

        self.default_value = params["default_value"]
        self.value = self.default_value
        self.selected_layer = None  # Add attribute for selected layer
        if "saved_value" in params.keys():
            self.value = params["saved_value"]

        self.layout = QtWidgets.QHBoxLayout()
        self.label = QtWidgets.QLabel(self.name)
        self.label.setMinimumWidth(200)
        self.in_file = QtWidgets.QLineEdit(self.value)
        self.btn_select = QtWidgets.QPushButton("...")
        self.btn_select.clicked.connect(self.select_file)

        # ComboBox for displaying GeoPackage layers
        self.layer_combo = QtWidgets.QComboBox()
        self.layer_combo.setVisible(False)  # Initially hidden
        # Connect layer change event
        self.layer_combo.currentTextChanged.connect(self.set_layer)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.in_file)
        self.layout.addWidget(self.layer_combo)
        self.layout.addWidget(self.btn_select)

        self.setLayout(self.layout)

        # text changed
        self.in_file.textChanged.connect(self.file_name_edited)

        # Handle showing the layer combo and making it editable when needed
        if self.value.lower().endswith(".gpkg"):
            self.layer_combo.setVisible(True)  # Show the combo box if it's a .gpkg
            if self.output:
                self.layer_combo.setEditable(True)  # Ensure editable if output is True
                self.layer_combo.addItem("")  # Add an empty item to the combo box
                # If the .gpkg file doesn't exist, show empty layer
                if not os.path.exists(self.value):
                    self.layer_combo.clear()  # Clear the combo box
                    self.layer_combo.addItem("layer_name")  # Show "layer_name"
            else:
                self.layer_combo.setEditable(False)  # Non-editable if output is False
                self.load_gpkg_layers(self.value)  # Load layers if output is False

        # check saved layer existence, if True then set it to selected
        index = self.search_saved_combo_items()
        if index != -1:
            self.layer_combo.setCurrentIndex(index)

        # If the file is not a .gpkg, don't show the combo box at all
        elif self.layer_combo.isVisible():
            self.layer_combo.setVisible(False)

        self.update_combo_visibility()  # Update combo visibility after init

    def update_combo_visibility(self):
        if self.value.lower().endswith(".gpkg"):
            self.layer_combo.setVisible(True)
            if os.path.exists(self.value):
                if self.output:
                    self.layer_combo.setEditable(True)
                    if self.layer_combo.count() == 0:
                        self.layer_combo.addItem("layer_name")
                        self.load_gpkg_layers(self.value)
                    elif self.layer_combo.itemText(0) != "layer_name":
                        self.layer_combo.insertItem(0, "layer_name")
                        self.load_gpkg_layers(self.value)
                else:  # output is False
                    self.layer_combo.setEditable(False)
                    if self.layer_combo.count() == 0 or self.layer_combo.itemText(0) == "layer_name":
                        self.layer_combo.clear()
                        self.load_gpkg_layers(self.value)
            else:  # gpkg does not exist
                self.layer_combo.clear()
                if self.output:
                    self.layer_combo.setEditable(True)
                    self.layer_combo.addItem("layer_name")
                else:
                    self.layer_combo.addItem("layer_name")

            self.layer_combo.adjustSize()
        else:
            self.layer_combo.setVisible(False)

        self.adjustSize()
        if self.parentWidget():
            self.parentWidget().layout().invalidate()
            self.parentWidget().adjustSize()
            self.parentWidget().update()

    def select_file(self):
        try:
            dialog = QtWidgets.QFileDialog(self)
            dialog.setViewMode(QtWidgets.QFileDialog.Detail)
            dialog.setDirectory(str(Path(self.value).parent))
            dialog.selectFile(Path(self.value).name)
            file_names = None

            file_types = "All files (*.*)"

            if "RasterAndVector" in self.file_type:
                file_types = """Shapefiles (*.shp);; 
                                Raster files (*.dep *.tif *.tiff *.bil *.flt *.sdat *.asc *grd)"""
            elif "Raster" in self.file_type:
                file_types = """Tiff raster files (*.tif *.tiff);; 
                                Other raster files (*.dep *.bil *.flt *.sdat *.asc *grd)"""
            elif "Lidar" in self.file_type:
                file_types = "LiDAR files (*.las *.zlidar *.laz *.zip)"
            elif "Vector" in self.file_type:
                file_types = """GeoPackage (*.gpkg);;
                                    Shapefiles (*.shp)"""
            elif "Text" in self.file_type:
                file_types = "Text files (*.txt);; all files (*.*)"
            elif "Csv" in self.file_type:
                file_types = "CSV files (*.csv);; all files (*.*)"
            elif "Dat" in self.file_type:
                file_types = "Binary data files (*.dat);; all files (*.*)"
            elif "Html" in self.file_type:
                file_types = "HTML files (*.html)"
            elif "json" in self.file_type or "JSON" in self.file_type:
                file_types = "JSON files (*.json)"

            # Check for GeoPackage/Shapefile first in filter order by current value
            if self.value.lower().endswith(".gpkg"):
                file_types = """GeoPackage (*.gpkg);;
                               Shapefiles (*.shp);;
                               All files (*.*)"""
            elif self.value.lower().endswith(".shp"):
                file_types = """Shapefiles (*.shp);;
                               GeoPackage (*.gpkg);;
                               All files (*.*)"""

            dialog.setNameFilter(file_types)

            if "ExistingFile" in self.parameter_type:
                dialog.setFileMode(QtWidgets.QFileDialog.ExistingFiles)
            else:
                dialog.setFileMode(QtWidgets.QFileDialog.AnyFile)

            if dialog.exec_():
                file_names = dialog.selectedFiles()

            if not file_names:
                return

            result = file_names[0]
            base_name, selected_ext = os.path.splitext(result)
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
            elif not selected_ext:  # No filter and no extension
                result = f"{base_name}.txt"

            self.set_value(result)

            if result.lower().endswith(".gpkg"):
                if not os.path.exists(result):
                    self.layer_combo.clear()
                    self.layer_combo.addItem("layer_name")
                else:
                    self.load_gpkg_layers(result)
                    if self.output:
                        self.layer_combo.setEditable(True)
            else:
                self.layer_combo.setVisible(False)

            # Update combo visibility after file selection
            self.update_combo_visibility()
        except Exception as e:
            print(e)
            msg_box = QtWidgets.QMessageBox()
            msg_box.setIcon(QtWidgets.QMessageBox.Warning)
            msg_box.setText("Could not find the selected file.")
            msg_box.exec()

    def load_gpkg_layers(self, gpkg_file):
        """Load layers from a GeoPackage and populate the combo box using get_layers."""
        try:
            # Print the file path to verify it's correct
            # print(f"Attempting to load layers from: {gpkg_file}")

            # Use get_layers to load layers from the GeoPackage
            self.gpkg_layers = get_layers(gpkg_file)

            # Check if layers is empty
            if not self.gpkg_layers:
                raise ValueError("No layers found in the GeoPackage.")

            # Clear any existing layers in the combo box
            self.layer_combo.clear()

            # Iterate over the layers dictionary
            # and add each layer name with geometry type to the combo box
            for layer_name, geometry_type in self.gpkg_layers.items():
                self.layer_combo.addItem(f"{layer_name} ({geometry_type})")

            # Set the tooltip for the layer list widget
            self.layer_combo.setToolTip("Select layer")

            # Make the combo box visible
            self.layer_combo.setVisible(True)

        except Exception as e:
            # Print the full error message for debugging purposes
            print(f"Error loading GeoPackage layers: {e}")

            # Show a message box with the error
            msg_box = QtWidgets.QMessageBox()
            msg_box.setIcon(QtWidgets.QMessageBox.Warning)
            msg_box.setText(f"Could not load layers from GeoPackage: {gpkg_file}")
            msg_box.setDetailedText(str(e))  # Show detailed error message
            msg_box.exec()

    def file_name_edited(self):
        # Step 1: Get the current value in the file input field
        new_value = self.in_file.text()
        self.value = new_value  # update file name

        # Step 2: Check if the new value ends with a .gpkg extension
        if new_value.lower().endswith(".gpkg"):
            # If it's a GeoPackage, check if the file exists
            if os.path.exists(new_value):
                # File exists, load layers from the GeoPackage
                self.load_gpkg_layers(new_value)
                self.layer_combo.setVisible(True)  # Show the layer combo box
                self.update_combo_visibility()  # Ensure layers are updated properly
            else:
                # File doesn't exist, clear the layer combo box and show message
                self.layer_combo.clear()
                self.layer_combo.addItem("layer_name")
                if self.output:
                    self.layer_combo.setEditable(True)

                # Show the layer combo box but indicate no layers
                self.layer_combo.setVisible(True)
        else:
            # If it's not a GeoPackage, hide the layer combo box
            self.layer_combo.setVisible(False)

        # Optional: Adjust the combo box visibility and layout
        self.adjustSize()
        if self.parentWidget():
            self.parentWidget().layout().invalidate()
            self.parentWidget().adjustSize()
            self.parentWidget().update()

    def set_value(self, value):
        # Check if the value has an extension
        base_name, ext = os.path.splitext(value)

        # Only append an extension if none exists AND the value doesn't end with a dot
        if not ext:  # If there's no extension
            if not value.endswith("."):  # If the user hasn't typed a dot at the end
                # Don't force the .txt extension unless the filename doesn't have one
                # Add default extension for other cases
                if not value.endswith(".gpkg") and not value.endswith(".shp"):
                    value = f"{base_name}.txt"
            # If the value ends with a dot (like `file.`), don't append anything yet

        # If the value ends with a dot, don't append an extension.
        elif value.endswith("."):
            value = base_name  # Strip the dot

        self.value = value
        self.in_file.setText(self.value)
        self.in_file.setToolTip(self.value)
        self.update_combo_visibility()

    def set_layer(self, layer):
        # Store only the selected layer's name (key) from the combo box display
        # The layer is in the format: "layer_name (geometry_type)"
        # Get only the layer name (before the space)
        self.selected_layer = layer.split(" ")[0]
        # print(f"Selected Layer: {self.selected_layer}")

    def get_value(self):
        # Return both the file path and the selected layer
        value = {self.flag: self.value}
        if self.layer_flag and self.selected_layer:
            # Store the layer name (key)
            value.update({self.layer_flag: self.selected_layer})

        return value

    def search_saved_combo_items(self):
        """
        Search saved layer in combo box items.

        Returns:
        If found, then return the index, or return -1

        """
        if not self.gpkg_layers:
            return -1

        for idx, key in enumerate(self.gpkg_layers.keys()):
            if key == self.saved_layer:
                return idx

        return -1


# TODO: check if this class is needed
class MultiFileSelector(QtWidgets.QWidget):
    """MultiFileSelector class for creating multiple file selection widgets."""

    def __init__(self, json_str, parent=None):
        super(MultiFileSelector, self).__init__(parent)
        pass


# TODO: check if this class is needed
class BooleanInput(QtWidgets.QWidget):
    """BooleanInput class for creating boolean input widgets."""

    def __init__(self, json_str, parent=None):
        super(BooleanInput, self).__init__(parent)
        pass


class OptionsInput(QtWidgets.QWidget):
    """OptionsInput class for creating option selection widgets."""

    def __init__(self, json_str, parent=None):
        super(OptionsInput, self).__init__(parent)

        # first make sure that the json data has the correct fields
        params = json.loads(json_str)
        self.name = params["name"]
        self.description = params["description"]
        self.flag = params["flag"]
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
        return {self.flag: self.value}


class DataInput(QtWidgets.QWidget):
    """DataInput class for creating data input widgets."""

    def __init__(self, json_str, parent=None):
        super(DataInput, self).__init__(parent)

        # first make sure that the json data has the correct fields
        params = json.loads(json_str)
        self.name = params["name"]
        self.description = params["description"]
        self.flag = params["flag"]
        self.parameter_type = params["parameter_type"]
        self.optional = params["optional"]

        self.default_value = params["default_value"]
        self.value = self.default_value
        if "saved_value" in params.keys():
            self.value = params["saved_value"]

        self.label = QtWidgets.QLabel(self.name)
        self.label.setMinimumWidth(BT_LABEL_MIN_WIDTH)
        self.data_input = None

        if "Integer" in self.parameter_type:
            self.data_input = QtWidgets.QSpinBox()
        elif "Float" in self.parameter_type or "Double" in self.parameter_type:
            self.data_input = QtWidgets.QDoubleSpinBox()

        if self.data_input:
            self.data_input.setValue(self.value)

        self.data_input.valueChanged.connect(self.update_value)

        self.layout = QtWidgets.QHBoxLayout()
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.data_input)
        self.setLayout(self.layout)

    def update_value(self):
        self.value = self.data_input.value()

    def get_value(self):
        v = self.value
        if v is not None:
            if "Integer" in self.parameter_type:
                value = int(self.value)
            elif "Float" in self.parameter_type:
                value = float(self.value)
            elif "Double" in self.parameter_type:
                value = float(self.value)
            else:  # String or StringOrNumber types
                value = self.value

            return {self.flag: value}
        else:
            if not self.optional:
                msg_box = QtWidgets.QMessageBox()
                msg_box.setIcon(QtWidgets.QMessageBox.Warning)
                msg_box.setText("Unknown non-optional parameter {}.".format(self.flag))
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
