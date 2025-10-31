# Installation

Welcome to **BERA Tools**! This guide will help you install the package and get started quickly.

## Prerequisites

- Python 3.10 - 3.13
- conda or pip

## Installation Methods

### Using conda

Have Miniconda installed on your system, then create an environment from the provided [environment.yml](https://raw.githubusercontent.com/appliedgrg/beratools/main/environment.yml):

```bash
conda env create -f environment.yml
conda activate bera
```

### Using Pip

BERA Tools is published to Pypi and can be installed by pip. But on Windows, GDAL should be installed first. Please refer to [GDAL for Windows](https://gdal.org/en/stable/download.html#windows) for more information.

 [OSGeo4W](https://trac.osgeo.org/osgeo4w/https://trac.osgeo.org/osgeo4w/) is recommended for Windows, alongside conda.

```bash
pip install beratools
```

## Verify Installation

After installation, verify that BERA Tools is installed correctly:

```bash
beratools
```

This will start the main GUI.

## Advanced Installation

[Developer Guide](../developer_guide.md) — Detailed instructions for installing from source, running tests, and contributing.

## Update BERA Tools

Run the follwing commands to update BERA Tools.

=== "conda"

    ```bash
    conda update beratools
    ```

=== "pip"

    ```bash
    pip install --upgrade beratools
    ```

## Remove BERA Tools

Remove BERA Tools from environment:

=== "conda"

    ```bash
    conda remove beratools
    ```

=== "pip"

    ```bash
    pip uninstall beratools
    ```

Remove whole conda environment:

```bash
conda activate  # go to base env
conda env remove -n bera
```
