# Development Standards

This document outlines the development standards and practices for contributing to the BERA Tools project.

## Coding Standards

When writing code, follow [PEP8](https://peps.python.org/pep-0008/) (style guide) and [PEP257](https://peps.python.org/pep-0257/) (docstring conventions) guidelines. This project uses [`ruff`](https://github.com/appliedgrg/beratools/blob/main/pyproject.toml:83) for linting and [`mypy`](https://github.com/appliedgrg/beratools/blob/main/pyproject.toml:120) for type checking, as configured in [`pyproject.toml`](https://github.com/appliedgrg/beratools/blob/main/pyproject.toml). Some rules are ignored or customized; see the configuration for details. When in doubt, match the formatting of existing code.

### PEP8 Summary

- Use 4 spaces per indentation level.
- Limit lines to 110 characters.
- Use blank lines to separate functions and classes.
- Use spaces around operators and after commas.
- Use `snake_case` for function and variable names, `PascalCase` for class names.
- Use docstrings to document all public modules, functions, classes, and methods.

### PEP257 Summary

- Use triple double quotes for docstrings.
- The first line should be a short summary of the object's purpose.
- For multi-line docstrings, the second line should be blank, followed by a more detailed description.
- Use imperative mood for function and method docstrings.

### Running Linters and Type Checkers

Ruff is recommended for linting. `pyproject.toml` has configuration for Ruff. Ruff can be run directly via the command line from the root of the project:

``` bash
ruff .
```

MyPy is used for static type checking. Type hints should be added to functions and methods where appropriate.

Mypy can be run with:

``` bash
mypy .
```
