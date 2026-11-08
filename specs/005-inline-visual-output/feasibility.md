# Native Presentation Feasibility Gate

**Status**: Minimal local and live Hosted transport/history proof passed on 2026-11-07. Product authorization/lifecycle, Durable, and UI gates remain unverified. This is not an end-to-end feature quickstart.

## Purpose

Prove that the existing Responses protocol can carry a validated table/chart presentation, persist the same values in native state, and restore them after reopening, without introducing a second transcript store or weakening authorization.

The first experiment uses fixed synthetic output, not model-generated chart data. This isolates transport and history from retrieval/model variability. It does not prove the complete feature or all acceptance criteria.

## Executed Minimum Proof

The deterministic implementation uses official `Agent` over a public `BaseChatClient`, hosted by `ResponsesHostServer(..., history_source="agent_server")`. Its standard `output_text` contains a versioned application JSON envelope with a markdown fallback, table, and line chart. It neither calls a model/tool nor adds a custom protocol event.

| Gate or check | Observed result |
| --- | --- |
| A: local exact-SDK transport | Passed. Standard text deltas and completed output contain identical fixture data. |
| Local restoration and source guard | Passed with a fresh host/client while fixture execution was disabled. One source call total. |
| Local negative/lifecycle checks | Synthetic other partition returns 404, malformed response ID returns 400, and native deletion followed by read returns 404. These are not product authorization evidence. |
| B: minimal live Hosted transport/history subset | Passed. Active code-deployed version 3 streamed the fixture. Fresh-client response retrieval and conversation-item listing restored the identical JSON, including decimal strings `10.125`, `12.500`, and `9.750`. |
| B: product owner/deletion/retention checks | Not exercised. No BFF, trusted cross-user test, or live deletion/retention proof. |
| C: Durable | Not exercised. |
| D: Chainlit | Not exercised. No rendered chart/table UI claim. |

Live reads must use the **agent-scoped OpenAI protocol base** returned by deployment. Reading the same response through the project-wide client returned 403, and project-wide conversation listing returned 404. Correct agent-scoped response and conversation reads passed. These routing errors are not evidence of cross-user access control.

Only a public-access Foundry account/project and the minimal Hosted agent were created. No model deployment, ACR, Search, Cosmos, App Configuration, VNet, or private endpoint was added. The Hosted compute session was stopped after the final history reads and verified `idle`, preserving its filesystem and the proof resources.

The local environment resolved the original component dependencies. The deployed fixture deliberately narrowed direct dependencies to `agent-framework-core==1.24.0` and `agent-framework-foundry-hosting==1.0.0b261030`, with their resolved transitive dependencies. Core server versions were `azure-ai-agentserver-core==2.3.0` and `azure-ai-agentserver-responses==2.4.0`. This is a narrow proof, not full component dependency parity.

Two remote builds failed using an index-bound lock. A public-index regeneration also failed locally with a TLS handshake error. Exporting pinned `requirements.txt` without index/artifact URLs and excluding local uv/pyproject configuration from the code package produced a successful remote build. No lock URLs or SDK internals were patched.

Implementation, probe scripts, raw live stream, and machine-readable local/live comparisons persist in the session's `responses-proof` artifacts. Private resource identifiers stay there, not in this repository. Following the maintainer's instruction to continue planning, remaining product gates are implementation acceptance requirements, not prerequisites for generating the design.

## Preconditions

- Read exact component dependency files, supported Python versions, and current native client/host code at the manifest pins.
- Use isolated local environments and the existing dependency manifests. No global package changes, invented SDK hooks, or editable unpublished SDK dependency.
- Identify an official output/state API supported by the exact installed Foundry hosting package. Capture its documented signature and exact package source. An upstream-main example alone does not pass.
- Use synthetic data only. Do not persist tokens, invocation identity, raw personal data, or private validation environment names in evidence.
- The maintainer authorized a minimal, low-cost proof in a new resource group in the requested subscription on 2026-11-07. Resolve that subscription by its supplied name and keep identifiers in local session evidence, not committed product documentation. This does not authorize a full Landing Zone, production changes, or a different protocol.
- Bound the investigation to one working day of engineering effort and one minimal, approved native test deployment. If the supported carrier is still unavailable at that point, return the blocker, do not expand into an alternative platform.

## Gate A: Local Exact-SDK Probe

1. Record installed Python and all native hosting/Responses/agent-framework package versions.
2. Find the official way to emit structured application output and read it back. If none is documented/supported, stop and request upstream clarification. Do not inject extra event bytes, override private SDK internals, or misuse refusals/citations/tool events.
3. Supply a synthetic turn with markdown text and two hydrated blocks: a table and a line chart sharing the same authorized fixture.
4. Capture the standard Responses event/output sequence and verify that text still follows the existing contract.
5. Exercise a new proof client against that output. An ordinary `output_text` containing a versioned application JSON envelope is a valid candidate if produced deterministically from the fixture, not copied by a model. This preserves Responses but deliberately requires a new reader. Arbitrary custom events or fake tools are not candidates.

**Pass**: Exact installed SDK exposes a supported carrier and local native event/output parsing preserves both presentation and ordinary text. This permits the live probe, not a release claim.

**Fail**: No supported API, private hook required, protocol replacement, or text completion regresses. Record the API limitation and stop.

## Gate B: Native Hosted Persistence and Owner Check

Using an explicitly approved minimal Hosted test publication:

1. Send the fixture through the existing Responses endpoint and authenticated BFF user path.
2. Verify the receiving client obtains the same column types, numeric values, chart categories/points, agent attribution, source references, and order.
3. Close the client/session. Reopen using the actual owner-gated native history path from a fresh client.
4. Compare restored presentation content with the original accepted payload. Instrument the fixture source so any re-query fails the proof.
5. Attempt read/reopen with a different synthetic user and with an arbitrary conversation/response ID. Neither presentation nor text may be exposed.
6. Verify a supported new reader exposes the markdown fallback. The maintainer explicitly removed unchanged older-client compatibility from acceptance on 2026-11-07.
7. Apply the existing supported deletion/retention operation to the test conversation and confirm visuals are not independently retained or readable. If the current product lacks the necessary deletion behavior, record that gap instead of claiming it passed.

**Pass**: The official native path stores and restores identical values with no tool re-query, no duplicate transcript storage, correct negative authorization, and compatible text delivery.

**Fail**: The platform strips structured content, historical reads omit it, a side store is required, or owner/deletion behavior is missing or unsafe. Stop enablement/full delivery and return the exact missing capability. Do not silently change the approved boundaries.

## Gate C: Durable Native Output/Restoration

Use the official durable worker/client and an approved isolated test task hub with exact matching dependency pins. Do not mix incompatible state/protocol versions.

Repeat the fixed fixture, fresh-client native history/progress/result read, source-query guard, authorization negatives, and existing lifecycle check. Validate the actual UI product projection rather than the SDK's structured-value example alone.

**Pass**: The product restores the accepted presentation from durable native state with the same owner and lifecycle semantics.

**Scope**: This does not prove Hosted parity, cross-version replay, exactly-once effects, private-network behavior, or durable SLA.

## Gate D: Small Web Smoke

After a supported carrier exists, render a fixed presentation using Chainlit 2.12.0's build-free custom-element facility.

Verify one table and local SVG chart in standalone and embedded views, light/dark themes, keyboard access, numeric copy precision, and a follow-up sent by documented `sendUserMessage`. Interactions must create a normal user turn, not a direct tool call. Confirm no new external resource request or CSP relaxation.

**Pass**: All four view/theme combinations show readable output and the normal follow-up path works.

**Scope**: This is a feasibility smoke, not performance/user-study or full FR-001 through FR-022 acceptance.

## Existing Platform Regression Commands for Later Implementation

These are observed entrypoints, not commands executed by this planning invocation. Run from each owning checkout after the relevant code exists.

From the umbrella root on Windows:

```powershell
python -m pytest tests\test_app_settings_resolution.py tests\test_appconfig_intent.py tests\test_native_application.py tests\test_infra_provider_hooks.py --quiet
pwsh -NoProfile -File .\infra\tests\Invoke-OfflineContracts.ps1
```

From `infra\terraform`:

```powershell
terraform fmt -check -recursive
terraform init -backend=false -lockfile=readonly
terraform validate
terraform test
```

The existing `.github/workflows/infra-validate.yml` also runs Bicep build/lint and the full umbrella pytest suite on Windows/Linux. Preserve its explicit tool/module pins. Follow its platform-appropriate commands instead of assuming Windows PowerShell exercises shell hooks.

Exact component CI commands and environment prerequisites are now recorded in [quickstart.md](quickstart.md) from pinned source inspection. They cover existing regressions. Future feature acceptance scenarios are not represented as already existing test commands.

## Evidence and Exit Decision

Record:

- Selected existing target and separate deployment authorization, without private names in committed evidence.
- Exact component commits, installed package versions, immutable test image digest, and native protocol version.
- Official carrier/state API references and accepted synthetic payload.
- Live and reopened payload comparisons, source-query counter, new-reader fallback result, authorization negatives, and deletion result.
- UI smoke results, duration/timeouts, failures, and unverified private-network/provider scenarios.

The passing minimum carrier/history proof permits the authorized Phase 1 design. All remaining product gates must pass before enablement or declaring full feature acceptance. Record individual statuses honestly. No silent switch to Invocations, custom proxy, UI Cosmos transcript storage, or Hosted/Container Apps-only scope is authorized.
