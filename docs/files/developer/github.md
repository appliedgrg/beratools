# GitHub

## Protect Branches

branch protection rules help you enforce certain workflows in your repository. You can use them to:
- Apply protection to main branch
- Require pull requests before merging
- Require 1 approving review
- Require status checks (CI) to pass before merge
- Dismiss stale approvals when new commits are pushed
- Prevent force pushes and branch deletion (restrict to admins)
- Limit merge types (e.g., enable only squash merges to keep history clean)


## Actions

GitHub Actions allow you to automate workflows directly in your repository. 
BERA Tools uses GitHub Actions for CI/CD pipelines, including:

Here is a summary of the actions defined in all workflow files in `.github/workflows`:

- __mkdocs-gh-pages.yml__  
    - Deploys MkDocs documentation to GitHub Pages on push to `main` affecting `docs/**`.
    - Installs GDAL system libraries and Python dependencies, installs the project in editable mode, then runs `mkdocs gh-deploy` to publish docs.
    - Summary: Documentation deployment workflow that builds and publishes docs on changes to `docs/**`.

- __publish_to_anaconda.yml__  
    - Triggers on version tag pushes; verifies the tag comes from `main`.
    - Uses Pixi and rattler-build to build Conda packages, collects build artifacts, uploads them to Anaconda.org, and zips test data to attach to a GitHub Release.
    - Summary: Conda packaging and release workflow that publishes packages and attaches test data to Releases.

- __publish_to_pypi_test.yml__  
    - Runs on pull requests to `main`; builds the package and publishes to TestPyPI.
    - Installs build tools and dependencies and uses `pypa/gh-action-pypi-publish` for publishing.
    - Summary: Pre-merge PyPI test deployment to validate package publishing on PRs.

- __publish_to_pypi.yml__  
    - Triggers on version tag pushes; verifies the tag comes from `main`.
    - Installs build tools and dependencies and uses `pypa/gh-action-pypi-publish` to publish to PyPI.
    - Summary: Official PyPI publish workflow for tagged releases.

- __python-tests.yml__  
    - Runs on push or pull request to `main` affecting `beratools/**`; installs GDAL and Pixi, sets up the Pixi environment, and installs project dependencies.
    - Runs pytest with coverage and uploads results to Codecov.
    - Summary: CI test and coverage workflow using Pixi and pytest that reports to Codecov.

- __tox.yml__  
    - Runs on pull requests to `main` affecting `beratools/**`; installs GDAL and tox.
    - Executes tox across multiple Python versions (matrix) to run tests for each target interpreter.
    - Summary: Matrix testing via tox for multiple Python versions (3.10–3.13).

# Discussions