"""Shared firewall defaults, explicit intent and hook materialization."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from config.deployment.firewall import resolve_firewall_inputs

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("sku", ["Basic", "Standard"])
@pytest.mark.parametrize("isolation", [False, True])
@pytest.mark.parametrize("local", [False, True])
def test_resource_selection(sku, isolation, local):
    result = resolve_firewall_inputs({
        "networkIsolation": isolation, "deployAzureFirewall": local,
        "azureFirewallSku": sku,
    }, {})
    assert result["azureFirewallSku"] == sku
    assert result["deployAzureFirewallSubnet"] is (isolation and local)
    assert result["deployAzureFirewallManagementSubnet"] is (isolation and local and sku == "Basic")
    assert result["deployGatewaySubnet"] is False


@pytest.mark.parametrize("flag", [
    "deployAzureFirewallSubnet", "deployAzureFirewallManagementSubnet", "deployGatewaySubnet",
])
@pytest.mark.parametrize("value", [True, False])
def test_explicit_creation_intent(flag, value):
    assert resolve_firewall_inputs({"networkIsolation": True, flag: value}, {})[flag] is value


@pytest.mark.parametrize("overrides", [
    {"azureFirewallSku": "Premium"}, {"azureFirewallSku": ["Basic"]},
    {"deployGatewaySubnet": "yes"},
    {"deployAzureFirewallSubnet": "typo"}, {"deployAzureFirewallManagementSubnet": "typo"},
    {"enableFirewallDnsProxy": True}, {"deploymentMode": "ailz-integrated"},
])
def test_invalid_input_fails(overrides):
    with pytest.raises(ValueError):
        resolve_firewall_inputs({"networkIsolation": True, **overrides}, {})


def test_external_hub_does_not_require_local_standard():
    result = resolve_firewall_inputs({
        "networkIsolation": True, "deploymentMode": "ailz-integrated",
        "deployAzureFirewall": False,
    }, {})
    assert result["deployAzureFirewallSubnet"] is False
    assert result["deployAzureFirewallManagementSubnet"] is False


def test_unresolved_isolation_keeps_auto_for_native_root():
    result = resolve_firewall_inputs({"networkIsolation": "${NETWORK_ISOLATION}"}, {})
    assert result["deployAzureFirewallSubnet"] is None
    assert result["deployAzureFirewallManagementSubnet"] is None


def test_standard_proxy_is_explicitly_supported():
    result = resolve_firewall_inputs({
        "networkIsolation": True, "azureFirewallSku": "Standard",
        "enableFirewallDnsProxy": True,
    }, {})
    assert result["azureFirewallSku"] == "Standard"


def test_cli_persists_only_normalized_fields():
    result = subprocess.run(
        [sys.executable, "-m", "config.deployment.firewall", "--input", "main.parameters.json"],
        cwd=ROOT, env={**os.environ, "NETWORK_ISOLATION": "true", "AZURE_FIREWALL_SKU": "Basic",
                       "DEPLOY_AZURE_FIREWALL": "true", "DEPLOYMENT_MODE": "standalone",
                       "ENABLE_FIREWALL_DNS_PROXY": "false", "DEPLOY_AZURE_FIREWALL_SUBNET": "null",
                       "DEPLOY_AZURE_FIREWALL_MANAGEMENT_SUBNET": "null", "DEPLOY_GATEWAY_SUBNET": "false"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert dict(line.split("=", 1) for line in result.stdout.splitlines()) == {
        "AZURE_FIREWALL_SKU": "Basic", "DEPLOY_AZURE_FIREWALL_SUBNET": "true",
        "DEPLOY_AZURE_FIREWALL_MANAGEMENT_SUBNET": "true", "DEPLOY_GATEWAY_SUBNET": "false",
    }


def test_both_hooks_materialize_before_composition():
    for extension in ("ps1", "sh"):
        hook = (ROOT / "scripts" / f"preProvision.{extension}").read_text(encoding="utf-8")
        assert hook.index("config.deployment.firewall") < hook.index("config.deployment.terraform_inputs", hook.index("config.deployment.firewall"))


def test_product_defaults_are_explicit():
    parameters = json.loads((ROOT / "main.parameters.json").read_text())["parameters"]
    assert parameters["azureFirewallSku"]["value"] == "${AZURE_FIREWALL_SKU=Basic}"
    assert parameters["deployGatewaySubnet"]["value"] == "${DEPLOY_GATEWAY_SUBNET=false}"
