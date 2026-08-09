# Publishing BERA Tools

BERA Tools is published to Conda and PyPI when the `main` branch is tagged with a new version. The Windows installer is then built, signed, and published by manually dispatching its release workflow from that tagged `main` commit.

## Versioning

BERA Tools Versioning follows [PEP440](https://peps.python.org/pep-0440/): `major.minor.patch`.

| Versions | Description |
| --- | --- |
| **Major** | This is reserved for releases that introduce breaking features. |
| **Minor** | This is reserved for releases that introduce new functionality. |
| **Patch** | This is reserved for releases that only include bug fixes. |

## Packaging BERA Tools

BERA Tools is packaged for distribution on both PyPI and Anaconda. The packaging process is automated using GitHub Actions workflows that are triggered on version tag pushes to the main branch.

See the following workflows:

- Conda Packaging and Release: [publish_to_anaconda.yml](https://github.com/appliedgrg/beratools/blob/main/.github/workflows/publish_to_anaconda.yml)
- PyPI Packaging and Release: [publish_to_pypi.yml](https://github.com/appliedgrg/beratools/blob/main/.github/workflows/publish_to_pypi.yml)
- Windows Installer Build and Signing: [build-win-installer.yml](https://github.com/appliedgrg/beratools/blob/main/.github/workflows/build-win-installer.yml)

See the workflow inventory in the [Maintainer Guide](maintainer.md#actions).

### Re-running a Failed PyPI Publication

If `publish_to_pypi.yml` fails before PyPI accepts any distribution files, a maintainer with write access can open the original GitHub Actions run and select **Re-run jobs -> Re-run failed jobs**. GitHub rebuilds and republishes from the same version tag, commit SHA, Git ref, and trusted-publishing identity. Workflow runs can be rerun for up to 30 days.

Before rerunning, confirm that the version has no files on PyPI. If PyPI accepted any files before the failure, do not rerun blindly: distribution filenames are immutable and duplicate uploads fail. Inspect the release and publish a new patch version if the release is incomplete. A rerun also uses the workflow definition from the tagged commit, so a defect in the workflow itself must be fixed before creating a new release tag.

### Re-running a Failed Anaconda Publication

If the tag-triggered Anaconda workflow fails before uploading a package, open [Publish to Anaconda](https://github.com/appliedgrg/beratools/actions/workflows/publish_to_anaconda.yml), select **Run workflow**, choose `main`, and enter the existing numeric version tag in **Version tag to publish**. The workflow checks out that tag and verifies that its commit belongs to `main` before rebuilding.

Leave **Build and validate without publishing** enabled to test the complete build and smoke-test path without using the Anaconda token or modifying a GitHub Release. The validated Conda package is attached to the workflow run as an artifact. For a production recovery, confirm that the version is absent from [Anaconda BERA Tools](https://anaconda.org/appliedgrg/beratools), disable the dry run, and dispatch the workflow. Do not rerun it after a package file has already been accepted.

## Windows Installer Signing

Official Windows installers follow the project [Code signing policy](https://github.com/appliedgrg/beratools/blob/main/CODE_SIGNING_POLICY.md). Test and release signing use the same SignPath artifact configuration so a manual test validates the artifact that will later be released.

| Trigger | Signing policy | Approval | Result |
| --- | --- | --- | --- |
| Manual dispatch with no release tag | `test-signing` | Disabled by policy | Signed GitHub Actions artifact only |
| Manual dispatch from `main` with a matching release tag | `release-signing` | One approval required | Signed artifact and GitHub Release |

### Manual Signing Test

Run a test after changing the installer, its build script, the signing workflow, or the SignPath artifact configuration.

1. Open [Build Windows Installer](https://github.com/appliedgrg/beratools/actions/workflows/build-win-installer.yml) in GitHub Actions.
2. Select **Run workflow** and choose the branch to test.
3. Wait for the `Submit installer to SignPath` step to complete using `test-signing`.
4. Confirm the run contains both `beratools-installer-unsigned` and `beratools-installer-signed` artifacts.
5. Confirm `Upload signed installer to release` was skipped.

The test certificate is self-signed, so `Get-AuthenticodeSignature` may report `UnknownError` because its root is not trusted by Windows. The workflow still requires a signer certificate and rejects an unsigned installer. Test-signed installers are for validation only and must not be distributed as releases.

### Production Release

1. Merge the release changes into `main` and ensure all release workflows are ready.
2. Create a `major.minor.patch` version tag on the current `main` commit and push the tag. Do not advance `main` until all release workflows complete.
3. Open [Build Windows Installer](https://github.com/appliedgrg/beratools/actions/workflows/build-win-installer.yml), select **Run workflow**, choose `main`, and enter the version tag in **Version tag to release**.
4. Confirm the workflow verifies that the supplied tag points exactly to the dispatched `main` commit, is the latest numeric version tag, and submits with `release-signing`.
5. Open the signing request from the SignPath email or the URL printed by the workflow.
6. An authorized SignPath approver must approve the request within the workflow's one-hour timeout.
7. Confirm the release signature status is `Valid`.
8. Confirm the signed installer was attached to the GitHub Release.

The person who creates the tag does not need to be a SignPath approver. With multiple approvers and one required approval, any listed approver can authorize the request. If the request is denied or times out, the workflow does not publish the installer. A rerun does not overwrite an installer asset that is already attached to the release.

### SignPath Configuration

Open **Projects -> beratools -> Signing policies** in SignPath to review policy settings.

| Setting | `test-signing` | `release-signing` |
| --- | --- | --- |
| Certificate | Self-signed test certificate | Active SignPath Foundation release certificate |
| Submitter | `CI builds` | `CI builds` |
| Approval process | Disabled | Enabled; one approval required |
| Intended origin | Branch selected for the manual test | `main` only |
| Allowed build definition | `.github/workflows/build-win-installer.yml` | `.github/workflows/build-win-installer.yml` |
| Result | Actions artifact only | Approved GitHub Release |

For `release-signing`, require trusted-build-system verification and origin verification. Set the repository URL to `https://github.com/appliedgrg/beratools.git`, the allowed branch to `main`, and the allowed build definition to `.github/workflows/build-win-installer.yml`.

GitHub reports a tag-triggered workflow's tag name as its origin branch. Do not add version tags or wildcard patterns to the production policy's allowed branches. Release signing is dispatched from `main`, and the workflow verifies that the supplied tag resolves exactly to that `main` commit.

Both policies use the default artifact configuration below. Only these artifact rules are shared; certificates, approval requirements, branch restrictions, and origin settings remain policy-specific.

```xml
<?xml version="1.0" encoding="utf-8" ?>
<artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
  <parameters>
    <parameter name="version" required="true" />
  </parameters>
  <zip-file>
    <pe-file path="beratools-installer-${version}.exe">
      <authenticode-sign />
    </pe-file>
  </zip-file>
</artifact-configuration>
```

Inno Setup pads text fields in the PE version resource. Do not add `product-name`, `product-version`, or `file-version` restrictions without confirming a supported configuration with SignPath and completing a manual signing test.

The GitHub workflow reads `SIGNPATH_API_TOKEN` and `SIGNPATH_ORGANIZATION_ID` from repository Actions secrets. Never expose secret values, organization identifiers, user email addresses, or signing-request URLs in documentation or source control.

For maintainer handoff, add replacement users as SignPath approvers and retain at least one organization administrator or project configurator. With multiple approvers and one required approval, any listed approver can approve. Require MFA, keep the `CI builds` submitter independent of personal accounts, and verify replacement access before removing a departing maintainer.

After any portal or artifact-configuration change, run the manual signing test. The message `No GitHub policy found at .signpath/policies/...` is informational when no repository policy file is configured; open the signing request in SignPath for actual processing failures. GitHub connector requests contain attestation authorization data and cannot be promoted with SignPath's resubmit API.

## Releases

[Anaconda BERA Tools](https://anaconda.org/appliedgrg/beratools)

[PyPI BERA Tools](https://pypi.org/project/BERATools)
