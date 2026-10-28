"""Private declared runtime intent; no state, output transport or Azure writes.

The CLI caller supplies a fresh, validated selected azd snapshot. The current
root parameter document is required even on a clean runner; ignored generated
tfvars and process guesses are never reconstruction sources. Runtime authority
still belongs to the existing appconfig/continuity/platform publishers.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Mapping, TypedDict

from config.continuity.settings import public_settings as continuity_settings
from config.deployment.input_types import INPUT_TYPES
from config.deployment.resolution import resolve_parameters
from config.deployment.resource_groups import resolve_resource_groups
from config.deployment.terraform_inputs import _native_value, _substitute

OWNERSHIP_PATH = Path(__file__).with_name("appconfig_ownership.json")


class Setting(TypedDict):
    name: str
    value: str
    label: str
    contentType: str


def ownership() -> dict:
    document = json.loads(OWNERSHIP_PATH.read_text(encoding="utf-8"))
    if document.get("schemaVersion") != 1 or document.get("label") != "agent-lz":
        raise ValueError("Unsupported App Configuration ownership inventory.")
    return document


def normalize_settings(value: object, label: str = "agent-lz") -> list[Setting]:
    if not isinstance(value, list):
        raise ValueError("additionalAppConfigurationSettings must be an array.")
    result: list[Setting] = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) - {"name", "value", "label", "contentType"}:
            raise ValueError("Invalid additional App Configuration entry fields.")
        name, data = item.get("name"), item.get("value")
        entry_label = item.get("label") if item.get("label") is not None else label
        content_type = item.get("contentType") if item.get("contentType") is not None else "text/plain"
        if (
            not isinstance(name, str) or not name or not isinstance(data, str)
            or not isinstance(entry_label, str) or not isinstance(content_type, str)
            or any("\0" in text for text in (name, data, entry_label, content_type))
        ):
            raise ValueError("App Configuration entries require named string values, labels and content types.")
        pair = (name, entry_label)
        if pair in seen:
            raise ValueError("Duplicate additional App Configuration name/label.")
        seen.add(pair)
        result.append(Setting(name=name, value=data, label=entry_label, contentType=content_type))
    return result


@dataclass(frozen=True)
class RuntimeIntent:
    explicit: list[Setting]
    effective: list[Setting]
    canonical_names: frozenset[str]
    application_names: frozenset[str]


def resolve_intent(parameter_source: Path, environment: Mapping[str, str]) -> RuntimeIntent:
    """Resolve the same typed declaration/application intent, without provisioning."""
    if not environment or any(
        not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
        or not isinstance(value, str) or "\0" in value
        for key, value in environment.items()
    ):
        raise ValueError("Runtime intent requires a validated selected azd environment snapshot.")
    if not environment.get("AZURE_ENV_NAME"):
        raise ValueError("Select an azd environment before resolving runtime intent.")
    groups = resolve_resource_groups(environment)
    try:
        document = json.loads(parameter_source.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ValueError(
            "Cannot read the declared runtime parameter source. Restore main.parameters.json "
            "or supply --input with the same private declaration used for provision; "
            "a clean runner must not reconstruct missing intent from defaults or Terraform state."
        ) from None
    entries = document.get("parameters") if isinstance(document, dict) else None
    if not isinstance(entries, dict) or any(
        not isinstance(entry, dict) or "value" not in entry for entry in entries.values()
    ):
        raise ValueError("Declared runtime source must be a parameter document with value entries.")
    source = _substitute({name: entry["value"] for name, entry in entries.items()}, environment)
    if source.keys() - INPUT_TYPES.keys() - {"aiFoundryLocation"}:
        raise ValueError("Unknown infrastructure input in the declared runtime source.")
    alias = source.pop("aiFoundryLocation", "")
    if alias and alias != source.get("location"):
        raise ValueError("A separate aiFoundryLocation is unsupported; declare location instead.")
    native = {name: _native_value(name, value) for name, value in source.items()}
    if native.get("environmentName") not in (None, "", environment["AZURE_ENV_NAME"]):
        raise ValueError("Declared runtime source conflicts with the selected environment.")
    for name, selected in (
        ("applicationResourceGroupName", groups.application),
        ("networkResourceGroupName", groups.network),
    ):
        declared = native.get(name)
        if declared and declared.casefold() != selected.casefold():
            raise ValueError("Declared runtime source conflicts with the selected resource-group binding.")
    label = native.get("appConfigLabel", "agent-lz")
    if not isinstance(label, str):
        raise ValueError("appConfigLabel must be a string.")
    explicit = normalize_settings(native.get("additionalAppConfigurationSettings", []), label)
    resolved = resolve_parameters(native, environment)
    effective = normalize_settings(resolved.get("additionalAppConfigurationSettings", []), label)
    canonical = frozenset(
        item["canonical_name"]
        for name in ("modelDeploymentList", "databaseContainersList", "storageAccountContainersList")
        for item in resolved.get(name, []) if isinstance(item, dict) and item.get("canonical_name")
    )
    applications = frozenset(
        item["canonical_name"] for item in resolved.get("containerAppsList", [])
        if isinstance(item, dict) and item.get("canonical_name")
    )
    return RuntimeIntent(explicit, effective, canonical, applications)


def is_runtime(setting: Setting, intent: RuntimeIntent, policy: dict | None = None) -> bool:
    policy = policy or ownership()
    name = setting["name"]
    names = (
        set(policy["controlled"]) | set(policy["evidence"]) | set(policy["ordinary"])
        | set(policy["ownerReferences"])
        | {app + suffix for app in intent.application_names for suffix in policy["applicationSuffixes"]}
    )
    return (
        setting["label"] == policy["label"] and name not in intent.canonical_names
        and (name in names or any(re.fullmatch(pattern, name) for pattern in policy["patterns"]))
    )


def _validate_metadata(setting: Setting, *, controlled: bool = False) -> None:
    content_type = setting["contentType"]
    if content_type.startswith("application/vnd.microsoft.appconfig.keyvaultref+json"):
        raise ValueError(
            f"{setting['name']}: runtime Key Vault-reference overrides have no generic "
            "publication contract; configure the existing governance/continuity owner instead."
        )
    if controlled and content_type != ("application/json" if setting["name"] == "CONTAINER_APPS" else "text/plain"):
        raise ValueError(f"{setting['name']}: authority-controlled contentType cannot be overridden.")
    if content_type.split(";", 1)[0] == "application/json":
        try:
            json.loads(setting["value"])
        except ValueError:
            raise ValueError(f"{setting['name']}: application/json requires valid JSON.") from None


def prepare_publication(intent: RuntimeIntent, authority: Mapping[str, str]) -> list[Setting]:
    """Validate all explicit conflicts before returning any writable entries.

    Derived fields are compared with the existing owner's verified result, never
    taken from additional settings. Other owners' derived/ref overrides fail
    actionably rather than being flattened or silently ignored.
    """
    policy = ownership()
    for setting in intent.explicit:
        if not is_runtime(setting, intent, policy):
            continue
        name = setting["name"]
        if name in policy["ownerReferences"]:
            raise ValueError(f"{name}: use its existing governance/continuity owner; explicit runtime-reference overrides are unsupported.")
        controlled = name not in policy["ordinary"]
        _validate_metadata(setting, controlled=controlled)
        if controlled:
            expected = policy["evidence"].get(name, authority.get(name))
            if expected is None:
                raise ValueError(f"{name}: explicit derived override is unsupported here; use its existing runtime/platform owner.")
            if setting["value"] != expected:
                raise ValueError(f"{name}: explicit runtime intent conflicts with routing, identity or evidence authority.")

    result = {
        name: Setting(
            name=name, value=value, label=policy["label"],
            contentType="application/json" if name == "CONTAINER_APPS" else "text/plain",
        )
        for name, value in authority.items()
        if is_runtime(Setting(name=name, value=value, label=policy["label"], contentType="text/plain"), intent, policy)
    }
    for setting in intent.effective:
        if not is_runtime(setting, intent, policy):
            continue
        name, value = setting["name"], setting["value"]
        if name in policy["ordinary"]:
            _validate_metadata(setting)
            kind = policy["ordinary"][name]
            if kind == "boolean" and value not in ("true", "false"):
                raise ValueError(f"{name}: runtime intent requires true or false.")
            if kind == "positive_integer" and (not re.fullmatch(r"[0-9]+", value) or int(value) < 1):
                raise ValueError(f"{name}: runtime intent requires a positive integer.")
            result[name] = setting
        elif name in policy["evidence"]:
            result[name] = Setting(name=name, value=policy["evidence"][name], label=policy["label"], contentType="text/plain")
        # Generated derived values are desires, not proof of completed cutover.
        # Their existing owner's authority above controls what is actually written.
    if any(policy["ordinary"].get(name) == "continuity" for name in result):
        from config.continuity.setup import validate_continuity_settings
        continuity = continuity_settings({})
        continuity.update({name: s["value"] for name, s in result.items() if name in continuity})
        validate_continuity_settings(
            continuity, deployment_topology=authority.get("DEPLOYMENT_TOPOLOGY", ""),
            chat_backend=authority.get("CHAT_BACKEND", ""),
        )
    return [setting for name, setting in result.items() if name != "CHAT_BACKEND"] + (
        [result["CHAT_BACKEND"]] if "CHAT_BACKEND" in result else []
    )
