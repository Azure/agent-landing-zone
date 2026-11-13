# ADR-0041: Discover deployment resources from provider-owned metadata

**Status:** Accepted<br>
**Date:** 2026-11-12<br>
**Owners:** Agent Landing Zone maintainers

## Context

[Issue #875](https://github.com/Azure/agent-landing-zone/issues/875) requires
deployment hooks and selected platform setup to work without App Configuration.
The default appConfig runtime, setting ownership, security boundaries and both
providers/hooks must remain supported. Runtime rewrites, a new validation
application and its live demonstration are explicitly excluded.

Bicep already uses all 64 root outputs. Terraform mirrors those names plus
existing PostgreSQL adapter outputs. `HOSTED_AGENT_DEPLOYMENT` is present outside
hosted mode and already carries platform egress, scheduler and private-build
context. Existing Python readers inspect specific siblings.

The platform repository owns provider outputs and setup. Runtime implementation
belongs to manifest-pinned components. Central docs belong to
`Azure/AI-Landing-Zones`. No runtime contract or component pin change is proposed.

Prioritized characteristics and measures:

| Priority | Characteristic | Fitness measure |
| --- | --- | --- |
| 1 | Correct destination and confidentiality | Invalid bindings/sensitive sources fail before dependent mutation, no secret/state export |
| 2 | Service independence | Store-free exercised flows make zero store requests and complete selected setup |
| 3 | Contract clarity and controlled migration | Dedicated metadata output, explicit migration for affected root consumers, unchanged runtime outputs v1 |
| 4 | Provider/platform parity | Same schema and pass/fail matrix in Bicep/Terraform and PowerShell/Bash |
| 5 | Recoverability | Separate invocation/retry works from native outputs, missing/stale sources have explicit repair |

## Alternatives considered

### A. Add a versioned member to the existing handoff

- Benefits: additive, no 65th output or new persistent inventory, available to
  native provider output readers and existing azd object transport.
- Costs/risks: neutral platform metadata lives under a hosted-named output.
  Full carrier remains subject to non-secret source review and serialization.
- Security/identity: typed non-secret member, exact output allowlist, source
  sensitivity preflight and independent live resource verification.
- Operation/cost: named control-plane/backend reads, no additional Azure service.
  Existing permissions and private-runner requirements remain.
- Compatibility: preserve siblings and runtime contract. Old foundations need
  reprovision before new hooks.
- Reversibility: additive producer can remain, consumers can roll back only where
  old store prerequisites are still satisfied.

### B. Introduce a neutral root output with an explicit output migration

- Benefits: cleanly named independent interface, no overloaded carrier.
- Costs/risks: at the ARM output limit, requires removal/transition of an existing
  output and coordinated updates to its consumers.
- Security/identity: same validation and non-secret producer obligations as A.
- Operation/cost: no new service, but a broader compatibility/recovery window.
- Compatibility: replace blanket root-name preservation with an explicitly
  reviewed output/consumer migration. Preserve runtime v1 and hosted handoff
  semantics, including the five Terraform PostgreSQL adapter contracts.
- Reversibility: harder after consumers stop receiving the retired output.

### C. Persist a provider-produced deployment artifact

- Benefits: neutral naming, can include explicit producer binding and version.
- Costs/risks: another inventory, atomic update/freshness/distribution/recovery
  requirements, possible stale or copied-environment artifact.
- Security/identity: must reject secrets and verify origins/live bindings. A local
  hash alone does not establish destination identity.
- Operation/cost: no new Azure service, additional lifecycle and clean-runner
  complexity.
- Compatibility: feasible alongside old outputs but every hook must adopt the
  artifact lifecycle.
- Reversibility: possible, with artifact cleanup and retained native outputs.

### Do not change

- Benefits: existing metadata hydration and publisher behavior are untouched.
- Costs/risks: no-store provision/deploy remains broken, with skip paths and
  inconsistent hook discovery. Does not satisfy the issue.

## Decision

The maintainer selected B on 2026-11-12: an independently versioned closed
`DEPLOYMENT_METADATA` root output, produced equivalently by both providers.
Do not place generic deployment metadata in `HOSTED_AGENT_DEPLOYMENT`.
The proposed [schema and interface](../../specs/006-optional-app-configuration/contracts/deployment-metadata-interface.md)
remain feature-local until the migration is accepted and implemented.

The maintainer accepted the concrete migration below on 2026-11-12, requesting
verification that current behavior remains intact without preserving the retired
output for historical consumers. Preserve the original typed policy and its
validation, all other root contracts, and the 64-output ARM limit.

### Concrete migration proposed by T002

The inventory is against platform commit
`823109be4aafe2870972941ac3cec34f880d6153`, the manifest combination recorded in
the feature quickstart, and central documentation commit
`964a1f65e1100eaa2c0c19e6274bde3e61bcd945`.
The maintainer explicitly accepted this proposal after the inventory and
compatibility impact were explained. T001 is satisfied.

| Existing interface | Proposed interface | Consumer transition |
| --- | --- | --- |
| `OBSERVABILITY_MIXED_WORKSPACES_ALLOWED` root boolean | Retire this output in both providers, with no metadata replacement field | Read the original typed `allowMixedObservabilityWorkspaces` input when inspecting operator intent |
| No neutral inventory output | Add `DEPLOYMENT_METADATA` schema v1 in both providers | Shared setup loader reads only the approved named provider value |
| Other 63 Bicep root output names | Retain names, types and existing semantics | Existing consumers remain supported, overlapping discovery aliases are checked against verified metadata |
| Five Terraform PostgreSQL adapter outputs | Retain all five unchanged | Existing PostgreSQL consumers remain supported |
| `HOSTED_AGENT_DEPLOYMENT` | Retain its specialized handoff semantics | Do not put generic metadata inside this object |
| Runtime `platform-outputs-v1` | Retain exact schema and integrity bytes | No runtime implementation or manifest component pin changes |

This is a 64-to-64 root-output transition in Bicep and a 69-to-69 transition in
Terraform. The retired boolean is a direct echo of declared operator policy,
not resource discovery, an evaluated destination, a readiness result or runtime
configuration. Moving it into deployment metadata would preserve that category
mistake. Keep `allowMixedObservabilityWorkspaces`,
`ALLOW_MIXED_OBSERVABILITY_WORKSPACES`, both parameter declarations, the typed
input catalog, PowerShell preflight and Terraform's monitoring precondition.
Retirement must not remove or relax the mixed-workspace check.

#### Audited consumers and required changes

| Consumer area | Inventory evidence | Required change |
| --- | --- | --- |
| Bicep/Terraform producers | `infra/bicep/main.bicep`, `infra/terraform/outputs.tf` | Replace only the policy echo root declaration with the new neutral output and remove its now-unused Terraform local entry |
| Root interface tests | `tests/test_terraform_interface.py` | Assert the exact approved removed/added pair, not just output count or provider set equality |
| Historical graph contracts | `infra/tests/contracts/ScopedResourceGroupNormalization.ps1` and the three normalization fixtures named below | Add an exact reviewed projection for the new output and restored historical boolean before historical comparison, preserve original fixture membership and graph fingerprints |
| Policy checks | `scripts/infra/Invoke-PreflightChecks.ps1`, `config/deployment/input_types.py`, `infra/terraform/main.monitoring.tf` and their existing tests | Preserve the typed input and both true/false policy behavior |
| Deployment hooks | `scripts/postProvision.ps1`, `scripts/postProvision.sh`, `scripts/preDeploy.ps1`, `scripts/preDeploy.sh` | No retired-name consumer found, adopt shared verified discovery and run it before dependent mutations |
| Shared deployment modules | `config/deployment/outputs.py`, `resource_groups.py`, `context.py`, `appconfig.py`, MCP/native and private/hosted modules | Retain other root contracts, replace store metadata hydration and resource-name guessing with verified metadata, keep specialized guards |
| Selected service setup | Foundry/toolbox, Search/templates, governance, Container Apps and panel | Apply the consumed-key ownership table in the feature interface, not a bulk store-to-environment copy |
| Samples and hosted service manifests | `samples/custom-app/`, `hosted-agent/`, `config/deployment/templates/` | No retired-name consumer found, do not rewrite applications or promise store-free sample runtimes |
| Four manifest-pinned runtime repositories | Exact commits in the quickstart, all regular archive files inspected | No occurrence of the retired name, no runtime migration needed for this output retirement |
| Central documentation | All 204 text source files inspected at the captured revision | No occurrence of the retired name, update discovery, configuration categories and upgrade/recovery guidance with shipped implementation |

The historical fixtures are
`foundry-root-normalization.json`,
`scoped-resource-groups-normalization.json` and
`incorporated-foundation-normalization.json`. Their references to the retired
output describe older graphs. Do not delete those references or regenerate
baselines to hide the output migration. The projection must validate the new
output's complete reviewed definition before removing it from the historical
comparison, restore exactly the old boolean definition, and reject any other
output delta. Schema validation of runtime values is additional coverage, not
a substitute for compiled producer comparison.

`RESOURCE_TOKEN` and `RELEASE` have hook/runtime-publication consumers.
`HOSTED_AGENT_PREPARED` has native and hosted-contract consumers. Public-ingress
outputs describe actual platform resources, including external integration
surfaces. Retire none of those merely because a different field could also
free a slot. The original and proposed root sets and broader consumer groups
are recorded in the quickstart.

The audit establishes no known consumer of the retired name in the inspected
sources. It cannot establish that customer-owned automation never reads a
public output. Treat the retirement as an explicit incompatible output change,
not as universally backward compatible.

#### Compatibility window and recovery

Ship both producers, the shared loader and affected setup/hook consumers as one
platform change. Do not claim support for new hooks against an old foundation
without `DEPLOYMENT_METADATA`. Old hooks retain their store dependency and are
not the supported store-free path, even though their other root names remain.

Customer automation reading the retired policy echo must instead read its
preserved original typed input. Do not substitute store values, a generated
tfvars file, the azd output cache or a field invented in metadata. An independent
operator who retained no original declarations must restore them before upgrade.
New generic resource automation should use the versioned neutral output rather
than depend on store-populated aliases.

Reprovision from the coordinated revision using the same provider, groups,
original declarations and Terraform backend. Refresh saved outputs and validate
the selected deployment before deploy. `azd env refresh` alone cannot add the
new provider output. A retained stale policy-echo cache is not authoritative and
must not be used by new code.

For rollback, restore the previous coordinated platform revision and reprovision
from the same inputs/backend to restore the previous root-output set. Old hooks
still require their original usable store. Store-free environments instead use
a reviewed roll-forward fix. Do not create a store, change runtime mode or
disable verification as an implicit compatibility measure.

Read only the selected provider output. Bicep selects its exact ARM value from
the bound root deployment. Terraform requests only the approved named root
output after parsing its literal nonsensitive declaration, using its original
backend. Named JSON output alone does not protect secrets. Reviewed producers
must not declassify sensitive dependencies.

Use a shared Python loader plus focused setup-setting resolution. Bind selection,
declared inputs, groups and cached aliases independently, then verify resource,
identity and Foundry endpoint bindings live before dependent mutations.
Keep current ownership/external-resource approval and private DNS/TLS checks.
Do not create local-state substitutes or store metadata fallbacks.

Separate setup from optional runtime publication. Preserve default appConfig
behavior, label `agent-lz`, user settings/flags, least-privilege grants and Key
Vault references. Remove implicit store dependencies for containerEnv, but fail
explicitly for genuinely incompatible selected features.
Keep runtime `platform-outputs-v1` unchanged and retain mode `none` semantics.

Approval of the direction does not approve unspecified output removals.
Obtain maintainer acceptance of the completed migration before
production-contract implementation. Task decomposition can proceed.

## Consequences

### Positive

- Both providers can supply the actual setup inventory without a store.
- Deployment metadata has a dedicated, accurately named contract.
- Existing runtime v1 and hosted handoff semantics remain compatible.
- Shared setup discovery replaces current PowerShell/shell divergence.
- No extra runtime service, state reader or application rewrite is needed.

### Negative or accepted

- The ARM output limit requires a coordinated output migration, potentially
  incompatible for consumers of retired names. Identify those consumers and
  document the exact transition before implementation.
- Old foundations require reprovision, not a silent legacy discovery path.
- Provider output/read-only verification adds explicit access/connectivity
  requirements, using existing least privilege rather than bypass roles.
- Terraform sensitivity preflight needs HCL parsing in Python tooling.
- Automated evidence does not establish cloud parity or application readiness.
  The user declined an additional application and live reference validation.

## Adoption and migration

Complete and accept the output migration in this ADR, add both provider
producers/shared schema, prove native
serialization, add loader/verification, then migrate every affected setup
consumer and both hook variants in one coordinated platform change.
Update central docs with the implementation. Preserve manifest pins and
infrastructure provenance, no runtime schema change or upstream sync is involved.

Before new deploy hooks, old environments reprovision from original inputs
with their existing provider/backend. Refresh stale saved outputs and reverify.
No store deletion or in-place runtime-mode conversion is promised.

The migration must specify how old hooks and external output consumers relate
to the new foundation. Cached aliases are not compatibility shims or metadata
authority. Do not promise mixed-version operation without explicit evidence.

Rollback retains groups, backend, ownership and inputs. Old hooks can run only
where their original store requirement remains satisfied. For store-free
environments, use a corrected roll-forward revision rather than disabling guards
or fabricating a store endpoint.

## Compliance verification

Require provider output/schema tests, an ARM output count at or below 64,
approved old-to-new output/consumer migration tests, unchanged
runtime-v1/hosted-handoff semantics tests,
Terraform literal sensitivity/declassification checks, and zero store-request
assertions at actual CLI/SDK boundaries.
Exercise the four primary provider/mode combinations, optional/required services,
separate/repeated invocations, wrong destinations/identities/versions,
forbidden/DNS/TLS failures and explicit feature prerequisites.
Verify both real hook wrappers and selected Foundry/Search/governance/app/role
operations, not just endpoint guards.

Run Bicep build/lint, offline contracts, locked Terraform fmt/init/validate/test
and focused Python/hook suites. Record simulation separately from deployed Azure
evidence. Do not create a new application or claim unperformed live validation.

## Documentation impact

Update the central AI Landing Zones configuration, application settings, custom
application, platform output, Bicep/Terraform deployment and recovery pages.
Search all references to runtime mode, deployAppConfig and metadata discovery.
Explain four configuration categories, real feature prerequisites and recovery.
Keep current samples documented as store-dependent. No new product docs here
or service README duplication. Do not publish unshipped behavior during planning.

## Review trigger

Before Phase 2, review the concrete output/consumer inventory and migration.
Before consumer adoption, prove the dedicated output round-trips through the
pinned provider/CLI transport, fits ARM limits and preserves the approved
contracts. Failure blocks adoption and requires an explicit ADR revision, not
reintroducing generic metadata under the hosted handoff or a silent fallback.
Revisit when a consumer outside the inventory is found, the output gains
secret-bearing content, or a runtime contract needs store-free publication.
