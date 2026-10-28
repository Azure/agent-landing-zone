"""Shared explicit settings merge and one-pass product placeholder resolution."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Mapping, Sequence

_PLACEHOLDER = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*)(?:=(.*))?\}$", re.DOTALL)
_RESERVED_KEYS = frozenset({"COSMOS_DB_ACCOUNT_RESOURCE_ID", "COSMOS_DB_ENDPOINT"})
OWNERSHIP_PATH = Path(__file__).with_name("appconfig_ownership.json")


def ownership() -> dict:
    """Read the same runtime-authority inventory used by the shared publisher.

    Kept below the runtime/native adapters to avoid circular dependencies.
    """
    policy = json.loads(OWNERSHIP_PATH.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or policy.get("schemaVersion") != 1 or policy.get("label") != "agent-lz":
        raise ValueError("Unsupported App Configuration ownership inventory.")
    for key in ("controlled", "ownerReferences", "patterns", "applicationSuffixes"):
        if not isinstance(policy.get(key), list) or not all(isinstance(item, str) for item in policy[key]):
            raise ValueError("Invalid App Configuration ownership inventory.")
    for key in ("evidence", "ordinary"):
        if not isinstance(policy.get(key), dict) or not all(
            isinstance(name, str) and isinstance(value, str) for name, value in policy[key].items()
        ):
            raise ValueError("Invalid App Configuration ownership inventory.")
    return policy


def substitute_values(value: object, environment: Mapping[str, str]) -> object:
    """Resolve whole-value placeholders once; replacement strings stay data.

    Bicep uses this only for its shared settings collection; the native adapter
    uses it for the complete product input before typed/shared resolution.
    """
    if isinstance(value, str):
        match = _PLACEHOLDER.fullmatch(value)
        if match:
            name, default = match.groups()
            return environment.get(name, default if default is not None else "")
    elif isinstance(value, list):
        return [substitute_values(item, environment) for item in value]
    elif isinstance(value, dict):
        return {key: substitute_values(item, environment) for key, item in value.items()}
    return value


def merge_app_configuration_settings(
    supplied: object,
    generated: list[dict[str, str]],
    *,
    default_label: object = "agent-lz",
    application_names: Sequence[str] = (),
) -> list[dict[str, object]]:
    """Explicit name+label wins ordinary defaults, never security evidence.

    Preserve generated order (especially the final cutover selector). Matching
    protected defaults are allowed for compatibility with the shipped template;
    differing values/content types fail, rather than being silently erased.
    """
    if not isinstance(supplied, list):
        raise ValueError("additionalAppConfigurationSettings requires an array.")
    if not isinstance(default_label, str):
        raise ValueError("appConfigLabel requires a string.")
    policy = ownership()
    protected = (
        set(policy["controlled"]) | set(policy["evidence"]) | set(policy["ownerReferences"])
        | {app + suffix for app in application_names for suffix in policy["applicationSuffixes"]}
        # This selection is checked by the ingestion/source guard, not by the
        # runtime publisher. Pass it through its owning azd input as well.
        | {"SEARCH_RAG_INDEX_NAME"}
    )
    authoritative = {item["name"]: item for item in generated}
    explicit: dict[tuple[str, str], dict[str, object]] = {}
    for item in supplied:
        if (
            not isinstance(item, dict) or not isinstance(item.get("name"), str)
            or not item["name"] or not isinstance(item.get("value"), str)
            or item.get("label") is not None and not isinstance(item["label"], str)
            or item.get("contentType") is not None and not isinstance(item["contentType"], str)
        ):
            raise ValueError(
                "additionalAppConfigurationSettings requires named string values "
                "and optional string labels/content types."
            )
        if item["name"] in _RESERVED_KEYS or item["name"].endswith("_APIKEY"):
            raise ValueError("additionalAppConfigurationSettings contains a reserved infrastructure key.")
        key = (item["name"], item["label"] if item.get("label") is not None else default_label)
        if key in explicit:
            raise ValueError("Duplicate additionalAppConfigurationSettings name+label.")
        normalized = {
            **item, "label": key[1],
            "contentType": item["contentType"] if item.get("contentType") is not None else "text/plain",
        }
        if key[1] == policy["label"] and (
            item["name"] in protected or any(
                re.fullmatch(pattern, item["name"]) for pattern in policy["patterns"]
            )
        ):
            expected = authoritative.get(item["name"])
            if expected is None or any(normalized[field] != expected[field] for field in ("value", "contentType")):
                raise ValueError(
                    f"additionalAppConfigurationSettings {item['name']} conflicts with a protected "
                    "deployment or validation field. Configure its owning azd input "
                    "and rerun the authoritative validation instead."
                )
        explicit[key] = normalized
    generated_keys = {(item["name"], item["label"]) for item in generated}
    return [
        item for key, item in explicit.items() if key not in generated_keys
    ] + [
        explicit.get((item["name"], item["label"]), item) for item in generated
    ]
