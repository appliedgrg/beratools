# Overview

## Versioning

Versioning follows [PEP440](https://peps.python.org/pep-0440/): `major.minor.patch`.

| Versions | Description |
|-----------|--------------|
| **Major** | This is reserved for releases that introduce breaking features. |
| **Minor** | This is reserved for releases that introduce new functionality. |
| **Patch** | This is reserved for releases that only include bug fixes. |

## From Source

To install the latest development version from source:

### Use Conda

```bash
# Option A: create env from the provided environment.yml
conda env create -f environment.yml
conda activate beratools

# Option B: create a fresh conda env manually
conda create -n beratools python=3.11 -y
conda activate beratools
conda install -c conda-forge pip git setuptools wheel -y

# Install the package from the cloned source (editable for development)
git clone https://github.com/appliedgrg/beratools.git
cd beratools
pip install -e .

# If the project exposes development extras:
# pip install -e ".[dev]"
```

### Use Pip

```bash
git clone https://github.com/appliedgrg/beratools.git
cd beratools
pip install .
```


## Packaging BERA Tools

### Build PyPI Package

### Build Conda Package


pip build only
backend: mamba install hatch
front end: pip install build
PyPI upload: mamba install twine


 recommended way to install BERA Tools
 > conda create -n bera -c conda-forge -c appliedgrg python=3.11 mamba --override-channels
 > conda activate bera
 > conda config --set channel_priority strict
 > mamba install --file conda_requirements.txt

 check channels in use
 > conda config --get channels
 Example output:
   --add channels 'conda-forge'   # lowest priority
   --add channels 'appliedgrg'   # highest priority