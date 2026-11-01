# ADR-0019: Keyless UI-to-orchestrator authentication with managed identity

**Status:** Accepted<br>
**Date:** 2026-10-13<br>
**Owners:** Agent Landing Zone maintainers<br>
**Approver:** Paulo (maintainer)

## Context

In the classic topology the default deployment (`useCAppAPIKey=false`)
provisioned no credential for UI-to-orchestrator calls, but the orchestrator
still required one, so chat returned 401. Enabling an API key by default
fixes the symptom but introduces a long-lived shared secret that must be
stored, rotated, and distributed. Dapr service invocation (mTLS) is not
available when the orchestrator runs as a Foundry hosted agent, so it cannot
be the single mechanism across topologies.

Prioritized characteristics:

1. No shared secrets by default (managed identity first).
2. One mechanism that works in classic and hosted topologies.
3. User OBO token (`Authorization`) remains untouched.

## Alternatives considered

- **API key by default**: works everywhere, but is a shared secret; kept only
  as an opt-in fallback.
- **Dapr mTLS with internal ingress**: keyless, but classic-only and depends on
  sidecar trust and ingress settings; not available for hosted agents.
- **Entra managed identity token (chosen)**: keyless, standard Entra
  validation, works wherever the caller has a managed identity.

## Decision

- The UI acquires a token for `ORCHESTRATOR_AUTH_AUDIENCE` with its managed
  identity (`AZURE_CLIENT_ID`, falling back to Azure CLI locally) and sends it
  as `X-Service-Authorization: Bearer <token>`.
- The orchestrator validates issuer (`AZURE_TENANT_ID`), audience
  (`ORCHESTRATOR_AUTH_AUDIENCE`), and caller object ID
  (`ORCHESTRATOR_ALLOWED_CALLER_IDS`). Order: `DISABLE_AUTH`, service token,
  Dapr, API key, otherwise 401.
- Post-provision publishes, in classic mode, with label `agent-lz`:
  - `ORCHESTRATOR_AUTH_AUDIENCE`: environment override, else the UI's
    user-assigned identity client ID, else `https://management.azure.com`
    when the UI has only a system-assigned identity.
  - `ORCHESTRATOR_ALLOWED_CALLER_IDS`: environment override, else the UI's
    user-assigned identity principal ID, else its system-assigned principal ID.
- `useCAppAPIKey` defaults to `false` and remains gated off for hosted
  topologies.

## Consequences

- Default deployments have no shared secret between UI and orchestrator.
- With only a system-assigned identity (the default), the audience falls back
  to the Azure Resource Manager audience so keyless auth works out of the box.
  That token is broad; the caller object ID check is what binds it to the UI.
  For hardening, set `ORCHESTRATOR_AUTH_AUDIENCE` to a dedicated app
  registration or attach a user-assigned identity to the UI.
- Requires compatible component versions: Azure/agent-app-orchestrator#370
  and Azure/agent-app-ui#118. The manifest pin is updated after both merge.

## Fitness functions

- `tests/test_deployment_modes.py::KeylessOrchestratorAuthTests` verifies
  identity extraction, audience and caller derivation, overrides, and that
  empty keyless values are not published.
- `OrchestratorApiKeyGateTests` verifies the API key default is disabled and
  gated off for hosted topologies.
