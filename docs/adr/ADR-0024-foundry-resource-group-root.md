# ADR-0024: Foundry is the native deployment resource-group root

**Status:** Accepted for implementation<br>
**Date:** 2026-10-26<br>
**Owners:** Agent Landing Zone maintainers<br>
**Approver:** Maintainer direction for a Foundry root and three-group new deployments

## Context

ADR-0023 introduced optional destinations with the application as the native
azd root. The maintainer requests that the primary resource group instead
represent Foundry, the central element of Agent Landing Zone. This affects
configuration, Bicep scopes, lifecycle hooks and the central documentation in
`Azure/AI-Landing-Zones`. Runtime component versions remain those in the
manifest. Their application-deployment scripts read the resource group from
App Configuration, so they must adopt the application key before new pins
can be selected by the umbrella.

Priorities are: three groups for new environments; exact resource/identity ownership;
consistent PowerShell and shell behavior; no implicit movement of existing
resources; and no new Azure deployment for this naming adjustment.

## Alternatives considered

### Keep the application root

Preserves the v4.4.0 interface but does not meet the requested Foundry-first
configuration. Identity, networking and cost remain unchanged.

### Rename operator settings but retain a hidden application root

Avoids moving direct Bicep declarations into scoped modules, but gives azd and
operators conflicting meanings for `AZURE_RESOURCE_GROUP`. Environment refresh,
preview and cleanup could target the wrong group. Not selected.

### Make Foundry the actual native root

Selected. Keep the RG-scoped entrypoint and use explicit application-scoped
modules, just as ADR-0023 already does for Foundry/network resources. This
requires focused wrappers for direct application resources but preserves exact
resource names, service properties, identities and existing BYO precedence.
RG count does not itself add service cost or broaden runtime authorization.
Creating groups requires the deploying identity's subscription-level group-write
permission; using pre-created groups does not.

Keeping a single-group default would minimize bootstrap changes but would not
match the maintainer's current deployment expectation. Default to three for new
environments, while preserving all existing bindings and deployed single-group
environments. Explicit equal destination names still select one or two groups.

## Decision

| Interface | Contract |
| --- | --- |
| `AZURE_RESOURCE_GROUP` | Foundry/grounding destination and native azd root; initialized to `rg-<environment>` when unset in a new environment. |
| `AZURE_APP_RESOURCE_GROUP` | Application destination; initialized to `<root>-app` for new environments when unset. |
| `AZURE_NETWORK_RESOURCE_GROUP` | Locally owned network destination; initialized to `<root>-network` for new environments when unset. |
| `CREATE_RESOURCE_GROUPS` | Strict boolean, initialized to `true` for new environments unless explicitly set; only missing additional application/network destinations may be bootstrapped. |
| Bicep `applicationResourceGroupName` | Optional application RG; empty uses `resourceGroup().name`. |

This supersedes ADR-0023's choice of root, Foundry override and new-environment
single-group/creation defaults.
Resource ownership, RBAC, network placement, private-endpoint subnet selection,
explicit cleanup approval and the closed platform-outputs v1 schema remain
unchanged. Publish the three effective destinations as flat `agent-lz` settings.
Replace the old Foundry override/output with the application override/output
without exceeding ARM's 64-output limit.

The preprovision CLI reads the selected azd environment and persists effective
names before bootstrap. Native azd still creates Foundry/root. Existing bindings,
local provisioning markers and exact environment-tagged Azure inventory prevent
automatic expansion of an existing single-group environment. Read-only check
and describe modes do not initialize defaults. Default names derived from long
roots retain their suffix and a stable hash instead of colliding by truncation.
Both hooks export the resolved names before composition; native azd reloads them
before its Bicep provider starts. Local persistence failures stop before creation.

Additional-RG bootstrap must never
mistake the application override for that root. Application configurators and
container/image operations use the application destination explicitly.
Manifest-pinned Container App deployment scripts read `AZURE_APP_RESOURCE_GROUP`
with a missing/empty-key fallback to the legacy `AZURE_RESOURCE_GROUP`.
Actual App Configuration authorization/transport failures must remain failures,
not select the legacy destination. Copied component azd environments retain the
same Foundry/root context as the umbrella.
Foundry agent deployments retain the actual project ID and Foundry root.

## Adoption and migration

Keep the persisted subscription/application/Foundry/network fields unchanged
and write binding version 2 to identify the native Foundry-root contract.
Accept version 1 only when all destinations coincide; reject a version 1
split even if renamed inputs reproduce its logical destinations, because
its native deployment root was the application group.
Compare effective destinations before writes. Do not silently reinterpret
the old non-root `AZURE_FOUNDRY_RESOURCE_GROUP` setting: reject it with guidance
to use the original release/environment or a new Foundry-root environment.
An old output equal to root is harmless for a single-RG environment.
Do not delete or rewrite a binding to move deployed resources.

Coordinate compatible component releases before the umbrella manifest update,
then implementation and central documentation in feature branches.
Do not edit the already published v4.4.0 tag. Existing split environments stay
on their original release; resource migration remains outside this change.
Rollback is selection of the original release with its original environment,
not replaying it over a changed destination map.

## Compliance verification

Use offline resolver, immutable-binding, consumer and hook regression tests,
Bicep compilation and exact compiled scope/property checks. Preserve historical
resource fingerprints through explicit reviewed graph projections, not updated
security baselines. No live Azure provision/deploy/replay is requested.

Verify actual local azd hook ordering and environment reload while intercepting
all Azure calls and aborting before provider initialization. Assert three distinct
persisted destinations, no root-group creation by bootstrap, no writes from
read-only modes, and preservation of existing single-group mappings.

Verify one/two/three RG mappings, additional application/network bootstrap,
correct Foundry IDs, application ACR/apps/configuration/vault/monitoring scopes,
unchanged service properties and fail-closed old override/teardown handling.

## Documentation impact

Update central configuration, deployment, network, operations and troubleshooting
references and examples. Explain the three-group new-environment default,
pre-created-group option and explicit equal-name selection for one or two groups.
Remove mandatory detached-commit checkout steps from the normal deployment guides.

## Review trigger

Revisit if existing split-environment migration, cross-subscription workload
destinations, independently operated deployments or a different native azd
root contract is requested.
