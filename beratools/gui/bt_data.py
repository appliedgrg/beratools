"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide main interface for GUI related settings.
"""

import json
import logging
import os
from collections import OrderedDict
from pathlib import Path

import beratools.core.constants as bt_const
from beratools.utility.spatial_common import decode_file_layer
from beratools.utility.tool_args import CallMode, determine_cpu_core_limit

BT_SHOW_ADVANCED_OPTIONS = False


def default_callback(value):
    """
    Define default callback that outputs using the print function.

    When tools are called without providing a custom callback, this function
    will be used to print to standard output.
    """
    print(value)


class SettingsManager:
    """An object for managing settings related to BERA Tools GUI."""
    
    def __init__(self, setting_file):
        self.setting_file = setting_file
        self.settings = {}

    def load_saved_tool_info(self):
        if self.setting_file is not None:
            data_path = Path(self.setting_file).parent
            if not data_path.exists():
                data_path.mkdir()

        saved_parameters = {}
        if self.setting_file is not None:
            json_file = Path(self.setting_file)
            if not json_file.exists():
                self.settings = saved_parameters
                return
            with open(json_file, "r") as open_file:
                try:
                    saved_parameters = json.load(open_file, object_pairs_hook=OrderedDict)
                except json.decoder.JSONDecodeError:
                    logging.error("Failed to decode settings JSON file of saved tool info.", exc_info=True)

            # Remove any entry with None or "null" as tool name
            if isinstance(saved_parameters, dict):
                saved_parameters = OrderedDict(
                    (k, v) for k, v in saved_parameters.items()
                    if k is not None and k != "null"
                )

            self.settings = saved_parameters
        else:
            self.settings = saved_parameters
            return

        self.settings = saved_parameters

    def save_tool_info(self, recent_tool=None):
        if recent_tool:
            if "gui_parameters" not in self.settings:
                self.settings["gui_parameters"] = {}
                
            self.settings["gui_parameters"]["recent_tool"] = recent_tool

        if self.setting_file is not None:
            with open(str(self.setting_file), "w") as file_setting:
                try:
                    json.dump(self.settings, file_setting, indent=4)
                except json.decoder.JSONDecodeError:
                    logging.error("Failed to encode settings to JSON when writing.", exc_info=True)

    def save_setting(self, key, value):
        # Guard against None/null tool name
        if key is None:
            print("Warning: tool_name is None, not saving parameters.")
            return

        # check setting directory existence
        if self.setting_file is not None:
            data_path = Path(self.setting_file).resolve().parent
            if not data_path.exists():
                data_path.mkdir()

        self.load_saved_tool_info()

        if value is not None:
            if "gui_parameters" not in self.settings.keys():
                self.settings["gui_parameters"] = {}

            # Fix: Ensure value is a list if existing value is a list
            if (
                key in self.settings["gui_parameters"]
                and isinstance(self.settings["gui_parameters"][key], list)
                and not isinstance(value, list)
            ):
                value = [value]
            self.settings["gui_parameters"][key] = value

            if self.setting_file is not None:
                with open(str(self.setting_file), "w") as write_settings_file:
                    json.dump(self.settings, write_settings_file, indent=4)

    def get_saved_tool_params(self, tool_api, variable=None):
        self.load_saved_tool_info()

        if (
            isinstance(self.settings, dict)
            and "tool_history" in self.settings
            and self.settings["tool_history"] is not None
        ):
            tool_history = self.settings["tool_history"]
            if tool_history is None:
                return None
            if tool_api in list(tool_history):
                tool_params = tool_history[tool_api]
                if tool_params is None:
                    return None
                if variable:
                    if isinstance(tool_params, dict):
                        if variable in tool_params.keys():
                            saved_value = tool_params[variable]
                            return saved_value
                        else:
                            return None
                    else:
                        return None
                else:  # return all params
                    return tool_params

        return None

    def add_tool_history(self, tool, params):
        if "tool_history" not in self.settings:
            self.settings["tool_history"] = OrderedDict()

        self.settings["tool_history"][tool] = params
        self.settings["tool_history"].move_to_end(tool, last=False)

    def remove_tool_history_item(self, index):
        key = list(self.settings["tool_history"].keys())[index]
        self.settings["tool_history"].pop(key)
        self.save_tool_info()

    def remove_tool_history_all(self):
        self.settings.pop("tool_history")
        self.save_tool_info()

    def get_tool_history(self):
        tool_history = []
        self.load_saved_tool_info()
        if (
            isinstance(self.settings, dict)
            and "tool_history" in self.settings
            and self.settings["tool_history"] is not None
        ):
            tool_history = self.settings["tool_history"]

        return tool_history

class BTData(object):
    """An object for interfacing with the BERA Tools executable."""

    def __init__(self):
        self.current_file_path = Path(__file__).resolve().parent

        self.work_dir = Path("")
        self.user_folder = Path("")
        self.data_folder = Path("")
        self.verbose = True
        self.show_advanced = BT_SHOW_ADVANCED_OPTIONS
        self.selected_cpu_cores = -1
        self.recent_tool = None
        self.ascii_art = ""
        self.get_working_dir()
        self.get_user_folder()

        # set maximum available cpu core for tools
        max_cores = determine_cpu_core_limit()
        self.max_cpu_cores = max_cores

        # load bera tools
        self.tool_history = []
        self.bera_tools = None
        self.tools_list = []
        self.sorted_tools = []
        self.upper_toolboxes = []
        self.lower_toolboxes = []
        self.toolbox_list = []
        self.get_bera_tools()
        self.get_bera_tool_list()
        self.get_bera_toolboxes()
        self.sort_toolboxes()

        self.setting_file = None
        self.get_data_folder()
        self.get_setting_file()
        self.settings_manager = SettingsManager(self.setting_file)
        self.gui_setting_file = Path(self.current_file_path).joinpath(bt_const.ASSETS_PATH, r"gui.json")

        self.settings_manager.load_saved_tool_info()
        self.settings = self.settings_manager.settings
        gui_settings = self.settings.get("gui_parameters", {})
        self.recent_tool = gui_settings.get("recent_tool", None)
        self.load_gui_data()
        self.get_tool_history()

        self.default_callback = default_callback
        self.start_minimized = False

    def set_bera_dir(self, path_str):
        """Set the directory to the BERA Tools executable file."""
        self.current_file_path = path_str

    def add_tool_history(self, tool, params):
        self.settings_manager.add_tool_history(tool, params)

    def remove_tool_history_item(self, index):
        self.settings_manager.remove_tool_history_item(index)

    def remove_tool_history_all(self):
        self.settings_manager.remove_tool_history_all()

    def save_tool_info(self):
        self.settings_manager.save_tool_info(self.recent_tool)

    def save_setting(self, key, value):
        # check setting directory existence
        if self.setting_file is not None:
            data_path = Path(self.setting_file).resolve().parent
            if not data_path.exists():
                data_path.mkdir()

        self.load_saved_tool_info()

        if value is not None:
            if "gui_parameters" not in self.settings.keys():
                self.settings["gui_parameters"] = {}

            # Fix: Ensure value is a list if existing value is a list
            if (
                key in self.settings["gui_parameters"]
                and isinstance(self.settings["gui_parameters"][key], list)
                and not isinstance(value, list)
            ):
                value = [value]
            self.settings["gui_parameters"][key] = value

            if self.setting_file is not None:
                with open(str(self.setting_file), "w") as write_settings_file:
                    json.dump(self.settings, write_settings_file, indent=4)

    def get_working_dir(self):
        current_file = Path(__file__).resolve()
        btool_dir = current_file.parents[1]
        self.work_dir = btool_dir

    def get_user_folder(self):
        self.user_folder = Path.home().joinpath(".beratools")
        if not self.user_folder.exists():
            self.user_folder.mkdir()

    def get_data_folder(self):
        self.data_folder = self.user_folder.joinpath(".data")
        if not self.data_folder.exists():
            self.data_folder.mkdir()

    def get_logger_file_name(self, name):
        if not name:
            name = "beratools"

        logger_file_name = self.user_folder.joinpath(name).with_suffix(".log")
        return logger_file_name.as_posix()

    def get_setting_file(self):
        self.setting_file = self.data_folder.joinpath("saved_tool_parameters.json")

    def set_selected_cpu_cores(self, val=-1):
        """Set the number of CPU cores to use."""
        self.selected_cpu_cores = val
        self.save_setting("selected_cpu_cores", val)

    def get_selected_cpu_cores(self):
        return self.selected_cpu_cores

    def get_max_cpu_cores(self):
        return self.max_cpu_cores

    def prepare_tool_run(self, tool_api, args, callback=None):
        """Prepare tool command and arguments."""
        try:
            if callback is None:
                callback = self.default_callback
        except Exception as err:
            if callback is not None:
                callback(str(err))
            else:
                print(str(err))

            return 1

        # Call script using new process to make GUI responsive
        try:
            # convert to valid json string
            args_string = str(args).replace("'", '"')
            args_string = args_string.replace("True", "true")
            args_string = args_string.replace("False", "false")

            tool_name = self.get_bera_tool_name(tool_api)
            tool_type = self.get_bera_tool_type(tool_name)
            tool_args = None

            if tool_type == "python":
                tool_args = [
                    self.work_dir.joinpath(f"tools/{tool_api}.py").as_posix(),
                    "-i", args_string,
                    "-p", str(self.get_selected_cpu_cores()),
                    "-c", CallMode.GUI,
                    "-l", "INFO"
                ]  # fmt: skip
            elif tool_type == "executable":
                print(globals().get(tool_api))
                tool_args = globals()[tool_api](args_string)
                lapis_path = self.work_dir.joinpath("./third_party/Lapis_0_8")
                os.chdir(lapis_path.as_posix())
        except Exception as err:
            callback(str(err))
            return 1

        if tool_args is None:
            tool_args = []
        return tool_type, tool_args

    def about(self):
        """Retrieve the description for BERA Tools."""
        try:
            about_text = "BERA Tools provide a series of tools developed by AppliedGRG lab.\n\n"
            about_text += self.ascii_art
            return about_text
        except (OSError, ValueError) as err:
            return err

    def license(self):
        """Retrieve the license information for BERA Tools."""
        try:
            with open(Path(self.current_file_path).joinpath(r"..\..\LICENSE.txt"), "r") as f:
                ret = f.read()

            return ret
        except (OSError, ValueError) as err:
            return err

    def load_saved_tool_info(self):
        if self.setting_file is not None:
            data_path = Path(self.setting_file).parent
            if not data_path.exists():
                data_path.mkdir()

        saved_parameters = {}
        if self.setting_file is not None:
            json_file = Path(self.setting_file)
            if not json_file.exists():
                self.settings = saved_parameters
                return
            with open(json_file, "r") as open_file:
                try:
                    saved_parameters = json.load(open_file, object_pairs_hook=OrderedDict)
                except json.decoder.JSONDecodeError:
                    logging.error("Failed to decode settings JSON file of saved tool info.", exc_info=True)

            self.settings = saved_parameters
        else:
            self.settings = saved_parameters
            return

        self.settings = saved_parameters

        # parse file
        if (
            isinstance(self.settings, dict)
            and "gui_parameters" in self.settings
            and self.settings["gui_parameters"] is not None
        ):
            gui_settings = self.settings["gui_parameters"]

            if "selected_cpu_cores" in gui_settings and gui_settings["selected_cpu_cores"] is not None:
                self.selected_cpu_cores = gui_settings["selected_cpu_cores"]

            if "recent_tool" in gui_settings and gui_settings["recent_tool"] is not None:
                self.recent_tool = gui_settings["recent_tool"]
                api_result = self.get_bera_tool_api(self.recent_tool)
                if not api_result:
                    self.recent_tool = None
    def load_gui_data(self):
        gui_settings = {}
        if not self.gui_setting_file.exists():
            print("gui.json not exist.")
        else:
            # read the settings.json file if it exists
            with open(self.gui_setting_file, "r") as file_gui:
                try:
                    gui_settings = json.load(file_gui)
                except json.decoder.JSONDecodeError:
                    pass

            # parse file
            if "ascii_art" in gui_settings.keys():
                bera_art = ""
                for line_of_art in gui_settings["ascii_art"]:
                    bera_art += line_of_art
                self.ascii_art = bera_art

    def get_tool_history(self):
        tool_history = self.settings_manager.get_tool_history()

        if tool_history:
            self.tool_history = []
            for item in tool_history:
                item = self.get_bera_tool_name(item)
                self.tool_history.append(item)

    def get_saved_tool_params(self, tool_api, variable=None):
        return self.settings_manager.get_saved_tool_params(tool_api, variable)

    def get_bera_tools(self):
        tool_json_path = Path(self.current_file_path).joinpath(bt_const.ASSETS_PATH, r"beratools.json")
        if tool_json_path.exists():
            with open(tool_json_path, "r") as tool_json_file:
                self.bera_tools = json.load(tool_json_file)
        else:
            print("Tool configuration file not exists")

    def get_bera_tool_list(self):
        self.tools_list = []
        self.sorted_tools = []

        if self.bera_tools and "toolbox" in self.bera_tools:
            for toolbox in self.bera_tools["toolbox"]:
                category = []
                for item in toolbox["tools"]:
                    if item["name"]:
                        category.append(item["name"])
                        self.tools_list.append(item["name"])  # add tool to list

                self.sorted_tools.append(category)

    def sort_toolboxes(self):
        for toolbox in self.toolbox_list:
            # Does not contain a sub toolbox, i.e. does not contain '/'
            if toolbox.find("/") == (-1):
                # add to both upper toolbox list and lower toolbox list
                self.upper_toolboxes.append(toolbox)
                self.lower_toolboxes.append(toolbox)
            else:  # Contains a sub toolbox
                self.lower_toolboxes.append(toolbox)  # add to the lower toolbox list

    def get_bera_toolboxes(self):
        toolboxes = []
        if self.bera_tools and "toolbox" in self.bera_tools:
            for toolbox in self.bera_tools["toolbox"]:
                tb = toolbox["category"]
                toolboxes.append(tb)

            self.toolbox_list = toolboxes
        else:
            self.toolbox_list = []

    def _set_param_flag_and_saved_value(self, single_param, param, tool):
        """Set parameter variable and load saved value if it exists in beratools.json."""
        saved_value = None
        if "variable" in param.keys():
            single_param["variable"] = param["variable"]
            # Only load saved value if tool API exists - discard if API changed
            saved_value = self.get_saved_tool_params(tool["tool_api"], param["variable"])
        if saved_value is not None:
            single_param["saved_value"] = saved_value

    def _set_param_type_for_input(self, single_param, param):
        # Assume subtype is already a list
        subtypes = param["subtype"]

        # No mapping, use raw subtypes directly
        if param["type"] == "list":
            single_param["parameter_type"] = {"OptionList": param["data"]}
            single_param["data_type"] = subtypes
        elif param["type"] == "text":
            single_param["parameter_type"] = "Text"
        elif param["type"] == "number":
            single_param["parameter_type"] = subtypes
        elif param["type"] == "file":
            single_param["parameter_type"] = {"ExistingFile": subtypes}
        elif param["type"] == "directory":
            single_param["parameter_type"] = {"Directory": subtypes}
        else:
            raise ValueError(f"Unknown parameter type: {param['type']}")

    def _set_param_type_for_output(self, single_param, param):
        # Assume subtype is already a list
        subtypes = param["subtype"]
        single_param["parameter_type"] = {"NewFile": subtypes}

    def _find_tool_params(self, tool_name):
        """
        Find raw tool parameters by name.

        Eliminates duplication across multiple methods.
        
        Returns:
            List of parameter definitions from beratools.json, or empty list if not found.
        """
        if self.bera_tools and "toolbox" in self.bera_tools:
            for toolbox in self.bera_tools["toolbox"]:
                for single_tool in toolbox["tools"]:
                    if tool_name == single_tool["name"]:
                        return single_tool.get("parameters", [])
        return []

    def validate_tool_parameter(self, value, param_def):
        """
        Validate and convert parameter to correct type based on beratools.json definition.
        
        Orchestrates validation by dispatching to type-specific validators.

        Args:
            value: The value from GUI input
            param_def: The original parameter definition from beratools.json

        Returns:
            Converted and validated value

        Raises:
            ValueError: If validation fails
        """
        # GUARD CLAUSE 1: Handle None/empty for optional parameters
        if value is None or value == "":
            if param_def.get("optional", False):
                return param_def.get("default", None)
        
        # GUARD CLAUSE 2: Skip validation for output parameters (they don't exist yet)
        if param_def.get("output", False):
            return value
        
        # DISPATCH to type-specific validator
        param_type = param_def.get("type")
        if param_type == "number":
            return self._validate_number(value, param_def)
        elif param_type == "file":
            return self._validate_file(value, param_def)
        elif param_type == "directory":
            return self._validate_directory(value, param_def)
        elif param_type == "text":
            return self._validate_text(value, param_def)
        elif param_type == "list":
            return self._validate_list(value, param_def)
        
        return value

    def _validate_number(self, value, param_def):
        """Validate and convert numeric types (int, float)."""
        subtype = param_def.get("subtype", "")
        variable = param_def.get("variable", "unknown")
        
        if subtype == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    raise ValueError(f"Parameter '{variable}' must be an integer, got {type(value).__name__}")
        
        elif subtype == "float":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    raise ValueError(f"Parameter '{variable}' must be a number, got {type(value).__name__}")
        
        return value

    def _validate_file(self, value, param_def):
        """Validate file exists and is accessible."""
        variable = param_def.get("variable", "unknown")
        
        if not isinstance(value, str):
            raise ValueError(f"Parameter '{variable}' must be a file path string")
        
        # Extract file path and layer name (supports both | and :: separators)
        actual_file_path, layer_name = decode_file_layer(value)
        file_path = Path(actual_file_path)
        
        if not file_path.exists():
            raise ValueError(f"File not found: {actual_file_path}")
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {actual_file_path}")
        
        return value

    def _validate_directory(self, value, param_def):
        """Validate directory exists and is accessible."""
        variable = param_def.get("variable", "unknown")
        
        if not isinstance(value, str):
            raise ValueError(f"Parameter '{variable}' must be a directory path string")
        
        dir_path = Path(value)
        
        if not dir_path.exists():
            raise ValueError(f"Directory not found: {value}")
        if not dir_path.is_dir():
            raise ValueError(f"Path is not a directory: {value}")
        
        return value

    def _validate_text(self, value, param_def):
        """Validate and convert to text/string type."""
        variable = param_def.get("variable", "unknown")
        
        if not isinstance(value, str):
            try:
                value = str(value)
            except Exception:
                raise ValueError(f"Parameter '{variable}' must be text/string")
        
        return value

    def _validate_list(self, value, param_def):
        """Validate list parameter with allowed values and type conversion."""
        subtype = param_def.get("subtype", "")
        variable = param_def.get("variable", "unknown")
        allowed_values = param_def.get("data", [])
        
        # Convert to correct type based on subtype
        if subtype == "bool":
            value = self._convert_bool(value, variable)
        elif subtype == "int":
            value = self._convert_int(value, variable)
        elif subtype == "float":
            value = self._convert_float(value, variable)
        
        # Validate against allowed values
        if value not in allowed_values:
            raise ValueError(
                f"Parameter '{variable}' value '{value}' not in allowed options: {allowed_values}"
            )
        
        return value

    def _convert_bool(self, value, variable):
        """Convert value to boolean."""
        if isinstance(value, str):
            if value.lower() in ["true", "1", "yes"]:
                return True
            elif value.lower() in ["false", "0", "no"]:
                return False
            else:
                raise ValueError(f"Parameter '{variable}' must be boolean, got '{value}'")
        elif not isinstance(value, bool):
            try:
                return bool(value)
            except Exception:
                raise ValueError(f"Parameter '{variable}' must be boolean")
        return value

    def _convert_int(self, value, variable):
        """Convert value to integer."""
        if not isinstance(value, int) or isinstance(value, bool):
            try:
                return int(value)
            except (ValueError, TypeError):
                raise ValueError(f"Parameter '{variable}' must be integer")
        return value

    def _convert_float(self, value, variable):
        """Convert value to float."""
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            try:
                return float(value)
            except (ValueError, TypeError):
                raise ValueError(f"Parameter '{variable}' must be float")
        return value

    def validate_tool_params(self, tool_name, kwargs):
        """
        Validate and convert all tool parameters against beratools.json definitions.

        Args:
            tool_name: Tool name to lookup in beratools.json
            kwargs: Dict of parameter values from GUI input

        Returns:
            Dict of validated/converted values

        Raises:
            ValueError: If any parameter validation fails
        """
        raw_params = self._find_tool_params(tool_name)

        # Build a mapping of variable -> beratools.json param definition
        params_by_variable = {}
        for param in raw_params:
            if "variable" in param:
                params_by_variable[param["variable"]] = param

        validated_kwargs = {}
        for key, value in kwargs.items():
            # Skip framework parameters (handled separately)
            if key in ["processes", "call_mode", "log_level"]:
                validated_kwargs[key] = value
                continue

            # Validate tool parameters against beratools.json definitions
            if key in params_by_variable:
                param_def = params_by_variable[key]
                try:
                    validated_value = self.validate_tool_parameter(value, param_def)
                    validated_kwargs[key] = validated_value
                except ValueError as e:
                    raise ValueError(f"Invalid argument '{key}': {str(e)}")
            else:
                # Unknown parameter - pass through (may be framework param or typo)
                validated_kwargs[key] = value

        return validated_kwargs

    def get_bera_tool_params(self, tool_name):
        new_param_whole = {"parameters": []}
        tool = {}
        
        # Find tool in beratools.json
        if self.bera_tools and "toolbox" in self.bera_tools:
            for toolbox in self.bera_tools["toolbox"]:
                for single_tool in toolbox["tools"]:
                    if tool_name == single_tool["name"]:
                        tool = single_tool

        # Copy non-parameter fields to result
        for key, value in tool.items():
            if key != "parameters":
                new_param_whole[key] = value

        # convert json format for parameters
        if "parameters" not in tool.keys():
            print("issue")

        parameters = self._find_tool_params(tool_name)
        if parameters:
            for param in parameters:
                # Parse subtype string to list once, here
                if isinstance(param.get("subtype", ""), str):
                    param["subtype"] = [s.strip() for s in param["subtype"].split("|")]
                single_param = {"name": param["label"]}
                self._set_param_flag_and_saved_value(single_param, param, tool)
                single_param["output"] = param["output"]
                if not param["output"]:
                    self._set_param_type_for_input(single_param, param)
                else:
                    self._set_param_type_for_output(single_param, param)

                single_param["description"] = param["description"]

                single_param["default_value"] = param["default"]
                single_param["optional"] = param.get("optional", False)

                new_param_whole["parameters"].append(single_param)

        return new_param_whole

    def get_bera_tool_parameters_list(self, tool_name):
        params = self.get_bera_tool_params(tool_name)
        param_list = {}
        parameters = params.get("parameters")
        if parameters is None:
            return param_list
        for item in parameters:
            if item is not None and "variable" in item and "default_value" in item:
                param_list[item["variable"]] = item["default_value"]

        return param_list

    def get_bera_tool_args(self, tool_name):
        params = self.get_bera_tool_params(tool_name)
        tool_args = params["parameters"]

        return tool_args

    def get_bera_tool_name(self, tool_api):
        tool_name = None
        if self.bera_tools and "toolbox" in self.bera_tools:
            for toolbox in self.bera_tools["toolbox"]:
                for tool in toolbox["tools"]:
                    if tool_api == tool["tool_api"]:
                        tool_name = tool["name"]

        return tool_name

    def get_bera_tool_api(self, tool_name):
        tool_api = None
        if self.bera_tools and "toolbox" in self.bera_tools:
            for toolbox in self.bera_tools["toolbox"]:
                for tool in toolbox["tools"]:
                    if tool_name == tool["name"]:
                        tool_api = tool["tool_api"]

        return tool_api

    def get_bera_tool_type(self, tool_name):
        tool_type = None
        if self.bera_tools and "toolbox" in self.bera_tools:
            for toolbox in self.bera_tools["toolbox"]:
                for tool in toolbox["tools"]:
                    if tool_name == tool["name"]:
                        tool_type = tool["tool_type"]

        return tool_type
