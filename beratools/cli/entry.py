"""Unified BERATools CLI entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from beratools.utility.tool_args import CallMode


TOOL_ALIASES = {
    "check_line": "check_seed_line",
    "vertex_opt": "vertex_optimization",
    "centerline": "centerline",
    "footprint_abs": "canopy_footprint_absolute",
    "footprint_rel": "line_footprint_relative",
    "footprint_grd": "ground_footprint",
}


def _assets_json_path() -> Path:
    return Path(__file__).resolve().parents[1] / "gui" / "assets" / "beratools.json"


def _load_tools_config() -> dict[str, dict[str, Any]]:
    with open(_assets_json_path(), "r", encoding="utf-8") as f:
        data = json.load(f)

    by_api: dict[str, dict[str, Any]] = {}
    for toolbox in data.get("toolbox", []):
        for tool in toolbox.get("tools", []):
            api = tool.get("tool_api")
            if api:
                by_api[api] = tool
    return by_api


def _parse_subtype(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [token.strip() for token in value.split("|") if token.strip()]
    return []


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value!r}")


def _coerce_value(value: Any, subtype: str) -> Any:
    if subtype == "bool":
        return _to_bool(value)
    if subtype == "int":
        return int(value)
    if subtype == "float":
        return float(value)
    return value


def _argparse_type_for_param(param: dict[str, Any]):
    ptype = param.get("type")
    subtypes = _parse_subtype(param.get("subtype"))
    subtype = subtypes[0] if subtypes else ""

    if ptype == "number":
        if subtype == "int":
            return int
        return float

    if ptype == "list":
        if subtype == "bool":
            return _to_bool
        if subtype == "int":
            return int
        if subtype == "float":
            return float
        return str

    return str


def _add_framework_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-p", "--processes", type=int, default=0, help="Number of CPU processes (default: 0)")
    parser.add_argument(
        "-c",
        "--call_mode",
        default=CallMode.CLI.value,
        help="Tool call mode: CLI or GUI (default: CLI)",
    )
    parser.add_argument(
        "-l",
        "--log_level",
        default="INFO",
        help="Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)",
    )


def _add_tool_args(parser: argparse.ArgumentParser, tool_cfg: dict[str, Any]) -> None:
    for param in tool_cfg.get("parameters", []):
        variable = param.get("variable")
        if not variable:
            continue

        ptype = _argparse_type_for_param(param)
        optional = bool(param.get("optional", False))
        default = param.get("default")
        required = not optional
        help_text = (param.get("description") or "").replace("%", "%%")

        kwargs: dict[str, Any] = {
            "required": required,
            "help": help_text,
            "type": ptype,
        }

        if optional and default not in (None, ""):
            subtypes = _parse_subtype(param.get("subtype"))
            subtype = subtypes[0] if subtypes else ""
            kwargs["default"] = _coerce_value(default, subtype)

        if param.get("type") == "list" and isinstance(param.get("data"), list):
            subtypes = _parse_subtype(param.get("subtype"))
            subtype = subtypes[0] if subtypes else ""
            kwargs["choices"] = [_coerce_value(choice, subtype) for choice in param.get("data", [])]

        parser.add_argument(f"--{variable}", **kwargs)


def _build_parser(prog: str, tools_cfg: dict[str, dict[str, Any]]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description="BERATools unified CLI")
    subparsers = parser.add_subparsers(dest="command")

    gui_parser = subparsers.add_parser("gui", help="Launch BERATools GUI")
    gui_parser.set_defaults(handler=lambda _args: launch_gui())

    list_parser = subparsers.add_parser("list-tools", help="List available short tool commands")
    list_parser.set_defaults(handler=lambda _args: print_tool_list())

    for short_name, tool_api in TOOL_ALIASES.items():
        tool_cfg = tools_cfg.get(tool_api)
        if tool_cfg is None:
            continue

        tool_parser = subparsers.add_parser(short_name, help=tool_cfg.get("info", ""))
        _add_tool_args(tool_parser, tool_cfg)
        _add_framework_args(tool_parser)
        tool_parser.set_defaults(tool_api=tool_api, handler=run_tool_command)

    return parser


def _resolve_tool_function(tool_api: str):
    if tool_api == "check_seed_line":
        from beratools.tools.check_seed_line import check_seed_line

        return check_seed_line
    if tool_api == "vertex_optimization":
        from beratools.tools.vertex_optimization import vertex_optimization

        return vertex_optimization
    if tool_api == "centerline":
        from beratools.tools.centerline import centerline

        return centerline
    if tool_api == "canopy_footprint_absolute":
        from beratools.tools.canopy_footprint_absolute import canopy_footprint_abs

        return canopy_footprint_abs
    if tool_api == "line_footprint_relative":
        from beratools.tools.line_footprint_relative import line_footprint_relative

        return line_footprint_relative
    if tool_api == "ground_footprint":
        from beratools.tools.ground_footprint import ground_footprint

        return ground_footprint
    raise ValueError(f"Unsupported tool_api: {tool_api}")


def run_tool_command(args: argparse.Namespace) -> int:
    from beratools.utility import env_checks

    env_checks.warn_gdal_proj_env()

    tool_api = args.tool_api
    fn = _resolve_tool_function(tool_api)
    payload = vars(args).copy()
    payload.pop("command", None)
    payload.pop("handler", None)
    payload.pop("tool_api", None)
    fn(**payload)
    return 0


def launch_gui() -> int:
    from beratools.gui.main import gui_main

    gui_main()
    return 0


def print_tool_list() -> int:
    print("Available tools:")
    for short_name, tool_api in TOOL_ALIASES.items():
        print(f"- {short_name} ({tool_api})")
    return 0


def print_basic_info(prog: str) -> int:
    print("BERATools CLI")
    print(f"Alias: {prog}")
    print("Use 'gui' to launch the GUI.")
    print("Use '--help' to see all commands.")
    print("Use 'list-tools' to list tool subcommands.")
    return 0


def run(argv: list[str] | None = None, prog_name: str | None = None) -> int:
    import sys

    if argv is None:
        argv = sys.argv[1:]

    prog = prog_name or Path(sys.argv[0]).name
    tools_cfg = _load_tools_config()
    parser = _build_parser(prog=prog, tools_cfg=tools_cfg)

    if not argv:
        return print_basic_info(prog)

    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return int(handler(args))
