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
import os
import platform
from collections import OrderedDict
from pathlib import Path

import beratools.core.constants as bt_const

running_windows = platform.system() == "Windows"
BT_SHOW_ADVANCED_OPTIONS = False


def default_callback(value):
    """
    Define default callback that outputs using the print function.

    When tools are called without providing a custom callback, this function
    will be used to print to standard output.
    """
    print(value)


class BTData(object):
    """An object for interfacing with the BERA Tools executable."""

    def __init__(self):
        if running_windows:
            self.ext = ".exe"
        else:
            self.ext = ""
        self.current_file_path = Path(__file__).resolve().parent

        self.work_dir = ""
        self.user_folder = Path("")
        self.data_folder = Path("")
        self.verbose = True
        self.show_advanced = BT_SHOW_ADVANCED_OPTIONS
        self.max_procs = -1
        self.recent_tool = None
        self.ascii_art = None
        self.get_working_dir()
        self.get_user_folder()

        # set maximum available cpu core for tools
        self.max_cpu_cores = os.cpu_count()

        # load bera tools
        self.tool_history = []
        self.settings = {}
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
        self.gui_setting_file = Path(self.current_file_path).joinpath(bt_const.ASSETS_PATH, r"gui.json")

        self.load_saved_tool_info()
        self.load_gui_data()
        self.get_tool_history()

        self.default_callback = default_callback
        self.start_minimized = False

    def set_bera_dir(self, path_str):
        """Set the directory to the BERA Tools executable file."""
        self.current_file_path = path_str

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

    def save_tool_info(self):
        if self.recent_tool:
            if "gui_parameters" not in self.settings.keys():
                self.settings["gui_parameters"] = {}

            self.settings["gui_parameters"]["recent_tool"] = self.recent_tool

        with open(self.setting_file, "w") as file_setting:
            try:
                json.dump(self.settings, file_setting, indent=4)
            except json.decoder.JSONDecodeError:
                pass

    def save_setting(self, key, value):
        # check setting directory existence
        data_path = Path(self.setting_file).resolve().parent
        if not data_path.exists():
            data_path.mkdir()

        self.load_saved_tool_info()

        if value is not None:
            if "gui_parameters" not in self.settings.keys():
                self.settings["gui_parameters"] = {}

            self.settings["gui_parameters"][key] = value

            with open(self.setting_file, "w") as write_settings_file:
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

    def set_max_procs(self, val=-1):
        """Set the maximum cores to use."""
        self.max_procs = val
        self.save_setting("max_procs", val)

    def get_max_procs(self):
        return self.max_procs

    def get_max_cpu_cores(self):
        return self.max_cpu_cores

    def run_tool(self, tool_api, args, callback=None):
        """
        Run a tool and specifies tool arguments.

        Returns 0 if completes without error.
        Returns 1 if error encountered (details are sent to callback).
        Returns 2 if process is cancelled by user.
        """
        try:
            if callback is None:
                callback = self.default_callback
        except Exception as err:
            callback(str(err))
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
                    "-i",
                    args_string,
                    "-p",
                    str(self.get_max_procs()),
                    "-v",
                    str(self.verbose),
                ]
            elif tool_type == "executable":
                print(globals().get(tool_api))
                tool_args = globals()[tool_api](args_string)
                lapis_path = self.work_dir.joinpath("./third_party/Lapis_0_8")
                os.chdir(lapis_path.as_posix())
        except Exception as err:
            callback(str(err))
            return 1

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
        data_path = Path(self.setting_file).parent
        if not data_path.exists():
            data_path.mkdir()

        saved_parameters = {}
        json_file = Path(self.setting_file)
        if not json_file.exists():
            return

        with open(json_file) as open_file:
            try:
                saved_parameters = json.load(open_file, object_pairs_hook=OrderedDict)
            except json.decoder.JSONDecodeError:
                pass

        self.settings = saved_parameters

        # parse file
        if "gui_parameters" in self.settings.keys():
            gui_settings = self.settings["gui_parameters"]

            if "max_procs" in gui_settings.keys():
                self.max_procs = gui_settings["max_procs"]

            if "recent_tool" in gui_settings.keys():
                self.recent_tool = gui_settings["recent_tool"]
                if not self.get_bera_tool_api(self.recent_tool):
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
        tool_history = []
        self.load_saved_tool_info()
        if self.settings:
            if "tool_history" in self.settings:
                tool_history = self.settings["tool_history"]

        if tool_history:
            self.tool_history = []
            for item in tool_history:
                item = self.get_bera_tool_name(item)
                self.tool_history.append(item)

    def get_saved_tool_params(self, tool_api, variable=None):
        self.load_saved_tool_info()

        if "tool_history" in self.settings:
            if tool_api in list(self.settings["tool_history"]):
                tool_params = self.settings["tool_history"][tool_api]
                if tool_params:
                    if variable:
                        if variable in tool_params.keys():
                            saved_value = tool_params[variable]
                            return saved_value
                    else:  # return all params
                        return tool_params

        return None

    def get_bera_tools(self):
        tool_json = Path(self.current_file_path).joinpath(bt_const.ASSETS_PATH, r"beratools.json")
        if tool_json.exists():
            tool_json = open(Path(self.current_file_path).joinpath(bt_const.ASSETS_PATH, r"beratools.json"))
            self.bera_tools = json.load(tool_json)
        else:
            print("Tool configuration file not exists")

    def get_bera_tool_list(self):
        self.tools_list = []
        self.sorted_tools = []

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
        for toolbox in self.bera_tools["toolbox"]:
            tb = toolbox["category"]
            toolboxes.append(tb)

        self.toolbox_list = toolboxes

    def get_bera_tool_params(self, tool_name):
        new_param_whole = {"parameters": []}
        tool = {}
        batch_tool_list = []
        for toolbox in self.bera_tools["toolbox"]:
            for single_tool in toolbox["tools"]:
                if single_tool["batch_processing"]:
                    batch_tool_list.append(single_tool["name"])

                if tool_name == single_tool["name"]:
                    tool = single_tool

        for key, value in tool.items():
            if key != "parameters":
                new_param_whole[key] = value

        # convert json format for parameters
        if "parameters" not in tool.keys():
            print("issue")

        for param in tool["parameters"]:
            single_param = {"name": param["parameter"]}
            if "variable" in param.keys():
                single_param["flag"] = param["variable"]
                # restore saved parameters
                saved_value = self.get_saved_tool_params(tool["tool_api"], param["variable"])
                if saved_value is not None:
                    single_param["saved_value"] = saved_value
            else:
                single_param["flag"] = "FIXME"

            single_param["output"] = param["output"]
            if not param["output"]:
                if param["type"] == "list":
                    if tool_name == "Batch Processing":
                        single_param["parameter_type"] = {"OptionList": batch_tool_list}
                        single_param["data_type"] = "String"
                    else:
                        single_param["parameter_type"] = {"OptionList": param["data"]}
                        single_param["data_type"] = "String"
                        if param["typelab"] == "text":
                            single_param["data_type"] = "String"
                        elif param["typelab"] == "int":
                            single_param["data_type"] = "Integer"
                        elif param["typelab"] == "float":
                            single_param["data_type"] = "Float"
                        elif param["typelab"] == "bool":
                            single_param["data_type"] = "Boolean"
                elif param["type"] == "text":
                    single_param["parameter_type"] = "String"
                elif param["type"] == "number":
                    if param["typelab"] == "int":
                        single_param["parameter_type"] = "Integer"
                    else:
                        single_param["parameter_type"] = "Float"
                elif param["type"] == "file":
                    single_param["parameter_type"] = {"ExistingFile": [param["typelab"]]}
                else:
                    single_param["parameter_type"] = {"ExistingFile": ""}
            else:
                single_param["parameter_type"] = {"NewFile": [param["typelab"]]}

            single_param["description"] = param["description"]

            if param["type"] == "raster":
                for i in single_param["parameter_type"].keys():
                    single_param["parameter_type"][i] = "Raster"
            elif param["type"] == "lidar":
                for i in single_param["parameter_type"].keys():
                    single_param["parameter_type"][i] = "Lidar"
            elif param["type"] == "vector":
                for i in single_param["parameter_type"].keys():
                    single_param["parameter_type"][i] = "Vector"
                if "layer" in param.keys():
                    layer_value = self.get_saved_tool_params(tool["tool_api"], param["layer"])
                    single_param["layer"] = {
                        "layer_name": param["layer"],
                        "layer_value": layer_value,
                    }

            elif param["type"] == "Directory":
                single_param["parameter_type"] = {"Directory": [param["typelab"]]}

            single_param["default_value"] = param["default"]
            if "optional" in param.keys():
                single_param["optional"] = param["optional"]
            else:
                single_param["optional"] = False

            new_param_whole["parameters"].append(single_param)

        return new_param_whole

    def get_bera_tool_parameters_list(self, tool_name):
        params = self.get_bera_tool_params(tool_name)
        param_list = {}
        for item in params["parameters"]:
            param_list[item["flag"]] = item["default_value"]

        return param_list

    def get_bera_tool_args(self, tool_name):
        params = self.get_bera_tool_params(tool_name)
        tool_args = params["parameters"]

        return tool_args

    def get_bera_tool_name(self, tool_api):
        tool_name = None
        for toolbox in self.bera_tools["toolbox"]:
            for tool in toolbox["tools"]:
                if tool_api == tool["tool_api"]:
                    tool_name = tool["name"]

        return tool_name

    def get_bera_tool_api(self, tool_name):
        tool_api = None
        for toolbox in self.bera_tools["toolbox"]:
            for tool in toolbox["tools"]:
                if tool_name == tool["name"]:
                    tool_api = tool["tool_api"]

        return tool_api

    def get_bera_tool_type(self, tool_name):
        tool_type = None
        for toolbox in self.bera_tools["toolbox"]:
            for tool in toolbox["tools"]:
                if tool_name == tool["name"]:
                    tool_type = tool["tool_type"]

        return tool_type
