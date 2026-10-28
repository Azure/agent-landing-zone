# ADR-0028: Deliver delegated hosted retrieval as a built-in capability

**Status:** Accepted implementation direction; local implementation and Azure
acceptance tracked separately<br>
**Date:** 2026-10-27<br>
**Owners:** Agent Landing Zone maintainers

## Context

UI sign-in and OBO authenticate invocation of Foundry, but the shipped hosted
`maf_lite` strategy does not receive the credential its direct retrieval provider
requires. Customers should not have to implement that missing integration.
Keep hosted orchestration and the default strategy, preserve source permissions,
and never replace a missing user's authorization with application-only access.

The inspected manifest pins UI v3.3.1, orchestrator v5.2.2, ingestion v3.1.3 and
incorporated infrastructure v2.7.3. Component feature work starts from develop;
the inspected orchestrator develop differs from its manifest commit only in
CHANGELOG.md. Revalidate the exact release combination before publishing.

Prioritized characteristics:

1. Authorization: no protected content, citations or downloads for a denied user.
2. Isolation: no credentials or retrieval state shared across user requests.
3. Completeness: required retrieval and configured sources cannot silently fail.
4. Operability: automatic deployment configuration and explicit consent errors.
5. Compatibility: preserve conversation ownership, classic behavior and rollback.

## Alternatives considered

| Alternative | Benefits | Costs and constraints |
| --- | --- | --- |
| Managed Foundry Toolbox delegation | Preferred when the complete source, delegated connection and filter contract is supported; Foundry manages credential lifecycle. | Current pinned projects/MAF packages do not provide the required authenticated Toolbox integration. The IQ quickstart uses agent identity, not proof of user authorization. A call ID alone is not client authentication. |
| Built-in application OBO and official header forwarding | Reuses the existing UI confidential client and Search connector, without customer code or a new service. | The solution owns audience-specific acquisition, consent handling, secret redaction and request isolation. Each source's authorization contract still applies. |
| Leave the integration to the deployer | No immediate implementation change. | Does not deliver protected retrieval through the product's default path. Rejected. |

Prefer managed delegation where it demonstrably covers the complete combination.
Use integrated OBO for the current direct Search path. Never choose a different
route after authentication failure. Do not expose an unimplemented Toolbox mode
or upgrade the entire framework merely to imitate a service-identity sample.

## Decision

### Preserve invocation and separate downstream authorization

Keep `HOSTED_AGENT_AUTH_MODE=user_delegated` and the existing user-delegated
Foundry invocation. Publish `RETRIEVAL_AUTH_MODE=native_search` automatically
under App Configuration label `agent-lz` for the integrated protected path.
No customer-authored JSON source inventory is required.

The authenticated UI BFF obtains both delegated tokens from the same current
UI API assertion:

| Hop | Credential |
| --- | --- |
| UI -> Foundry `Authorization` | Existing user-delegated Foundry token for `https://ai.azure.com/.default`. |
| UI -> Foundry -> hosted `x-client-search-token` | Raw, already-exchanged delegated token for `https://search.azure.com/.default`. |
| Hosted -> Search `Authorization` | Existing workload transport credential. It is not the user's source entitlement. |
| Hosted -> Search `x-ms-query-source-authorization` | Exact raw Search delegated token, without a Bearer prefix. |

The official hosted runtime contract forwards `x-client-*` on both Responses
and Invocations. An immutable request-local credential must remain separate
from the legacy `request_access_token` assertion, which requires OBO.
Do not decode the downstream token, exchange it again, fabricate its expiry,
or persist it for refresh/recovery.

Native Search enforces source access; forwarded principal/group claims do not.
Do not introduce an unsigned identity envelope, a new invocation mode,
impersonation grant, application token broker or group-expansion service.
Existing conversation ownership and its grants remain separate.

### Enforce permissions at the retrieval boundary

Enable `permissionFilterOption` on the application index, retaining its existing
`userIds`, `groupIds` and `rbacScope` field annotations. Search resolves user and
group access from the delegated token. Application-side filters may restrict
conversation/source scope, but are not a substitute for native authorization.
The hosted workload still needs least-privilege Search transport access at the
exact provisioned resource; it must not gain elevated-read permission.

| Source | Required authorization contract |
| --- | --- |
| Blob / ADLS | Ingest native RBAC/ACL permission metadata and send the delegated Search token. Empty permission ingestion is not protected access. |
| `searchIndex` / ALZ-ingested files | Native permission filtering over correctly populated Entra user/group/RBAC fields. Permission freshness remains an ingestion responsibility. |
| Conversation uploads | Native `userIds` authorization to the authenticated uploader plus a mandatory conversation filter. A conversation ID or platform partition key is not an uploader oid. Missing required scope must not silently omit a bound source. |
| Fabric ontology / Data Agent | Documented Search-token mediation to Fabric, with compatible API/source configuration and the user's Fabric permissions. |
| Work IQ | A distinct app-audience user assertion in `x-ms-query-work-iq-source-authorization`; never substitute the Search token. The matching Entra app authentication/consent is a source-specific requirement. |
| Indexed SharePoint | Permission ingestion must be enabled. App-only indexing access alone proves no user trimming. Site groups need the documented connector app registration and site-URL metadata. |
| Generic MCP | Endpoint-specific delegated authentication and approved destinations; an arbitrary MCP server is not automatically supported. |

Runtime-only OneLake/remote SharePoint wiring is not promoted into an integrated
platform capability by this change. Public web or intentionally shared content
does not relax the authorization of other members of a mixed knowledge base.
Configured protected sources must not disappear to make a request pass.
`knowledgeSourceParams` is not assumed to be an exclusion allowlist.

For solution-produced conversation uploads, the trusted UI passes exactly the
authenticated uploader's object ID to ingestion. Ingestion stamps
`metadata_security_user_ids` with that ID, an empty
`metadata_security_group_ids` array, an empty `metadata_security_rbac_scope`
and the conversation ID on every chunk. Native permission filtering therefore
enforces uploader ownership from the delegated Search token; it does not need
a second application-side oid filter or a new forwarded identity assertion.
The UI must reject uploads with a missing or invalid authenticated uploader ID
before ingestion, and retrieval must retain the conversation filter. Never
infer ownership by decoding the Search token or trusting an opaque hosted
partition key. Legacy non-native authorization retains its existing trusted
principal requirements.

Work IQ registration uses `WORK_IQ_APPLICATION_ID`,
`WORK_IQ_FEDERATED_CREDENTIAL_ID` (the federated credential object ID), and
optional `WORK_IQ_TENANT_ID`. The client obtains an assertion for the app's
`api://<application-id>/access_as_user` scope. The indexed SharePoint source
uses the native `connectionString`/`ingestionParameters` contract with
`userIds`/`groupIds` permission ingestion, not the obsolete prebuilt-index shape.
Its `SHAREPOINT_INDEXED_FEDERATED_CREDENTIAL_APPLICATION_ID` is Search's managed
identity application/client ID, not a credential object ID. Federation and
tenant consent remain administrator-owned, not customer-written integration.

Validate these nonsecret UUID inputs before publication. Enabled sources with
missing bindings, incompatible APIs or unverifiable required consent stop
before Search resource mutations; never remove a source to report success.
The implemented advanced-source contract requires `2026-08-01-preview`.
Keep the Blob default unchanged. Bound Fabric sources select a planning model
and `low` reasoning; Blob-only knowledge bases retain `minimal`.

Reconcile permission enforcement on existing indexes with conditional updates,
preserving documents and operator customizations. Already enabled indexes are
no-ops. Incompatible permission annotations fail before dependent cleanup
instead of silently retaining an unprotected schema.

### Authorize citation downloads again at redemption

Native hosted citations use the authenticated UI `/api/download/{grant_token}`
route, not Blob SAS or the legacy container-only reader. Signed selectors bind
the current principal and UI session, but do not grant source permission by
themselves. Every redemption requires fresh authorization.

Shared Blob/ADLS downloads use OBO for `https://storage.azure.com/.default`
from the current UI API assertion. The UI registration requires delegated
Storage `user_impersonation` consent, and the user still needs source RBAC/ACLs.
There is no workload fallback on this path.

Conversation uploads are different: the UI verifies the exact document URL,
conversation and authenticated uploader against a fresh native Search query,
using the current user's Search token for source authorization. Only then may
its workload identity read that upload from Blob. The bundled UI therefore
uses the existing `retrieval-reader` capability profile and receives
`SearchIndexDataReader` for Search transport. Preserve its existing Blob grants;
neither transport grant replaces user authorization.

Restrict downloads to configured storage accounts/containers and stream within
bounded size/time limits. Unverifiable upload targets, oversized query results,
expired sessions and changed permissions fail closed. Embedded sessions use
their own validated principal/session, not classic Cosmos conversation owners.

### Fail explicitly and protect credentials

Missing required delegated credentials fail before retrieval/streaming.
Preserve the distinction between intentionally disabled retrieval, successful
zero results and failed required retrieval. Handle consent, Conditional Access,
expiry, source denial, timeout and cancellation through safe existing errors.
Never retry without the user header, switch to service data authorization,
or replay a partially executed model stream.

Both adapters must isolate credentials per request, including concurrent users.
The pinned Responses SDK can serialize `client_headers` into resilient-task
input. Token-bearing requests must not enter that persistence/recovery path.
Credentials are forbidden in prompts, conversations, checkpoints, logs,
exceptions, model tool arguments and response metadata. Redact custom headers
as well as Authorization.

Initial UI MSAL acquisition classifies consent and authentication failures.
Downstream Search 401/403 failures must retain a typed, safe authentication
outcome instead of becoming generic retrieval errors. Accept only bounded,
unambiguous Bearer claims challenges from the configured Search response;
ignore provider bodies, authorization URLs, resource hints and arbitrary
destinations. An ordinary 403 remains source denial, not an instruction to
request broader permissions.

Carry the validated challenge only in authenticated transport error metadata,
never model text, history, telemetry or runtime recovery checkpoints. Both hosted
adapters must expose the same outcome. The UI offers explicit interactive
recovery; it never replays the failed turn, including partial output.

For standalone OAuth, reuse the configured tenant, UI scopes and normal
Chainlit OAuth state/callback controls. Protect temporary recovery context
with the existing signing-secret boundary, encryption, short expiry and
principal/session binding; do not expose claims in links or introduce a
token store. Keep refreshed assertions current for subsequent resource-specific
OBO. Embedded Entra recovery stays with the portal's MSAL/bootstrap identity
boundary rather than silently switching to standalone OAuth. Anonymous
embedding cannot use recovery to acquire a delegated identity.

Manual sign-out alone was rejected because it can lose the required claims.
Transparent re-execution was rejected because tool/model work might already
have run. Local HTTP, SDK, MSAL and UI-boundary regressions must prove the
round trip without contacting Azure; they do not certify a tenant's live
Conditional Access policy.

## Consequences

Positive: the solution owns its integration, retains native source enforcement
and reuses existing infrastructure. No new long-lived service or credential
store is required. Search-token acquisition adds an OBO operation; downstream
source and group evaluation can add latency and preview-service costs.

Constraints: tenant consent, source licenses and source permissions remain
necessary. Native permission filtering changes previously permissive index
behavior and can expose missing ingestion metadata. Test ACL completeness
and revocation before admitting a corpus. Private networking must cover the
actual Search/source path, not just container connectivity.

## Adoption and recovery

Implement compatible UI, orchestrator and platform changes on feature branches
from develop, then validate them as one combination. Keep runtime source in
component repositories. Publish configuration with the matching consumers;
update manifest pins only to real reviewed component commits/tags.

The user explicitly selected local validation now and deferred Azure testing.
That is not two-user authorization evidence or release approval. No production
deployment, package/image publication or release is authorized by this ADR.

Updating `develop` must not deploy the orchestrator to Azure automatically.
Its dev deployment workflow is manually dispatched only. Maintainer-authorized
protected-contract adoption preserves behavioral checks and does not authorize
a deployment or permanently weaken the quality gate.

Rollback restores the compatible UI/runtime/configuration combination without
removing ACLs or granting app-only source access. Since the baseline contains
the gap, rollback suspends protected hosted retrieval rather than claiming
the old combination supports it.

## Compliance verification

- Both actual hosted adapters propagate the delegated token without second OBO.
- Missing/invalid credentials and source failures never become successful empty
  retrieval or a credential-free retry.
- Concurrent/alternating callers cannot share credentials or results.
- Native index permissions and existing conversation restrictions remain active.
- Responses persistence, telemetry and error paths retain no token values.
- Downstream authentication challenges reach explicit UI recovery without
  becoming model content, anonymous retries or automatic turn replay.
- Existing classic, streaming, citations and download authorization regressions
  pass; template and lifecycle contracts remain cross-platform equivalent.
- Before release, two independently signed-in users prove allow/deny per
  protected source, including citations/downloads, in Basic and isolated modes.

## Documentation impact and review trigger

Update the central `Azure/AI-Landing-Zones` authentication, agent tools, hosted,
retrieval, configuration and troubleshooting pages with the compatible release.
Do not publish implementation candidates as latest-shipped support or remove
real consent/preview limitations. Revisit this decision when managed Toolbox
delegation becomes compatible, a source's token contract changes, or permission
freshness/private-network tests reveal a gap.

## References

- [Hosted runtime and custom headers](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-contract)
- [Application-managed OBO forwarding](https://learn.microsoft.com/azure/foundry/agents/how-to/use-on-behalf-of-flow)
- [Knowledge-base query permissions](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-retrieve)
- [Native query-time ACL/RBAC](https://learn.microsoft.com/azure/search/search-query-access-control-rbac-enforcement)
- [Authenticated hosted Toolbox](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/use-toolbox-hosted-agent)
- [Source-specific managed delegation](https://learn.microsoft.com/azure/foundry/agents/how-to/configure-user-delegation)
