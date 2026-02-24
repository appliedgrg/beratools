import pytest

from beratools.cli import entry


@pytest.mark.parametrize("alias", ["bt", "beratools"])
def test_no_arg_alias_prints_basic_cli_info(capsys, alias):
    code = entry.run(argv=[], prog_name=alias)
    assert code == 0

    out = capsys.readouterr().out
    assert "BERATools CLI" in out
    assert "Use 'gui' to launch the GUI." in out
    assert "Use 'list-tools' to list tool subcommands." in out


def test_gui_subcommand_launches_gui(monkeypatch):
    called = {"value": False}

    def _fake_launch_gui():
        called["value"] = True
        return 0

    monkeypatch.setattr(entry, "launch_gui", _fake_launch_gui)
    code = entry.run(argv=["gui"], prog_name="bt")

    assert code == 0
    assert called["value"] is True


def test_help_smoke(capsys):
    with pytest.raises(SystemExit) as exc:
        entry.run(argv=["--help"], prog_name="bt")

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "list-tools" in out
    assert "gui" in out
    assert "check_line" in out


def test_parse_and_dispatch_short_tool(monkeypatch):
    received = {}

    def _fake_tool(**kwargs):
        received.update(kwargs)

    monkeypatch.setattr("beratools.utility.env_checks.warn_gdal_proj_env", lambda: None)
    monkeypatch.setattr(entry, "_resolve_tool_function", lambda _api: _fake_tool)

    code = entry.run(
        argv=[
            "check_line",
            "--in_line",
            "input.gpkg|seed_lines",
            "--out_line",
            "out.gpkg|seed_lines_checked",
            "--processes",
            "2",
            "--call_mode",
            "CLI",
            "--log_level",
            "DEBUG",
        ],
        prog_name="bt",
    )

    assert code == 0
    assert received["in_line"] == "input.gpkg|seed_lines"
    assert received["out_line"] == "out.gpkg|seed_lines_checked"
    assert received["processes"] == 2
    assert received["call_mode"] == "CLI"
    assert received["log_level"] == "DEBUG"


def test_alias_parity_no_arg_output(capsys):
    outputs = []
    for alias in ("bt", "beratools"):
        entry.run(argv=[], prog_name=alias)
        outputs.append(capsys.readouterr().out)

    for out in outputs:
        assert "BERATools CLI" in out
        assert "Use '--help' to see all commands." in out
        assert "Use 'list-tools' to list tool subcommands." in out
