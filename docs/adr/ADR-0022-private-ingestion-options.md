# ADR-0022: Explicit private ingestion and optional application composition

**Status:** Accepted<br>
**Date:** 2026-10-14<br>
**Owners:** Agent Landing Zone maintainers

## Context

Private native Blob ingestion exposed pending Search-managed outbound private
links and incomplete package-download egress. Firewall-as-DNS deployments also
need a persistent, opt-in proxy setting. Shared sources need a deliberate way to
omit document permission metadata without weakening protected sources.

The operator approved these changes and making the ingestion Container App
optional. Orchestration hosting and ingestion selection are independent.
Affected repositories are Azure/agent-landing-zone and the central documentation
source, Azure/AI-Landing-Zones. Runtime component implementations and release
pins are unchanged unless implementation evidence identifies a required
coordinated change.

Priorities are explicit authorization (no unrelated connection approval),
compatibility (no implicit removal on upgrade), consistent composition (one
selection for provisioning and deployment), bounded readiness, and offline
verifiability. No live Azure deployment or environment validation is authorized
for this change.

## Alternatives considered

### Option A: Explicit selections using the existing composition mechanism

- Add default-off firewall DNS proxy support without changing client DNS.
- Complete only build-subnet HTTPS package destinations justified by dependencies.
- Reconcile exact Search/target shared links before native source creation.
- Preserve an explicitly empty source permission list as operator intent;
  omitted values retain protected defaults.
- Make ingestion application selection independent of orchestration hosting;
  fresh deployments omit it, existing deployments retain their prior selection.
- Reuse managed identities, existing configuration labels and template-driven
  Search provisioning. Deployment permissions do not grant document access.
- Costs include selection propagation, upgrade handling and mocked Azure tests.
- Existing component versions remain usable; operators can restore prior
  selections without replacing document data.

### Option B: Separate fixed deployment templates for each combination

- Offers visibly distinct bundles, but duplicates topology, identity and hook
  logic across hosted/classic and native/application-managed ingestion.
- Increases synchronization and migration risks and makes custom applications
  harder to maintain. Reversing template choices can affect resource ownership.

### Do not change

- Preserves current behavior and incurs no implementation cost.
- Retains mandatory ingestion applications, manual private-link recovery and
  failure to honor deliberately empty source permission options.

## Decision

Adopt Option A. Expose ingestion application selection through normal azd
deployment configuration, resolved consistently by the existing composition
layer. A disabled component must not be provisioned, built, deployed or required
by endpoint/configuration reconciliation. Custom definitions retain their
explicit component intent. Existing deployment state must be preserved or an
actionable explicit migration decision required; absence of the new setting is
not permission to remove an existing component.

Native ingestion applies to supported, configured Foundry IQ sources, not every
source kind. Deploying an optional ingestion application does not automatically
change retrieval backends, source/index bindings or document authorization.
Invalid combinations must fail explicitly rather than silently ingest nothing.

Approve only target-side connections verified against the deployment Search
resource and expected target/group. Missing approval privileges must produce
actionable instructions; never approve all pending requests. Readiness polling
must be bounded. Firewall DNS proxy stays off unless selected and does not
rewrite VNet/VPN DNS. Shared-source permission opt-in must not alter application
authentication, other sources, or network restrictions.

## Consequences

### Configuration contracts

- `ENABLE_FIREWALL_DNS_PROXY` defaults to `false` and maps to
  `enableFirewallDnsProxy`, rendered as `dnsSettings.enableProxy` in the existing
  firewall policy. Firewall deployment and network-isolation gates still apply.
- The four pinned Microsoft npm feeds (`ms-feed-2`, `ms-feed-12`, `ms-feed-17`,
  `ms-feed-25` under `pkgs.visualstudio.com`) and `*.vsblob.vsassets.io` belong
  only to the build-subnet HTTPS/443 application rule. The existing
  `additionalAcrTaskBuildFqdns` array remains the extension mechanism.
- Omitted or actual-null `FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS` keeps
  `["rbacScope"]`. Explicit `[]` is the shared-source opt-in for native
  `foundry_iq` / `azureBlob` (including the existing `managed` alias), non-ADLS
  sources only. Invalid permission input, ambiguous ADLS selection, or active
  empty lists with unsupported native source kinds fail explicitly. Infrastructure
  also emits inactive `[]` for `ai_search` and `foundry_iq` / `searchIndex`;
  those values remain unused metadata, not a shared native-source opt-in.
  No additional runtime configuration key is introduced.
- `DEPLOY_INGESTION_CONTAINER_APP` is independent of orchestration topology.
  Fresh supported native deployments resolve it to `false`; existing deployments
  preserve explicit or persisted selections, and unmarked existing deployments
  preserve ingestion. Explicit custom definitions preserve declared components.
- `SEARCH_SHARED_PRIVATE_LINKS` publishes the exact Search link names, target
  IDs and groups with label `agent-lz` for post-provision verification. Only
  the deployment's exact Search shared links are readiness authorities.
  Pending links fail immediately with administrator approval instructions;
  approved links still provisioning have a 600-second budget with 10-second
  polling and request timeouts capped at 30 seconds.

### Approval evidence and runtime integration

The [Microsoft Learn shared private link guide, sections 2 and 3](https://learn.microsoft.com/en-us/azure/search/search-indexer-howto-access-private)
documents Search backend private endpoints as Microsoft-managed resources, not
customer-owned Network endpoints whose ownership can be inferred from request
text or names. Target-side connection shapes do not provide a
verified general association to the deployment's Search link. Therefore the
implementation performs no automatic target approval writes or target connection
enumeration. An administrator approves pending links; exact source-side
`Approved` plus `Succeeded` is the documented readiness signal. This avoids
guessing ownership while preserving an actionable, fail-closed gate.

The baseline UI v3.2.2 ignores ingestion selection and synthesizes a URL or Dapr
fallback for attachments. Coordinated UI support must consume the existing
selection key: a missing key preserves legacy eligibility; `false` gates upload
controls and rejects attachments server-side before endpoint resolution.
Text chat, authentication and retrieval remain unchanged. Native Blob ingestion
does not replace application-managed conversation attachments.

The compatible UI implementation originated in Azure/agent-app-ui commit
`6f1af9aa051bae4a0a8e713b49633d559ab96689` on
`feature/optional-ingestion-uploads`. Offline source, installed-wheel and
quality-gate checks passed for that source. The separately authorized
UI v3.3.0 release publishes this support at commit
`858ed4205d866b7bfbff43ca9ed20ab812baa24e`; the platform manifest and default
application definition pin that exact released commit.

Release and pin compatible UI support before activating ingestion-free platform
defaults. The initial implementation preserved published pins and did not
authorize runtime publication. The operator subsequently approved the
coordinated GitHub integration and release sequence. Azure deployment and
live-environment validation remain outside that authorization.

### Positive

- Fewer unnecessary Container Apps and builds on fresh native deployments.
- Existing private links become usable before dependent native source setup.
- Explicit shared-source and DNS choices survive normal configuration.

### Negative or accepted

- Native ingestion and application ingestion are not feature-equivalent.
- Private approval requires appropriate operator authorization.
- Changing defaults requires sticky upgrade handling and clear rollback.
- Offline checks cannot prove live network reachability or service readiness.

## Adoption and migration

Implement platform parameters, configuration, lifecycle selection and UI upload
gating together, then update central operator documentation on a feature branch.
Publish and pin the compatible UI first in a separately authorized release.
Preserve release pins during implementation and obtain separate approval before
publishing releases. Do not deploy Azure resources as part of this work.
Existing deployments retain selected components. Operators explicitly opt out
only after checking source bindings and ingestion dependencies. Do not destroy
existing applications or document/index data as a side effect of new defaults.

Rollback restores explicit ingestion selection and protected permission options,
or disables DNS proxy for non-firewall-DNS topologies. Reverting a private-link
readiness gate does not revoke previously approved links; revocation requires a
separate deliberate operator action.

## Compliance verification

- Offline composition matrices cover hosted/classic, ingestion on/off,
  fresh/existing environments and explicit custom definitions.
- Provisioning and both shell hooks select the same components.
- Mocked Search tests cover matching, unrelated requests, denied approval,
  timeouts, already-approved links and propagation delays.
- Permission tests distinguish omitted, empty and invalid input and preserve
  protected defaults.
- Bicep compilation and contract tests verify default-off DNS proxy and
  build-only egress scope. No live Azure validation is claimed.

## Documentation impact

Update configuration, deployment, native ingestion, network-isolation and
troubleshooting pages in Azure/AI-Landing-Zones. The legacy docs branch is not
the product documentation source.

## Review trigger

Reassess before release if offline integration identifies runtime incompatibility,
and when Foundry IQ APIs or supported source capabilities change. Live acceptance
requires separate operator authorization.
