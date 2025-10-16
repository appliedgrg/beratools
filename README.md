# BERA Tools
<div align="center">
BERA Tools is successor of [Forest Line Mapper](https://github.com/appliedgrg/flm). It is a toolset for enhanced delineation and attribution of linear disturbances in forests.

[![GitHub Workflow Status (Build)](https://img.shields.io/github/actions/workflow/status/appliedgrg/bera-tools/python-tests.yml?branch=develop&style=for-the-badge)](https://github.com/appliedgrg/bera-tools/actions/workflows/python-tests.yml)
[![Read the Docs](https://img.shields.io/readthedocs/bera-tools?style=for-the-badge&logo=readthedocs&logoColor=white)](https://bera-tools.readthedocs.io/en/latest/)
<br>
[![Conda Version](https://img.shields.io/conda/v/AppliedGRG/beratools?style=for-the-badge&logo=anaconda&color=green)](https://anaconda.org/AppliedGRG/beratools)
[![Python - Version](https://img.shields.io/badge/PYTHON-3.9+-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/release/python-390/)
<br>
[![License: MIT](https://img.shields.io/github/license/appliedgrg/bera-tools?style=for-the-badge&color=blue)](https://github.com/appliedgrg/bera-tools/blob/main/LICENSE)

</div>
<!--![Banner](docs/files/images/BERALogo.png)-->

## [Quick Start](https://appliedgrg.github.io/beratools)

BERA Tools is built upon open-source Python libraries. Anaconda is used to manage runtime environments.

Installation Steps:

- Install Miniconda. Download Miniconda from [Miniconda](https://docs.anaconda.com/miniconda/) and install on your machine.
- Launch **Anaconda Prompt**. Run the following command to create a new environment. **BERA Tools** will be installed in the new environment at the same time. Download the file [conda_environment.yml](https://github.com/RichardQZeng/BTools/blob/main/conda_environment.yml) first.

   ```bash
   $ conda env create -f conda_environment.yml
   ```

   Wait until the installation is done.
- Activate the **bera** environment and launch BERA Tools:

  ```bash
  $ conda activate bera
  $ beratools
  ```


## User Guide

Check the online [User Guide](https://appliedgrg.github.io/beratools/) for more information.

## Technical Documentation

BERA Tools provides a series of tools for forest lines processing. Please refer to the technical documentation for programming APIs and algorithm details.

[Technical Documentation](https://appliedgrg.github.io/beratools/)

## Contribution Guide

We welcome contributions! Please see our [Contribution Guide](contribution_guide.md) for details.

## Credits

This tool is part of the [**Boreal Ecosystem Recovery and Assessment (BERA)**](http://www.beraproject.org/) Project, and is being actively developed by the [**Applied Geospatial Research Group**](https://www.appliedgrg.ca/).

![Logos](docs/files/images/BERALogo.png)
*Copyright (C) 2025  Applied Geospatial Research Group*
