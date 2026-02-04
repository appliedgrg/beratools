# Publishing BERA Tools

BERA Tools is published to Conda and Pypi when main brach is tagged by new version.

## Versioning

BERA Tools Versioning follows [PEP440](https://peps.python.org/pep-0440/): `major.minor.patch`.

| Versions | Description |
|-----------|--------------|
| **Major** | This is reserved for releases that introduce breaking features. |
| **Minor** | This is reserved for releases that introduce new functionality. |
| **Patch** | This is reserved for releases that only include bug fixes. |

## Packaging BERA Tools

BERA Tools is packaged for distribution on both PyPI and Anaconda. The packaging process is automated using GitHub Actions workflows that are triggered on version tag pushes to the main branch.

See the following workflows:

- Conda Packaging and Release: [publish_to_anaconda.yml](https://github.com/appliedgrg/beratools/blob/main/.github/workflows/publish_to_anaconda.yml)
- PyPI Packaging and Release: [publish_to_pypi.yml](https://github.com/appliedgrg/beratools/blob/main/.github/workflows/publish_to_pypi.yml)
- TestPyPI Packaging (manual): [publish_to_pypi_test.yml](https://github.com/appliedgrg/beratools/blob/main/.github/workflows/publish_to_pypi_test.yml)

See two actions details in [Maintainer Guide](maintainer.md#version-tag-push).

## Releases

[Anaconda BERA Tools](https://anaconda.org/appliedgrg/beratools)

[Pypi BERA Tools](https://pypi.org/project/BERATools)

## TestPyPI (Manual Validation)

For release rehearsals or packaging checks, maintainers can trigger the TestPyPI workflow manually.

1. Go to **Actions** in GitHub and select **Publish to PyPI Test**.
2. Click **Run workflow** to trigger the `workflow_dispatch` job.
3. The workflow builds the package and publishes it to TestPyPI.