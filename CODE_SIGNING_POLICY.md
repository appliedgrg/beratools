# Code signing policy

Free code signing is provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

## Team roles

- Committers and reviewers: [AppliedGRG developers](https://github.com/orgs/appliedgrg/teams/developers)
- Approvers: [AppliedGRG administrators](https://github.com/orgs/appliedgrg/teams/admin)

## Release process

Official Windows installers are built by GitHub Actions from version tags whose commits are on the `main` branch. SignPath verifies the build origin and requires an authorized approver to approve each `release-signing` request before the installer is published.

Manual GitHub Actions runs use the `test-signing` policy, do not require signing approval, and do not use the release certificate. Release signing uses a separate policy that requires an authorized approver.

Maintainers can find test-signing and release instructions in [Publishing BERA Tools](docs/files/developer/publishing.md#windows-installer-signing).

## Privacy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.
