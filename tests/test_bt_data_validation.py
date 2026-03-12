import pytest

from beratools.gui.bt_data import BTData


def _param(subtype):
    return {
        "variable": "in_line",
        "type": "file",
        "subtype": subtype,
        "optional": False,
        "output": False,
    }


def test_validate_file_restricted_gpkg_requires_layer(tmp_path):
    bt = BTData()
    gpkg = tmp_path / "input.gpkg"
    gpkg.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="requires a layer"):
        bt._validate_file(str(gpkg), _param("vector|line"))


def test_validate_file_restricted_gpkg_mismatch(monkeypatch, tmp_path):
    bt = BTData()
    gpkg = tmp_path / "input.gpkg"
    gpkg.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "beratools.gui.bt_data.pyogrio.read_info",
        lambda *_args, **_kwargs: {"geometry_type": "Polygon"},
    )

    with pytest.raises(ValueError, match="Geometry mismatch"):
        bt._validate_file(f"{gpkg}|centerline", _param("vector|line"))


def test_validate_file_restricted_shp_mismatch(monkeypatch, tmp_path):
    bt = BTData()
    shp = tmp_path / "input.shp"
    shp.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "beratools.gui.bt_data.pyogrio.read_info",
        lambda *_args, **_kwargs: {"geometry_type": "Polygon"},
    )

    with pytest.raises(ValueError, match="Geometry mismatch"):
        bt._validate_file(str(shp), _param("vector|line"))


def test_validate_file_restricted_shp_match(monkeypatch, tmp_path):
    bt = BTData()
    shp = tmp_path / "input.shp"
    shp.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "beratools.gui.bt_data.pyogrio.read_info",
        lambda *_args, **_kwargs: {"geometry_type": "MultiLineString"},
    )

    value = bt._validate_file(str(shp), _param("vector|line"))
    assert value == str(shp)


def test_validate_file_unrestricted_vector_allows_plain_path(tmp_path):
    bt = BTData()
    gpkg = tmp_path / "input.gpkg"
    gpkg.write_text("", encoding="utf-8")

    value = bt._validate_file(str(gpkg), _param("vector"))
    assert value == str(gpkg)


def test_validate_list_text_option_accepts_allowed_value():
    bt = BTData()
    param = {
        "variable": "guided_strategy",
        "type": "list",
        "subtype": "text",
        "data": ["main_route", "pairwise", "virtual_nodes"],
        "optional": False,
        "output": False,
    }

    value = bt.validate_tool_parameter("pairwise", param)
    assert value == "pairwise"


def test_validate_list_text_option_rejects_unknown_value():
    bt = BTData()
    param = {
        "variable": "guided_strategy",
        "type": "list",
        "subtype": "text",
        "data": ["main_route", "pairwise", "virtual_nodes"],
        "optional": False,
        "output": False,
    }

    with pytest.raises(ValueError, match="allowed options"):
        bt.validate_tool_parameter("legacy_mode", param)


def test_set_last_browse_dir_keeps_latest_value_after_save_side_effect(monkeypatch, tmp_path):
    bt = BTData()
    old_dir = tmp_path / "old"
    old_dir.mkdir()
    new_dir = tmp_path / "new"
    new_dir.mkdir()
    bt.last_browse_dir = old_dir.as_posix()

    def fake_save_setting(_key, _value):
        bt.last_browse_dir = old_dir.as_posix()

    monkeypatch.setattr(bt, "save_setting", fake_save_setting)

    bt.set_last_browse_dir(new_dir.as_posix())

    assert bt.get_last_browse_dir() == new_dir.as_posix()
