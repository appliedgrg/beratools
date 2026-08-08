import tomllib
from pathlib import Path


def test_pixi_environment_installs_project_and_docs_dependencies():
    manifest_path = Path(__file__).parents[1] / "pixi.toml"
    with manifest_path.open("rb") as manifest_file:
        manifest = tomllib.load(manifest_file)

    pypi_dependencies = manifest["pypi-dependencies"]
    assert pypi_dependencies["beratools"] == {"path": ".", "editable": True}
    assert {
        "zensical",
        "mkdocstrings",
        "mkdocstrings-python",
        "pymdown-extensions",
    } <= pypi_dependencies.keys()
