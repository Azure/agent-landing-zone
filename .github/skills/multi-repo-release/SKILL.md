---
name: multi-repo-release
description: Prepares and validates Agent Landing Zone umbrella and multi-repository releases. Use whenever work involves release preparation, semantic versions, release branches, manifest or component pins, changelog release entries, tags, GitHub Release notes, or AI Landing Zone release alignment.
---

# Agent Landing Zone multi-repository release

Read `.github/copilot-instructions.md` completely before changing a release
artifact. Its branching, versioning, changelog, and release-note requirements
are authoritative.

1. Determine the intended semantic version and create the release branch from
   `develop` using `release/x.y.z`.
2. Update `manifest.json` `tag` to `vX.Y.Z` and verify it matches the release
   branch version, changelog heading, Git tag, and GitHub Release title.
3. Read every runtime component tag from `manifest.json` `components[]` and the
   infrastructure provenance from `infra.source` (`repo`, `tag`, `commit`);
   never copy a previous version table.
   Align the bundled `app-definition.json` source commits and the exact
   component-pin review in
   `infra/tests/contracts/fixtures/incorporated-foundation-normalization.json`
   in the same change. Run the release gate against the real loaded application
   definition, not just the manifest values.
4. `infra/` is repository-owned source (no submodule). Keep `manifest.json`
   `infra.source` equal to the AI Landing Zone release the in-repository
   `infra/` was incorporated from, and validate the exact `infra/` tree being
   released.
5. Confirm that the exact pinned combination was validated and record the
   relevant commands and Azure deployment mode without private environment or
   resource group names.
6. Replace `[Unreleased]` with `## [vX.Y.Z] - YYYY-MM-DD` for the release.
7. Keep `CHANGELOG.md` and GitHub Release notes consistent, including the full
   required component version table.
8. Use exactly `vX.Y.Z` for both the tag and GitHub Release title.
9. Target the release pull request to `main`.
10. Re-fetch published release notes and verify headings, lists, tables, and the
    absence of private `gptrag-*` and `rg-gptrag-*` validation names.

Do not publish a tag, release, package, image, or production deployment without
explicit human approval. Report incompatible pins, missing validation, or
documentation drift as blockers rather than filling gaps by assumption.
