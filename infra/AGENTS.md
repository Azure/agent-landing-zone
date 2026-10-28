# AI Landing Zone engineering-agent contract

This is the stable repository-wide contract for GitHub Copilot engineering
agents. Detailed procedures belong in `.github/skills/`; file-specific rules
belong in `.github/instructions/`.

When this directory is part of Agent Landing Zone, the root `AGENTS.md` and
constitution also apply. The incorporated Bicep foundation and product-owned
`terraform/` composition are co-maintained; the root manifest's `infra.source`
records Bicep provenance only.

The assets under `.github/agents/` and `.github/skills/` guide engineers who
develop and operate this repository. They do not define Microsoft Foundry
agents, Container Apps, MCP servers, or any other deployed Azure resource.

## Priority

Follow, in this order:

1. Security, privacy, authorization, and platform instructions.
2. Task requirements and acceptance criteria.
3. Executable Bicep/Terraform, parameter, manifest, and pipeline contracts.
4. `.github/copilot-instructions.md`, this contract, and applicable scoped
   instructions.
5. Local conventions observed in the affected files.

Do not guess when missing information could affect identity, networking,
compatibility, releases, or production. Record the uncertainty and obtain a
human decision.

## Repository purpose and boundaries

This repository is a reusable Azure AI Landing Zone implemented in Bicep. It
provides secure, parameterized infrastructure for Microsoft Foundry and related
Azure services in standard and network-isolated deployment modes.

- `main.bicep` is the resource-group-scoped orchestrator. It composes AVM and
  local modules under feature-flag conditions.
- `main.parameters.json` is the azd parameter and environment-substitution
  surface.
- `modules/` contains reusable resource logic:
  - `ai-foundry/`: Foundry account, project, connections, and nested resources.
  - `networking/`: VNets, subnets, NSGs, private DNS, private endpoints,
    public ingress, Bastion, and Azure Firewall.
  - `security/`: control-plane and Cosmos DB data-plane role assignments.
  - `container-apps/`: app-list shaping and runtime configuration values.
  - `app-configuration/`: App Configuration key-value population.
  - `bing-search/`: Grounding with Bing resources.
- `constants/` is the source for role IDs and resource abbreviations.
- `terraform/` contains the Agent Landing Zone Terraform root, with flat domain
  composition, explicit AVM module pins and a committed provider lock.
- `scripts/` and `install.ps1` contain cross-platform PowerShell automation.
- `pipelines/azuredevops/` and `.github/workflows/` contain validation and
  deployment automation.
- `tests/` contains deterministic preflight tests and the optional hub/spoke
  integration fixture.
- `manifest.json` is a release and jumpbox-bootstrap contract. Consumers may
  extend its pinned `components` list.

Keep `main.bicep` as the orchestrator. Add reusable resource bodies to focused
modules rather than duplicating them inline. Drive deployment shape from
`containerAppsList`, `modelDeploymentList`, `databaseContainersList`,
`storageAccountContainersList`, and related data structures instead of
workload-specific branches.

## Bicep and Terraform parity

Every infrastructure change, including fixes and defaults, must assess the
counterpart in both directions. Update affected Bicep modules and Terraform
domain files in the same coordinated change, or explain and test why the other
implementation needs no change. Compare supported inputs/defaults, ownership,
outputs, identity/RBAC, networking, App Configuration and lifecycle behavior.
Preserve foundation/application separation and provider-specific state
boundaries; equal generated names are not required.

Run the relevant checks for both providers and shared hooks. Terraform checks
include formatting, backend-disabled readonly initialization, validation and
the affected tests under `terraform/tests`. Record approved differences and
unverified scenarios explicitly; compilation and mocks are not deployed parity.

## Compatibility and parameterization

- Preserve feature-flag gating and the distinction between standard and Zero
  Trust/network-isolated deployments.
- Preserve nullable fallback behavior for substituted values. A value that azd
  can replace with an empty string must have a safe Bicep fallback before it
  reaches a resource property.
- Add capabilities in this order: described Bicep parameter, matching parameter
  file value, empty-substitution fallback when needed, module/resource wiring,
  App Configuration publication when runtime consumers need it, and an output
  when downstream automation needs it.
- Treat parameter names, defaults, allowed values, output names, manifest
  fields, App Configuration keys, and module interfaces as compatibility
  contracts. Prefer additive changes and document migration for breaking ones.
- Preserve `app.target_port` for ingress and Dapr, with `8080` as the fallback.
- Preserve compatibility for consumers that mount this repository at `infra/`
  and overlay `main.parameters.json` and `manifest.json`.

## Identity, networking, and naming

- Prefer managed identity and least-privilege RBAC. Keep Bicep role assignments
  explicit through `modules/security/` and Terraform assignments through
  `terraform/main.identity.tf`, using the shared role constants.
- Read role IDs and abbreviations from `constants/`; do not duplicate literals.
- Never hardcode tenant IDs, subscription IDs, credentials, or environment-
  specific resource names.
- Preserve both CAF and legacy naming modes. Explicit resource-name parameters
  override generated names in both modes.
- Treat private DNS, private endpoint ordering, subnet delegation and sizing,
  hub/spoke peering, route tables, and public-network-access decisions as
  security-sensitive contracts.
- Keep private endpoint creation and dependencies serialized where the existing
  topology requires it.

## PowerShell and deployment automation

- PowerShell 7 is the shared script runtime on Windows and POSIX azd hooks.
- Quote external input, avoid logging secrets, fail explicitly on unmet
  prerequisites, and preserve idempotency.
- `install.ps1` runs under the Windows Custom Script Extension's fixed timeout.
  Preserve its wall-clock budgets, fatal/optional step distinction, and bounded
  network operations.
- Azure DevOps deploy steps use Bash inside pipeline YAML. When shared behavior
  changes, keep pipeline and PowerShell semantics aligned where applicable.
- What-If or `azd provision --preview` is evidence, not authorization to deploy.
  Never provision, tag, release, or modify production without explicit approval.

## Validation and evidence

Run the narrowest existing validation that covers the change, then broaden with
risk:

- Copilot assets:
  `pwsh ./.github/scripts/Validate-CopilotAssets.ps1`
- Validator tests:
  `pwsh ./tests/scripts/Validate-CopilotAssets.Tests.ps1`
- Bicep compile/lint:
  `az bicep build --file main.bicep` and
  `az bicep lint --file main.bicep`
- Compiled-template size:
  `pwsh ./scripts/Measure-MainJsonSize.ps1`
- Deterministic preflight tests:
  `pwsh ./tests/scripts/Invoke-PreflightChecks.Tests.ps1`
- Azure-aware preflight:
  `pwsh ./scripts/Invoke-PreflightChecks.ps1`
- Deployment preview:
  `azd provision --preview`
- End-to-end validation:
  `azd provision` in an approved test environment.

Do not invent validation commands or claim Azure behavior from compilation
alone. Report commands, results, skipped validation, and residual risk.

## Architecture, documentation, and releases

Load `engineering-principles` for design, meaningful refactoring, Azure
integration, security, testing, or operational changes. Load
`architecture-decision` for hard-to-reverse changes to boundaries, contracts,
identity, topology, or deployment behavior.

Use `documentation-consistency` whenever behavior, parameters, defaults,
outputs, deployment modes, or operator steps change. Keep `README.md`,
`CHANGELOG.md`, relevant `docs/` runbooks, and the public
`Azure/AI-Landing-Zones` documentation aligned with shipped behavior.

This repository uses semantic versioning. `main` holds released versions and
`develop` is the integration branch when present. Before feature work, ensure
the integration branch includes the latest release from `main`. Release tags
and GitHub Release titles use exactly `vMAJOR.MINOR.PATCH`; keep
`manifest.json`, changelog, tag, and release title aligned. Major or minor
changes require Portal parity review. Bicep/Terraform parity review applies to
every infrastructure behavior change, including patches.

## Collaboration and handoffs

- Agents deliver decisions, changed contracts, evidence, documentation status,
  rollback guidance, and residual risks rather than activity summaries.
- Architecture hands implementation explicit boundaries, trade-offs, fitness
  functions, migration constraints, and open questions.
- Implementation hands validation the changed behavior, affected files,
  expected compatibility, and required evidence.
- Validation hands release reproducible commands and results, not assumptions.
- Release and production operations require explicit human approval.
