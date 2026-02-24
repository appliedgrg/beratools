import logging

from packaging.version import Version
from beratools.gui import bt_data


class _FakeDist:
    def __init__(self, version, path):
        self.version = version
        self._path = path
        self.metadata = {"Name": "BERATools"}


def test_get_app_version_info_prefers_metadata(monkeypatch):
    monkeypatch.delenv("BERATOOLS_APP_VERSION", raising=False)
    monkeypatch.setattr(bt_data, "_resolve_metadata_version", lambda: "1.2.3")
    monkeypatch.setattr(bt_data, "_run_git_command", lambda *args, **kwargs: "v9.9.9-1-gabc123")

    info = bt_data.get_app_version_info()

    assert info["version"] == "1.2.3"
    assert info["short_version"] == "1.2.3"
    assert info["is_release"] is True


def test_get_app_version_info_handles_no_git(monkeypatch):
    monkeypatch.delenv("BERATOOLS_APP_VERSION", raising=False)
    monkeypatch.setattr(bt_data, "_resolve_metadata_version", lambda: None)
    monkeypatch.setattr(bt_data, "_run_git_command", lambda *args, **kwargs: None)

    info = bt_data.get_app_version_info()

    assert info["version"] != ""
    assert "short_version" in info
    assert "is_release" in info


def test_get_app_version_info_from_git_describe_ahead(monkeypatch):
    def _fake_run_git(command, **_kwargs):
        if command[:2] == ["git", "describe"]:
            return "v1.2.3-4-gabc123"
        if command[:2] == ["git", "rev-parse"]:
            return "abc123"
        return None

    monkeypatch.delenv("BERATOOLS_APP_VERSION", raising=False)
    monkeypatch.setattr(bt_data, "_resolve_metadata_version", lambda: None)
    monkeypatch.setattr(bt_data, "_run_git_command", _fake_run_git)

    info = bt_data.get_app_version_info()

    assert info["version"] == "1.2.3+4.gabc123"
    assert info["short_version"] == "1.2.3"
    assert info["git_revision"] == "abc123"
    assert info["is_release"] is False


def test_get_app_version_info_prefers_runtime_override(monkeypatch):
    monkeypatch.setenv("BERATOOLS_APP_VERSION", "3.4.5")
    monkeypatch.setattr(bt_data, "_resolve_metadata_version", lambda: "1.2.3")
    monkeypatch.setattr(bt_data, "_run_git_command", lambda *args, **kwargs: "v9.9.9-1-gabc123")

    info = bt_data.get_app_version_info()

    assert info["version"] == "3.4.5"
    assert info["short_version"] == "3.4.5"


def test_resolve_metadata_version_selects_highest_and_logs_warning(monkeypatch, caplog):
    dists = [
        _FakeDist("0.2.5", "C:/env/site-packages/BERATools-0.2.5.dist-info"),
        _FakeDist("0.3.3", "C:/env/site-packages/BERATools-0.3.3.dist-info"),
    ]
    monkeypatch.setattr(bt_data, "_iter_beratools_distributions", lambda: dists)

    with caplog.at_level(logging.WARNING):
        selected = bt_data._resolve_metadata_version()

    assert selected == "0.3.3"
    assert "multiple BERATools metadata versions" in caplog.text
    assert "selected=0.3.3" in caplog.text


def test_resolve_metadata_version_tie_breaks_deterministically(monkeypatch, caplog):
    dists = [
        _FakeDist("0.3.3", "C:/env/site-packages/z.dist-info"),
        _FakeDist("0.3.3", "C:/env/site-packages/a.dist-info"),
    ]
    monkeypatch.setattr(bt_data, "_iter_beratools_distributions", lambda: dists)

    with caplog.at_level(logging.WARNING):
        selected = bt_data._resolve_metadata_version()

    assert selected == "0.3.3"
    assert "source=C:/env/site-packages/a.dist-info" in caplog.text


def test_resolve_metadata_version_orders_release_post_dev_local(monkeypatch):
    versions = ["1.2.3", "1.2.3.post1", "1.2.4.dev1", "1.2.3+local.1"]
    dists = [_FakeDist(version, f"C:/env/site-packages/{i}.dist-info") for i, version in enumerate(versions)]
    monkeypatch.setattr(bt_data, "_iter_beratools_distributions", lambda: dists)

    selected = bt_data._resolve_metadata_version()

    expected = max(versions, key=Version)
    assert selected == expected


def test_run_git_command_uses_no_console_flag_on_windows(monkeypatch):
    captured = {}

    class _Completed:
        stdout = "abc123\n"

    def _fake_run(*args, **kwargs):
        captured.update(kwargs)
        return _Completed()

    monkeypatch.setattr(bt_data.os, "name", "nt")
    monkeypatch.setattr(bt_data.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(bt_data.subprocess, "run", _fake_run)

    value = bt_data._run_git_command(["git", "rev-parse", "--short", "HEAD"], cwd=".")

    assert value == "abc123"
    assert captured["creationflags"] == 0x08000000
