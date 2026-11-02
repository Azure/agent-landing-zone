# ADR-0038: Explicit service identity without delegated fallback

**Status:** Accepted for bounded implementation; not deployed<br>
**Date:** 2026-11-02<br>
**Owners:** Agent Landing Zone maintainers

## Context

The approved product plan preserves authenticated user-delegated access and
adds authenticated service access governed by each source's authentication
and scoped permissions, without a Blob-only source allowlist. Priorities are fail-closed source
authorization, one operator choice, native SDK ownership of state, provider
parity, and reversible coordinated deployment. No tenant-specific configuration
or consent workaround belongs in the product.

## Alternatives considered

- **Keep delegation mandatory:** preserves protected-source behavior, but cannot
  serve the approved common-corpus use case.
- **Remove guards or retry OBO failures with service credentials:** simpler, but
  cannot establish source audience and can expose protected content. Rejected.
- **Explicit structural profile with source-owned authorization:** selected.
  Requires coordinated platform, UI, runtime and connection updates, but has no
  implicit fallback or additional authentication flags.

## Decision

Reuse `HOSTED_AGENT_AUTH_MODE=user_delegated` (default) or `service_identity`.
Both retain mandatory login and Entra admission. Both use the existing
`RETRIEVAL_AUTH_MODE=native_search` publication under `agent-lz`.

Service mode does not restrict source families or capability flags and does not
require `FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS=[]`. Missing/null remains protected
`["rbacScope"]`. Sources authorize their configured service caller, and operations
requiring unavailable user delegation fail explicitly at invocation.
Never rewrite permission metadata or remove knowledge-base members to satisfy
mode selection. Source configuration and schema validation remain independent.

Provision the KB connection as a real project child, category `RemoteTool`,
`authType=ProjectManagedIdentity`, audience `https://search.azure.com/`, targeting
`{Search endpoint}/knowledgebases/{KB}/mcp?api-version={foundryIqApiVersion}`.
The separate direct Search connection remains `CognitiveSearch`. The project
MI's existing exact-service Search Index Data Reader grant authenticates this
connection. Ingestion retains its own Search identity and Blob grant.
After Search succeeds, both post-provision hooks run
`config.aifoundry.toolbox`. The official `azure-ai-projects==2.7.0` data-plane
SDK creates a Toolbox version with `MCPToolboxTool` named/server-labeled
`knowledge_base`, the project connection name, the configured KB MCP endpoint,
`allowed_tools=["knowledge_base_retrieve"]`, and approval `never`, then promotes
that version. No unsupported ARM Toolbox resource is invented.

Both providers publish internal `TOOLBOX_ENDPOINT` under `agent-lz`:
`{AI_FOUNDRY_PROJECT_ENDPOINT}/toolboxes/{KNOWLEDGE_BASE_NAME}/mcp?api-version=v1`.
It is a structural runtime binding, not another operator selector or root ARM
output. Native MAF uses the pinned official `FoundryToolbox`, authenticating as
the workload to `https://ai.azure.com/.default` and forwarding the genuine
**current** platform call ID. Foundry resolves the user and, for the KB target,
sets `x-ms-query-source-authorization` from its managed user delegation.
No local Search token acquisition, raw model MCP assertion, or parallel
fallback remains in this KB path. Preserve the existing AzureRbac Foundry
audience; no blueprint migration or arbitrary `UserEntraToken` is introduced.

The hosted instance receives the shared `AzureAIUser` (Foundry User) role at
the exact project. It receives no redundant Search grant for managed KB calls.
Standalone Search retains its exact-service grant.
The UI receives only Foundry Agent Consumer at project scope through the shared
role catalog, covering its conversational/workflow endpoint calls.

## Consequences

Service source access is shared by admitted application users, not public.
Mode and native connection-binding changes require redeployment, not hot reload.
The official Responses host still requires genuine gateway-supplied caller
partition and call-ID context for service callers. Never synthesize user IDs,
inject trusted gateway headers, or replace SDK checkpoints/storage.
Missing context fails before Toolbox HTTP. Managed tool authorization failures
abort the response rather than becoming model-visible error text. Delegated
consent produces official `oauth_consent_request` output with `incomplete`
status; service consent is a failed dependency, never user fallback. The UI
suppresses consent links and offers actionable denial/manual retry, not an
interactive consent/resumption implementation.

## Adoption and migration

Review the actual corpus and existing resource bindings first; choosing the
mode does not prove an existing source is shared. Configure/validate Search
sources and the project MCP connection, then deploy the compatible native UI
and runtime together with the selected publication. A failed configuration
stage must block component deployment. Existing components fail closed on a
live profile change; profile publication alone is not activation readiness.

The old account-level CognitiveSearch KB connection is not the native MCP
connection. Review its migration separately: incremental Bicep may leave the
old resource; Terraform removes the old managed account connection while
creating the project child. Do not delete sources or rewrite ACLs.
Rollback restores the coordinated delegated publication/components and reviewed
connection binding; it does not convert an approved common corpus back into a
protected source or restore permission metadata automatically.

## Compliance verification

Focused offline publication, pre-provision CLI, source-type independence,
RBAC and native connection contract tests cover defaults and negative cases.
Real project-SDK HTTP mocks verify Toolbox registration/promotion. Real pinned
MAF, Toolbox MCP transport and Responses-host tests verify current two-user
call IDs, both profiles, successful KB function invocation, consent and hard
failures, and absence of bearer/source tokens in model inputs or checkpoints.
Compile the affected Bicep connection and root, check Terraform interfaces and
formatting, and run native SDK tests in the orchestrator. Local evidence is not
deployed provider, gateway, downstream user-token exchange, retrieval or
tenant-consent-policy proof. Those boundaries require external validation.

## Documentation impact

The coordinating change owns central authentication, Foundry IQ, settings,
deployment, migration and rollback guidance in `Azure/AI-Landing-Zones`.
This record is an internal decision, not a duplicated product guide.

## Review trigger

Review before any live adoption, when SDK gateway/storage requirements change,
or before introducing hybrid authorization.
