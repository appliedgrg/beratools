# Local Development

This document provides guidelines and instructions for setting up a local development environment for BERA Tools.

## Local Development Setup

### Using Pixi

Pixi is the easiest way to set up a consistent development environment for BERA Tools. The configuration is defined in [`pixi.toml`](https://github.com/appliedgrg/beratools/blob/main/pixi.toml).

#### Setup Instructions

1. **Install pixi**

    Follow the official instructions at [pixi.sh](https://pixi.sh/docs/install/) to install pixi.

1. **Create the environment**

    In the project root, run the command to setup all dependencies as specified in `pixi.toml`.

    ```bash
    git clone https://github.com/appliedgrg/beratools.git
    pixi install  # Run this command inside the beratools project root
    ```

1. **Activate the environment**

    ```bash
    pixi shell
    pip install -e .  # Install your local code in editable mode
    ```

1. **Update the environment**

    To update dependencies, re-run the `pixi install` again. Pixi will detect changes in pixi.toml and install or update packages accordingly.

    For more details, review the dependencies and tasks in [`pixi.toml`](../../../../pixi.toml:1).

### Using Conda

A manual conda environment setup for local development (without using environment.yml) can be done as follows:

1. Create a new environment:

   ```bash
   conda create -n bera python=3.11 -y
   conda activate bera
   ```

1. Install dependencies individually:

   ```bash
   conda install -c appliedgrg bera_centerlines
   conda install -c conda-forge dask gdal=3.9.3 geopandas pyogrio>=0.9.0 pyqt rasterio scikit-image>=0.24.0 tqdm xarray-spatial
   ```

1. Install your local code in editable mode:

   ```bash
    git clone https://github.com/appliedgrg/beratools.git
    cd beratools
    pip install -e .
   ```

This approach avoids installing the released beratools package and uses only the dependencies listed in [`environment.yml`](../../../../environment.yml:8), but installs them step-by-step.

---
**Note:**
If you use `environment.yml`, conda will install the released `beratools` package from the channel, not your local code.

## pyproject.toml

[pyproject.toml](https://github.com/appliedgrg/beratools/blob/main/pyproject.toml) is used to define the build system and dependencies for BERA Tools. It is recommended to use this file for managing project dependencies and packaging.

### pyproject.toml Functional Groups

| Group                      | Purpose/Functionality                                                                 |
|---------------------------|---------------------------------------------------------------------------------------|
| Build System              | **[build-system]**: build backend and build-time dependencies (e.g., build-backend, requires). |
| Metadata & Core           | **[project]**: project identity and core settings — name, version, description, authors, license, requires-python, dependencies, classifiers, keywords. |
| Optional Dependencies     | **[project.optional-dependencies]**: extras grouped for development, documentation, testing, etc. |
| Entry Points / Scripts    | **[project.scripts]**: CLI entry points mapping console commands to callables.            |
| Project URLs              | **[project.urls]**: homepage, repository, issue tracker, documentation, changelog links. |
| Versioning & Build        | **[tool.hatch.version]**, **[tool.hatch.version.raw-options]**, **[tool.hatch.build.targets.sdist]**: version strategy and build-target customization. |
| Linting & Formatting Tools| **[tool.ruff]**, **[tool.markdownlint]**: code and markdown linting/formatting configurations. |
| Type Checking             | **[tool.mypy]**: static type-checker configuration and strictness options.               |
| Testing & Coverage        | **[tool.coverage.run]**, **[tool.coverage.report]**, **[tool.pytest.ini_options]**: test runner and coverage reporting settings. |
