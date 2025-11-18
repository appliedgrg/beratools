# How to Add a New Tool

## tool_template.py

This file provides a template for developing new geospatial tools in the BERA Tools framework.

## Purpose

- Provides a consistent structure for tool development.
- Serves as a starting point for custom tool development.
- Demonstrates all steps to use the BERA Tools framework to create a new geospatial tool.
    - Tool API definition.
    - Argument parsing for CLI and GUI modes.
- Illustrates the optional use of multiprocessing for performance optimization and easy GUI integration.

## Features

- **GeoPandas Integration:** Reads and writes geospatial files.
- **Buffer Operation:** Applies a buffer to each feature in the input dataset.
- **Parallel Processing:** Uses Python's `multiprocessing` via `execute_multiprocessing` for faster operations.
- **GUI Integration:** Arguments are defined in `beratools.json` for GUI support.

## Usage

- Can run in different modes:
    - from inside main GUI
    - as a standalone script (CLI)
    - imported as a module in another Python script.

## Steps to Add a New Tool

- Update `gui/assets/beratools.json` for GUI integration.
  Add this json snippet to the "tools" array:

  ```json
  {
      "category": "Templates",
      "description": "Tools template.",
      "tools": [
        {
          "name": "Feature Buffer",
          "info": "Buffer input feature class.",
          "tool_type": "python",
          "tool_api": "tool_template",
          "icon": "tool_template.gif",
          "tech_link": "https://appliedgrg.github.io/beratools/developer/tool_template/",
          "parameters": [
            {
              "variable": "in_feature",
              "label": "Input Feature Class",
              "description": "Input Feature Class.",
              "type": "file",
              "subtype": "vector",
              "default": "",
              "output": false,
              "optional": false
            },
            {
              "variable": "buffer_dist",
              "label": "Buffer Distance (m)",
              "description": "Set distance to generate buffer for input features.",
              "type": "number",
              "subtype": "float",
              "default": 10,
              "output": false,
              "optional": false
            },
            {
              "variable": "out_feature",
              "label": "Output Buffered Features",
              "description": "Output buffered features.",
              "type": "file",
              "subtype": "vector",
              "default": "",
              "output": true,
              "optional": false
            }
          ]
        }
      ]
    }
  ```

This is both for documentation and GUI integration.

- This snippet adds new category called "Templates".
- "Tools" is the sub-array where each tool is defined. Now only one tool: "Feature Buffer" is defined.
- Tool description provides metadata which is used by both the GUI and CLI.
    - "name"  - Tool name as shown in GUI.
    - "info"  - Short description of the tool.
    - "tool_type" - Type of tool, here it's "python".
    - "tool_api"  - Corresponding python script name without .py extension.
    - "icon"  - Icon file for the tool in GUI.
    - "tech_link"  - Link to technical documentation.
- "parameters"  - Array defining tool parameters.
      - Each parameter has attributes:
          -  "variable": parameter name used in the script. This will be the argument name in CLI too.
          -  "label": Label shown in GUI.
          -  "description": Description shown in GUI and CLI help.
          -  "type" and "subtype" together define data type.
          -  "default": default value of the parameter.
          -  "output": Shows if parameter is an output or input, this helps GUI to manage file dialogs.
          -  "optional": Indicates if parameter is optional. Will affect GUI appearance and CLI parsing.
- Add CLI parser in "__main__" section of the tool script, tool_template.py which can be found inside "beratools/tools".

Tool API:

```python
def tool_template(in_feature, buffer_dist, out_feature, 
                processes=0, call_mode=CallMode.CLI, log_level="INFO")
```

\_\_main\_\_ section of tool_template.py:

```python
if __name__ == "__main__":
    from beratools.utility.tool_args import compose_tool_kwargs
    kwargs = compose_tool_kwargs("tool_template")
    tool_template(**kwargs)
```

compose_tool_kwargs reads `beratools.json` and sets up argument parsing for the tool based on the defined parameters. In three modes:

- GUI mode: arguments are passed from the GUI. all tool parameters are packed into json and passed as a single argument -i/--input. This will help GUI to manage complex parameters for different tools universally.
- CLI mode: arguments are parsed from command line. each parameter is passed as a separate argument. Only non-optional parameters are added to CLI arguments. Optional parameters with default values are omitted unless user wants to override them. But thee still printed in help output with default values.
  When developing a new tool, you can test it from CLI first before integrating into GUI.
- Module mode: arguments are passed as function parameters. Since compose_tool_kwargs is called only in __main__ section, so this mode is independent of it.

Here is the help output when running the script from CLI:

```bash
$ python .\tool_template.py --help

usage: python tool_template.py --in_feature --buffer_dist --out_feature

Tool: Feature Buffer

options:
  -h, --help            show this help message and exit

Required Parameters:
  --in_feature IN_FEATURE
                        Input Feature Class.
  --buffer_dist BUFFER_DIST
                        Set distance to generate buffer for input features.
  --out_feature OUT_FEATURE
                        Output buffered features.

Framework Options:
  -p PROCESSES, --processes PROCESSES
                        Number of CPU processes (default: 0)
  -c CALL_MODE, --call_mode CALL_MODE
                        'CLI' or 'GUI' mode (default: CLI)
  -l LOG_LEVEL, --log_level LOG_LEVEL
                        DEBUG, INFO, WARNING, ERROR (default: INFO)
```

Thi will print arguments in three sections: 

- Required Parameters: have to be present to run the tool.
- Optional Parameters: default values are provided and can be omitted.
- Framework Options: These are added on top of user-defined parameters for all tools in the framework. They are added to make GUI and CLI modes handle multiprocessing, call mode and log level automatically, so users typically don't need to set them manually. They are usually added as the last arguments in the tool API.
    - `--processes`: Number of CPU processes (default: 0). Tools will determine optimal CPU cores to use. When set to 1, multiprocessing is automatically disabled and runs in sequential process mode.
    - `--call_mode`: 'CLI' or 'GUI' mode (default: CLI). Tools will know how they are called and set this value. The value will affect logging and progress reporting behavior. In GUI mode, progress is reported to the GUI progress bar, while in CLI mode, progress is printed to the console.
    - `--log_level`: DEBUG, INFO, WARNING, ERROR (default: INFO).

## Multiprocessing

We provide a utility function `execute_multiprocessing` in `beratools.core.tool_base` to help run processing functions in parallel using Python's `multiprocessing` module.

This function takes split data and a processing function as input, manages the creation of worker processes, and handles the collection of results. It simplifies the implementation of parallel processing in your tools by:

- Auto detecting the number of CPU cores available and setting up worker processes accordingly.
- It will reserve one core for system operations. For Windows, it limits the maximum CPU cores to 60 to address system limitations (WaitForMultipleObjects in Windows is 64 kernel objects). No limits on Linux.
- Auto switching to sequential processing when only one process is specified.
- Other than processing, it also manages logging and progress reporting based on the call mode (CLI or GUI). This makes it easier to integrate multiprocessing tools into both CLI and GUI environments.

```python
results = execute_multiprocessing(buffer_worker, gdf_list, "tool_template", processes, call_mode)
```

- `buffer_worker`: The processing function to be executed in parallel. It should accept a single argument (a subset of the data) and return the processed result.
- `gdf_list`: The data to be processed, split into chunks for each worker process.
- `"tool_template"`: The name of the tool, used for logging and progress reporting.
- `processes`: Number of CPU processes to use.
- `call_mode`: 'CLI' or 'GUI' mode for logging and progress reporting.

## Complex tools

This template has only simple algorithm. In real-world scenarios, the processing function may involve more complex logic and data manipulations. The tool scripts in "tools" folder means to provide lightweight gateway to all tools. Heavy logics are suppose to be implemented in core modules. This will help keep tool scripts clean and focused on argument parsing and integration with the BERA Tools framework.

Please see all [documentation for developers](https://appliedgrg.github.io/beratools/developer_guide/) and other tools in the "tools" folder for more examples. This follows the BERA Tools structure and best practice of seperation of concerns.
