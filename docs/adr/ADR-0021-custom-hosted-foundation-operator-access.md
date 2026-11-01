# ADR-0021: Separate custom Hosted foundation pull from operator grants

**Status:** Accepted for implementation; Azure application requires review<br>
**Date:** 2026-10-13<br>
**Owners:** Agent Landing Zone maintainers

## Context

Custom `azure.ai.agent` components require the existing foundation project
managed identity's registry pull grant even when bundled routing stays classic.
The shared preparation flag also selects an executor Project Manager grant.
Read-only validation found that exact assignment absent, although the existing
operator's management and data-plane roles collectively covered its permissions.
A redundant but new assignment is still an authorization change, not an implicit
prerequisite approved by selecting a custom application.

Scope is this repository's Bicep foundation, application composition and shared
preflight. Priorities are no implicit operator escalation, compatible foundation
defaults, exact per-instance runtime profiles, private deployment viability and
no new models or capacity.

## Alternatives considered

### Reuse an existing narrow executor gate

No Project Manager-specific gate exists. Disabling the entire executor or Hosted
preparation path would suppress other necessary roles or project-identity pull.
Reusing those broad gates therefore cannot meet the required fitness functions.

### Explicit compatible operator gate (selected)

Add a boolean `grantHostedAgentProjectManager` defaulting to true. It controls
only the existing executor Project Manager entry. Custom Hosted preparation in
classic topology composes false; existing foundation callers and bundled Hosted
keep their previous behavior. The project-identity pull gate is unchanged.
Preflight verifies existing operator authorization when the grant is suppressed
and fails with actionable guidance rather than granting or silently falling back.
Before a new project exists, it verifies inherited management access and
explicitly reports that the unchanged foundation Cognitive Services User executor
role supplies new-account data access. It does not require an impossible
pre-existing project binding or invent existing data authorization.

### Do not change / request an extra grant

Leaves an unnecessary new operator assignment coupled to image pull, or requires
permission beyond the requested least-privilege behavior. It does not address the
root authorization separation even where existing permissions are sufficient.

## Decision

Use the explicit compatible gate. Do not invent identities, ACR/OIDC connections,
Entra permissions, role replacements, catch/retry deployment or deferred-start
lifecycles. Preparation never selects a bundled agent version. Runtime capability
profiles remain reconciled on the verified provider instance before smoke.

## Consequences

The additive parameter defaults to legacy behavior. Custom classic Hosted/mixed
definitions suppress only Project Manager, not managed-identity pull or runtime
profiles. Operators must already possess appropriate scoped authorization; missing
or unverifiable authorization stops preflight. No network, models, capacity or
runtime configuration contract changes.

The Bicep backend is supported. The repository's Terraform parity inventory
records Hosted preparation as unsupported; this gate does not establish Terraform
parity or require inventing a second backend implementation.

## Adoption and migration

Review and integrate source and coordinated central documentation before normal
foundation refresh. Compose, run intact preflight and actual preview, inspect
privilege/resource deltas, then apply only with explicit execution authorization.
Existing environments need declarative project-MI pull, not a manual role grant.

Rollback source/selection preserves existing assignments: incremental deployment
does not revoke prior operator or runtime grants. Do not automatically delete
roles. A previously assigned Project Manager role needs separate explicit removal
authorization, never implicit cleanup.

## Compliance verification

- Compiled gate default true; only executor Project Manager depends on it.
- Custom Hosted classic: prepare true, operator gate false, bundled deploy false.
- Mixed components same; Container-only and bundled defaults unchanged.
- Project-MI pull remains selected with operator gate false.
- Missing operator permissions fail before apply; no role writes in preflight.
- Both hook variants reuse shared preflight; metadata and profiles remain aligned.
- Bicep build/lint/size, owned-infra integrity, parity inventory and actual preview
  demonstrate no unrelated resources, models, identities or topology introduced.

## Documentation impact

Parent coordinates central AI Landing Zones operator documentation: explain the
new compatibility gate, pre-existing authorization requirement and distinction
between foundation image pull and exact runtime profiles.

## Review trigger

Reassess if provider pull identity requirements, Project Manager permissions,
custom bundled topology selection or supported Terraform Hosted preparation
change; also review if real preflight rejects a legitimate narrower role.
