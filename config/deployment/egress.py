"""Review component runtime egress and reconcile only deployment-owned rules."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

from config import find_repo_root
from config.appdefinition import AppDefinitionError
from config.deployment.context import bound_resource_id, parse_resource_id
from config.deployment.egress_plan import (
    GROUP_NAME,
    GROUP_PRIORITY,
    canonical,
    declaration_plan,
    fingerprint,
    reconcile,
    subnet_prefixes,
)
from util.azure_cli import resolve_az_command

LOGGER = logging.getLogger("config.deployment.egress")
API_VERSION = "2024-07-01"


class NetworkClient:
    """Narrow Azure CLI boundary; no firewall or parent-policy write operation."""

    def request(
        self, method: str, resource_id: str, *,
        body: Mapping[str, Any] | None = None, headers: list[str] | None = None,
    ) -> dict[str, Any]:
        command = [
            resolve_az_command(), "rest", "--method", method,
            "--url", resource_id + "?api-version=" + API_VERSION,
            "--only-show-errors", "--output", "json",
        ]
        if headers:
            command.extend(["--headers", *headers])
        with tempfile.TemporaryDirectory(prefix="agentlz-egress-") as directory:
            if body is not None:
                path = Path(directory) / "request.json"
                path.write_text(canonical(body), encoding="utf-8")
                command.extend(["--body", "@" + str(path)])
            result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
        if result.returncode:
            raise RuntimeError(
                f"Egress management-plane {method} failed; review Azure CLI access, "
                "policy ownership and concurrent updates, then regenerate the plan. "
                + result.stderr.strip()
            )
        response = json.loads(result.stdout)
        if not isinstance(response, dict):
            raise ValueError("Egress management-plane response must be an object.")
        return response


def _context(plan: Mapping[str, Any], environment: Mapping[str, str]) -> dict[str, Any]:
    raw = environment.get("HOSTED_AGENT_DEPLOYMENT", "")
    if not raw:
        raise ValueError("Missing HOSTED_AGENT_DEPLOYMENT. Run azd provision with the current foundation first.")
    handoff = json.loads(raw)
    if not isinstance(handoff, dict):
        raise ValueError("HOSTED_AGENT_DEPLOYMENT must be an object.")
    context = handoff.get("workloadEgress")
    if not isinstance(context, dict) or context.get("networkIsolation") is not True:
        raise ValueError("Workload egress context conflicts with the isolated declaration plan.")
    policy_id = context.get("managedFirewallPolicyId")
    if not isinstance(policy_id, str):
        raise ValueError("Workload egress context has no valid firewall ownership.")
    if bool(policy_id) != (plan["policyMode"] == "managed"):
        raise ValueError("Firewall ownership changed since provision. Regenerate the plan and reprovision.")
    if policy_id:
        bound_resource_id(policy_id, environment, "Microsoft.Network/firewallPolicies", area="network")
    return context


def resolve_sources(
    plan: Mapping[str, Any], context: Mapping[str, Any], environment: Mapping[str, str],
    client: NetworkClient,
) -> dict[str, list[str]]:
    kinds = {kind for component in plan["components"] for kind in component["kinds"]}
    sources = {}
    vnet_id = environment.get("VNET_RESOURCE_ID", "")
    if not vnet_id:
        raise ValueError("VNET_RESOURCE_ID is required to verify workload subnet ownership.")
    vnet = parse_resource_id(vnet_id)
    if vnet.resource_type.lower() != "microsoft.network/virtualnetworks":
        raise ValueError("VNET_RESOURCE_ID must identify the provisioned workload VNet.")
    for kind in sorted(kinds):
        resource_id = context.get("subnets", {}).get(kind)
        if not isinstance(resource_id, str):
            raise ValueError(f"No provisioned workload subnet for {kind}.")
        subnet = parse_resource_id(resource_id)
        if (subnet.resource_type.lower() != "microsoft.network/virtualnetworks/subnets" or
                resource_id.rsplit("/subnets/", 1)[0].lower() != vnet_id.lower()):
            raise ValueError("Egress source subnet does not belong to the provisioned workload VNet.")
        response = client.request("get", resource_id)
        if response.get("id", "").lower() != resource_id.lower():
            raise ValueError("Subnet discovery returned a different resource ID.")
        properties = response["properties"]
        prefixes = properties.get("addressPrefixes") or [properties.get("addressPrefix")]
        sources[kind] = subnet_prefixes(prefixes)
    return sources


def read_group(client: NetworkClient, policy_id: str) -> dict[str, Any] | None:
    result = client.request("get", policy_id + "/ruleCollectionGroups")
    if result.get("nextLink"):
        raise ValueError("Firewall rule-group listing is paginated; review policy size before reconciliation.")
    groups = result.get("value")
    if not isinstance(groups, list):
        raise ValueError("Firewall rule-group listing must contain a value array.")
    matches = [group for group in groups if group["name"].lower() == GROUP_NAME.lower()]
    if len(matches) > 1:
        raise ValueError("Duplicate component-egress groups.")
    if any(group["name"].lower() != GROUP_NAME.lower()
           and group["properties"]["priority"] == GROUP_PRIORITY for group in groups):
        raise ValueError(f"Component-egress group priority {GROUP_PRIORITY} is already in use; review the policy.")
    if not matches:
        return None
    group = matches[0]
    expected_id = policy_id + "/ruleCollectionGroups/" + GROUP_NAME
    if group.get("id", "").lower() != expected_id.lower():
        raise ValueError("Firewall discovery returned a different policy/group ID.")
    if group["properties"].get("provisioningState") not in (None, "Succeeded"):
        raise ValueError("Firewall component-egress group has an in-progress or failed operation.")
    return group


def _emit(value: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
    sys.stdout.flush()


def review_or_apply(
    plan: Mapping[str, Any], environment: Mapping[str, str], *,
    apply: bool, client: NetworkClient | None = None,
) -> dict[str, Any]:
    if plan["policyMode"] == "none":
        report = {"policyMode": "none", "changed": False, "declarationPlan": plan}
        _emit(report)
        return report
    client = client or NetworkClient()
    context = _context(plan, environment)
    sources = resolve_sources(plan, context, environment, client)
    policy_id = context["managedFirewallPolicyId"]
    # An external policy is deliberately not even read; its operator owns reconciliation.
    current = read_group(client, policy_id) if policy_id else None
    report = reconcile(plan, sources, current)
    report["managedFirewallPolicyId"] = policy_id
    report["sourceSubnets"] = context["subnets"]
    report["operation"] = "reconcile" if policy_id else "report-only"
    _emit(report)
    if not apply or not policy_id or not report["changed"]:
        return report
    latest = read_group(client, policy_id)
    if latest != current:
        raise ValueError("Firewall rules changed during review; refusing to overwrite the concurrent change.")
    if resolve_sources(plan, context, environment, client) != sources:
        raise ValueError("Workload subnet prefixes changed during review; regenerate the resolved plan.")
    if current is None:
        headers = ["If-None-Match=*"]
    else:
        etag = current.get("etag")
        if not isinstance(etag, str) or not re.fullmatch(r'(?:W/)?"[^"\r\n]+"', etag):
            raise ValueError("Firewall group has no valid ETag; refusing an unguarded write.")
        headers = ["If-Match=" + etag]
    resource_id = policy_id + "/ruleCollectionGroups/" + GROUP_NAME
    client.request("put", resource_id, body={"properties": report["properties"]}, headers=headers)
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        observed = client.request("get", resource_id)
        if observed.get("id", "").lower() != resource_id.lower():
            raise ValueError("Firewall verification returned a different policy/group ID.")
        state = observed.get("properties", {}).get("provisioningState")
        if state == "Succeeded":
            remaining = reconcile(plan, sources, observed)
            if remaining["changed"]:
                raise RuntimeError("Firewall operation completed but owned rules do not match the reviewed plan.")
            LOGGER.info("Component runtime egress reconciled; unrelated rules were preserved.")
            return report
        if state not in {"Updating", "Creating", "Accepted"}:
            raise RuntimeError(f"Component-egress rule operation did not succeed (state={state!r}).")
        time.sleep(5)
    raise TimeoutError("Timed out waiting for the component-egress rule operation. Review its state before retrying.")


def _plan_path(root: Path, environment: Mapping[str, str]) -> Path:
    name = environment.get("AZURE_ENV_NAME", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("A valid AZURE_ENV_NAME is required to save/check the egress declaration plan.")
    return root / ".azure" / name / "component-egress-plan.json"


def selected_environment(root: Path, name: str) -> dict[str, str]:
    """Read an explicit local azd environment without shell evaluation or writes."""
    result = subprocess.run(
        ["azd", "env", "get-values", "--environment", name, "--output", "json"],
        cwd=root, capture_output=True, text=True, timeout=60, check=False,
    )
    if result.returncode:
        raise ValueError("Cannot read the requested azd environment. Select it and retry.")
    values = json.loads(result.stdout)
    if not isinstance(values, dict) or not values or any(
        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or
        not isinstance(value, str) or "\0" in value for key, value in values.items()
    ):
        raise ValueError("azd returned invalid environment keys or values.")
    if values.get("AZURE_ENV_NAME", name) != name:
        raise ValueError("azd returned a different environment.")
    return {**values, "AZURE_ENV_NAME": name}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--plan", action="store_true", help="Offline declaration plan; no Azure access.")
    action.add_argument("--review", action="store_true", help="Read-only resolved source and rule change plan.")
    action.add_argument("--apply", action="store_true", help="Reconcile only deployment-managed policy rules.")
    parser.add_argument("--save", action="store_true", help="Save the offline preprovision declaration plan.")
    parser.add_argument("--environment", help="Read this local azd environment instead of the process environment.")
    args = parser.parse_args(argv)
    try:
        root = find_repo_root()
        environment = selected_environment(root, args.environment) if args.environment else os.environ
        source = json.loads((root / "main.parameters.json").read_text(encoding="utf-8-sig"))
        plan = declaration_plan(root, environment, source)
        if args.save:
            if not args.plan:
                raise ValueError("--save is only valid with --plan.")
            path = _plan_path(root, environment)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        if args.plan:
            _emit({"declarationSha256": fingerprint(plan), "declarationPlan": plan,
                   "sourceScope": "Resolve provisioned workload subnet IDs to actual address prefixes before applying."})
        else:
            if args.apply:
                path = _plan_path(root, environment)
                if not path.is_file() or json.loads(path.read_text(encoding="utf-8")) != plan:
                    raise ValueError("Egress declaration plan is missing or stale. Review --plan, then rerun azd provision.")
            review_or_apply(plan, environment, apply=args.apply)
    except (AppDefinitionError, ValueError, RuntimeError, OSError, KeyError, TypeError,
            subprocess.SubprocessError) as error:
        LOGGER.error("Component runtime egress failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
