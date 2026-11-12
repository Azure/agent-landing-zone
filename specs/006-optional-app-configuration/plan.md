# Implementation Plan: Optional App Configuration in deployment flows

**Branch**: `feature/optional-app-configuration` | **Date**: 2026-11-12

**Spec**: [spec.md](spec.md) | **Issue**: [#875](https://github.com/Azure/agent-landing-zone/issues/875)

## Summary

Make provider outputs, not App Configuration, the deployment metadata authority.
Add an independently versioned `DEPLOYMENT_METADATA` root output in both
providers. The maintainer selected this direction instead of nesting generic
metadata in `HOSTED_AGENT_DEPLOYMENT`. Inventory and approve the concrete
output/consumer migration before Phase 2 to stay within ARM's 64-output limit.
Preserve hosted handoff semantics and runtime v1. Shared Python tooling reads only the
approved output, binds it to the selected environment and declared inputs, and
verifies live resources before dependent configuration mutations.

Separate platform setup from optional runtime publication. Migrate actual
Foundry, Search, governance, Container Apps, panel and supporting deployment
consumers, not merely endpoint guards. Preserve `appConfig` defaults, label
`agent-lz`, setting ownership, feature flags, Key Vault references and the
unchanged runtime `platform-outputs-v1` contract.

The user excluded an additional validation application and its live
demonstration. Neither sample nor pinned runtime is rewritten. Required evidence
is provider, contract, module and hook regression coverage. Live store-free
application readiness and deployed Azure parity remain unverified.

## Technical Context

**Language/Version**: Python 3.11+ configuration tooling, PowerShell 7 and Bash,
Bicep CLI v0.42.1, Terraform >=1.13.0,<2.0.0. CI uses Terraform 1.13.0.

**Primary Dependencies**: Existing Azure CLI, azd, Azure SDKs, jsonschema, PyYAML,
Jinja2 and pytest. Add `python-hcl2` to `config/requirements.txt` during
implementation for fail-closed Terraform output declaration inspection before
requesting a value. No dependency installation during planning.

**Storage**: Native ARM deployment outputs and the existing Terraform backend.
The azd environment supplies selection and cached output consistency checks,
not independent authority. No new persistent inventory or state reader.

**Testing**: Existing pytest suites, compiled Bicep/offline contracts, Terraform
checks and PowerShell/Bash behavioral parity. See [quickstart.md](quickstart.md).

**Target Platform**: Existing Windows/Linux deployment runners, including
VNet-connected runners for private resource verification.

**Project Type**: Infrastructure and deployment tooling, not application runtime.

**Performance Goals**: One named provider-output request per loader invocation.
Reuse that context within the module. Eliminate per-setting store discovery.
Preserve bounded CLI/SDK timeouts and existing retry policies.

**Constraints**: ARM's 64-root-output limit, unchanged runtime v1 schema,
provider lock/module pins/backend binding, least privilege, exact destinations,
network isolation, shared-resource contracts and no secret values.
No store deletion or promised in-place runtime-mode conversion.

**Scale/Scope**: One selected environment per invocation, both providers,
both hooks, deployment metadata consumers and central operator documentation.
Arbitrary runtime settings are not added to metadata.

## Constitution Check

Evaluated against constitution v2.1.0 before research and after design.

| Principle/gate | Pre-design assessment | Post-design disposition |
| --- | --- | --- |
| I. Boundaries | Platform owns deployment, components own runtime | Pass. Foundation-only outputs, focused Python setup, template-driven Search/Foundry payloads, no runtime/sample edits |
| II. Compatibility | Closed runtime v1 requires a store | Runtime schema/hash remains unchanged. The accepted migration replaces only `OBSERVABILITY_MIXED_WORKSPACES_ALLOWED` with dedicated deployment metadata v1 |
| III. Identity/confidentiality | Editable aliases and Terraform JSON are not trusted | Pass by design. Approved named output, sensitivity preflight, closed fields, bound destinations, live verification, Key Vault-only secret values |
| IV. Visible failures | Endpoint removal alone can mask incomplete setup | Pass by design. No fallback or missing-service skips, explicit errors before dependent mutation |
| V. Evidence | Actual setup consumers must be covered | Pass for plan. Automated evidence required. User excluded new app/live reference validation. No cloud parity/readiness claim |
| VI. Provider parity | Both providers and hooks are affected | Pass by design. Same schema, defaults, required-service decisions and negative matrix, preserved provider-specific state mechanics |
| Architectural decision | New versioned boundary needs a recorded decision | [ADR-0041](../../docs/adr/ADR-0041-provider-owned-deployment-metadata.md) records the accepted neutral output and concrete output/consumer migration. T001 and T002 are complete |
| Documentation | Published flow still describes shipped store behavior | Update central docs with implementation, not during planning |

No constitutional exception is requested. The maintainer explicitly accepted
the concrete migration after the inventory. No other output removal is approved.

## Design and Integration

### Provider-owned metadata

The proposed [schema](contracts/deployment-metadata-v1.schema.json) contains
context, resource states, model/app mappings, identities and named data children.
It excludes arbitrary settings, credentials, connection strings and resolved
secrets. Setup options come from typed declared inputs and approved runtime
preferences, not infrastructure reconstructed from a store.

Bicep reads `properties.outputs.DEPLOYMENT_METADATA.value` from the selected root
deployment. Terraform uses only `terraform output -json DEPLOYMENT_METADATA` in
the native selected provider directory with the existing backend. Both return
the closed metadata object directly, without a hosted-agent wrapper.
The Terraform root declaration must explicitly contain literal
`sensitive = false`, with no declassification of sensitive sources. Unknown,
malformed or sensitive declarations fail before requesting the value.
Named JSON output does not provide sensitivity protection.

Source selection, freshness, errors and CLI shape are specified in
[the interface contract](contracts/deployment-metadata-interface.md).
The design does not rely on undocumented azd Terraform output filtering,
transient process values or an additional local inventory.

### Verification order

1. Resolve the provider from root `azure.yaml`, explicit azd environment,
   declared parameter source and immutable resource-group binding.
2. Read and validate approved metadata. Reject unsupported versions, missing
   fields, destination/alias conflicts and stale cached metadata.
3. Cross-check selected capabilities, ownership/external IDs, names, model/app
   mappings and optional states against typed declarations.
4. Perform read-only Azure checks for relevant groups, IDs, identities, endpoints
   and exact Foundry account/project binding. Check only selected services.
5. Check private connectivity and genuinely store-dependent feature
   prerequisites, then perform selected mutations.

The post-provision guard precedes PostgreSQL protection, RBAC, egress,
publication and service setup. Pre-deploy guards precede builds, registration
and application/feature changes. Modules also validate at their mutation
boundaries when called directly. Explicit private-setup deferral remains
incomplete readiness, not successful full configuration.

### Consumer migration

| Area | Planned change and preserved behavior |
| --- | --- |
| `config/deployment/outputs.py` | Separate metadata/foundation checks from runtime v1 publication. Remove store hydration |
| `appconfig.py`, `appconfig_seed.py`, `appconfig_intent.py` | Preserve typed intent, seed-only/user-owned behavior and publication ownership. Invoke publication only for a selected runtime consumer |
| Both postProvision hooks | Replace PowerShell-only flat discovery/seeding with shared Python setup inputs. Keep all required service operations |
| Both preDeploy hooks | Replace unconditional store foundation checks with metadata verification and capability prerequisites |
| `config/aifoundry/setup.py`, `keyvault.py`, `toolbox.py` | Use verified Foundry/model/vault/Search/connection metadata. Keep RAI, evaluation Key Vault secret and toolbox setup |
| `config/search/setup.py` | Build StrictUndefined context from metadata and declared setup settings. Preserve Search/Foundry IQ/MCP validation/provisioning. Separate optional publication of derived settings |
| `config/containerapps/setup.py` | Configure selected app registry/identity using verified app mappings |
| `config/governance/setup.py` | Separate audit HMAC Key Vault creation/reuse from store publication. Preserve appConfig migration/reference semantics. Pass references, not HMAC values |
| `config/panel/setup.py` | Resolve selected Cosmos account/database from metadata, without store fallback |
| `mcp.py`, `native_access.py`, native/hosted helpers | Replace resource-discovery fallback only. Retain genuine runtime store state, Entra retry ownership and access rules where selected |
| `config/appdefinition/profiles.py`, `roles.py`, provider RBAC | Make implicit store-reader grants runtime-requirement aware. Keep ACR/other required grants. Reject explicit incompatible store prerequisites |
| `private_network.py` | Probe required selected services only. Preserve DNS/TLS, registry, Foundry, scheduler, runner and explicit deferral safeguards |

Use focused `config/deployment/metadata.py` and
`config/deployment/setup_settings.py` boundaries. Reuse `provider.py`,
`selected_environment`, `resource_groups.py`, `context.py`, typed resolution
and ownership helpers. Do not introduce another orchestration framework.

### Mode behavior

| Selection | Discovery | Runtime publication/access |
| --- | --- | --- |
| `containerEnv`, no store | Provider metadata, zero store requests | Keep existing curated environment/Key Vault-reference delivery. Complete setup or reject incompatible selected features |
| `containerEnv`, provisioned store | Same discovery and guards | Presence does not change mode or trigger metadata reads/publication |
| `appConfig`, usable store | Provider metadata | Verify exact store, preserve settings/flags/label/access/references and user-owned operational preferences |
| `appConfig`, missing/unusable store | Reject before dependent mutation | No implicit mode switch |
| `none` | Provider metadata | Preserve existing no-injection semantics and explicit feature prerequisites |

Allowlisted runtime preferences may still be read in appConfig mode by their
existing owners. Those reads never supply or override resource IDs, endpoints,
model/app identities or infrastructure selection.

## Project Structure

### Planning artifacts

```text
specs\006-optional-app-configuration\
  spec.md
  plan.md
  research.md
  data-model.md
  quickstart.md
  checklists\requirements.md
  contracts\deployment-metadata-v1.schema.json
  contracts\containerenv.example.json
  contracts\deployment-metadata-interface.md
docs\adr\ADR-0041-provider-owned-deployment-metadata.md
```

`tasks.md` belongs to `/speckit-tasks` and is not generated here.

### Implementation locations, not changed by this plan

```text
infra\bicep\main.bicep
infra\terraform\outputs.tf
infra\terraform\main.*.tf
infra\terraform\tests\root.tftest.hcl
contracts\deployment-metadata-v1.schema.json
config\requirements.txt
config\deployment\metadata.py
config\deployment\setup_settings.py
config\deployment\outputs.py
config\deployment\appconfig*.py
config\deployment\private_network.py
config\deployment\mcp.py
config\deployment\native_access.py
config\aifoundry\
config\search\
config\containerapps\
config\governance\
config\panel\
config\appdefinition\
scripts\preDeploy.ps1
scripts\preDeploy.sh
scripts\postProvision.ps1
scripts\postProvision.sh
tests\
infra\tests\
```

Promote the feature-local schema to root `contracts/` during implementation,
following contract integrity conventions. Do not alter the unchanged runtime
`platform-outputs-v1.schema.json` bytes or integrity hash.

## Adoption, Documentation and Recovery

Integration order: inventory outputs/consumers, accept the concrete migration in
the ADR, add both provider producers and contract tests,
add loader/verification, migrate all setup consumers and both hooks together,
then deliver regression evidence and central docs. Preserve manifest pins and
infrastructure provenance unless separate runtime work or upstream re-sync is
authorized.

Old foundations lacking the dedicated output require reprovision from declared inputs
before new deploy hooks run. For stale saved outputs, run
`azd env refresh --environment <name>` and verify again. If provider outputs are
absent/outdated, reprovision the same provider with preserved inputs. Restore the
existing Terraform backend binding, never guess a backend or inspect raw state.

Rollback keeps the same provider, backend and resource groups. Old hooks require
a store and are not a safe fallback for a store-free environment. Roll forward
with a corrected loader/provider revision instead. No store deletion or existing
mode conversion is included.

Central docs target `Azure/AI-Landing-Zones` main with implementation. Search
the complete docs source for affected mode, parameter and metadata terms.
Confirmed impact includes configuration, custom applications, platform outputs
and provider-specific deploy/recovery guidance. Preserve the existing samples'
actual store prerequisite, distinguish deployment metadata v1 from runtime
outputs v1, and focus on supported behavior, prerequisites and recovery.
Keep test results and evidence limitations in the feature validation record and
engineering handoff, without generic validation-status warnings on product
pages. Do not publish future behavior during planning.

## Evidence and Completion Boundary

[quickstart.md](quickstart.md) defines the automated matrix, negative cases,
repeated-invocation evidence and real repository commands. Assert actual selected
service calls and target identities, not only guard success or compilation.
No new application, runtime/sample changes, live reference-app deployment,
release, tag or Azure mutation is part of this planning request.

## Complexity Tracking

Two focused Python boundaries separate trusted
discovery from optional publication and remove PowerShell-only discovery
duplication. A dedicated output keeps platform discovery separate from hosted
deployment. ARM's output limit requires an explicit reviewed root-output
migration, not blanket preservation of every existing name. No additional
persistent inventory is introduced.
