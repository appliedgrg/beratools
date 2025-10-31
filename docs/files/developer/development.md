# Development

## Project Layout

There are a number of files for build, test, and continuous integration in the root of the project, but in general, the
project is broken up like so.

```
├── beratools
│   ├── core
│   ├── gui
│   └── tools
├── docs
│   └── files
├── notebooks
├── tests
```

Directory            | Description
-------------------- | -----------
`beratools/core`     | Core algorithms and logic.
`beratools/gui`      | GUI components and assets.
`beratools/tools`    | Tool implementations.
`docs/files/developer`   | Developer documentation.
`notebooks`          | Example notebooks and configs.
`tests`              | Unit and integration tests.

## Coding Standards

When writing code, the code should roughly conform to PEP8 and PEP257 suggestions.  The PyMdown Extensions project
utilizes the Flake8 linter (with some additional plugins) to ensure code conforms (give or take some of the rules).
When in doubt follow the formatting hints of existing code when adding or modifying files. existing files.  Listed below
are the modules used:

-   @PyCQA/flake8
-   @PyCQA/flake8-docstrings
-   @PyCQA/pep8-naming
-   @ebeweber/flake8-mutable
-   @gforcada/flake8-builtins

Flake8 can be run directly via the command line from the root of the project.

```
flake8
```

## Building and Editing Documents

Documents are in Markdown (with some additional syntax) and converted to HTML via Python Markdown and this
extension bundle. If you would like to build and preview the documentation, you must have these packages installed:

-   @Python-Markdown/markdown: the Markdown parser.
-   @mkdocs/mkdocs: the document site generator.
-   @squidfunk/mkdocs-material: a material theme for MkDocs.
-   @timvink/mkdocs-git-revision-date-localized-plugin: inserts date a page was last updated.
-   @facelessuser/pymdown-extensions: this Python Markdown extension bundle.

These can be installed via:

```
pip install -r requirements/docs.txt
```

In order to build and preview the documents, just run the command below from the root of the project and you should be
able to view the documents at `localhost:8000` in your browser. After that, you should be able to update the documents
and have your browser preview update live.

```
mkdocs serve
```

## Tests

In order to preserve good code health, a test suite has been put together with pytest (@pytest-dev/pytest). There are
currently two kinds of tests: syntax and targeted.  To run these tests, you can use the following command:

You can also run the tests by first installing the requirements:

```
pip install -e .[dev]
```

And then run the tests with:

```
python tests/test_workflow.py
```

### Targeted

Targeted tests are unit tests that target specific areas in the code and exercises them to ensure proper functionality.
These tests are found in `test_targeted.py`.

You can run **only** these tests from the root of the project with:

```
python run_tests.py --test-target targeted
```

You could also run them directly with:

```
py.test tests/test_targeted.py
```


## Code Coverage

When running the validation tests through Tox, it is setup to track code coverage via the Coverage
(@bitbucket:ned/coveragepy) module.  Coverage is run on each `pyxx` environment.  If you've made changes to
the code, you can clear the old coverage data:

```
coverage erase
```

Then run each unit test environment to and coverage will be calculated. All the data from each run is merged together.
HTML is output for each file in `.tox/pyXX-unittests/tmp`.  You can use these to see areas that are not
covered/exercised yet with testing.

You can checkout `tox.ini` to see how this is accomplished.
