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
