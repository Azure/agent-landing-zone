# Contract: azd lifecycle

**Feature**: 002-agent-landing-zone-rebrand | **Requirements**: FR-011, FR-012,
FR-015a–h, FR-016 | **Research**: R7–R11, R13, R16

This contract defines what each standard `azd` verb does in Agent Landing Zone.
No new verbs or flags are added. Operators select behavior only through the
verb they run and through the `AGENTLZ_APP_DEFINITION` environment value.

## Inputs

| Input | Source | Default |
|---|---|---|
| `AGENTLZ_APP_DEFINITION` | `azd env set` | The built-in trio definition (`ui`, `orchestrator`, `ingestion`) |
| `AGENTLZ_APP_ID` | Written by `preProvision` (binding) | Unset until the first provision |
| `main.parameters.json` | Repository | Current topology parameters |
| `manifest.json` | Repository | Release pins (unchanged by the app definition) |

The app definition format is defined in
[app-definition.schema.json](app-definition.schema.json); semantic rules are in
[../data-model.md](../data-model.md).

## Verbs

### `azd provision` (infra only)

| Step | Hook | Action | Fails when |
|---|---|---|---|
| 1 | `preProvision` | Resolve the definition path and validate it (`python -m config.appdefinition --validate <path>`). | Schema error, unknown profile, unpinned source, missing local path, hook fields present, zero components, or no `azure.yaml` in the folder. |
| 2 | `preProvision` | Bind the environment: store `AGENTLZ_APP_ID` and the definition path. | The environment is bound to a different app id. |
| 3 | (Bicep) | Deploy the foundation from the pinned infra source. | Azure deployment error (reported by azd). |
| 4 | `postProvision` | Report the placeholder plan for `containerapp` components only (`python -m config.deployment.existing_images`). Existing published images are never reset. | Invalid definition or deployment mode. |
| 5 | `postProvision` | Assign capability-profile roles to each `containerapp` component identity (`python -m config.appdefinition --assign-roles`; idempotent). | Role assignment error, or the component's Container App or target resource cannot be resolved uniquely. |
| 6 | `postProvision` | Publish platform outputs to App Configuration (label `agent-lz`): the JSON key `AGENTLZ_PLATFORM_OUTPUTS` plus flat keys ([platform-outputs.schema.json](platform-outputs.schema.json)). | App Configuration write error. |

Outcome: a working foundation with zero application images (SC-005). Hosted
agents are not created at this stage.

### `azd deploy` (app only)

| Step | Hook | Action | Fails when |
|---|---|---|---|
| 1 | `preDeploy` | Guard: confirm the foundation and platform outputs exist. | Foundation missing → "run azd provision first". |
| 2 | `preDeploy` | Re-validate the definition and compare it with the binding. | Validation error or app id mismatch. |
| 3 | `preDeploy` | For each `containerapp` component: build (or take the pinned image digest), push to ACR, update the Container App. | Build, push, or update error. |
| 4 | `preDeploy` | For each `azure.ai.agent` component: run the hosted-agent path below. | Any step of the hosted-agent path. |

### `azd up` (full stack)

First runs `preup`: read-only definition validation and environment-binding
comparison (`python -m config.appdefinition --validate --check-binding`).
An invalid definition or mismatched application stops before azd's deployment
pipeline can initialize a resource group. It then runs `azd provision` and
`azd deploy`, with every step above in order.
With no `AGENTLZ_APP_DEFINITION`, it deploys the default trio exactly as the
current release does.

## Hosted-agent path (per `azure.ai.agent` component)

1. Use the component's child azd project (`<path>/azure.yaml`, for example
   `hosted-agent/azure.yaml`).
2. Run `prepareHostedDeployment.ps1` / `prepareHostedDeployment.sh` to render
   the agent definition from platform outputs. **Limitation (T079):** this
   step applies only to the bundled hosted orchestrator, because
   `config.deployment.hosted_prepare` builds the manifest-pinned orchestrator
   image. A custom `azure.ai.agent` component is deployed from its own child
   project: `azd deploy <name>` builds its image, or `source.imageDigest` is
   pinned through `AGENTLZ_IMAGE_DIGEST`.
3. Pin the image by digest.
4. Copy the parent `.azure` environment into the child project.
5. Run `azd deploy <service>` in the child project.
6. Run the smoke test and fail the deployment if it does not pass.

## Environment binding states

| State | Condition | Behavior |
|---|---|---|
| Unbound | No `AGENTLZ_APP_ID` | The first `provision`/`up` binds the environment to the definition's `id`. |
| Bound | `AGENTLZ_APP_ID` equals the definition's `id` | Normal operation; content changes within the same `id` are applied. |
| Mismatch | `AGENTLZ_APP_ID` differs from the definition's `id` | Fail before any change: "This environment is bound to app `<old>`. Create a new azd environment to deploy `<new>`." |

## Failure behavior (FR-016)

- Fail closed **before** any Azure change, with one actionable message.
- The `preup` guard enforces that boundary for `azd up`. Standalone
  `azd provision` can initialize its resource group before `preprovision`;
  run `azd hooks run preup` first when requiring the same no-write boundary.
  A rejected definition after an empty resource-group write is not strict
  no-Azure-change acceptance evidence.
- Definition errors include a JSON pointer (for example `/components/1/source`).
- Re-running the same command after a fix is idempotent and converges.
- No automatic rollback and no silent fallback to the default trio.

| Condition | Message (summary) |
|---|---|
| Definition file not found | "`AGENTLZ_APP_DEFINITION` points to `<path>`, which does not exist." |
| Schema violation | "`<pointer>`: `<reason>`. See contracts/app-definition-v1.schema.json." |
| Unknown profile | "`<pointer>`: profile `<name>` is not supported. Supported: base, model-user, retrieval-reader, conversation-store, blob-delegator, ingestion-writer." |
| Unpinned source | "`<pointer>`: source must be a 40-character commit or a sha256 image digest." |
| Reserved setting key | "`<pointer>`: keys starting with `AGENTLZ_` are reserved." |
| Missing `azure.yaml` | "The app folder `<path>` must contain its own azure.yaml." |
| Binding mismatch | See the binding table above. |
| Foundation missing on `deploy` | "The foundation is not provisioned. Run azd provision first." |

## Fallback (R16)

If one-command orchestration for custom apps (FR-015b/c) is not validated by
2026-10-09, v4.0.0 ships the schema, the standalone validator, platform
outputs, the sample app, and a documented manual procedure. The one-command
custom-app path is then listed as pending in the release notes. The default
trio path is unaffected.
