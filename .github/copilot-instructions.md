# Repository Development and Release Instructions

## Overview

This repository follows a structured workflow based on two primary branches:

- `develop` → ongoing development
- `main` → stable, released versions

All work must follow the branching, versioning, and changelog rules defined below.

---

## Branching Strategy

### Default Behavior

Unless explicitly instructed otherwise:

- All development work MUST start from `develop`
- All new work MUST be done in a feature branch
- Feature work MUST target `develop`
- Release preparation MUST target `main`

---

## Feature Development Workflow

### Branch Creation

- Always create feature branches from `develop`
- Naming convention:
  - `feature/<short-description>`

Examples:
- `feature/conversation-metadata`
- `feature/improve-chat-history`

---

### Feature Pull Requests

- Source branch: `feature/*`
- Target branch: `develop`
- Never target `main` from a feature branch

---

### Expected Flow

1. Start from `develop`
2. Create `feature/<name>`
3. Implement changes
4. Commit changes
5. Open pull request to `develop`

---

## Infrastructure Parity (Mandatory)

Bicep and Terraform are co-maintained implementations of the same Agent Landing
Zone capabilities. Every infrastructure change MUST check parity in both
directions, including bug fixes, defaults, feature flags, dependencies and shared
lifecycle behavior, not only new features or major/minor releases.

- Update both affected providers in the same coordinated change. A provider-only
  internal change MUST explain the counterpart's non-impact and include
  regression evidence.
- Compare inputs/defaults, resource ownership, outputs and consumers,
  identity/RBAC, networking, App Configuration and azd lifecycle behavior.
  Equivalent behavior does not require identical generated names or state
  mechanics.
- Run the relevant Bicep, Terraform, shared contract and PowerShell/shell checks.
  Preserve the provider lock file and explicit module pins.
- PRs MUST report counterpart changes or justified non-impact, checks for each
  provider, approved differences and unverified scenarios. Never silently omit
  an option or equate compilation/mocks with deployed Azure parity.

See [AGENTS.md](../AGENTS.md) and principle VI of the
[constitution](../.specify/memory/constitution.md) for the governing contract.

---

## Release Workflow

### Release Branch Creation

- Release branches MUST be created from `develop`
- Naming convention:
  - `release/x.y.z` (no `v` prefix)

Examples:
- `release/1.2.3`
- `release/2.4.2`

---

### Release Responsibilities

When preparing a release branch:

- Update version references where applicable
- Update `CHANGELOG.md`
- Ensure the repository reflects a releasable state
- Do NOT introduce new feature work
- **GitHub Release titles MUST be exactly the tag name** (for example,
  `v2.8.0`). Never prefix release titles with the product or service name (for
  example, do not use `Agent Landing Zone v2.8.0`, `Agent Landing Zone Orchestrator v2.8.0`, or
  `agent-app-ui v2.8.0`).
- **MANDATORY for EVERY Agent Landing Zone umbrella release — no exceptions.** The
  published GitHub Release notes (the `gh release create` / `gh release edit`
  body, NOT just the `CHANGELOG.md`) MUST include a `## Component versions`
  section with a Markdown table listing every validated runtime component
  from `manifest.json` `components[]` plus `infra / AI Landing Zone` from
  `manifest.json` `infra.source.tag`. This is required even for a patch release where
  only the landing-zone pin changed and the runtime component versions are
  unchanged — always restate the full validated combination so operators see
  the exact set without cross-referencing other releases.
- Read the versions directly from `manifest.json` at release time (`tag` for
  each entry in `components[]`, and `infra.source.tag` for the landing zone). Do not
  hand-copy from a previous release.
- Place the `## Component versions` table immediately after the `## Changed`
  section and before `## Validation`, matching the existing published
  releases (e.g. `v2.8.0`, `v2.8.1`).
- The same table is ALSO added to `CHANGELOG.md` under the release heading
  (as the `### Validation` component table). The GitHub Release notes and the
  changelog must agree.

Required GitHub Release notes skeleton:

```md
## Changed
- <what changed in this release>

## Component versions

| Component | Version |
| --- | --- |
| agent-app-ui | vX.Y.Z |
| agent-app-orchestrator | vX.Y.Z |
| agent-app-ingestion | vX.Y.Z |
| infra / AI Landing Zone | vX.Y.Z |

## Validation
- <commands / Azure env used to validate>
```

- **MANDATORY — never leak personal Azure environment or resource group names
  in published GitHub Release notes.** The `## Validation` section (and any
  other prose) MUST NOT contain the maintainer's `azd` environment names
  (`gptrag-MMDDYYHHMM`, e.g. `gptrag-0601261130`) or resource group names
  (`rg-gptrag-MMDDYYHHMM`). These are private, throwaway validation
  environments and are noise to operators. Use generic phrasing instead:
  "a validation environment", "a fresh Basic deployment", or "the validation
  resource group". Region names (`swedencentral`, `francecentral`) and
  feature flags (`NETWORK_ISOLATION=false`, `BUILD_MODE=acr-task`) are fine to
  keep — only the `gptrag-*` / `rg-gptrag-*` tokens must be stripped. Before
  publishing or editing any release, grep the body for `gptrag-\d{10}` and
  remove every match.

- **Preserve markdown formatting when editing release notes via the API.**
  `gh release view <tag> --json body -q .body` returns the body as a
  PowerShell **array of lines**; passing that array straight into
  `[regex]::Replace` coerces it to a single string joined with spaces and
  **flattens the whole release** (headings, bullets, and table rows collapse
  into one paragraph). Always rejoin the array on newlines first (e.g.
  `[string]::Join([char]10, $arr)`), edit with `Get-Content -Raw`, write back
  with `Set-Content -NoNewline`, and republish with `gh release edit <tag> --notes-file <file>`. After editing, re-fetch and
  confirm the body still has the expected line count and that `## ` headings
  start at the beginning of a line.

---

### Release Pull Requests

- Source branch: `release/x.y.z`
- Target branch: `main`

---

### Expected Flow

1. Start from `develop`
2. Create `release/x.y.z`
3. Update version and changelog
4. Open pull request to `main`

---

## Versioning Rules

- Follow semantic versioning: `MAJOR.MINOR.PATCH`
- Version numbers MUST use the `v` prefix in:
  - tags
  - changelog entries

Examples:
- `v1.2.3`
- `v2.4.2`

---

### Important Distinction

- Branch name:
  - `release/1.2.3`
- Tag and changelog:
  - `v1.2.3`

---

### Version Increment Guidelines

- PATCH → bug fixes and minor improvements
- MINOR → backward-compatible features
- MAJOR → breaking changes

---

## Changelog Rules

### Format

- Follow **Keep a Changelog**
- Follow **Semantic Versioning**
- Every release MUST update `CHANGELOG.md`

### IMPORTANT: No `[Unreleased]` Section on `main`

- The `main` branch MUST NEVER contain an `[Unreleased]` section in `CHANGELOG.md`.
- When creating a release branch, the `[Unreleased]` header MUST be replaced with the versioned header `## [vX.Y.Z] - YYYY-MM-DD`.
- The `develop` branch MAY use `[Unreleased]` as a staging area for upcoming changes, but it MUST be converted before merging into `main`.

---

### Version Header Format

```md
## [vX.Y.Z] - YYYY-MM-DD
```

---

## Documentation Consistency (Mandatory)

Documentation must always reflect the **current, shipped** implementation.
Whenever a change in this repository (or in a runtime component it pins via
`manifest.json`) has a user-visible effect — a new or renamed feature, a new
App Configuration key, a new/changed deployment parameter or default, a
changed deploy flow, a new component version, or a breaking change — the
matching documentation MUST be updated **in the same change set**, not
deferred.

- **User-facing docs live in the central AI Landing Zones documentation
  site** (ADR-0014). Update the relevant page in that site's source
  repository through a feature branch; the legacy `docs` branch is no longer
  the product documentation source.
- **Do not duplicate** product docs into this repo or into service-repo
  READMEs — keep READMEs short and link to the published site instead.
- **If unsure whether a doc page is affected, check**: search the docs source
  for the feature / config-key / parameter name you changed and update every
  page that references it.
- A change with a user-visible effect is **not complete** until its docs are
  updated or you have confirmed no page is affected. Treat drift between the
  published site and the implementation as a bug.