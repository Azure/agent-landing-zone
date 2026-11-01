---
applyTo: "manifest.json,CHANGELOG.md,.gitmodules,scripts/preDeploy.ps1,scripts/preDeploy.sh"
---

# Multi-repository release surfaces

- Follow `.github/copilot-instructions.md` and load `multi-repo-release`.
- `manifest.json` is the authoritative list of runtime components and tags.
- Keep the umbrella `manifest.json` `tag` equal to the release branch,
  changelog, Git tag, and GitHub Release version.
- Keep `manifest.json` `infra.source` (`repo`, `tag`, `commit`) aligned with the
  AI Landing Zone release incorporated into the Bicep foundation. Do not use
  this field for the local Terraform composition or its dependency pins.
- Require Bicep-to-Terraform and Terraform-to-Bicep parity assessment for every
  infrastructure change, including patches. Record counterpart changes or
  justified non-impact and evidence for each provider; never infer deployed
  parity from compilation, mocked tests or release numbering.
- Keep PowerShell and shell deployment behavior aligned with the same manifest
  contract.
- Validate the exact component and infrastructure combination before changing
  the platform release pin.
- Keep changelog, release notes, documentation, and manifest versions
  consistent.
- Never infer a version from stale prose or a previous release table.
