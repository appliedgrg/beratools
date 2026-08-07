# Advanced Installation

Welcome to **BERA Tools**! This guide will give you advanced installation options and configurations.

## Prerequisites

- Python 3.10 - 3.14
- conda or pip

## Installation Methods

### Windows Installer

Download the standalone Windows installer from the [latest BERA Tools release](https://github.com/appliedgrg/beratools/releases/latest). Official installers are signed according to the project [Code signing policy](https://github.com/appliedgrg/beratools/blob/main/CODE_SIGNING_POLICY.md).

Only installers attached to an official GitHub Release are intended for users. Artifacts from manual signing tests use a self-signed test certificate and must not be distributed.

#### Verify the Installer Signature

Before running a downloaded installer on Windows:

1. Right-click the installer and select **Properties**.
2. Open the **Digital Signatures** tab.
3. Select the SignPath Foundation signature and click **Details**.
4. Confirm Windows reports **This digital signature is OK**.

You can also verify the installer with PowerShell:

```powershell
Get-AuthenticodeSignature .\beratools-installer-x.y.z.exe |
    Format-List Status, StatusMessage, SignerCertificate, TimeStamperCertificate
```

For an official release, `Status` must be `Valid`. Do not run the installer if the signature is missing or invalid.

### Using conda

Have Miniconda installed on your system, then create an environment from the provided [environment.yml](https://raw.githubusercontent.com/appliedgrg/beratools/main/environment.yml):

```bash
conda env create -f environment.yml
conda activate bera
```

### Using Pip

BERA Tools is published to Pypi and can be installed by pip. On Windows, if you use the standalone installer, GDAL/PROJ are bundled. For pip-based installs, GDAL should be installed first. Please refer to [GDAL for Windows](https://gdal.org/en/stable/download.html#windows) for more information.

Example: install GDAL from a Windows wheel (adjust the URL/version as needed):

```bash
pip install "gdal @ https://github.com/cgohlke/geospatial-wheels/releases/download/v2025.10.25/gdal-3.11.4-cp311-cp311-win_amd64.whl"
```

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

## Install From Source

[Developer Guide](../developer_guide.md) — Detailed instructions for installing from source, running tests, and contributing.

## Update BERA Tools

Run the following commands to update BERA Tools.

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
