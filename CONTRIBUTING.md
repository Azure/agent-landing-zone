# Contributing

Thank you for contributing to Agent Landing Zone.

Create your working branch from `develop` and open contribution pull requests
against `develop`. Only branches named exactly `release/X.Y.Z` in this repository
may open release pull requests against `main`.

Include a short description of the change, relevant tests and results, and
documentation updates when needed. The quality gate runs automatically on pull
requests and must pass before merge. These checks support manual review; they do
not replace it.

## Spec Kit skills

The repository installs the upstream Spec Kit Copilot integration in skills mode
with PowerShell helpers. Installation versions and file hashes live in
`.specify/init-options.json`, `.specify/integration.json`, and
`.specify/integrations/`.

The **Update Spec Kit** GitHub Actions workflow checks the latest stable
`github/spec-kit` release every Monday at 09:00 UTC and can also run manually.
It upgrades from the release's resolved commit and opens or updates
`feature/update-speckit` against `develop`. It does not merge automatically.
Scheduled execution starts only after the workflow reaches the default branch.

Updates preserve the repository constitution, custom agents, and instructions.
Locally modified managed skills cause the upgrade to fail rather than being
overwritten. LF line endings keep upstream file hashes valid on Windows and Linux.
The installation regression tests verify managed assets and version metadata.

Enable **Allow GitHub Actions to create and approve pull requests** in the
repository's Actions settings. Optionally configure `SPECKIT_UPDATE_TOKEN` with
contents and pull-request write permissions so the bot's pull requests trigger
normal CI. With the default `GITHUB_TOKEN`, GitHub does not trigger other
workflows from the created pull request, so run the quality gate manually.

Contributions follow the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
See the [FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact
[opencode@microsoft.com](mailto:opencode@microsoft.com) with questions.
You may be asked to sign a [Contributor License Agreement (CLA)](https://cla.opensource.microsoft.com).
