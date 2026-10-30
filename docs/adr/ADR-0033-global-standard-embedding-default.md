# ADR-0033: Default embedding deployments to Global Standard

**Status:** Accepted<br>
**Date:** 2026-10-30<br>
**Owners:** Agent Landing Zone maintainers<br>
**Decision basis:** Maintainer-requested Global Standard embedding default

## Context

The default embedding deployment uses `text-embedding-3-large`, version `1`,
with the regional `Standard` SKU. The maintainer requested `GlobalStandard`
instead. This is an intentional behavioral change, separate from ADR-0032's
behavior-preserving infrastructure source reorganization.

Affected repositories are `Azure/agent-landing-zone` and its central product
documentation in `Azure/AI-Landing-Zones`. Prioritized characteristics:

1. Provider parity: root inputs, Bicep seed and both providers' defaults and
   empty-list fallbacks select the same embedding deployment type.
2. Explicit control: user-supplied deployment lists retain their requested SKU.
3. Compatibility: model, version, deployment names, dimensions, capacity and
   runtime component pins do not change.
4. Processing transparency: operators can distinguish global inference
   processing from regional processing and storage geography.
5. Evidence: local checks cover default selection, overrides and quota buckets
   without requiring an Azure deployment or evaluation.

Microsoft documents this model/version under
[Global Standard availability](https://learn.microsoft.com/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability#global-standard).
Availability and quota still depend on the target region and subscription.
[Deployment-type guidance](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/deployment-types#azure-ai-foundry-deployment-data-processing-locations)
states that global processing can occur outside the resource's region, while
data stored at rest remains in the customer-designated geography.

## Alternatives considered

### Change the existing deployment-list defaults (selected)

Set only the embedding SKU to `GlobalStandard` everywhere defaults are
declared. Keep the existing deployment-list override rather than introduce a
second configuration surface. This meets the request without changing runtime
contracts, identity, authorization or network isolation.

Global processing changes the processing-location boundary. Capacity remains
unchanged, but quota buckets and pricing are deployment-type-specific. No cost,
latency or subscription-capacity improvement is guaranteed.

### Add a separate embedding deployment-type parameter

A dedicated parameter could expose the choice independently, but would duplicate
the existing `modelDeploymentList` SKU, introduce precedence rules and require
additional cross-provider and lifecycle configuration. It offers no required
capability beyond the existing explicit deployment-list override.

### Do not change

Retain regional `Standard` defaults and require per-environment global overrides.
This avoids changing the default processing boundary but does not meet the
requested baseline. It remains available through an explicit `Standard` SKU.

## Decision

Use `GlobalStandard` for `text-embedding-3-large`, version `1`, in root deployment
inputs, the tracked Bicep seed, Terraform native defaults and both foundation
fallback lists. Preserve the existing capacities: `100` in declared deployment
inputs and `10` in the empty-list foundation fallback.

Do not rewrite explicit user SKUs or silently fall back to another deployment
type when availability or quota checks fail. Preserve the model/version,
deployment identifiers, API versions, dimensions, component versions, managed
identities, RBAC, document authorization and networking.

## Consequences

### Positive

Both providers expose the requested default consistently without adding a new
parameter or changing embedding-vector compatibility.

### Negative or accepted

Global inference is not constrained to the resource's region. A private endpoint
or network-isolated deployment does not turn a global model SKU into regional
processing. Operators requiring regional processing must explicitly select
`Standard`, subject to that region's model availability and quota.

Existing regional allocations cannot be credited against a global quota bucket.
Changing SKU on an existing Azure deployment is not validated by local tests.

## Adoption and migration

Update both providers, shared inputs, regression coverage and central
documentation together. No runtime component or Search index migration is
required by this SKU-only source change, and no existing Azure resource is
modified merely by updating the checkout.

For a subsequent provision of an existing environment, inspect the resolved
deployment list and Azure's supported SKU-transition behavior first. Preserve an
explicit `Standard` override if a transition is not intended. Do not automate
deletion or recreation to work around an unsupported transition.

Rollback the source default or explicitly restore the previous SKU through the
same reviewed deployment workflow. Reverting configuration cannot undo requests
already processed globally. No state/backend migration or provider conversion
is part of this decision.

## Compliance verification

- Assert default agreement across root inputs, tracked seed and native inputs.
- Check both providers' rendered default/fallback deployment SKUs and unchanged
  model/version/capacity, including preservation of explicit `Standard` inputs.
- Exercise SKU-specific regional quota selection and allocation-credit isolation.
- Keep historical graph fingerprints and narrowly identify the intentional
  default change rather than accepting unrelated resource-graph drift.
- Preserve Terraform lock/module pins and validate affected lifecycle contracts.

Only local compilation, mocked contracts and documentation checks are authorized.
Azure evaluation, what-if, provisioning, apply and destruction remain excluded.
These checks do not prove deployed parity, SKU-transition support or live quota.

## Documentation impact

Update current model defaults and affected deployment examples in the central
AI Landing Zones documentation. Explain processing location and the explicit
regional override without duplicating product guidance into repository READMEs.
Coordinate publication with availability of this product change.

## Review trigger

Reassess if Microsoft changes embedding deployment-type support, processing
commitments, regional availability, quota semantics or supported SKU transitions,
or if product requirements mandate regional-only inference.
