# Versioning

BERA Tools uses semantic versioning.
<https://semver.org/>

Given a version number MAJOR.MINOR.PATCH, increment the:

- MAJOR version when you make incompatible API changes  
- MINOR version when you add functionality in a backward compatible manner  
- PATCH version when you make backward compatible bug fixes  

Additional labels for pre-release and build metadata are available as extensions to the MAJOR.MINOR.PATCH format.

The version start from 0.1.0.

## From Source

To install the latest development version from source:

### Use Conda

```bash
# Option A: create env from the provided environment.yml
conda env create -f environment.yml
conda activate beratools

# Option B: create a fresh conda env manually
conda create -n beratools python=3.10 -y
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