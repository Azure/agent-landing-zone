"""Offline contracts for persistent, opt-in firewall DNS proxy (ADR-0022)."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from config.deployment.composition import compose_parameters


ROOT = Path(__file__).resolve().parents[1]
SETTING = "enableFirewallDnsProxy"
ENV_VALUE = "${ENABLE_FIREWALL_DNS_PROXY=false}"


def compile_template(path):
    compiler = shutil.which("bicep")
    assert compiler, "Standalone Bicep CLI is required for this offline contract."
    result = subprocess.run(
        [compiler, "build", str(ROOT / path), "--no-restore", "--stdout"],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def template():
    return compile_template("infra/main.bicep")


@pytest.fixture(scope="module")
def firewall_template():
    return compile_template("infra/modules/networking/azure-firewall.bicep")


def evaluate(value, parameters):
    """Evaluate only compiled parameter bindings and Boolean gates, fail closed.

    This deliberately cannot invoke Azure or Python eval. Unsupported ARM
    expressions fail rather than silently substituting an expected test value.
    """
    if isinstance(value, dict):
        return {key: evaluate(item, parameters) for key, item in value.items()}
    if not isinstance(value, str) or not value.startswith("["):
        return value

    def expression(text):
        match = re.fullmatch(r"parameters\('([^']+)'\)", text)
        if match:
            return parameters[match[1]]
        if text.startswith("and(") and text.endswith(")"):
            arguments = text[4:-1]
            depth = 0
            for index, char in enumerate(arguments):
                depth += (char == "(") - (char == ")")
                if char == "," and depth == 0:
                    left = expression(arguments[:index].strip())
                    right = expression(arguments[index + 1:].strip())
                    assert isinstance(left, bool) and isinstance(right, bool)
                    return left and right
        raise AssertionError(f"Unsupported compiled ARM expression: {text}")

    return expression(value[1:-1])


def resource(template, name):
    return template["resources"][name]


def test_parameter_defaults_and_azd_surface(template, firewall_template):
    assert template["parameters"][SETTING]["type"] == "bool"
    assert template["parameters"][SETTING]["defaultValue"] is False
    assert firewall_template["parameters"][SETTING]["type"] == "bool"
    assert firewall_template["parameters"][SETTING]["defaultValue"] is False
    firewall = resource(template, "firewall")["properties"]
    forwarding = firewall["parameters"][SETTING]["value"]
    policy = resource(firewall["template"], "firewallPolicy")
    for proxy in (False, True):
        module_parameters = {SETTING: evaluate(forwarding, {SETTING: proxy})}
        assert evaluate(policy["properties"]["dnsSettings"], module_parameters) == {
            "enableProxy": proxy,
        }
    for path in ("main.parameters.json", "infra/main.parameters.json"):
        parameters = json.loads((ROOT / path).read_text(encoding="utf-8"))
        assert parameters["parameters"][SETTING]["value"] == ENV_VALUE


@pytest.mark.parametrize("proxy", [None, False, True])
def test_compiled_policy_renders_selected_proxy_and_reprovisions(firewall_template, proxy):
    parameters = {
        SETTING: firewall_template["parameters"][SETTING]["defaultValue"],
    }
    if proxy is not None:
        parameters[SETTING] = proxy
    policy = resource(firewall_template, "firewallPolicy")
    expected = {"enableProxy": proxy is True}
    assert evaluate(policy["properties"]["dnsSettings"], parameters) == expected
    # Reusing the same persisted input renders the same policy on each provision.
    assert evaluate(policy["properties"]["dnsSettings"], parameters) == expected
    assert policy["properties"]["sku"] == {"tier": "Standard"}
    assert policy["properties"]["threatIntelMode"] == "Alert"


@pytest.mark.parametrize("deploy,isolation,proxy", list(itertools.product([False, True], repeat=3)))
def test_proxy_does_not_create_firewall_or_resolver(firewall_template, deploy, isolation, proxy):
    parameters = {
        "deployAzureFirewall": deploy, "networkIsolation": isolation, SETTING: proxy,
    }
    for name in ("firewallPolicy", "azureFirewall", "firewallPublicIp"):
        assert evaluate(resource(firewall_template, name)["condition"], parameters) is (deploy and isolation)
    resources = firewall_template["resources"]
    items = resources.values() if isinstance(resources, dict) else resources
    assert not any("dnsResolvers" in item["type"] for item in items)


@pytest.mark.parametrize("proxy", ["false", "true"])
@pytest.mark.parametrize("hosted", ["false", "true"])
def test_recomposition_preserves_persisted_azd_setting(proxy, hosted):
    source = json.loads((ROOT / "main.parameters.json").read_text(encoding="utf-8"))
    environment = {
        "ENABLE_FIREWALL_DNS_PROXY": proxy,
        "DEPLOY_HOSTED_AGENT_ORCHESTRATION": hosted,
        "DEPLOY_ADMINISTRATIVE_PANEL": "false",
        "HOSTED_AGENT_RESOURCE_SCOPE": "api://test-agent/.default",
    }
    first = compose_parameters(source, environment)
    second = compose_parameters(source, environment)
    assert first["parameters"][SETTING]["value"] == ENV_VALUE
    assert second["parameters"][SETTING] == first["parameters"][SETTING]
