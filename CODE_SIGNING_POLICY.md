# Code signing policy

Free code signing is provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

## Team roles

- Committers and reviewers: [AppliedGRG developers](https://github.com/orgs/appliedgrg/teams/developers)
- Approvers: [AppliedGRG administrators](https://github.com/orgs/appliedgrg/teams/admin)

## Release process

Official Windows installers are built by GitHub Actions from version tags whose commits are on the `main` branch. SignPath verifies the build origin and requires an authorized approver to approve each `release-signing` request before the installer is published.

Manual GitHub Actions runs use the `test-signing` policy and do not use the release certificate.

## Privacy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.
