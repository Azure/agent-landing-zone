"""Deterministic application egress selection and ownership-safe rule merging."""

from __future__ import annotations

import copy
from dataclasses import asdict
import hashlib
import ipaddress
import json
from pathlib import Path
import re
from typing import Any, Mapping

from config.appdefinition import load_definition, load_selected_definition, validate_definition
from config.appdefinition.egress import Destination, validate_requirement
from config.appdefinition.loader import component_service_name, effective_components
from config.deployment.composition import (
    DeploymentMode,
    compose_parameters,
    is_truthy,
    resolve_ingestion_selection,
    resolve_mode,
)

GROUP_NAME = "AgentLzComponentEgress"
GROUP_PRIORITY = 400
MARKER = "agent-lz-egress/v1:"


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def declaration_plan(
    root: Path, environment: Mapping[str, str], source: Mapping[str, object],
) -> dict[str, Any]:
    """Follow actual additive application composition, not just the selected file."""
    selected = validate_definition(load_selected_definition(environment, root), root)
    bundled = validate_definition(load_definition(root / "app-definition.json", root), root)
    composed = compose_parameters(source, environment)
    services = {
        app["service_name"]
        for app in composed["parameters"]["containerAppsList"]["value"]
    }
    hosted = resolve_mode(environment) is not DeploymentMode.CLASSIC
    definitions = [bundled] if selected.bundled else [bundled, selected]
    components: list[dict[str, Any]] = []
    for definition in definitions:
        for component in effective_components(
            definition, hosted_orchestration=hosted,
            deploy_ingestion=resolve_ingestion_selection(environment),
        ):
            kinds = []
            if component["kind"] == "azure.ai.agent":
                kinds.append("azure.ai.agent")
                if definition.bundled and component["name"] == "orchestrator":
                    if "orchestrator" in services:
                        kinds.append("containerapp")
            elif component_service_name(definition, component) in services:
                kinds.append("containerapp")
            if not kinds:
                continue
            item = {"id": f"{definition.id}/{component['name']}", "kinds": sorted(kinds)}
            if "egress" in component:
                item["egress"] = [
                    {**asdict(validate_requirement(requirement)), "purpose": requirement["purpose"]}
                    for requirement in component["egress"]
                ]
                item["egress"].sort(key=canonical)
            components.append(item)
    parameters = composed["parameters"]
    isolated = _boolean_parameter(parameters, "networkIsolation", environment, False)
    managed = _boolean_parameter(parameters, "deployAzureFirewall", environment, True)
    return {
        "schemaVersion": 1,
        "applicationId": selected.id,
        "policyMode": "none" if not isolated else ("managed" if managed else "external"),
        "components": sorted(components, key=lambda item: item["id"]),
    }


def _boolean_parameter(
    parameters: Mapping[str, Any], name: str, environment: Mapping[str, str], default: bool,
) -> bool:
    value = parameters.get(name, {}).get("value", default)
    if isinstance(value, str):
        match = re.fullmatch(r"\$\{([A-Z_]+)(?:=([^}]*))?\}", value)
        if match:
            value = environment.get(match[1], match[2] if match[2] is not None else "")
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"", "true", "false"}:
        return is_truthy(value)
    raise ValueError(f"{name} must resolve to true or false before planning egress.")


def collection_name(plan: Mapping[str, Any]) -> str:
    return "agent-lz-" + fingerprint(plan["applicationId"])[:16] + "-runtime"


def _rule_name(destination: Destination) -> str:
    return "runtime-" + fingerprint(asdict(destination))[:24]


def _owner_prefix(plan: Mapping[str, Any]) -> str:
    return MARKER + plan["applicationId"] + ":"


def _is_owned(rule: Mapping[str, Any], plan: Mapping[str, Any]) -> bool:
    description = rule.get("description")
    return isinstance(description, str) and description.startswith(_owner_prefix(plan))


def subnet_prefixes(values: list[str]) -> list[str]:
    if not values:
        raise ValueError("A workload subnet must have at least one address prefix.")
    networks = []
    for value in values:
        network = ipaddress.ip_network(value, strict=True)
        if network.prefixlen == 0:
            raise ValueError("An unrestricted source prefix is not a workload subnet.")
        networks.append(str(network))
    return sorted(set(networks))


def _owned_destination(rule: Mapping[str, Any]) -> Destination:
    """Do not adopt a tampered marked rule with broader selectors."""
    try:
        destination = validate_requirement({
            "fqdn": rule["targetFqdns"][0],
            "protocol": rule["protocols"][0]["protocolType"].lower(),
            "port": rule["protocols"][0]["port"],
            "purpose": "Previously owned runtime requirement",
        })
        if rule["ruleType"] != "ApplicationRule" or rule["name"] != _rule_name(destination):
            raise ValueError("Unexpected owned rule type or name.")
        if len(rule["targetFqdns"]) != 1 or len(rule["protocols"]) != 1:
            raise ValueError("Unexpected owned destination selectors.")
        allowed = {"ruleType", "name", "description", "protocols", "targetFqdns", "sourceAddresses"}
        if any(value for key, value in rule.items() if key not in allowed):
            raise ValueError("Unexpected additional owned rule selectors.")
        subnet_prefixes(rule["sourceAddresses"])
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise ValueError("Malformed owned runtime-egress rule; review it before reconciliation.") from error
    return destination


def reconcile(
    plan: Mapping[str, Any],
    sources: Mapping[str, list[str]],
    current: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a change plan; never mutate inputs or unrelated policy content."""
    components = {component["id"]: component for component in plan["components"]}
    required: dict[Destination, dict[str, str]] = {}
    for component in components.values():
        for requirement in component.get("egress", []):
            destination = validate_requirement(requirement)
            owners = required.setdefault(destination, {})
            previous = owners.get(component["id"])
            purpose = requirement["purpose"]
            owners[component["id"]] = purpose if not previous else "; ".join(sorted({previous, purpose}))

    properties = copy.deepcopy((current or {}).get("properties", {
        "priority": GROUP_PRIORITY, "ruleCollections": [],
    }))
    properties = {key: value for key, value in properties.items()
                  if key not in {"provisioningState", "size"}}
    if properties.get("priority") != GROUP_PRIORITY:
        raise ValueError("Component-egress group priority collision; refusing to adopt the group.")
    collections = properties["ruleCollections"]
    matches = [item for item in collections if item["name"].lower() == collection_name(plan)]
    if len(matches) > 1:
        raise ValueError("Duplicate component-egress collections.")
    collection = matches[0] if matches else {
        "name": collection_name(plan), "priority": 100,
        "ruleCollectionType": "FirewallPolicyFilterRuleCollection",
        "action": {"type": "Allow"}, "rules": [],
    }
    if (collection.get("ruleCollectionType") != "FirewallPolicyFilterRuleCollection"
            or collection.get("action") != {"type": "Allow"} or collection.get("priority") != 100):
        raise ValueError("Component-egress collection ownership collision.")
    unrelated = []
    old_owned = []
    for rule in collection["rules"]:
        description = rule.get("description", "")
        if not _is_owned(rule, plan):
            unrelated.append(rule)
            continue
        destination = _owned_destination(rule)
        try:
            owners = json.loads(description[len(_owner_prefix(plan)):])
        except json.JSONDecodeError as error:
            raise ValueError("Malformed runtime-egress ownership metadata.") from error
        if (not isinstance(owners, list) or not owners or
                any(not isinstance(owner, str) or not re.fullmatch(
                    r"[a-z][a-z0-9-]{2,39}/[a-z][a-z0-9-]{1,23}", owner,
                ) for owner in owners) or
                len(owners) != len(set(owners))):
            raise ValueError("Malformed runtime-egress owners.")
        old_owned.append({key: value for key, value in rule.items() if key in {
            "ruleType", "name", "description", "protocols", "targetFqdns", "sourceAddresses",
        }})
        for owner in owners:
            component = components.get(owner)
            if component is not None and "egress" not in component:
                required.setdefault(destination, {}).setdefault(owner, "Retained legacy declaration")

    rules = []
    review = []
    for destination, owners in sorted(required.items()):
        addresses = set()
        for owner in owners:
            for kind in components[owner]["kinds"]:
                addresses.update(subnet_prefixes(sources[kind]))
        description = _owner_prefix(plan) + canonical(sorted(owners))
        if len(description) > 1024:
            raise ValueError("Runtime-egress ownership metadata exceeds the supported 1024-character budget.")
        rule = {
            "name": _rule_name(destination), "description": description,
            "ruleType": "ApplicationRule",
            "protocols": [{"protocolType": destination.protocol.title(), "port": destination.port}],
            "targetFqdns": [destination.fqdn], "sourceAddresses": sorted(addresses),
        }
        rules.append(rule)
        review.append({**asdict(destination), "sourceAddresses": sorted(addresses),
                       "owners": [{"component": owner, "purpose": purpose}
                                  for owner, purpose in sorted(owners.items())]})
    new_collection = {**collection, "rules": unrelated + rules}
    if {rule["name"].lower() for rule in unrelated} & {rule["name"].lower() for rule in rules}:
        raise ValueError("Runtime rule name collision without matching ownership metadata.")
    # Keep an empty owned collection's group but not an invalid empty collection.
    new_collections = []
    for item in collections:
        if item["name"].lower() != collection_name(plan):
            new_collections.append(item)
        elif new_collection["rules"]:
            new_collections.append(new_collection)
    if not matches and new_collection["rules"]:
        new_collections.append(new_collection)
    properties["ruleCollections"] = new_collections
    old_by_name = {item["name"]: item for item in old_owned}
    new_by_name = {item["name"]: item for item in rules}
    previous_properties = {
        key: value for key, value in (current or {}).get("properties", {}).items()
        if key not in {"provisioningState", "size"}
    }
    previous_properties = copy.deepcopy(previous_properties)
    for item in previous_properties.get("ruleCollections", []):
        if item["name"].lower() == collection_name(plan):
            item["rules"] = [
                ({key: value for key, value in rule.items() if key in {
                    "ruleType", "name", "description", "protocols", "targetFqdns", "sourceAddresses",
                }} if _is_owned(rule, plan) else rule)
                for rule in item["rules"]
            ]
    changed = properties != previous_properties
    return {
        "policyMode": plan["policyMode"], "declarationSha256": fingerprint(plan),
        "group": GROUP_NAME, "rules": review,
        "legacyComponents": sorted(key for key, item in components.items() if "egress" not in item),
        "added": sorted(new_by_name.keys() - old_by_name.keys()),
        "removed": sorted(old_by_name.keys() - new_by_name.keys()),
        "updated": sorted(key for key in old_by_name.keys() & new_by_name.keys()
                          if old_by_name[key] != new_by_name[key]),
        "changed": changed and (current is not None or bool(rules)),
        "properties": properties,
    }
