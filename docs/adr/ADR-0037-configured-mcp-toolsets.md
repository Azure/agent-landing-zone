# ADR-0037: Explicit MCP toolsets above an application-independent foundation

**Status:** Accepted for implementation<br>
**Date:** 2026-11-02<br>
**Owners:** Agent Landing Zone maintainers

## Context

Agent App MCP hosts tools over MCP. NL2SQL is one toolset, not the server's
identity or an infrastructure prerequisite. The maintainer requires tools to
initialize only when selected, and the same foundation to support applications
other than the reference application.

Affected repositories are Agent App MCP, the platform's application composition,
the generic orchestrator consumer and central documentation. Priorities are:

1. Explicit selection: an omitted or empty toolset list registers zero tools.
2. Dependency isolation: disabled NL2SQL creates no Cosmos, model, SQL or
   Key Vault client and requires none of its configuration.
3. Authorization: authentication remains mandatory, including an empty server.
4. Foundation independence: application composition resolves requirements into
   generic Bicep/Terraform inputs, without tool names in the foundation.
5. Extension simplicity: adding a reviewed toolset requires one focused module
   and an explicit registration, not a plugin discovery framework.

## Alternatives considered

### Keep unconditional NL2SQL initialization

Preserves existing startup behavior but makes every MCP deployment depend on
SQL-specific configuration, Cosmos and models. It fails explicit selection and
prevents useful independent tools.

### Add one enable flag for every toolset

Provides explicit activation but multiplies the shared configuration contract
and conditions in server composition. It can work for one toolset but is not
selected for the extensible server.

### Select a reviewed list of toolsets

Selected. `MCP_TOOLSETS` is a JSON array, default `[]`. The current supported
selection is `["nl2sql"]`. Unknown names, duplicates and invalid shapes fail
before dependency initialization. Register only selected, packaged toolsets.
No arbitrary imports, remote plugins or user-supplied executable paths exist.

## Decision

Separate shared authentication, App Configuration bootstrap and MCP transport
from the NL2SQL module. Each selected toolset validates its own settings,
initializes its own clients and registers its own tools with the official SDK.
Use scoped asynchronous cleanup on normal shutdown and startup failure.
NL2SQL keeps its existing tool names, argument/result schemas, authorization
and bounded read-only behavior.

In the reference application, `DEPLOY_AGENT_APP_MCP` selects server compute
only. `MCP_TOOLSETS=["nl2sql"]` explicitly selects the SQL capability and its
application-owned catalog/model/declared-secret grants. Selection while server
compute is disabled is rejected rather than silently ignored.

Cosmos vector capability and catalog retention are independent of server
compute. Once a catalog is owned, deselection must not delete its containers
or downgrade account capabilities. A newly selected empty MCP server does not
require an application Cosmos account, model access or SQL secret access.

Keep all reference-application names, tool selection and dependency translation
in the application layer (`config/`, root application definition and parameters,
and lifecycle hooks). The foundation continues accepting generic compute,
container, capability and role inputs. A custom application definition contributes
only its declared components, profiles and resource requirements. Reference MCP
switches must never silently add the reference app or catalog to a custom app.
Custom applications may also consume or deploy MCP using their own explicit
configuration and dependency declarations.

## Consequences

Empty authenticated servers are supported but provide no business tools.
Toolset changes require a restart/redeployment because registration and client
lifetimes are startup-scoped. Selecting NL2SQL retains existing Cosmos/model
cost and network prerequisites. No additional Search dependency is introduced.
No hot reload, arbitrary tool installation or automatic permission broadening
is promised.

## Adoption and migration

Implement and test MCP first, then the platform's application selection and
both provider projections, then update central setup instructions. Publish a
new MCP major because implicit SQL activation is removed. Bind its exact release
commit together with the generic consumer release in the platform manifest,
loaded application definition and reviewed component-pin fixture.

Existing operators explicitly select `MCP_TOOLSETS=["nl2sql"]` to preserve SQL
behavior. Rollback restores the previous complete pinned combination and keeps
catalog data. Disabling a toolset stops registration and client initialization,
not resource deletion or implicit revocation of previously granted roles.

## Compliance verification

Use the real MCP client to verify empty and NL2SQL tool discovery, invocation,
auth denial and unchanged structured schemas. Fail tests if disabled NL2SQL
imports its runtime module, validates its settings or opens provider clients.
Prove selected-tool initialization and cleanup, unknown/duplicate rejection and
explicit failure rather than fallback on invalid selected configuration.

Composition tests cover empty server, enabled SQL, retained catalog, custom-only
definitions and both hosts. Verify identical generic inputs through the Bicep
and Terraform adapters and unchanged provider/module locks. Run relevant hook
and foundation contracts without Azure deployment. Mocked checks do not prove
deployed identity, network or provider parity.

## Documentation impact

Update central application, MCP, NL2SQL, tools, settings, deployment and
build-your-own guidance. Explain server selection separately from toolset
selection and show the explicit SQL setup. Keep service READMEs concise.

## Review trigger

Review when adding a second toolset, changing authorization scopes, introducing
per-caller tool visibility, or requiring live configuration reload.
