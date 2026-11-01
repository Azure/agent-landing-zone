# ADR-0036: Independent NL2SQL capability in Agent App MCP Server

**Status:** Accepted for implementation, release not published<br>
**Date:** 2026-11-01<br>
**Owners:** Agent Landing Zone maintainers

## Context

NL2SQL is an optional application capability, not an orchestration strategy.
The application needs an independently reusable boundary that also accommodates
future tools without introducing another agent or workflow engine.
The existing `Azure/agent-app-mcp` demonstration is replaced, not migrated.

The approved scope is Azure SQL/SQL Server, application-wide read-only access,
an optional Container App, application-owned Cosmos DB with vector metadata,
and central product documentation. No Fabric/DAX, compatibility adapters,
Azure deployments or extensive validation campaigns are part of this change.

Priorities are a small implementation, explicit authorization, bounded results,
no additional Search dependency, and bidirectional infrastructure parity.
Acceptance measures are exactly two public tools, no credentials in tool inputs,
one approved source per request, at most 1,000 rows and 256 KiB, and explicit
deadline/error behavior.

## Alternatives considered

### Keep NL2SQL inside the orchestrator

Avoids a network boundary but couples SQL drivers, catalog credentials and
implementation to the agent host. Does not provide the requested reusable MCP
component. Existing direct registrations are removed in this new product line.

### Independent MCP using Cosmos and Azure AI Search

Provides semantic metadata retrieval but adds another service dependency,
index lifecycle and permissions. Rejected for the initial MCP capability.
Other retrieval capabilities can continue using Search independently.

### Independent MCP using a non-vector Cosmos catalog

Has the smallest retrieval implementation but limited semantic selection for
large schemas. Not selected because native Cosmos vector search provides the
requested retrieval without an additional Search service.

### Independent MCP using application Cosmos vector search

Selected. Store approved source bindings, schemas, relationships and examples
with embeddings in separate application containers. Query only the authorized
source and active metadata version. Do not copy business rows.

## Decision

Use Python and the official MCP SDK with stateless Streamable HTTP at `/mcp`.
Do not add Microsoft Agent Framework to the server. Its operations are bounded
functions, not autonomous agents. The consuming application retains its native
Agents/Workflows and either supported execution host.

Expose `nl2sql.list_sources` and `nl2sql.query(source_id, question)`. The server
owns metadata retrieval, model invocation, read-only/object validation, bounded
SQL execution and typed result translation. No arbitrary SQL execution or
catalog administration tool is exposed.

Authenticate callers to a dedicated Entra API resource. Validate issuer,
signature, audience, lifetime, application role and allowed caller identity.
The MCP identity owns model/catalog/declared-secret access, while the consumer
receives MCP invocation authorization, not SQL/catalog grants.

`DEPLOY_AGENT_APP_MCP=false` is the generic component switch. Selection adds
Cosmos as a required application dependency and provisions the Container App.
No second NL2SQL or vector-search enable switch is required. Generic Cosmos
provisioning and custom-only applications remain usable without MCP.

Foundation changes belong to the platform's Bicep and Terraform. Add vector
capability and new container policies without removing existing capabilities,
changing existing container data or using the Foundry backing Cosmos account.
The MCP runtime cannot provision infrastructure.

## Consequences

Cosmos/vector operations and embeddings have consumption cost. Small catalogs
can use full vector scans before quantized indexes have sufficient vectors.
Vector dimension changes require explicit reindexing. Shared-throughput or
policy incompatibility is an actionable error, not permission to recreate data.

The extra network/authentication boundary requires ordered lifecycle setup and
consumer deadlines longer than the server's complete query deadline.
Read-only SQL principals are the primary database authorization boundary.
Prompt instructions and SQL parsing are defense in depth, not substitutes.

## Adoption and recovery

Define schemas/configuration first, implement server/onboarding and consumer,
then integrate composition, grants and ordered lifecycle in both providers.
Update central user/operator documentation in the coordinated change.
Release preparation binds the exact validated candidate commits. Do not invent
published tags, modify old releases or publish images/tags without approval.

Administrative onboarding imports approved metadata and publishes its active
version only after completion. It does not require a permanent ingestion app.
No automatic legacy data migration is supplied.
Recovery selects a previous complete catalog/new-line image or disables the
capability without deleting data. No fallback to Search or in-process SQL.

## Compliance verification

Use focused local tests for protocol/auth denial, approved source filtering,
SQL validation/cleanup, output types and limits. Verify composition on both
hosts/modes, custom-only definitions, disabled component, provider policies and
PowerShell/shell syntax/behavior. No Azure deployment occurs for this task.
Actual Azure identity, networking, throughput, recall and cost remain unverified.

## Documentation impact and review trigger

Update the central Agent application, MCP, tools, NL2SQL, settings, deployment
and operation pages. Explain operator choices, automatic provisioning, SQL
onboarding and costs separately. Keep the service README short.
Revisit the index on model/dimension changes or measured catalog growth,
latency, recall or RU issues. Do not introduce speculative backend abstractions.
