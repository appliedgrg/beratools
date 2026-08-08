# Code Testing

BERA Tools employs a `pytest` framework to ensure code quality and reliability. This document outlines the testing strategies, tools, and workflows used in the repository.

## Testing Workflows

- **pytest**: Tests use pytest and are located in the `tests` directory. The automated workflows described below run only `tests/test_workflow.py`, not the complete test suite.
- **Automatic integration testing**: The `python-integration-tests.yml` workflow runs `tests/test_workflow.py` on pushes to `main` and on qualifying pull requests targeting `main` when its configured path filters match.
- **Coverage**: Coverage from `tests/test_workflow.py` is printed in the GitHub Actions job log; it is not uploaded to an external service.
- **Runtime environment**: The automatic integration workflow uses the Pixi-managed Python 3.12/GDAL environment.
- **Manual compatibility testing**: The dispatch-only `python-compatibility-tests.yml` workflow runs `tests/test_workflow.py` through tox in Python 3.12, 3.13, and 3.14 micromamba environments with conda-forge GDAL.

## Running Tests Locally

To run tests locally, follow these steps:

1. Install the required dependencies:

   ```bash
   pip install .[dev]
   ```

2. Run all the test suite using `pytest`:

=== "Run All tests"
    Discover and execute all tests in the `tests` directory.
    ```bash
    pytest
    ```

=== "Run a test file"
    Run a specific test file:
    ```bash
    pytest tests/path/to/test_tools.py
    ```

=== "Run a test function"
    Run a specific test function within a file:
    ```bash
    pytest tests/path/to/test_tools.py::test_function_name
    ```

## GitHub Actions

BERA Tools uses GitHub Actions to automate testing and deployment processes. This document describes the various workflows set up in the repository to ensure code quality and streamline releases.

1. **python-compatibility-tests.yml**: This dispatch-only workflow runs `tests/test_workflow.py` through tox under Python 3.12, 3.13, and 3.14 in micromamba environments with conda-forge GDAL and native geospatial libraries.

2. **python-integration-tests.yml**: This automatic workflow runs `tests/test_workflow.py` with terminal coverage on pushes to `main` and qualifying pull requests targeting `main`.

Refer to the [Maintainer Guide](./maintainer.md#automatic-integration-tests) for more information on these workflows.

## Write Tests

It is required to write tests when contributing to BERA Tools. follow these guidelines to ensure consistency and quality in the test suite.

### conftest.py

The `conftest.py` file in the `tests` directory contains shared fixtures and configurations for the test suite. You can add common setup code here that can be reused across multiple test files.

### Test Organization

Tests are organized in the `tests` directory. Each module or tool should have a corresponding test file. .

### Naming Conventions

Test files should be named with the prefix `test_` which can be detected by pytest automatically. The test file name should be followed by the module or tool name (e.g., `test_tools.py`).

### Writing Tests

When writing tests, use assertions to verify that the code behaves as expected. Utilize fixtures from `conftest.py` for setup and cleanup operations.
