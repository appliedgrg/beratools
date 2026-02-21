from importlib.metadata import PackageNotFoundError

from beratools.gui import bt_data


def test_get_app_version_info_prefers_metadata(monkeypatch):
    monkeypatch.setattr(bt_data.importlib_metadata, "version", lambda name: "1.2.3")
    monkeypatch.setattr(bt_data, "_run_git_command", lambda *args, **kwargs: "v9.9.9-1-gabc123")

    info = bt_data.get_app_version_info()

    assert info["version"] == "1.2.3"
    assert info["short_version"] == "1.2.3"
    assert info["is_release"] is True


def test_get_app_version_info_handles_no_git(monkeypatch):
    def _raise_not_found(_name):
        raise PackageNotFoundError

    monkeypatch.setattr(bt_data.importlib_metadata, "version", _raise_not_found)
    monkeypatch.setattr(bt_data, "_run_git_command", lambda *args, **kwargs: None)

    info = bt_data.get_app_version_info()

    assert info["version"] != ""
    assert "short_version" in info
    assert "is_release" in info


def test_get_app_version_info_from_git_describe_ahead(monkeypatch):
    def _raise_not_found(_name):
        raise PackageNotFoundError

    def _fake_run_git(command, **_kwargs):
        if command[:2] == ["git", "describe"]:
            return "v1.2.3-4-gabc123"
        if command[:2] == ["git", "rev-parse"]:
            return "abc123"
        return None

    monkeypatch.setattr(bt_data.importlib_metadata, "version", _raise_not_found)
    monkeypatch.setattr(bt_data, "_run_git_command", _fake_run_git)

    info = bt_data.get_app_version_info()

    assert info["version"] == "1.2.3+4.gabc123"
    assert info["short_version"] == "1.2.3"
    assert info["git_revision"] == "abc123"
    assert info["is_release"] is False
