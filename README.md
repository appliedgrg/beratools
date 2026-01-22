# BERA Tools

BERA Tools is successor of [Forest Line Mapper](https://github.com/appliedgrg/flm). It is a toolset for enhanced delineation and attribution of linear disturbances in forests.

<div align="center">

[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/appliedgrg/beratools/python-tests.yml?branch=main)](https://github.com/appliedgrg/beratools/actions/workflows/python-tests.yml)
[![Codecov](https://img.shields.io/codecov/c/github/appliedgrg/beratools/main)](https://codecov.io/gh/appliedgrg/beratools)
[![GitHub Pages](https://img.shields.io/github/deployments/appliedgrg/beratools/github-pages?label=docs)](https://appliedgrg.github.io/beratools/)
[![Conda Version](https://img.shields.io/conda/v/AppliedGRG/beratools)](https://anaconda.org/AppliedGRG/beratools)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/release/python-3100/)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

</div>

## [Quick Start](https://appliedgrg.github.io/beratools)

BERA Tools is built upon open-source Python libraries. Anaconda is used to manage runtime environments.

There are multiple ways to install BERA Tools:

- Windows installer
- QGIS Plugin (To be released)
- Install with Anaconda.

### Windows Installer

Windows installer is provided with releases. Check the [latest release](https://github.com/appliedgrg/beratools/releases/latest) for the up-to-date installer.

### QGIS Plugin

BERA Tools is also available as a QGIS plugin (To be released).

### Install with Anaconda

Install with Anaconda works on Windows, macOS, and Linux.

- Install Miniconda. Download Miniconda from [Miniconda](https://docs.anaconda.com/miniconda/) and install on your machine.
- Download the file [environment.yml](https://raw.githubusercontent.com/appliedgrg/beratools/main/environment.yml
) and save to local storage. Launch **Anaconda Prompt** or **Miniconda Prompt**.
- **Change directory** to where environment.yml is saved in the command prompt.
- Run the following command to create a new environment named **bera**. **BERA Tools** will be installed in the new environment at the same time.

   ```bash
   $ conda env create -n bera -f environment.yml
   ```

   Wait until the installation is done.
- Activate the **bera** environment and launch BERA Tools:

  ```bash
  $ conda activate bera
  $ beratools
  ```

- [Download latest example data](https://github.com/appliedgrg/beratools/releases/latest/download/test_data.zip) to try with BERA Tools.
- To update BERA Tools when new release is issued, run the following commands:

    ```bash
    $ conda activate bera
    $ conda update beratools
    ```

- To completely remove BERA Tools and its environment, run the following command:

    ```bash
    $ conda remove -n bera
    ```

## BERA Tools Guide

Check the online [BERA Tools Guide](https://appliedgrg.github.io/beratools/) for user, developer guides.

## Credits

<table>
  <tr>
    <td><img src="docs/files/icons/bera_logo.png" alt="Logos" width="80"></td>
    <td>
      <p>
        This tool is part of the <strong><a href="http://www.beraproject.org/">Boreal Ecosystem Recovery & Assessment (BERA)</a></strong>.
        It is actively developed by the <a href="https://www.appliedgrg.ca/"><strong>Applied Geospatial Research Group</strong></a>.
      </p>
      <p>
        © 2026 Applied Geospatial Research Group. All rights reserved.
      </p>
    </td>
  </tr>
</table>
