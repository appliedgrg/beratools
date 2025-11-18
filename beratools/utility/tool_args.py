"""Utility functions for tool argument parsing."""

import argparse
import json
import os
import platform
from enum import Enum


# TODO: Consider using StrEnum from Python 3.11+
class StrEnum(str, Enum):
    pass

class CallMode(StrEnum):
    CLI = "CLI"
    GUI = "GUI"

def determine_cpu_core_limit():
    running_windows = platform.system() == "Windows"
    core_count = os.cpu_count() or 1
    max_cores = max(core_count - 1, 1)
    if running_windows:
        max_cores = min(max_cores, 60)
    return max_cores

def compose_tool_kwargs(tool_api):
    """
    Auto-detecting argument composer for both CLI and GUI modes.

    - Detects mode from --input presence
    - GUI: unpacks --input JSON, adds common args from CLI flags
    - CLI: parses all args from beratools.json definitions with validation
    - Returns: complete kwargs dict with all parameters

    Note: In CLI mode, argparse automatically prints help and exits
    if required arguments are missing.
    """
    from beratools.gui.bt_data import BTData

    bt_data = BTData()
    tool_name = bt_data.get_bera_tool_name(tool_api)
    tool_api_name = tool_api

    mode_parser = argparse.ArgumentParser(add_help=False)
    mode_parser.add_argument("-i", "--input", type=json.loads, default=None)
    mode_parser.add_argument("-c", "--call_mode", default=CallMode.CLI.value)
    mode_parser.add_argument("-p", "--processes", type=int, default=0)
    mode_parser.add_argument("-l", "--log_level", default="INFO")
    mode_args, remaining = mode_parser.parse_known_args()

    if mode_args.input is not None:
        # GUI MODE: unpack tool params from JSON
        kwargs = mode_args.input.copy()

    else:
        # CLI MODE: parse tool params from CLI args with validation
        # Load parameter definitions from beratools.json
        tool_params = bt_data.get_bera_tool_params(tool_name)

        # Helper: Separate parameters by type
        required_params = [
            p for p in tool_params.get("parameters", []) if p.get("variable") and not p.get("optional", False)
        ]
        optional_params = [
            p for p in tool_params.get("parameters", []) if p.get("variable") and p.get("optional", False)
        ]

        # Build usage string with only required parameters
        required_flags = " ".join([f"--{p.get('variable')}" for p in required_params])
        custom_usage = f"python {tool_api_name}.py {required_flags}" if required_flags else f"python {tool_api_name}.py"

        full_parser = argparse.ArgumentParser(
            prog=tool_name,
            usage=custom_usage,
            description=f"Tool: {tool_name}",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )

        # Create argument groups
        required_group = full_parser.add_argument_group("Required Parameters")
        optional_group = full_parser.add_argument_group("Optional Parameters")
        framework_group = full_parser.add_argument_group("Framework Options")

        # Helper function to add parameters to argument group
        def add_param_args(group, params, required=False):
            """Add parameter arguments to argument group."""
            for param in params:
                arg_config = {"required": required}
                if param.get("default_value") is not None and param.get("default_value") != "":
                    arg_config["default"] = param.get("default_value")
                if param.get("description"):
                    # Escape % in help text to prevent argparse formatting errors
                    arg_config["help"] = param.get("description").replace("%", "%%")
                group.add_argument(f"--{param.get('variable')}", **arg_config)

        # Add required and optional parameters using helper
        add_param_args(required_group, required_params, required=True)
        add_param_args(optional_group, optional_params, required=False)

        # Add framework parameters to their group (with descriptions)
        framework_group.add_argument(
            "-p",
            "--processes",
            type=int,
            default=mode_args.processes,
            help="Number of CPU processes (default: 1)",
        )
        framework_group.add_argument(
            "-c", "--call_mode", default=mode_args.call_mode, help="'CLI' or 'GUI' mode (default: CLI)"
        )
        framework_group.add_argument(
            "-l",
            "--log_level",
            default=mode_args.log_level,
            help="DEBUG, INFO, WARNING, ERROR (default: INFO)",
        )

        # Parse all arguments
        # This automatically prints help and exits if required args are missing
        args = full_parser.parse_args()
        kwargs = vars(args)

    # Always ensure framework params are set from first pass
    kwargs.update(
        {"processes": mode_args.processes, "call_mode": mode_args.call_mode, "log_level": mode_args.log_level}
    )

    return kwargs
