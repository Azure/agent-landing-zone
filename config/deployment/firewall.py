"""Provider-neutral firewall selection and subnet creation intent."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Mapping

from config.deployment.app_settings import substitute_values

LOGGER = logging.getLogger(__name__)
ENVIRONMENT_KEYS = {
    "azureFirewallSku": "AZURE_FIREWALL_SKU",
    "deployAzureFirewallSubnet": "DEPLOY_AZURE_FIREWALL_SUBNET",
    "deployAzureFirewallManagementSubnet": "DEPLOY_AZURE_FIREWALL_MANAGEMENT_SUBNET",
    "deployGatewaySubnet": "DEPLOY_GATEWAY_SUBNET",
}


def _boolean(value: object, name: str, *, nullable: bool = False) -> bool | None:
    if type(value) is bool:
        return value
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"true", "false"}:
            return value == "true"
    if nullable and (value is None or value == "null"):
        return None
    raise ValueError(f"{name} must be true or false" + (" or null (auto)." if nullable else "."))


def resolve_firewall_inputs(
    source: Mapping[str, object], environment: Mapping[str, str],
) -> dict[str, object]:
    """Resolve supplied values once; do not infer external ownership from a hub ID."""
    names = {
        *ENVIRONMENT_KEYS, "networkIsolation", "deploymentMode",
        "deployAzureFirewall", "enableFirewallDnsProxy",
    }
    if not names.intersection(source):
        return {}
    values = substitute_values(
        {name: source[name] for name in names if name in source}, environment,
    )
    sku = values.get("azureFirewallSku", "Basic")
    if not isinstance(sku, str) or sku not in {"Basic", "Standard"}:
        raise ValueError("azureFirewallSku/AZURE_FIREWALL_SKU must be Basic or Standard.")
    isolation_value = values.get("networkIsolation")
    # Composition can precede azd's required-value substitution. Keep auto
    # values unresolved until isolation is known; native roots enforce the gate.
    isolation = (
        None if isolation_value in (None, "")
        else _boolean(isolation_value, "networkIsolation")
    )
    deploy = _boolean(values.get("deployAzureFirewall", True), "deployAzureFirewall")
    proxy = _boolean(values.get("enableFirewallDnsProxy", False), "enableFirewallDnsProxy")
    active = False if not deploy or isolation is False else isolation
    standalone = values.get("deploymentMode", "standalone") == "standalone"
    if active and sku == "Basic" and (proxy or not standalone):
        raise ValueError(
            "Basic requires standalone mode and enableFirewallDnsProxy=false. "
            "Select Standard for a local integrated firewall or DNS proxy; "
            "disable local firewall deployment when using external hub egress."
        )
    data = _boolean(values.get("deployAzureFirewallSubnet"), "deployAzureFirewallSubnet", nullable=True)
    management = _boolean(
        values.get("deployAzureFirewallManagementSubnet"),
        "deployAzureFirewallManagementSubnet", nullable=True,
    )
    return {
        "azureFirewallSku": sku,
        "deployAzureFirewallSubnet": data if data is not None else active,
        "deployAzureFirewallManagementSubnet": (
            management if management is not None
            else (active and standalone and sku == "Basic")
        ),
        "deployGatewaySubnet": _boolean(values.get("deployGatewaySubnet", False), "deployGatewaySubnet"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = json.loads(args.input.read_text(encoding="utf-8"))
        source = {name: entry["value"] for name, entry in document["parameters"].items()}
        resolved = resolve_firewall_inputs(source, os.environ)
        for name, value in resolved.items():
            serialized = (
                "null" if value is None
                else str(value).lower() if isinstance(value, bool) else str(value)
            )
            print(f"{ENVIRONMENT_KEYS[name]}={serialized}")
    except (ValueError, KeyError) as error:
        LOGGER.error("Firewall input resolution failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
