# Code Testing

BERA Tools employs a `pytest` framework to ensure code quality and reliability. This document outlines the testing strategies, tools, and workflows used in the repository.

## Testing Workflows

- **pytest**: All code is tested using the pytest framework. Tests are located in the `tests` directory and cover modules, tools, and workflows.
- **Test triggers**: Tests run automatically on push and pull request events affecting `beratools` via GitHub Actions.
- **Coverage**: Test coverage is measured and reported to Codecov.
- **Matrix testing**: The `tox.yml` workflow runs tests across multiple Python versions (3.10–3.14) to ensure compatibility.

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

1. **tox.yml**: This workflow runs tests across multiple Python versions (3.10 to 3.14) using `tox`. It ensures that the codebase is compatible with all supported Python versions.

1. **python-tests.yml**: This workflow runs the test suite using `pytest` whenever code is pushed to the repository or a pull request is created. It helps catch issues early in the development process.

Refer to the [Maintainer Guide](./maintainer.md#pull-request-to-main) for more information on these workflows.

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
