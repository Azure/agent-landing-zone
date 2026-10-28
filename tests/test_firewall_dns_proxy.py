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


def evaluate(value, parameters, variables=None):
    """Evaluate only compiled parameter bindings and Boolean gates, fail closed.

    This deliberately cannot invoke Azure or Python eval. Unsupported ARM
    expressions fail rather than silently substituting an expected test value.
    """
    if isinstance(value, dict):
        return {key: evaluate(item, parameters, variables) for key, item in value.items()}
    if not isinstance(value, str) or not value.startswith("["):
        return value

    def expression(text):
        text = text.strip()
        match = re.fullmatch(r"parameters\('([^']+)'\)", text)
        if match:
            return parameters[match[1]]
        match = re.fullmatch(r"variables\('([^']+)'\)", text)
        if match:
            return evaluate(variables[match[1]], parameters, variables)
        if text.startswith("'") and text.endswith("'"):
            return text[1:-1].replace("''", "'")
        if text in ("true()", "false()", "null()"):
            return {"true()": True, "false()": False, "null()": None}[text]
        call = re.fullmatch(r"(\w+)\((.*)\)", text, re.S)
        if call:
            name, arguments = call.groups()
            parts, start, depth, quoted = [], 0, 0, False
            for index, char in enumerate(arguments):
                if char == "'":
                    quoted = not quoted
                if not quoted:
                    depth += (char == "(") - (char == ")")
                    if char == "," and depth == 0:
                        parts.append(arguments[start:index])
                        start = index + 1
            parts.append(arguments[start:])
            if name == "if":
                return expression(parts[1] if expression(parts[0]) else parts[2])
            if name in ("and", "or"):
                return (all if name == "and" else any)(expression(part) for part in parts)
            args = [expression(part) for part in parts if part.strip()]
            if name == "fail":
                raise ValueError(args[0])
            if name == "equals":
                return args[0] == args[1]
            if name == "not":
                return not args[0]
            if name == "createObject":
                return dict(zip(args[::2], args[1::2]))
            if name == "createArray":
                return args
            if name in ("union", "shallowMerge"):
                result = {}
                for arg in (args[0] if name == "shallowMerge" else args):
                    result.update(arg)
                return result
        raise AssertionError(f"Unsupported compiled ARM expression: {text}")

    return expression(value[1:-1])


def resource(template, name):
    return template["resources"][name]


def module_defaults(template):
    return {
        name: declaration["defaultValue"]
        for name, declaration in template["parameters"].items()
        if "defaultValue" in declaration
    }


def test_parameter_defaults_and_azd_surface(template, firewall_template):
    assert template["parameters"][SETTING]["type"] == "bool"
    assert template["parameters"][SETTING]["defaultValue"] is False
    assert firewall_template["parameters"][SETTING]["type"] == "bool"
    assert firewall_template["parameters"][SETTING]["defaultValue"] is False
    firewall = resource(template, "firewall")["properties"]
    forwarding = firewall["parameters"][SETTING]["value"]
    policy = resource(firewall["template"], "firewallPolicy")
    for proxy in (False, True):
        module_parameters = {
            **module_defaults(firewall["template"]),
            SETTING: evaluate(forwarding, {SETTING: proxy}), "azureFirewallSku": "Standard",
            "networkIsolation": True, "deployAzureFirewall": True,
        }
        assert evaluate(policy["properties"], module_parameters, firewall["template"]["variables"])["dnsSettings"] == {"enableProxy": proxy}
    for path in ("main.parameters.json", "infra/main.parameters.json"):
        parameters = json.loads((ROOT / path).read_text(encoding="utf-8"))
        assert parameters["parameters"][SETTING]["value"] == ENV_VALUE


@pytest.mark.parametrize("sku", ["Basic", "Standard"])
@pytest.mark.parametrize("proxy", [None, False, True])
def test_compiled_policy_renders_selected_proxy_and_reprovisions(firewall_template, proxy, sku):
    parameters = {
        **module_defaults(firewall_template),
        SETTING: firewall_template["parameters"][SETTING]["defaultValue"], "azureFirewallSku": sku,
        "networkIsolation": True, "deployAzureFirewall": True,
    }
    if proxy is not None:
        parameters[SETTING] = proxy
    policy = resource(firewall_template, "firewallPolicy")
    if sku == "Basic" and proxy:
        with pytest.raises(ValueError):
            evaluate(policy["properties"], parameters, firewall_template["variables"])
        return
    rendered = evaluate(policy["properties"], parameters, firewall_template["variables"])
    if sku == "Basic":
        assert "dnsSettings" not in rendered or rendered["dnsSettings"] is None
    else:
        assert rendered["dnsSettings"] == {"enableProxy": proxy is True}
    # Reusing the same persisted input renders the same policy on each provision.
    assert evaluate(policy["properties"], parameters, firewall_template["variables"]) == rendered
    assert rendered["sku"] == {"tier": sku}
    assert rendered["threatIntelMode"] == "Alert"


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
