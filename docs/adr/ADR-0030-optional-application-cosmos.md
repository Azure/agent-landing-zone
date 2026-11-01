# ADR-0030: Provision application Cosmos DB only when selected or required

**Status:** Accepted<br>
**Date:** 2026-10-28<br>
**Owners:** Agent Landing Zone maintainers

## Context

Fresh application deployments use hosted orchestration without the
administrative panel. That composition already omits application Cosmos DB,
but the raw Bicep, Terraform and parameter-file defaults still enable it.
Operators bypassing application composition can therefore provision an unused
account. The Foundry Agent Service has separate Cosmos dependencies and must
not be affected.

Affected repositories are Agent Landing Zone and the central AI Landing Zones
documentation source. Prioritized characteristics are:

1. Resource economy: no application Cosmos account or dedicated identity,
   database, container, endpoint or grant when disabled.
2. Compatibility: classic, panel and preserved-classic runtime dependencies
   continue to provision their required storage.
3. Provider parity: shared application selection produces the same Boolean
   and container list for Bicep and Terraform.
4. Explicit operation: an incompatible explicit disable fails before provision.
5. Isolation: Foundry backing storage, authorization and shared DNS are unchanged.

## Alternatives considered

### Keep default-on foundation templates

This preserves direct-template behavior but relies on hooks to avoid an unused
account. It leaves inconsistent defaults and unnecessary resource ownership.

### Disable application Cosmos unconditionally

This minimizes resources but breaks classic conversation storage, panel metadata
and custom components that declare the conversation-store capability. Rejected.

### Default off with dependency-aware application composition

This aligns both foundation providers while preserving automatic provisioning
for known consumers. It requires regression coverage for explicit selection,
custom profiles and migration preparation, but no runtime schema or component
version change. Resource identities and least-privilege panel grants are retained.

## Decision

- Default `deployCosmosDb` to false in both foundation roots and parameter seeds.
- Keep classic, hosted-panel and preserved-classic requirements enabled in the
  shared application composer.
- Include custom components whose capability profiles require application
  Cosmos, whether their runtime is Container Apps or a Hosted Agent. Preserve
  the configured application container list for these consumers.
- Honor `DEPLOY_COSMOS_DB=true` as an explicit opt-in. Accept only strict Boolean
  strings; reject false when a selected consumer requires storage.
- Do not derive Foundry Cosmos provisioning from this application flag.
- Keep the shared private DNS zone available to Foundry. Disable only
  application-specific resources and emit empty application database names when
  application Cosmos is absent.

## Consequences

The default hosted application requires no application Cosmos account. Direct
foundation consumers that need it must opt in explicitly. The existing public
parameter and environment-variable names remain unchanged. No runtime application
code, data schema, infrastructure provenance or module pins change.

## Adoption and migration

Apply the foundation defaults, shared composition and contract coverage together,
then update the central configuration reference. Existing accounts are not a
cleanup target of this change. Review every existing-environment preview before
provisioning: Bicep incremental deployment can retain an omitted account, while
Terraform can propose destroying a previously managed account. Preserve
`DEPLOY_COSMOS_DB=true` until data retention and consumer requirements have been
reviewed. Never destroy or migrate application data automatically.

Rollback retains the explicit opt-in or restores the previous defaults; it does
not restore deleted data. No production deployment is part of this decision.

## Compliance verification

Exercise default hosted, explicit opt-in, classic, panel, preserved-classic and
custom-profile selections through both adapters. Reject invalid Boolean values
and incompatible opt-outs. Compile Bicep and inspect conditional resources; run
Terraform validation and mocked plans with Cosmos enabled and disabled, including
UAI and network isolation. Exercise shared preflight and both hook contracts.
Mocks and compilation are not evidence of deployed Azure parity.

## Documentation impact

Update the current configuration reference in `Azure/AI-Landing-Zones` with the
application-only scope, inferred dependencies, explicit opt-in and existing-data
caution. Do not add a release announcement or duplicate product documentation.

## Review trigger

Revisit when a bundled runtime adds a Cosmos consumer, capability profiles change,
or a supported external application Cosmos binding is introduced.
