# Quickstart: Agent Landing Zone validation

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)

This guide lists runnable scenarios that prove the feature works end to end.
It references the contracts and data model instead of repeating them:

- Deployment verbs, steps, binding states, and failure messages:
  [contracts/azd-lifecycle.md](./contracts/azd-lifecycle.md)
- Application definition format:
  [contracts/app-definition.schema.json](./contracts/app-definition.schema.json)
- Platform outputs published to App Configuration:
  [contracts/platform-outputs.schema.json](./contracts/platform-outputs.schema.json)
- Names, renames, and the naming scan:
  [contracts/naming-map.md](./contracts/naming-map.md)
- Entities and deployment options: [data-model.md](./data-model.md)

## Prerequisites

- An Azure subscription where you can create resource groups and assign roles.
- Azure Developer CLI (`azd`), Azure CLI (`az`), Python 3.12+, and Git.
- `azd auth login` and `az login` against the same tenant.
- A **fresh clone** of `Azure/agent-landing-zone` (the renamed umbrella repo).
  Before the rename lands, use this feature branch.
- A **new** `azd` environment for every scenario. The release supports new
  deployments only (FR-004).

Each scenario shows PowerShell first and sh second. Use one validation
environment per scenario and delete it afterwards with `azd down --purge`.

## Acceptance by release

### Integrated-source and private-hosted evidence (2026-10-10)

The acceptance fixes are integrated into `develop`: platform #774 at
`dd4c8978db94ff56d4dbbdb30c8c9168625b75a3`,
Azure/agent-app-ui#144 at `ec18a7330982b188d1c1e6da9157230a20865242`,
and Azure/AI-Landing-Zones#149 at
`1f7c1d707abe99468c6c42f4a26c39f0443b76a8`. No repository rules were changed.
The first UI merge-push check still selected the old protected evaluator from
`github.event.before`; it is not evidence that the newly adopted gate passed.
The reference Azure/agent-app-ui#145 subsequently passed all nine checks
against the new protected `develop` base
`ec18a7330982b188d1c1e6da9157230a20865242` in CI run `38066592411`
at head `d41aa8da85754a19321f5d5004831754f6d59683` and merged at
`e93b3d3e0cf36d8e92e8f9d0c6d1c911aa0f715f`. This supplies positive
new-base gate evidence; the earlier merge-push check does not.

T098's custom hosted isolation and RBAC criteria are now verified:

- Repeated runtime checks confirmed hosted version 7 is active, uses the
  previously recorded immutable image digest, resolves inside its private
  spoke, and returns the exact project greeting through the Responses endpoint.
  The Container App sample also returned its exact live platform contract.
  These deployments retain corrective source
  `0ab4665db29fbfac6bc5a41a372c0b64df32b73e`.
- All 13 private endpoints have successful provisioning and approved
  connections. Foundry, registry, App Configuration and the canonical vault
  have public network access disabled. Foundry local authentication and the
  registry admin account are disabled; the canonical vault uses RBAC.
  App Configuration local authentication remains enabled as declared by the
  foundation template; this audit does not claim otherwise.
- The actual version-7 runtime principal has exactly five grants, including
  inherited assignments: App Configuration Data Reader on its store, AcrPull
  on its registry, Key Vault Secrets User on the canonical vault, and
  Cognitive Services User plus Cognitive Services OpenAI User on its Foundry
  account. No additional grant or broader scope was found.
- A dedicated unassigned principal obtained a valid Foundry resource token.
  Its request to the actual private custom Responses endpoint was rejected
  with structured HTTP 403 identifying an authorization failure. This is
  not an expired-token or anonymous-request test.

Local receipts are retained under `.azure/` as
`s7-custom-runtime-check-20261010.json`,
`custom-hosted-control-audit.json`, and
`custom-hosted-rbac-negative-20261010.json`. They contain no credential values.
The integrated contract suite passed 118 tests and 74 subtests.

The private trio's non-placeholder UI, Entra provider and login redirect,
ingestion health, and anonymous panel rejection were rechecked successfully.
The evaluation OAuth credential was renewed through encrypted transport into
Key Vault with a matching one-day expiry. None of these checks proves user
login, OBO, grounded answers, citations or document-level authorization.

On 2026-10-11 the VPN blocker was resolved using a fresh gateway-exported
profile with scoped private DNS configuration. The client accepted and
connected the profile without manual trust or authentication fields. All
three spoke routes and ten DNS suffix rules were verified; the frontend
resolved to its private address and returned HTTPS 200. The receipt is
`.azure/vpn-import-verified-20261011.json`.

The evaluation OAuth credential was renewed with a matching one-day vault
expiry. The frontend initially generated an HTTP callback behind HTTPS
ingress. Setting the supported `CHAINLIT_URL` to the canonical HTTPS origin
corrected the actual Entra redirect; the replacement revision is healthy and
receives all traffic. Central operator guidance is recorded in
Azure/AI-Landing-Zones#150, merged at `f8e3c881`. The genuine Entra sign-in page is
reachable, but a completed user session has not been verified. The earlier
delegated-token request returned `AADSTS65001` (`consent_required`,
`InteractionRequired`); an HTTPS redirect does not prove consent or OBO.

T035, T085 and T093 remain incomplete. Fresh stock one-command sample
deployments and complete classic/hosted conversational acceptance must not be
inferred from the successful private custom deployment, control-plane or
health checks. No authenticated grounded response, citations or
document-level authorization result has been established by these repairs.

Fresh one-command sample attempts at source `ef7417a` failed the embedding
quota gate: the region had 340/350 Standard units allocated, leaving 10, while
each evaluation environment requested 20. No existing allocation was credited
to a new account. Live negative validation also exposed a framework ordering
defect: azd created an empty resource group before the `preprovision` hook
rejected the invalid definition. That does not pass S5's strict no-write
criterion. Source `9b6db1a` adds read-only `preup` schema and binding checks;
12 focused tests passed using both PowerShell and Bash.

The subsequent actual Azure regression at exact source `9b6db1a` passed all
three `azd up` negatives: missing ID, unsupported profile and changed binding
fail in `preup`, leave complete environment files unchanged, and create no
resource group. Delayed Activity Log checks show no writes. The expanded
exact-source suite passed 51 tests and 71 subtests. This verifies S5.

Fresh S7 attempts then used evaluation embedding capacity 5 per mode, without
changing published defaults. Both quota gates and composed provision previews
passed, but each single `azd up` failed at the additional Foundry Search service
with `ServiceQuotaExceeded`: 12/12 Standard Search services were already used.
No fresh application runtime was deployed. Neither run allocated new model
deployments; embedding usage remained 340/350. Receipts are retained in
`.azure/t085-corrective-20261011/`, including `negative-results.json`,
`exact-source-tests.json`, `capacity-gate.json` and `final-audit.json`.

These attempts left partial billable foundations (57 and 56 resource inventory
entries), not empty groups. No cleanup or quota increase was performed. No
existing resources, SKU changes, disabled Search, split recovery or public
access were substituted for fresh one-command proof. Fresh S7 also retains
operator-owned reverse VPN peering and authoritative private DNS prerequisites.
T085 and T093 remain open; S5 success does not establish S7 or user acceptance.

### Latest corrective-source evidence (2026-10-09)

Both private custom-sample root `azd deploy` executions passed at exact source
`0ab4665db29fbfac6bc5a41a372c0b64df32b73e`, using the checked-in sample service
YAML. Evaluation-only source pins were restored after execution. A separate
guest check verified both complete deployment receipts and the exact checkout
source; the temporary deployment script was removed.

The hosted hook first failed because its verified runtime identity lacked four
declared profile grants. The existing evaluation Owner reconciled AcrPull,
KeyVaultSecretsUser, CognitiveServicesUser and CognitiveServicesOpenAIUser at
the resource scopes selected by the repository resolver. The runner did not
receive Owner or role-management privileges. A subsequent reconciliation
created no grants, and the unchanged deploy retry succeeded.

Independent runtime probes then verified:

- The Container App's latest revision was latest-ready, used an immutable
  custom-image digest and resolved only to its private spoke. Its HTTPS response
  exactly matched the live platform contract and actual component identity.
- Hosted version 7 was active with an immutable custom-image digest. The project
  endpoint resolved only to its private spoke; a managed-identity Responses
  invocation returned the exact expected project greeting.

These results do **not** establish source provenance solely from the deployed
digest, a fresh stock one-command `azd up`, delegated-user OBO, grounded answers,
citations or positive/negative document authorization. At that checkpoint,
T035, T085, T098 and T093 remained open. The later T098 audit above supersedes
its isolation/RBAC status; successful custom samples must not be substituted
for the bundled conversational stack.

| Release | Scenarios that must pass |
| --- | --- |
| `v4.0.0-preview.1` | S1 (steps 1, 2, 4), S3 (step 1), S4 (steps 1–3), S6; SC-007, SC-008 |
| `v4.0.0` | All scenarios S1–S7; SC-001–SC-007, SC-009 |

## S1 — Full stack with the default trio (US1)

```powershell
git clone https://github.com/Azure/agent-landing-zone.git; cd agent-landing-zone
azd env new <env-name>
azd up
```

```sh
git clone https://github.com/Azure/agent-landing-zone.git && cd agent-landing-zone
azd env new <env-name>
azd up
```

Expected outcome:

1. Provisioning and deployment finish without manual steps.
2. The UI, orchestrator, and ingestion apps run, and a test question returns a
   grounded answer with citations.
3. *(v4.0.0 only)* No resource, App Configuration key, label, container image,
   or UI text contains "gpt-rag" in any spelling (see
   [naming-map.md](./contracts/naming-map.md)).
4. The UI shows the "Agent Landing Zone" name and visual identity.

Repeat S1 with the orchestrator in hosted-agent mode, using the parameter
documented in [azd-lifecycle.md](./contracts/azd-lifecycle.md) (FR-024).

## S2 — Infrastructure only, then the application (US2)

```powershell
azd env new <env-name>
azd provision
azd deploy
```

```sh
azd env new <env-name>
azd provision
azd deploy
```

Expected outcome:

1. `azd provision` creates the foundation and placeholder Container Apps and
   pushes zero application images (SC-005).
2. App Configuration (label `agent-lz`) contains `AGENTLZ_PLATFORM_OUTPUTS`
   and its flat keys. The JSON value validates against
   [platform-outputs.schema.json](./contracts/platform-outputs.schema.json).
3. The environment is bound to the trio.
4. `azd deploy` then deploys the apps, and S1's expected outcomes hold.

Negative check: in a new environment, run `azd deploy` before
`azd provision`. It must fail before any change, with the "run azd provision
first" message from [azd-lifecycle.md](./contracts/azd-lifecycle.md).

Evidence (preview.2, a fresh Basic deployment in uksouth,
`NETWORK_ISOLATION=false`, ACR remote build):

- `azd provision` succeeded. The Container Apps ran placeholder images and
  no application image was pushed before `azd deploy`.
- App Configuration label `agent-lz` holds the platform outputs. Components
  read `agent-lz` first and fall back to `gpt-rag` (R14 dual-read,
  preview.2 tags).
- `azd deploy --no-prompt` built and deployed the trio at the manifest pins
  (ui `v3.0.0-preview.2`, orchestrator `v5.0.0-preview.2`, ingestion
  `v3.0.0-preview.2`). Smoke test: UI `/` 200, ingestion `/healthz` 200,
  orchestrator `/docs` 200. The orchestrator has no health route.
- The negative check is covered by `tests/test_provision_only.py` (T037).
- Pin rules found during validation: `app-definition.json` `source.commit`
  must equal the manifest pin, and each sibling component checkout's HEAD
  must equal its pin, or preDeploy stops before any change.
- Known environment issue: subscriptions whose policy disables Key Vault
  public access return 403 to postProvision secret writes when
  `NETWORK_ISOLATION=false`. Run from an allowed network, or use
  network isolation.

## S3 — Documentation and landing page (US3)

1. Open the repository README. It is a short landing page that links to the
   central documentation and lists the deployment options (FR-018). The preview
   lists only the options that ship in the preview.
2. *(v4.0.0)* The central documentation covers every deployment option, both
   orchestrator modes, and custom applications (FR-019).

## S4 — Short links (US4)

1. Every product short link listed in the documentation resolves to an Agent
   Landing Zone page.
2. Legacy GPT-RAG short links redirect or show a clear move notice.
3. A link that is not yet migrated is recorded as a known item in the release
   notes. It does not block the release (FR-020).

Evidence after the repository rename (`curl -sI`):

| Legacy URL | Result |
| --- | --- |
| `github.com/Azure/GPT-RAG` | 301 → `Azure/agent-landing-zone` |
| `github.com/Azure/gpt-rag-ui` | 301 → `Azure/agent-app-ui` |
| `github.com/Azure/gpt-rag-orchestrator` | 301 → `Azure/agent-app-orchestrator` |
| `github.com/Azure/gpt-rag-ingestion` | 301 → `Azure/agent-app-ingestion` |
| `azure.github.io/agent-landing-zone/` | 200 |
| `azure.github.io/GPT-RAG/` | 404 (GitHub Pages does not redirect; `Azure/azure.github.io` is archived, so a redirect page needs an org admin to unarchive it, or use an aka.ms link) |
| `aka.ms/gpt-rag` | 200, redirects to `github.com/Azure/agent-landing-zone` |
| `azure.github.io/AI-Landing-Zones/agent-landing-zone/` | 200 (central docs section, 11 pages, Azure/AI-Landing-Zones#141) |
| Legacy `docs` branch pages | All 44 pages carry a moved notice pointing to the central section (#756) |
## S5 — Validate an application definition (US5)

```powershell
python -m config.appdefinition --validate samples/custom-app/containerapp
python -m config.appdefinition --validate samples/custom-app/hosted
```

```sh
python -m config.appdefinition --validate samples/custom-app/containerapp
python -m config.appdefinition --validate samples/custom-app/hosted
```

Expected outcome:

- A valid definition prints a success message and exits with code 0.
- In a copy of the sample, remove a required field or request a capability
  profile that does not exist. The command exits with a non-zero code and
  prints the JSON pointer to the bad field (FR-015d, FR-016).

## S6 — Naming scan (FR-002, FR-003)

```powershell
python -m pytest tests/test_naming_inventory.py -q
```

```sh
python -m pytest tests/test_naming_inventory.py -q
```

Expected outcome: the test passes with no `gpt-rag` matches outside the
allow-list in [naming-map.md](./contracts/naming-map.md). In
`v4.0.0-preview.1` the allow-list still holds the temporary Phase 2 entries;
in `v4.0.0` they are gone, so the same command proves the full rename.

## S7 — Custom application, both hosting modes (US5, SC-009)

```powershell
azd env new <env-name>
azd env set AGENTLZ_APP_DEFINITION samples/custom-app/containerapp
azd up
```

```sh
azd env new <env-name>
azd env set AGENTLZ_APP_DEFINITION samples/custom-app/containerapp
azd up
```

Replace the all-zero component source pin with the actual checkout HEAD before
deployment. Run this once with `samples/custom-app/containerapp` and once in a
separate environment with `samples/custom-app/hosted`. The definition folder
contains `azure.yaml`; `components[].path` selects its service source folder.

Expected outcome:

1. One `azd up` from a fresh clone deploys the sample. In hosted-agent mode
   this follows the hosted path in
   [azd-lifecycle.md](./contracts/azd-lifecycle.md), including the smoke test.
2. The sample receives only the capability profiles it declared (FR-015e).
3. The environment is bound to the sample definition.

Negative checks. Both must fail **before any Azure change**:

- Point `AGENTLZ_APP_DEFINITION` at an invalid definition and run `azd up`.
  The output includes the JSON pointer to the error.
- On the bound environment, select a definition with a different application
  `id` (for example, point it at the trio)
  and run `azd up`. The output reports a binding mismatch and says to create a
  new azd environment (FR-015g).

Re-running `azd up` with the same definition is idempotent (FR-016).

## Acceptance status (2026-10-09)

UI `v3.2.1` and umbrella `v4.2.2` were published. Their publication does not
close the outstanding runtime acceptance scenarios:

- Classic foundation resources were provisioned, but post-provision governance
  failed with Key Vault `ForbiddenByConnection`: public access was disabled
  and the validation vault had no private endpoint. Governance subsequently
  passed from the jumpbox over approved recovery private endpoints, using
  the exact release source and managed identity. Continuity, Container Apps
  and Search setup also passed. Application deployment completed, but the
  latest frontend revision is unhealthy with the same vault connection denial.
  An HTTP 200 came from the old placeholder, not a healthy application.
  Authenticated grounded answers and ingestion startup remain unverified.
- Hosted-panel foundation, private governance recovery, continuity, Container
  Apps and Search setup passed. The pinned hosted image was built and resolved
  to an immutable digest. The release's quota preflight treats an existing
  allocation as a new request. Its corrective branch now passes both real
  preflight gates, crediting only verified matching deployments and checking
  incremental capacity. That does not prove the hosted deploy handoff.
  The separate network-isolated foundation and full post-provision hook
  completed from the jumpbox. Owner recovery reconciled the already-declared
  native Cosmos grants; the temporary management permission was then revoked.
  The private pinned image also built successfully after firewall denies
  identified the frontend lockfile's Azure Artifacts feeds. The existing
  application-specific build allow-list now includes those four feeds and their
  verified blob CDN, restricted to build-subnet HTTPS. The immutable image
  provenance was synchronized without credentials, and the actual hosted
  handoff preview passed.
  The private Owner ARM handoff and full managed post-provision hook passed.
  Project-scoped Foundry User resolved the runner's agent-authoring denial after
  propagation. Owner reconciled the three discovered runtime grants without
  granting the runner role-management permissions. Normal root deployment then
  completed, and a separate managed-identity greeting passed the strict terminal
  Responses validator. These are corrective-source results, not pristine release
  acceptance or delegated-user retrieval evidence.
  Initial UI and ingestion startup failed because OAuth configuration was
  absent. A dedicated single-tenant evaluation registration now exposes the UI's
  own API scope. Its short-lived credential was delivered encrypted to the
  private runner, stored only in Key Vault, and referenced in App Configuration
  with label `agent-lz`; tenant credential-lifetime policy was preserved.
  A persistent Key Vault-backed Chainlit signing key was also configured.
  Both intended pinned revisions are now Healthy/RunningAtMaxScale, match
  latestReadyRevisionName, and receive 100% of traffic; placeholders no longer
  serve the application. Private probes verified the real UI, enabled Entra
  provider, correct login redirect, ingestion health, and HTTP 401 on
  unauthenticated panel data access. Authentication has not been bypassed.
  Actual user login/consent, user-delegated OBO, grounded answers, citations,
  and positive document authorization remain unverified. An OAuth resource
  token diagnostic did not invoke the agent and is not OBO acceptance.
  A subsequent negative runtime test acquired a valid Foundry resource token
  for the dedicated evaluation service principal, which has no project role.
  The actual hosted invocation returned a structured HTTP 403 authorization
  rejection. The project endpoint resolved entirely inside the evaluation
  spoke. All private foundation endpoint connections were Approved/Succeeded;
  Foundry, ACR, and Key Vault public access remained Disabled, ACR admin
  authentication remained disabled, and Key Vault RBAC remained enabled.
  Runtime grants were rechecked at their exact scopes: App Configuration
  Data Reader on the store, OpenAI User on the model account, and Secrets
  User only on AUDIT-HMAC-KEY. This is hosted-principal isolation evidence,
  not delegated-user or document-authorization acceptance, and does not
  replace deploying the custom hosted sample.
- The evaluation VPN Gateway was provisioned and protected with `keep=true`
  and a deletion lock. Hub/spoke peerings are Connected with gateway transit.
  Private DNS and managed-identity governance calls succeeded from the actual
  jumpbox. Client VPN authentication and full delegated-user hosted runtime
  acceptance remain unverified.
- Classic runtime connectivity cannot be repaired by adding an endpoint to its
  current Container Apps environment: its `vnetConfiguration` is null and the
  classic resource group has no virtual network. The existing recovery
  endpoints make services reachable from the private jumpbox, not from apps
  in the Azure-managed network. Azure does not support changing that
  environment's network type after creation
  ([Azure Container Apps networking](https://learn.microsoft.com/azure/container-apps/networking)).
  Recovery requires a separate
  VNet-integrated environment; public Key Vault access was not enabled and
  existing apps/resources were not deleted or silently replaced.
- A fresh S7 foundation cannot use the current default Standard embedding
  allocation unchanged: live westus3 usage is 300 of 350, leaving 50 while
  the default new deployment requests 100. Existing-allocation credit is
  valid only for an actual matching deployment, not a fresh account. Both
  sample definitions validate, and the focused schema, roles, binding,
  composition, and custom-hook suite passed 43 tests and 28 subtests.
  Those checks do not constitute a successful one-command S7 deployment.
- Separate Container App and hosted sample evaluations now use 20 new
  Standard embedding units each in evaluation-only parameter copies. Published
  defaults are unchanged. Both real preProvision gates and composed previews
  passed with distinct nonoverlapping spokes and independent application
  bindings. Initial provisioning failed on each Container Apps private endpoint
  with provider `InternalServerError`, not a proven naming conflict. Retrying
  only the exact failed endpoint module, with unchanged exported parameters and
  a no-deletion what-if, recovered both endpoints to Succeeded/Approved.
  Reverse VPN gateway-transit peerings and direct runner-to-spoke peerings are
  Connected. Both normal root provisioning resumes completed successfully,
  explicitly deferring private configuration rather than claiming application
  readiness. Exact new-spoke private A records were added, without replacing
  existing records, to the evaluation runner's already-linked DNS zones.
  From the actual jumpbox, both samples' App Configuration, Key Vault, ACR,
  and Foundry endpoints resolved only into their corresponding private spokes
  and returned HTTPS responses with TLS verification. These are connectivity
  probes, not authenticated application acceptance. Resource-scoped runner
  configuration roles were reconciled without granting Owner or role-management
  permissions. The Container sample's full root postProvision subsequently
  passed from the pinned corrective guest source: platform outputs, governance,
  continuity, Foundry, Container Apps, and Search completed without deferral.
  The first capability-role attempt correctly rejected the runner's lack of
  role-management privileges; the parent Owner reconciled only the declared
  component grants before the successful unchanged hook retry. The hosted
  sample's full root postProvision also passed from the same pinned source,
  with explicit guest success markers and no guest stderr for both samples.
  Private image building then reached the dedicated ACR pool but failed on
  the Docker Hub base-image pull: `registry-1.docker.io` was absent from the
  build-subnet HTTPS allowlist. This is a build dependency, not a reason to
  enable public registry access or bypass the firewall. Extending only the
  build-subnet rule with the three documented Docker Hub HTTPS endpoints,
  persisted through evaluation-only `additionalAcrTaskBuildFqdns`, recovered
  both builds. Both images were built from the exact corrective source using
  their own private ACR `build-pool`; immutable image digests and an explicit
  guest completion marker were returned with no guest stderr. This separate
  prebuild is not proof of the stock one-command S7 deployment.
  Both samples subsequently packaged and deployed using evaluation-only
  child YAML with immutable `image` and `docker.imagePassthrough: true`.
  The Container App uses its existing managed identity for private ACR pulls;
  its latest revision is latest-ready and matches the built digest. Its `/`
  response, reached through private DNS, exactly matches live
  `AGENTLZ_PLATFORM_OUTPUTS` with label `agent-lz`, schema version 1 and
  `network.isolated=true`. A TLS-verified local VPN probe also received that
  contract using explicit DNS, not automatic OS resolution. The published
  identity map was initially empty despite the deployed app identity.
  The corrective publisher now discovers the actual Container App client ID.
  Two consecutive publications returned the same `web` identity in both the
  JSON document and its flat key; a subsequent private `/` response exactly
  matched that identity-bearing live contract. The guest temporarily staged
  the corrected publisher/resolver and restored its original source afterward.
  Missing endpoint aliases in this evaluation's copied azd metadata were
  explicitly hydrated from the schema-validated existing App Configuration
  document, not guessed. This proves the correction against the live resources,
  not a pristine published-release or stock one-command S7 run.
  The hosted sample initially failed activation because the actual Foundry
  project identity lacked AcrPull. An exact-registry grant recovered version
  2 to active with the built digest. Its actual runtime identity then received
  App Configuration Data Reader only on its configuration store. A real
  Responses invocation from the managed runner resolved the project into its
  private spoke and returned a completed assistant response containing the
  exact project endpoint published in live platform outputs, not `unknown`
  or `unavailable`. The explicit runtime-check marker and empty guest stderr
  were verified. This proves private managed-identity sample invocation,
  not user-delegated OBO, grounded answers, document authorization, repeated
  provisioning, or the original remote-build sample YAML.
  Repeating both child overlay deployments preserved their immutable image
  digests. The Container App's new revision
  `ca-ddzasx67ghev4-web--azd-1791574208` became latest-ready, and its repeated
  private response again exactly matched live platform outputs. The hosted
  deployment reused active `sample-hosted-agent` version 2 and the same runtime
  identity; its repeated Responses check again returned the exact live project
  endpoint. All 13 hosted private endpoints were Succeeded/Approved; Foundry
  public access and local authentication, and ACR public/admin access, remained
  disabled. These checks prove repeated child deployment, not repeated full
  root provisioning or the stock one-command S7 flow.
  The identity correction passed 413 tests and 500 subtests, with 4 skips;
  the central documentation update `0abad14` is in Azure/AI-Landing-Zones#148.
  The evaluation VPN client reached the existing firewall DNS proxy and
  received the expected private addresses for all three evaluation spokes.
  The updated client profile preserves authentication and split tunneling;
  automatic OS resolution still requires profile reimport and reconnect.
- Validation found directory-selection, custom-project working-directory,
  and hosted greeting-protocol defects. The corrective change passes
  598 tests and 591 subtests (4 skipped), but those offline results do not
  establish a successful S7 Azure deployment or retroactively validate
  the published release.
- Read-only checks against the actual private environment binding accepted
  the exact-release default definition, rejected a valid different application
  ID with exit 2, and rejected an unsupported capability with exit 1. The
  environment-file hash was unchanged. These negatives do not establish
  a successful custom-application deployment or repeated live provisioning.
- Validation also found false-success logging when an Entra-only Foundry
  account rejects evaluation API keys, and a missing Cosmos database-name
  handoff for the administrative panel. The corrective branch respects disabled
  local authentication and reads published database settings before assigning
  the unchanged container-scoped roles. Its live panel recovery created four
  narrow grants; these fixes are not in the published release.
- The pinned orchestrator still exposes the legacy `GPT-RAG Orchestrator`
  OpenAPI title. No branding acceptance or new component release is claimed.

The corrective shared custom-image flow in commit `a9214de` subsequently
built and deployed both samples using the checked-in service YAML rather than
a manually prepared image overlay. Each build used its existing private ACR
pool and returned an immutable image. Container digest:
`sha256:fb33898065127a48eab6e402cab4550b0eab72828899865f3d3e25771b43185a`;
hosted digest:
`sha256:ca213b38d82ae24ebbd01ba1f2597cec2c1b94a60f316cab3a684fc67a902243`.
The helper restored each original YAML; temporary helper staging was removed.
Evaluation definitions were temporarily pinned to verified guest source
`aae0a3c` and restored afterwards; missing metadata aliases still required
explicit evaluation hydration. This is corrective-flow evidence, not pristine
release or stock root-hook acceptance.

The resulting Container revision `ca-ddzasx67ghev4-web--azd-1791577126`
was latest-ready. Its actual private response on `10.252.2.11` exactly
matched the live platform contract, including the real `web` client ID.
Hosted version 3 was active with the exact new build digest and preserved
runtime principal `6e447da6-8aca-4f96-af56-e863aa0da041`. Its real private
Responses invocation on `10.253.2.33` returned the exact project greeting.
The combined runtime-check marker passed with empty guest stderr.
No new runtime role grant was needed. The final correction suite passed
432 tests and 500 subtests, with 4 skips; central guidance `1512486` is in
Azure/AI-Landing-Zones#148.

T035, T085, T098, and T093 remain open until their actual runtime outcomes
are captured. No network policy was disabled to obtain a passing result.

## Fallback check (R16)

If the hosted-agent automation misses the 2026-10-09 deadline, S7's
hosted-agent run is replaced with the manual procedure described in
[research.md](./research.md) R16. The schema, the validator (S5), the platform
outputs (S2), and the sample must still ship.
