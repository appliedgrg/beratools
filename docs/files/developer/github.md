# GitHub

## Protect Branches

branch protection rules help us enforce certain workflows in our repository. We can use them to:

- Apply protection to main branch
- Require pull requests before merging
- Require 1 approving review
- Require status checks (CI) to pass before merge
- Dismiss stale approvals when new commits are pushed
- Prevent force pushes and branch deletion (restrict to admins)
- Limit merge types (e.g., enable only squash merges to keep history clean)


## Actions

GitHub Actions allow you to automate workflows directly in our repository.
BERA Tools uses GitHub Actions for CI/CD pipelines, including:

Here is a summary of the actions defined in all workflow files in `.github/workflows`, grouped by trigger type:

### Push to main

- __mkdocs-gh-pages.yml__
    - Summary: Documentation deployment workflow that builds and publishes docs on changes to `docs/**`.
    - Trigger: On push to `main` affecting `docs/**`.
    - Deploys MkDocs documentation to GitHub Pages.

### Pull request to main

- __python-tests.yml__
    - Summary: CI test and coverage workflow using Pixi and pytest that reports to Codecov.
    - Trigger: On push or pull request to `main` affecting `beratools/**`.
    - Runs pytest with coverage and uploads results to Codecov.

- __publish_to_pypi_test.yml__
    - Summary: Pre-merge PyPI test deployment to validate package publishing on PRs.
    - Trigger: On pull request to `main`.
    - Builds the package and publishes to TestPyPI.

- __tox.yml__
    - Summary: Matrix testing via tox for multiple Python versions (3.10–3.13).
    - Trigger: On pull request to `main` affecting `beratools/**`.
    - Executes tox across multiple Python versions (matrix) to run tests for each target interpreter.

### Version tag push

- __publish_to_anaconda.yml__
    - Summary: Conda packaging and release workflow that publishes packages and attaches test data to Releases.
    - Trigger: On version tag push from `main`.
    - Uses Pixi and rattler-build to build Conda packages, collects build artifacts, uploads them to Anaconda.org, and zips test data to attach to a GitHub Release.

- __publish_to_pypi.yml__
    - Summary: Official PyPI publish workflow for tagged releases.
    - Trigger: On version tag push from `main`.
    - Builds the package and publishes to PyPI.

### Actions Flow

```mermaid
flowchart LR
    Start([Code Change]) --> CheckType{PUsh to GitHub}
    
    CheckType -->|Push to main| Files{Files changed}
    Files -->|docs/**| Mkdocs[Deploy Docs]
    Files -->|beratools/**| Pytest[CI Tests]
    
    CheckType -->|PR to main| PR[PR Validation]
    PR --> PyPITest[Test PyPI]
    PR --> Tox[Tox Grid Tests]
    
    CheckType -->|Version tag| Release[Release]
    Release --> Anaconda[Conda]
    Release --> PyPI[PyPI]
    
    classDef push fill:#e1f5ff,stroke:#01579b
    classDef pr fill:#fff3e0,stroke:#e65100
    classDef rel fill:#e8f5e9,stroke:#2e7d32
    
    class Mkdocs,Pytest push
    class PyPITest,Tox pr
    class Anaconda,PyPI rel
```


## Secure our repository

Our repository is using GitHub's available security features to protect our code from vulnerabilities, unauthorized access, and other potential security threats. These features include:

- Dependabot alerts notify of security vulnerabilities in BERA Tools dependency network, so that we can update the affected dependency to a more secure version.
- Secret scanning scans our repository for secrets (such as API keys and tokens) and alerts us if a secret is found, so that we can remove the secret from our repository.
- Push protection prevents we (and our collaborators) from introducing secrets to the repository in the first place, by blocking pushes containing supported secrets.
- Code scanning identifies vulnerabilities and errors in our repository's code, so that we can fix these issues early and prevent a vulnerability or error being exploited by malicious actors.

## Branching based workflow

To streamline collaboration, we recommend that regular collaborators work from a single repository, creating pull requests between branches instead of between repositories. 

Forking is best suited for accepting contributions from people that are unaffiliated with a project, such as open-source contributors.

To maintain quality of main branch, while using a branching workflow, we use protected branches with required status checks and pull request reviews.