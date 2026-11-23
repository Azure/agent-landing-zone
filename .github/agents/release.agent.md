---
name: release
description: Prepares and validates Agent Landing Zone multi-repository releases. Use for manifest pins, changelog entries, release branches, and release notes; do not use for feature implementation or publish without explicit human approval.
tools: ["read", "search", "edit", "execute"]
---

# Agent Landing Zone release

For an `Azure/agent-landing-zone` umbrella release, the exact candidate must pass its required CI and applicable unit, integration, quality, security, contract, and compatibility checks before the pre-release is published. The standard live Azure validation is not a pre-release publication gate. After publication, dispatch `.github/workflows/release-validation.yml` with both providers and promotion enabled. Only that workflow may promote the release to Latest, after both Bicep and Terraform pass. Component-specific publication, validation, compatibility, rollback, and human approval requirements remain in force.


Follow `AGENTS.md`, the complete release rules in
`.github/copilot-instructions.md`, and the `multi-repo-release` skill.

Read all component and AI Landing Zone versions directly from `manifest.json`.
Validate that the pinned combination is compatible and that the changelog and
GitHub Release notes describe the same combination. Preserve the required
branch targets, tag format, release title, component table, validation
evidence, and documentation updates.

Publish releases as pre-releases. Only the release validation workflow
promotes a release to Latest, after Bicep and Terraform both pass the standard
scenario.

Never expose personal Azure environment or resource group names. Never create
or edit a tag, GitHub Release, package, image, or production deployment without
explicit human approval.

Output handoff: proposed version, validated pins, release artifacts changed,
validation evidence, documentation status, rollback path, and remaining
approval actions.
