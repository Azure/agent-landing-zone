# ADR-0034: Use native agents and workflows with explicit host integrations

**Status:** Accepted architectural direction, implementation and release gated
by the evidence below<br>
**Date:** 2026-10-31<br>
**Owners:** Agent Landing Zone maintainers and runtime component owners

## Context

The current orchestrator strategy selector mixes hosting technology, retrieval
capabilities and application behavior. Its Hosted adapter deliberately runs
statelessly. Chainlit history and feedback still depend on classic orchestrator
APIs in some paths. Enabling a human-reviewed workflow must not introduce another
workflow engine, require an unused classic service, or conceal host differences.

The maintainer requested a clean major orchestrator revision based on Microsoft
Agent Framework (MAF), with conversational and workflow experiences on Foundry
Hosted Agents or Azure Container Apps. App Configuration remains an intentional
operational dependency. Runtime state and product metadata must be separated.
Provisioning must create resources and permissions before starting application
code, without runtime repair, circular bootstrap dependencies or duplicated
checkpoint databases.

Affected repositories are `Azure/agent-app-orchestrator`, `Azure/agent-app-ui`,
`Azure/agent-landing-zone` and `Azure/AI-Landing-Zones`. Ingestion remains a
separate optional component. The prioritized characteristics and measures are:

1. Native execution: use published official agent, workflow, hosting and durable
   client APIs without an ALZ workflow scheduler, state SDK or SDK monkeypatch.
2. Simple dependencies: a Hosted runtime has no application Cosmos dependency,
   and a durable Container Apps runtime has one execution backend, Durable Task
   Scheduler (DTS). Product features declare their own dependencies.
3. Explicit authorization: negative owner/session/action tests fail closed.
   A service identity or an arbitrary session ID is never an end-user identity.
4. Reproducible operation: exact packages, image digests, graph/executor names,
   configuration snapshots and compatible component commits are identifiable.
5. Bounded evidence: narrow local and contract tests plus minimal real sandbox
   tests, without provisioning the complete landing zone to exercise a workflow.

## Alternatives considered

### Option A: Native MAF execution with explicit integrations for both hosts

- Benefits: supports both deployment choices, composes tools independently of
  application kind, and delegates persistence and human waits to each official
  runtime integration.
- Costs and risks: two clients and different operational models remain visible.
  Published Python integration availability and preview constraints must be
  checked rather than inferred from a source sample.
- Security and identity: use trusted Foundry invocation context or the
  authenticated BFF boundary, and identity-based DTS access. Retrieval delegation
  and ownership remain separate checks.
- Operational consequences: Hosted publishes conversational and workflow
  applications separately when both are selected. Container Apps runs a durable
  worker without needing public worker HTTP ingress or Azure Functions.
- Component compatibility: requires a coordinated orchestrator major, UI
  integration, platform composition and documentation change.
- Reversibility: old deployment artifacts can be retained for explicit rollback,
  but native session/checkpoint data is not transparently transferable.

### Option B: Native Hosted execution only

- Benefits: one hosting integration and managed session/workflow storage, with
  fewer application-owned execution resources.
- Costs and risks: removes Container Apps as an application execution choice
  and couples supported behavior to Foundry availability and integration limits.
- Security and identity: requires the same trusted invocation and end-user
  ownership checks as Option A. Managed state does not eliminate these checks.
- Operational consequences: no application DTS worker or scheduler, but native
  checkpoint/version-affinity and retention still need operator guidance.
- Component compatibility: still requires the major runtime and native UI
  contracts, not merely a deployment flag change.
- Reversibility: adding Container Apps later introduces its explicit integration
  and independent durable state. No free state portability is assumed.

### Option C: Native durable Container Apps execution only

- Benefits: one official durable worker/client model for agents and workflows,
  including human waits, with an explicit execution backend.
- Costs and risks: excludes native Hosted execution and requires application
  operators to manage worker lifecycle, scheduler access and scaling.
- Security and identity: DTS service permission is not product-user
  authorization. The BFF must bind users to instance IDs and pending actions.
- Operational consequences: requires DTS and an appropriately available worker.
  Durable side effects still need idempotency at each external system.
- Component compatibility: requires compatible published Durable Extension
  packages and the same coordinated application/platform update.
- Reversibility: adding Hosted later creates separate native sessions and
  workflow publications. It does not import DTS checkpoints automatically.

### Do not change

- Benefits: preserves the deployed strategy APIs, classic persistence and current
  release combination without adoption work.
- Costs and risks: does not provide native workflow/HITL execution, retains
  hidden classic dependencies, and encourages application code to emulate
  platform functionality. It does not meet the requested outcome.

## Decision

Choose Option A. Share naturally common agent definitions, tools and typed
business inputs, not an abstraction that pretends both hosts have the same
protocol, state store, authorization context or operational behavior.

### Execution and user experience

- Use MAF agents for conversational operation and MAF workflows for processes
  with explicit steps, conditions and human input.
- Publish Hosted conversational and workflow applications through the official
  Responses hosting integration. Use request-aware factories and stable
  workflow/executor identifiers. Do not retain the old forced `store=false`
  adapter as the native implementation or use deprecated `workflow.as_agent()`
  hosting.
- Use the official standalone Durable Extension worker and client with DTS on
  Container Apps. Azure Functions is not required for this worker model.
- Keep Chainlit and its BFF. Present conversation and a named process when both
  are enabled. Do not expose a user-facing infrastructure or strategy selector.
- Persist a workflow's pending human input through the selected native runtime.
  A browser socket, waiting coroutine or Chainlit timeout is not its system of
  record. Reconnect and resume through the official client.
- Treat MCP, Foundry IQ and Search as capabilities/tools. A workflow can use the
  same authorized capabilities as an agent.
- Do not add a scheduler, workflow engine, generalized state SDK or Redis solely
  to make the two hosts appear identical. Distributed token streaming is not
  required for durable workflow progress.

### Configuration and provisioning

- Publish `APPLICATION_MODE` as `conversational`, `workflow` or `both`, with
  `conversational` as the default. Each Hosted publication receives one kind.
- Publish `ORCHESTRATION_HOST` as `hosted` or `container_apps`, with `hosted`
  as the default. Together with `APPLICATION_MODE`, these are the only public
  native deployment selectors.
- Include the UI/BFF in either host choice. Do not require a separate
  `hosted-panel` versus `hosted-no-panel` selection, an administrative-panel
  deployment flag or a redundant host boolean.
- Derive necessary foundation switches from the selected host internally.
  Native prompts, template inputs, persisted settings and public handoffs must
  use the canonical selectors rather than materializing the old panel topology.
  Reject obsolete explicit native selection inputs with corrective guidance,
  without silently migrating or deleting an older deployment's state.
- Keep any necessary legacy library interfaces isolated from the native
  lifecycle. They must not turn an old panel setting into an implicit history
  or metadata feature choice.
- Keep `HOSTED_AGENT_BASE_URL` for conversational invocation and
  `HOSTED_WORKFLOW_BASE_URL` for the separate workflow publication.
- Bind durable clients/workers through the official scheduler configuration and
  actual provisioned outputs, not a guessed endpoint.
- Retain one App Configuration store per installation/lifecycle. Load relevant
  settings deliberately with caching/refresh, rather than eagerly resolving
  every unrelated Key Vault reference. Publish settings under label `agent-lz`.
- Distinguish dynamic functional parameters from structural host, graph,
  identity, persistence and publication choices that require deployment.
  Capture functional configuration for a workflow run. Reevaluate current
  authorization separately on every interaction.
- Provision foundation resources and exact grants before application activation.
  An identity created by publication may receive scoped grants afterward as an
  explicit deployment step. Runtime code must not provision resources, grant
  roles or repair missing infrastructure at startup.
- Keep `infra/` foundation-only. Application publishing remains in the
  application lifecycle. Assess and implement every affected capability in
  both Bicep and Terraform, including outputs, consumers and hook behavior.

### State, identity and optional features

- Native execution state belongs to Foundry for Hosted and DTS for the durable
  Container Apps worker. Do not duplicate these checkpoints into application
  Cosmos. Foundry backing resources are a separate platform concern.
- The UI/BFF owns authenticated mappings, product metadata and feedback when
  those features are enabled. These are not a second workflow execution store.
- Use trusted platform user context or an explicitly supported delegation path.
  Never trust caller metadata, substitute the BFF identity for the user, or
  authorize a read/resume merely because an instance ID exists.
- Check ownership and the currently pending request before human replies.
  Rejected, stale, duplicate and wrong-run actions must not advance another run.
  Tool authorization, document-level security and OBO remain independently
  enforced.
- Keep history, feedback and private attachments explicit and feature-gated.
  They default off independently of the selected host. Workflow/both still
  requires owner/action metadata even when history is disabled.
  Private attachments do not publish documents into a corporate corpus.
  Use supported native attachments or an authorized private-storage tool path.
  Custom ingestion is optional and disabled by default.
- Grant Key Vault secret access only to actual consumers. App Configuration
  reader permission is not secret access. Prefer managed identity where the
  target service supports it.
- Preserve network-isolated deployments through the existing explicit runner,
  endpoint and egress model. Public sandbox reachability is not evidence that
  the private deployment path works.

This decision supersedes ADR-0001/ADR-0003/ADR-0004 policies that require a
history-blind stateless Hosted container and manual BFF replay for the new
native runtime.
Their security observations are not invalidated. In particular, untrusted
identity metadata and service-identity reads driven by arbitrary IDs remain
unsafe. It also supersedes any implication that classic conversation APIs are
the mandatory backing service for native UI history or feedback.

The maintainer explicitly approved the two-selector public contract on
2026-11-01. This supersedes the earlier decision to expose or map old panel
topology choices in the native lifecycle. Retaining the old public selectors
would preserve redundant choices and indirect feature defaults. Making history
or feedback unconditional for Hosted would also introduce unnecessary metadata
dependencies. The selected alternative includes the UI implicitly while keeping
product features and their dependencies explicit.

## Consequences

### Positive

Application behavior, tools, hosting and product metadata have separate owners.
Long human waits use an official execution backend without requiring a classic
orchestrator, Cosmos checkpoint layer or Functions application. Provisioning
dependencies and host differences are visible rather than hidden in adapters.

### Negative or accepted

The Python hosting/durable integrations may be prerelease even when the hosting
service is generally available. A published compatible package set is a release
gate. Native persistence does not promise state portability across changed
graphs, identities, immutable versions or hosts. Retention and service limits
apply. Durable execution does not guarantee exactly-once external writes.

Container Apps requires scheduler connectivity, appropriate worker availability
and tested scaling. No automatic scale-from-zero claim is made. Workflow token
streaming and Hosted Responses streaming need not have identical UX.

The sandbox introduces only the minimum required compute, registry and execution
services. Low-cost/Consumption SKUs are preferred where supported. Reused model
resources are not modified or deleted. New resources are inventoried and removed
after exact-product validation, not left as a permanent alternate landing zone.

## Adoption and migration

1. Confirm required APIs in compatible published packages, including explicit
   prereleases. Source examples with editable SDK requirements do not pass.
2. Implement and test the orchestrator and UI contracts on feature branches from
   `develop`. No compatibility engine or automated conversation-data migration
   is introduced. Existing conversations remain in the previous deployment.
3. Incorporate foundation/composition/hook changes for both providers, including
   the real native clients' configuration, resources and least-privilege access.
4. Run the bounded sandbox proof and then test the exact changed product
   entrypoints/images. A sample-only success cannot validate a different image.
5. Bind validated component commits in the manifest and application definition,
   prepare an orchestrator major and semantically appropriate umbrella release,
   and update central documentation as one coordinated delivery.

Do not delete existing Cosmos data or native sessions during adoption.
Operators may retain the prior deployment and exact images/configuration for
rollback. Rollback redirects to that deployment and its own state. It does not
convert or merge new-host checkpoints. Roll forward incompatible graph changes
through a new publication instead of pretending old checkpoints are portable.

## Compliance verification

Required focused checks cover typed inputs, host/mode selection, relevant
configuration loading and refresh, per-run functional snapshots, owner-bound
history/feedback/attachments and negative human-action authorization. Tests
must exercise real SDK call shapes, not only configuration mocks.

The minimal Azure proof uses synthetic data and bounded timeouts:

1. Hosted conversational turns recover a marker from native server state.
2. Hosted workflow pauses for approval and resumes from a fresh client.
3. Durable Container Apps conversational turns preserve the marker.
4. A durable workflow remains pending across an actual owned worker restart,
   then resumes from a fresh client with deterministic output.
5. Rejection prevents approved completion on both hosts.
6. Duplicate, stale and wrong-request/run replies do not change another or
   already completed execution.

After core execution passes, check App Configuration A-to-B refresh without
rebuilding and verify that an existing run retains its functional snapshot.
Use short waits, no hours-long soak, and never deploy the entire ALZ solely for
these tests. Report provisioning/RBAC propagation separately from test time.

Run relevant shared contracts, both provider checks and affected PowerShell/shell
lifecycle tests. Compilation, mocks, a short restart test and client reconnects
do not prove private-network parity, long-duration SLA, Hosted crash recovery,
cross-user platform isolation or exactly-once business writes. Record those
unverified scenarios explicitly.

The maintainer explicitly prioritized implementation and unit tests for this
iteration and deferred live private-network validation. Preserve private-network
configuration and provider contracts, but do not provision a complete ALZ to
validate this runtime revision. A bounded minimal Azure proof may supplement
local native-SDK checks where available. Record missing deployed evidence as a
limitation, not as a passing test or a reason to expand the deployment.

## Documentation impact

Update the current application architecture, quickstart/deployment, configuration,
orchestration/tools, UI history/feedback/uploads and workflow operation guidance in
`Azure/AI-Landing-Zones` main. Describe supported host differences and preview
constraints without release-comparison blocks. Keep service READMEs as short
links to the central site.

## Review trigger

Review before publication if a required native API is absent from published
packages or a sandbox checkpoint/authorization test fails. Revisit when Python
integrations graduate or materially change, a host gains supported state
portability, a production workflow adds external writes, or scaling/private
network requirements change.
