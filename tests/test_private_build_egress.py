"""Offline contracts for pinned orchestrator package-download egress (ADR-0022)."""

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIREWALL = ROOT / "infra/modules/networking/azure-firewall.bicep"
FEED_ARRAY = "_firewallAcrTaskPackageFeedFqdns"
# Verified from frontend/package-lock.json at manifest commit
# 27f952fcf8d48a2ba6267c237ea6bea8361fedd2 (orchestrator v5.2.1).
# The CDN is a download redirect, not a resolved URL in the lockfile.
FEEDS = {
    "ms-feed-2.pkgs.visualstudio.com",
    "ms-feed-12.pkgs.visualstudio.com",
    "ms-feed-17.pkgs.visualstudio.com",
    "ms-feed-25.pkgs.visualstudio.com",
    "*.vsblob.vsassets.io",
}


def _source():
    return FIREWALL.read_text(encoding="utf-8")


def _array(source, name):
    match = re.search(rf"^var {name} = \[(.*?)^\]", source, re.M | re.S)
    assert match, f"Missing literal destination array {name}"
    return re.findall(r"^\s*'([^']+)'", match[1], re.M)


def _rule(source, name):
    match = re.search(
        rf"^  \{{\s+ruleType: 'ApplicationRule'\s+name: '{name}'\s+(.*?)^  \}}",
        source, re.M | re.S,
    )
    assert match, f"Missing application rule {name}"
    return match[1]


def test_exact_pinned_feed_and_redirect_destinations():
    destinations = _array(_source(), FEED_ARRAY)
    assert set(destinations) == FEEDS
    assert len(destinations) == len(FEEDS)
    assert "*.vsassets.io" not in destinations
    assert "*.pkgs.visualstudio.com" not in destinations
    assert "*" not in destinations


def test_feeds_are_build_only_https_and_reuse_existing_extension():
    source = _source()
    rule = _rule(source, "AllowAcrTaskDevRuntimes")
    assert re.search(r"protocols:\s*\[\s*\{ protocolType: 'Https', port: 443 \}\s*\]", rule)
    assert "sourceAddresses: [devopsBuildAgentsSubnetPrefix]" in rule
    assert (
        "targetFqdns: (deployAcrTaskAgentPool && extendFirewallForAcrTaskBuilds) ? "
        f"union(_firewallDevRuntimeFqdns, {FEED_ARRAY}, additionalAcrTaskBuildFqdns) : []"
    ) in rule
    # A shared runtime array would also widen jumpbox egress. Each new host
    # must occur only in the build-only array, referenced by only this rule.
    assert source.count(FEED_ARRAY) == 2
    for host in FEEDS:
        assert source.count(f"'{host}'") == 1
    assert not FEEDS.intersection(_array(source, "_firewallDevRuntimeFqdns"))
    assert "targetFqdns: extendFirewallForJumpboxBootstrap ? _firewallDevRuntimeFqdns : []" in source
    assert "], rule => !empty(rule.targetFqdns))" in source


@pytest.mark.parametrize("pool,extension", [(False, False), (False, True), (True, False), (True, True)])
def test_build_gate_matrix_preserves_extras_and_filters_empty_rules(pool, extension):
    source = _source()
    rule = _rule(source, "AllowAcrTaskDevRuntimes")
    # Interpret only this rule's restricted array-union/boolean contract,
    # reading its gates and array references from the actual source.
    match = re.search(
        r"targetFqdns: \((\w+) && (\w+)\) \? union\(([^)]+)\) : \[\]", rule
    )
    assert match
    flags = {"deployAcrTaskAgentPool": pool, "extendFirewallForAcrTaskBuilds": extension}
    extra = ["extra.example.test", "ms-feed-2.pkgs.visualstudio.com"]
    values = {
        "_firewallDevRuntimeFqdns": _array(source, "_firewallDevRuntimeFqdns"),
        FEED_ARRAY: _array(source, FEED_ARRAY),
        "additionalAcrTaskBuildFqdns": extra,
    }
    targets = []
    if flags[match[1]] and flags[match[2]]:
        for name in match[3].split(", "):
            for host in values[name]:
                if host not in targets:
                    targets.append(host)
    if pool and extension:
        assert FEEDS.issubset(targets)
        assert set(extra).issubset(targets)
        assert targets.count("ms-feed-2.pkgs.visualstudio.com") == 1
    else:
        assert targets == []  # omitted by the existing empty-target filter


def test_microsoft_os_packages_already_allowed_without_duplicate():
    source = _source()
    assert source.count("'packages.microsoft.com'") == 1
    assert "packages.microsoft.com" in _array(source, "_firewallAcrTaskOsPackageFqdns")
    assert "packages.microsoft.com" not in _array(source, FEED_ARRAY)
    rule = _rule(source, "AllowAcrTaskOsPackages")
    assert "sourceAddresses: [devopsBuildAgentsSubnetPrefix]" in rule
    assert (
        "targetFqdns: (deployAcrTaskAgentPool && extendFirewallForAcrTaskBuilds) ? "
        "_firewallAcrTaskOsPackageFqdns : []"
    ) in rule


def test_existing_settings_and_defaults_are_unchanged():
    main = (ROOT / "infra/main.bicep").read_text(encoding="utf-8")
    assert "param extendFirewallForAcrTaskBuilds bool = true" in main
    assert "param deployAcrTaskAgentPool bool = true" in main
    assert "param additionalAcrTaskBuildFqdns array = []" in main
    assert "var _deployAcrTaskAgentPool = deployContainerRegistry && _networkIsolation && deployAcrTaskAgentPool" in main
    assert "additionalAcrTaskBuildFqdns: additionalAcrTaskBuildFqdns" in main
    for path in ("main.parameters.json", "infra/main.parameters.json"):
        parameters = json.loads((ROOT / path).read_text(encoding="utf-8"))["parameters"]
        assert parameters["additionalAcrTaskBuildFqdns"]["value"] == []


def test_offline_compilation_preserves_rule_scope_and_gates():
    compiler = shutil.which("bicep")
    if not compiler:
        pytest.skip("Standalone Bicep CLI unavailable; never restore or invoke Azure CLI")
    result = subprocess.run(
        [compiler, "build", str(FIREWALL), "--stdout", "--no-restore"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    template = json.loads(result.stdout)
    variables = template["variables"]
    assert set(variables[FEED_ARRAY]) == FEEDS
    expression = variables["_firewallDefaultApplicationRules"]
    rule = expression.split("'name', 'AllowAcrTaskDevRuntimes', ", 1)[1].split(
        ", createObject('ruleType'", 1
    )[0]
    assert "'protocols', createArray(createObject('protocolType', 'Https', 'port', 443))" in rule
    assert (
        "'targetFqdns', if(and(parameters('deployAcrTaskAgentPool'), "
        "parameters('extendFirewallForAcrTaskBuilds')), "
        f"union(variables('_firewallDevRuntimeFqdns'), variables('{FEED_ARRAY}'), "
        "parameters('additionalAcrTaskBuildFqdns')), createArray())"
    ) in rule
    assert "'sourceAddresses', createArray(parameters('devopsBuildAgentsSubnetPrefix'))" in rule
    assert expression.startswith("[filter(")
    assert "not(empty(lambdaVariables('rule').targetFqdns))" in expression
    group = template["resources"]["firewallPolicyDefaultRuleCollectionGroup"]
    assert group["condition"] == (
        "[and(parameters('deployAzureFirewall'), parameters('networkIsolation'))]"
    )
    assert group["properties"]["ruleCollections"] == "[variables('_firewallDefaultRuleCollections')]"
    collection = variables["_firewallDefaultRuleCollections"][0]
    assert collection["action"] == {"type": "Allow"}
    assert collection["rules"] == "[variables('_firewallDefaultApplicationRules')]"
    assert "enableFirewallDnsProxy" not in rule
