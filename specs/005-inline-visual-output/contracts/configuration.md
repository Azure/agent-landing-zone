# Presentation configuration contract

**Design key**: `AGENT_PRESENTATION_SETTINGS`

**Label**: `agent-lz`

**Content type**: `text/plain` containing compact JSON

**Default**: `{"schemaVersion":1,"agents":{}}`

The existing provider-neutral `additionalAppConfigurationSettings` parameter carries this setting. No new foundation parameter, deployment selector, resource, managed identity, role, endpoint, secret, network egress, or host mode is required.

## Ownership and validation

This is owner-edited functional configuration, not generated identity/routing authority. Add it to `appconfig_ownership.json`'s `ordinary` inventory with an explicit `json_object` validation kind during implementation. Do not classify it as `controlled`: that inventory protects derived values and would reject legitimate owner opt-in changes in `merge_app_configuration_settings`.

A focused validator checks [the settings schema](agent-presentation-settings-v1.schema.json), duplicate keys/agent IDs/rule IDs, disjoint numeric rule cases, stable configured agent IDs, allowed content, and the App Configuration service's existing value-size limit. Invoke it in shared resolution/publication and in the orchestrator reader. Unknown versions, malformed JSON, nonexistent agent IDs, invalid rules, unsupported metadata/label, or conflicting duplicate entries produce an actionable configuration error before enablement, not a silent all-disabled result.

The `json_object` ordinary path requires `text/plain` for this key. Do not special-case it as an authority-controlled `application/json` setting or bypass the runtime publisher as an unrecognized ordinary key.

Missing key and absent agent entries mean disabled. `enabled` is mandatory for present entries. Guidance cannot enable another agent, supply measurements, grant access, introduce new block types, alter hard limits, or install a rule. Persist the snapshot revision with accepted output, not the entire operator guidance or invocation credentials.

Enablement is per agent, not per tool. There is no presentation tool-name allowlist, required NL2SQL setting, source connector dependency or configurable timeout field. Any eligible native/MCP/customer-defined result uses the shared typed normalization path. A rule's `toolName` scopes that specific approved rule and provenance only; it does not determine whether the tool may supply visuals. Existing tool/endpoint admission remains unchanged.

The additional stage has a fixed 10-second per-agent budget, including retries. Neither guidance nor a settings refresh can extend an in-flight deadline. Disabled agents add no selection call. A timeout is an observable optional-generation outcome, not invalid configuration or a whole-turn limit rejection.

Snapshot settings at each new turn/workflow. Disablement affects the next snapshot, not historical rendering. Before any subsequent follow-up, use the normal current authorization path regardless of the prior snapshot.

## Declaration example

Put the serialized value represented by [settings-valid.json](examples/settings-valid.json) in the existing `additionalAppConfigurationSettings.value` entry for this key and label. The example agent names are synthetic. Operators must use the exact native IDs from their configured agent/workflow definitions.

Set `enabled=false` for one agent or remove its entry to stop its new visuals. Removing the entire key resolves to the default empty map. Runtime publication/reconciliation must remove stale owned values or explicitly publish the empty map so both provider paths converge after disablement.

## Provider and lifecycle obligations

| Surface | Required implementation evidence |
| --- | --- |
| Bicep path | Existing generic setting handoff publishes the same validated value, label and content type |
| Terraform path | Shared resolver and runtime publication preserve the identical value/default without a new resource |
| Shared ownership/publisher | Explicit `json_object` validation, no derived-authority override or unclassified-key bypass |
| PowerShell and shell | Provision/deploy/reprovision/disable/teardown paths apply the same snapshot and reconciliation behavior |
| Hosted and Durable | Stable agent-ID resolution, per-turn settings snapshot and equivalent opt-in behavior |

If neither foundation template needs an edit, document generic-setting
transport and exercise both provider adapters and hook implementations locally.
Preserve Terraform lock/module pins and Bicep provenance. Compilation/mocks do
not establish deployed parity. By the 2026-11-08 maintainer amendment, actual
Azure/private-network proof is removed from completion, not deferred; deployed
parity remains an unverified residual risk. Independent operators still verify
the instructions through local provider/publication/hook fixtures.
