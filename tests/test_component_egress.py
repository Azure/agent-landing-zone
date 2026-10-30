"""Offline component-egress contracts; the explicit cold-cache check uses public HTTPS."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock, patch

import pytest

from config.appdefinition import AppDefinition, collect_issues, load_definition
from config.appdefinition.egress import validate_requirement
from config.deployment import egress
from config.deployment.egress_plan import (
    GROUP_NAME, GROUP_PRIORITY, canonical, collection_name, declaration_plan, reconcile,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = json.loads((ROOT / "main.parameters.json").read_text(encoding="utf-8"))
REQUIREMENT = {
    "fqdn": "openaipublic.blob.core.windows.net", "protocol": "https", "port": 443,
    "purpose": "Initialize the tokenizer from an empty runtime cache.",
}
ENV = {
    "DEPLOYMENT_TOPOLOGY": "classic", "NETWORK_ISOLATION": "true",
    "DEPLOY_INGESTION_CONTAINER_APP": "true",
    "AZURE_SUBSCRIPTION_ID": "00000000-0000-0000-0000-000000000001",
    "AZURE_RESOURCE_GROUP": "rg-foundry", "AZURE_APP_RESOURCE_GROUP": "rg-app",
    "AZURE_NETWORK_RESOURCE_GROUP": "rg-network",
}
PREFIX = "/subscriptions/" + ENV["AZURE_SUBSCRIPTION_ID"] + "/resourceGroups/rg-network/providers/Microsoft.Network/"
POLICY = PREFIX + "firewallPolicies/deployment-policy"
VNET = PREFIX + "virtualNetworks/workload"
SOURCES = {"containerapp": ["10.20.1.0/24"], "azure.ai.agent": ["10.20.2.0/24"]}


def plan(**environment):
    return declaration_plan(ROOT, {**ENV, **environment}, SOURCE)


def context_env(mode="managed"):
    return {
        **ENV, "VNET_RESOURCE_ID": VNET,
        "HOSTED_AGENT_DEPLOYMENT": json.dumps({"workloadEgress": {
            "networkIsolation": True,
            "managedFirewallPolicyId": POLICY if mode == "managed" else "",
            "subnets": {
                "containerapp": VNET + "/subnets/aca",
                "azure.ai.agent": VNET + "/subnets/agents",
            },
        }}),
    }


def group(properties):
    return {
        "id": POLICY + "/ruleCollectionGroups/" + GROUP_NAME, "name": GROUP_NAME,
        "etag": 'W/"revision-1"',
        "properties": {**copy.deepcopy(properties), "provisioningState": "Succeeded"},
    }


class FakeNetwork:
    def __init__(self, current=None):
        self.current = current
        self.calls = []
        self.concurrent = False
        self.list_count = 0
        self.other_groups = []

    def request(self, method, resource_id, **kwargs):
        self.calls.append((method, resource_id, kwargs))
        if resource_id.endswith("/subnets/aca"):
            return {"id": resource_id, "properties": {"addressPrefixes": SOURCES["containerapp"]}}
        if resource_id.endswith("/subnets/agents"):
            return {"id": resource_id, "properties": {"addressPrefix": SOURCES["azure.ai.agent"][0]}}
        if method == "get" and resource_id.endswith("/ruleCollectionGroups"):
            self.list_count += 1
            result = copy.deepcopy(self.current)
            if self.concurrent and self.list_count > 1:
                if result:
                    result["etag"] = 'W/"concurrent-revision"'
                else:
                    result = group({"priority": GROUP_PRIORITY, "ruleCollections": []})
            return {"value": copy.deepcopy(self.other_groups) + ([] if result is None else [result])}
        if method == "put":
            assert resource_id == POLICY + "/ruleCollectionGroups/" + GROUP_NAME
            self.current = group(kwargs["body"]["properties"])
            return self.current
        assert resource_id == POLICY + "/ruleCollectionGroups/" + GROUP_NAME
        return copy.deepcopy(self.current)


@pytest.mark.parametrize("key,value", [
    ("fqdn", "*"), ("fqdn", "*.example.com"), ("fqdn", "https://example.com"),
    ("fqdn", "example.com/path"), ("fqdn", "user@example.com"), ("fqdn", "example.com:443"),
    ("fqdn", "127.0.0.1"), ("fqdn", "::1"), ("fqdn", "localhost"),
    ("fqdn", "host.local"), ("fqdn", "host.internal"), ("fqdn", "example.com."),
    ("fqdn", "-bad.example.com"), ("fqdn", "a" * 64 + ".example.com"),
    ("fqdn", "exämple.com"), ("fqdn", "example.com\n"),
    ("protocol", "tcp"), ("protocol", "HTTPS"), ("protocol", None),
    ("port", 0), ("port", 64001), ("port", 65535), ("port", True),
    ("port", "443"), ("port", 1.5), ("purpose", ""), ("purpose", " "),
    ("purpose", "\ncontrol"), ("purpose", "x" * 257),
])
def test_invalid_requirement_has_component_json_pointer(key, value):
    definition = load_definition(ROOT / "app-definition.json", ROOT)
    document = copy.deepcopy(definition.document)
    document["components"][0]["egress"] = [{**REQUIREMENT, key: value}]
    issues = collect_issues(AppDefinition(definition.path, document, bundled=True), ROOT)
    assert issues
    assert all(issue.pointer.startswith("/components/0/egress/0") for issue in issues)


@pytest.mark.parametrize("value", [None, {}, "example.com", [None], [{"fqdn": "example.com"}]])
def test_invalid_declaration_shape(value):
    original = load_definition(ROOT / "app-definition.json", ROOT)
    document = copy.deepcopy(original.document)
    document["components"][0]["egress"] = value
    assert collect_issues(AppDefinition(original.path, document, bundled=True), ROOT)


def test_exact_hostname_normalization_http_and_boundary_ports():
    assert validate_requirement({**REQUIREMENT, "fqdn": "API.Example.COM"}).fqdn == "api.example.com"
    for port in (1, 80, 443, 64000):
        assert validate_requirement({**REQUIREMENT, "port": port, "protocol": "http"}).port == port


def test_schema_copy_and_hash_agree():
    import hashlib
    schema = ROOT / "contracts/app-definition-v1.schema.json"
    assert json.loads(schema.read_text()) == json.loads(
        (ROOT / "specs/002-agent-landing-zone-rebrand/contracts/app-definition.schema.json").read_text()
    )
    assert hashlib.sha256(schema.read_bytes()).hexdigest() == schema.with_suffix(".json.sha256").read_text().strip().split()[0]


def test_bundled_review_and_shared_tokenizer_requirement():
    selected = plan()
    by_id = {component["id"]: component for component in selected["components"]}
    assert by_id["agent-lz-default/ui"]["egress"] == []
    result = reconcile(selected, SOURCES, None)
    assert len(result["rules"]) == 1
    rule = result["rules"][0]
    assert rule["fqdn"] == REQUIREMENT["fqdn"] and rule["protocol"] == "https" and rule["port"] == 443
    assert {owner["component"] for owner in rule["owners"]} == {
        "agent-lz-default/orchestrator", "agent-lz-default/ingestion",
    }
    assert rule["sourceAddresses"] == SOURCES["containerapp"]


@pytest.mark.parametrize("hosted,preserve,ingestion", [
    (False, False, False), (False, False, True), (True, False, False),
    (True, False, True), (True, True, False), (True, True, True),
])
def test_actual_selection_source_union(hosted, preserve, ingestion):
    selected = plan(
        DEPLOYMENT_TOPOLOGY="hosted-no-panel" if hosted else "classic",
        HOSTED_AGENT_RESOURCE_SCOPE="api://application/.default",
        PRESERVE_CLASSIC_RUNTIME=str(preserve).lower(),
        DEPLOY_INGESTION_CONTAINER_APP=str(ingestion).lower(),
    )
    rule = reconcile(selected, SOURCES, None)["rules"][0]
    expected = set(SOURCES["azure.ai.agent"] if hosted else SOURCES["containerapp"])
    if ingestion or preserve:
        expected.update(SOURCES["containerapp"])
    assert set(rule["sourceAddresses"]) == expected
    assert len(rule["owners"]) == 1 + ingestion
    assert all("*" not in source for source in rule["sourceAddresses"])


@pytest.mark.parametrize("kind", ["containerapp", "azure.ai.agent"])
def test_custom_components_follow_additive_workload_selection(tmp_path, kind):
    (tmp_path / "web").mkdir()
    (tmp_path / "azure.yaml").write_text(
        f"name: custom\nservices:\n  web:\n    host: {kind}\n    project: ./web\n", encoding="utf-8",
    )
    definition = tmp_path / "app-definition.json"
    definition.write_text(json.dumps({
        "schemaVersion": 1, "id": "custom-app", "components": [{
            "name": "web", "kind": kind, "path": "web", "source": {"commit": "a" * 40},
            "egress": [REQUIREMENT, {**REQUIREMENT, "fqdn": "api.example.com"}],
        }],
    }), encoding="utf-8")
    selected = plan(AGENTLZ_APP_DEFINITION=str(definition), DEPLOY_INGESTION_CONTAINER_APP="false")
    assert selected["applicationId"] == "custom-app"
    assert {item["id"] for item in selected["components"]} == {
        "agent-lz-default/ui", "agent-lz-default/orchestrator", "agent-lz-default/ingestion", "custom-app/web",
    }
    result = reconcile(selected, SOURCES, None)
    assert len(result["rules"]) == 2
    shared = next(rule for rule in result["rules"] if rule["fqdn"] == REQUIREMENT["fqdn"])
    assert len(shared["owners"]) == 3
    assert set(shared["sourceAddresses"]) == set(SOURCES["containerapp"] + SOURCES[kind])


def test_reconcile_preserves_shared_requirement_then_removes_final_owner():
    original = plan()
    current = group(reconcile(original, SOURCES, None)["properties"])
    selected = plan(DEPLOY_INGESTION_CONTAINER_APP="false")
    remaining = reconcile(selected, SOURCES, current)
    assert remaining["removed"] == [] and len(remaining["updated"]) == 1
    assert [owner["component"] for owner in remaining["rules"][0]["owners"]] == ["agent-lz-default/orchestrator"]
    for component in selected["components"]:
        component["egress"] = []
    removed = reconcile(selected, SOURCES, group(remaining["properties"]))
    assert len(removed["removed"]) == 1
    assert removed["properties"] == {"priority": GROUP_PRIORITY, "ruleCollections": []}


def test_legacy_absent_preserves_existing_ownership_but_fresh_legacy_adds_nothing():
    selected = plan()
    current = group(reconcile(selected, SOURCES, None)["properties"])
    for component in selected["components"]:
        component.pop("egress")
    assert reconcile(selected, SOURCES, None)["rules"] == []
    assert not reconcile(selected, SOURCES, current)["changed"]
    assert len(reconcile(selected, SOURCES, current)["rules"][0]["owners"]) == 2
    selected["components"] = []
    assert len(reconcile(selected, SOURCES, current)["removed"]) == 1


def test_unrelated_rules_collections_and_inputs_are_preserved_exactly():
    selected = plan()
    current = group(reconcile(selected, SOURCES, None)["properties"])
    unrelated_rule = {"name": "runtime-operator-rule", "ruleType": "NetworkRule", "destinationPorts": ["123"]}
    current["properties"]["ruleCollections"][0]["rules"].insert(0, unrelated_rule)
    unrelated_collection = {
        "name": "operator-deny", "priority": 200, "action": {"type": "Deny"},
        "ruleCollectionType": "FirewallPolicyFilterRuleCollection", "rules": [unrelated_rule],
    }
    current["properties"]["ruleCollections"].append(unrelated_collection)
    before = copy.deepcopy(current)
    for component in selected["components"]:
        component["egress"] = []
    result = reconcile(selected, SOURCES, current)
    assert current == before
    assert result["properties"]["ruleCollections"][0]["rules"] == [unrelated_rule]
    assert result["properties"]["ruleCollections"][1] == unrelated_collection


def test_unrelated_null_description_is_preserved_when_owned_rules_are_removed():
    selected = plan()
    current = group(reconcile(selected, SOURCES, None)["properties"])
    unrelated = {
        "name": "operator-exception", "description": None, "ruleType": "ApplicationRule",
        "protocols": [{"protocolType": "Https", "port": 443}],
        "targetFqdns": ["operator.example.com"], "sourceAddresses": ["10.88.0.0/24"],
    }
    current["properties"]["ruleCollections"][0]["rules"].insert(0, unrelated)
    before = copy.deepcopy(current)
    selected["components"] = []
    report = reconcile(selected, SOURCES, current)
    assert current == before
    assert report["properties"]["ruleCollections"][0]["rules"] == [unrelated]
    assert not reconcile(selected, SOURCES, group(report["properties"]))["changed"]


def test_reserved_priority_collision_is_actionable_without_writes():
    client = FakeNetwork()
    client.other_groups = [{
        "name": "operator-group", "properties": {"priority": GROUP_PRIORITY},
    }]
    with pytest.raises(ValueError, match=f"priority {GROUP_PRIORITY}"):
        egress.review_or_apply(plan(), context_env(), apply=True, client=client)
    assert not any(call[0] == "put" for call in client.calls)


@pytest.mark.parametrize("mutation", [
    lambda c: c["properties"].update(priority=301),
    lambda c: c["properties"]["ruleCollections"][0].update(action={"type": "Deny"}),
    lambda c: c["properties"]["ruleCollections"][0]["rules"][0].update(description="unowned"),
    lambda c: c["properties"]["ruleCollections"][0]["rules"][0].update(sourceAddresses=["0.0.0.0/0"]),
    lambda c: c["properties"]["ruleCollections"][0]["rules"][0].update(targetUrls=["https://other.example"]),
    lambda c: c["properties"]["ruleCollections"][0]["rules"][0].update(description="agent-lz-egress/v1:agent-lz-default:broken"),
])
def test_ownership_collisions_and_tampering_fail_closed(mutation):
    selected = plan()
    current = group(reconcile(selected, SOURCES, None)["properties"])
    mutation(current)
    with pytest.raises(ValueError):
        reconcile(selected, SOURCES, current)


def test_azure_empty_optional_fields_are_a_noop_not_an_endless_update():
    selected = plan()
    current = group(reconcile(selected, SOURCES, None)["properties"])
    current["properties"]["ruleCollections"][0]["rules"][0].update(
        targetUrls=[], sourceIpGroups=[], fqdnTags=[], terminateTLS=False,
    )
    assert not reconcile(selected, SOURCES, current)["changed"]


@pytest.mark.parametrize("owners", [[""], ["malformed"], ["valid-app/web", "valid-app/web"], [1], []])
def test_malformed_owner_ids_do_not_authorize_rule_removal(owners):
    selected = plan()
    current = group(reconcile(selected, SOURCES, None)["properties"])
    current["properties"]["ruleCollections"][0]["rules"][0]["description"] = (
        "agent-lz-egress/v1:agent-lz-default:" + canonical(owners)
    )
    with pytest.raises(ValueError, match="owners"):
        reconcile(selected, SOURCES, current)


def test_case_insensitive_unowned_rule_name_collision_is_not_adopted():
    selected = plan()
    current = group(reconcile(selected, SOURCES, None)["properties"])
    rule = current["properties"]["ruleCollections"][0]["rules"][0]
    rule.update(name=rule["name"].upper(), description="Operator-owned exception")
    with pytest.raises(ValueError, match="name collision"):
        reconcile(selected, SOURCES, current)


def test_managed_apply_is_child_only_scoped_idempotent_and_conditionally_guarded():
    selected = plan()
    client = FakeNetwork()
    report = egress.review_or_apply(selected, context_env(), apply=True, client=client)
    puts = [call for call in client.calls if call[0] == "put"]
    assert len(puts) == 1 and puts[0][2]["headers"] == ["If-None-Match=*"]
    assert report["rules"][0]["sourceAddresses"] == SOURCES["containerapp"]
    client.calls.clear()
    assert not egress.review_or_apply(selected, context_env(), apply=True, client=client)["changed"]
    assert not any(call[0] == "put" for call in client.calls)
    for component in selected["components"]:
        component["egress"] = []
    egress.review_or_apply(selected, context_env(), apply=True, client=client)
    assert [call for call in client.calls if call[0] == "put"][0][2]["headers"] == ['If-Match=W/"revision-1"']


@pytest.mark.parametrize("mode", ["none", "external"])
def test_report_only_modes_never_read_or_mutate_a_firewall(mode):
    selected = plan()
    selected["policyMode"] = mode
    client = FakeNetwork()
    egress.review_or_apply(selected, context_env(mode), apply=True, client=client)
    assert not any("firewall" in call[1].lower() or call[0] != "get" for call in client.calls)
    if mode == "none":
        assert client.calls == []


def test_read_only_review_does_not_mutate_managed_policy():
    client = FakeNetwork()
    egress.review_or_apply(plan(), context_env(), apply=False, client=client)
    assert all(call[0] == "get" for call in client.calls)


@pytest.mark.parametrize("existing", [False, True])
def test_concurrent_updates_fail_without_put(existing):
    selected = plan()
    current = group(reconcile(selected, SOURCES, None)["properties"]) if existing else None
    if existing:
        selected["components"][1]["egress"] = []
    client = FakeNetwork(current)
    client.concurrent = True
    with pytest.raises(ValueError, match="concurrent"):
        egress.review_or_apply(selected, context_env(), apply=True, client=client)
    assert not any(call[0] == "put" for call in client.calls)


def test_missing_etag_policy_owner_or_actual_subnet_fails_before_write():
    selected = plan()
    current = group(reconcile(selected, SOURCES, None)["properties"])
    current.pop("etag")
    selected["components"][1]["egress"] = []
    with pytest.raises(ValueError, match="ETag"):
        egress.review_or_apply(selected, context_env(), apply=True, client=FakeNetwork(current))
    with pytest.raises(ValueError, match="ownership"):
        egress.review_or_apply(selected, context_env("external"), apply=True, client=FakeNetwork())
    env = context_env()
    env["VNET_RESOURCE_ID"] = VNET + "-wrong"
    client = FakeNetwork()
    with pytest.raises(ValueError, match="subnet"):
        egress.review_or_apply(selected, env, apply=True, client=client)
    assert not client.calls


def test_source_prefix_change_during_review_fails_before_write():
    client = FakeNetwork()
    actual = client.request
    reads = 0

    def change_source(method, resource_id, **kwargs):
        nonlocal reads
        response = actual(method, resource_id, **kwargs)
        if resource_id.endswith("/subnets/aca"):
            reads += 1
            if reads > 1:
                response["properties"]["addressPrefixes"] = ["10.21.1.0/24"]
        return response

    client.request = change_source
    with pytest.raises(ValueError, match="subnet prefixes changed"):
        egress.review_or_apply(plan(), context_env(), apply=True, client=client)
    assert not any(call[0] == "put" for call in client.calls)


def test_post_write_verification_rejects_another_policy_group():
    client = FakeNetwork()
    actual = client.request

    def wrong_verification(method, resource_id, **kwargs):
        response = actual(method, resource_id, **kwargs)
        if method == "get" and resource_id.endswith("/" + GROUP_NAME):
            response["id"] = POLICY + "/ruleCollectionGroups/different"
        return response

    client.request = wrong_verification
    with pytest.raises(ValueError, match="different policy/group"):
        egress.review_or_apply(plan(), context_env(), apply=True, client=client)


def test_subnet_discovery_validates_actual_prefixes_not_assumed_defaults():
    client = Mock()
    resource_id = VNET + "/subnets/aca"
    client.request.return_value = {"id": resource_id, "properties": {"addressPrefixes": ["10.88.0.0/23", "fd00::/64"]}}
    selected = plan()
    context = json.loads(context_env()["HOSTED_AGENT_DEPLOYMENT"])["workloadEgress"]
    assert egress.resolve_sources(selected, context, context_env(), client) == {
        "containerapp": ["10.88.0.0/23", "fd00::/64"],
    }
    client.request.return_value["properties"]["addressPrefixes"] = ["0.0.0.0/0"]
    with pytest.raises(ValueError):
        egress.resolve_sources(selected, context, context_env(), client)


def test_cli_plan_is_offline_and_stale_plan_fails_before_azure(tmp_path, capsys):
    with patch.object(egress, "find_repo_root", return_value=ROOT), \
            patch.object(egress, "_plan_path", return_value=tmp_path / "plan.json"), \
            patch.dict(os.environ, ENV, clear=True), \
            patch.object(egress, "NetworkClient") as client:
        assert egress.main(["--plan", "--save"]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["declarationSha256"]
        client.assert_not_called()
        (tmp_path / "plan.json").write_text("{}")
        assert egress.main(["--apply"]) == 1
        client.assert_not_called()


@pytest.mark.parametrize("values", [[], {}, {"INVALID-KEY": "x"}, {"VALUE": True},
                                   {"VALUE": "\0"}, {"AZURE_ENV_NAME": "different"}])
def test_explicit_environment_rejects_invalid_local_settings(values):
    with patch.object(egress.subprocess, "run", return_value=subprocess.CompletedProcess(
        [], 0, stdout=json.dumps(values),
    )):
        with pytest.raises(ValueError):
            egress.selected_environment(ROOT, "selected")


def test_explicit_environment_is_local_and_does_not_inherit_stale_process_flags():
    with patch.object(egress.subprocess, "run", return_value=subprocess.CompletedProcess(
        [], 0, stdout=json.dumps({"NETWORK_ISOLATION": "false"}),
    )) as run:
        selected = egress.selected_environment(ROOT, "selected")
    assert selected == {"NETWORK_ISOLATION": "false", "AZURE_ENV_NAME": "selected"}
    assert run.call_args.args[0] == [
        "azd", "env", "get-values", "--environment", "selected", "--output", "json",
    ]


def test_destination_deduplication_preserves_different_protocols_ports_and_purposes():
    selected = plan()
    component = selected["components"][0]
    component["egress"] = [
        REQUIREMENT, {**REQUIREMENT, "fqdn": REQUIREMENT["fqdn"].upper(), "purpose": "Another caller"},
        {**REQUIREMENT, "port": 8443}, {**REQUIREMENT, "protocol": "http", "port": 80},
    ]
    report = reconcile(selected, SOURCES, None)
    assert len(report["rules"]) == 3
    shared = next(rule for rule in report["rules"] if rule["protocol"] == "https" and rule["port"] == 443)
    assert len(shared["owners"]) == 2
    assert "Another caller" in shared["owners"][0]["purpose"]


def test_network_cli_only_writes_reviewed_child_body_with_conditional_header(tmp_path):
    def run(command, **kwargs):
        body = json.loads(Path(command[command.index("--body") + 1][1:]).read_text())
        assert body == {"properties": {"priority": GROUP_PRIORITY, "ruleCollections": []}}
        assert command[command.index("--headers") + 1] == 'If-Match=W/"one"'
        assert command[command.index("--url") + 1] == POLICY + "/ruleCollectionGroups/" + GROUP_NAME + "?api-version=2024-07-01"
        return subprocess.CompletedProcess(command, 0, stdout="{}")
    with patch.object(egress.subprocess, "run", side_effect=run):
        egress.NetworkClient().request(
            "put", POLICY + "/ruleCollectionGroups/" + GROUP_NAME,
            body={"properties": {"priority": GROUP_PRIORITY, "ruleCollections": []}}, headers=['If-Match=W/"one"'],
        )


def test_management_access_and_conditional_write_failures_are_not_success():
    client = FakeNetwork()
    actual = client.request
    def fail_put(method, resource_id, **kwargs):
        if method == "put":
            raise RuntimeError("PreconditionFailed")
        return actual(method, resource_id, **kwargs)
    client.request = fail_put
    with pytest.raises(RuntimeError, match="PreconditionFailed"):
        egress.review_or_apply(plan(), context_env(), apply=True, client=client)
    with patch.object(egress.subprocess, "run", return_value=subprocess.CompletedProcess(
        [], 1, stderr="AuthorizationFailed",
    )):
        with pytest.raises(RuntimeError, match="AuthorizationFailed"):
            egress.NetworkClient().request("get", POLICY + "/ruleCollectionGroups")


def test_compiled_generic_handoff_does_not_create_new_resources_or_relax_firewall_gates(tmp_path):
    import shutil
    compiler = shutil.which("bicep")
    assert compiler, "Standalone Bicep is required for the foundation contract."
    result = subprocess.run(
        [compiler, "build", str(ROOT / "infra/bicep/main.bicep"), "--no-restore", "--stdout"],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stderr
    template = json.loads(result.stdout)
    assert len(template["outputs"]) <= 64
    handoff = template["outputs"]["HOSTED_AGENT_DEPLOYMENT"]["value"]["workloadEgress"]
    assert handoff["networkIsolation"] == "[variables('_networkIsolation')]"
    assert handoff["managedFirewallPolicyId"] == "[reference('firewall').outputs.policyResourceId.value]"
    for kind, parameter in (("containerapp", "acaEnvironmentSubnetName"), ("azure.ai.agent", "agentSubnetName")):
        expression = handoff["subnets"][kind]
        assert "parameters('useExistingVNet')" in expression
        assert "parameters('existingVnetResourceId')" in expression
        assert f"parameters('{parameter}')" in expression
    firewall = template["resources"]["firewall"]["properties"]["template"]
    assert firewall["outputs"]["policyResourceId"]["value"].startswith(
        "[if(and(parameters('deployAzureFirewall'), parameters('networkIsolation')), resourceId("
    )
    for name in ("firewallPolicy", "azureFirewall", "firewallPublicIp"):
        assert firewall["resources"][name]["condition"] == "[and(parameters('deployAzureFirewall'), parameters('networkIsolation'))]"
    assert GROUP_NAME not in json.dumps(firewall)
    assert REQUIREMENT["fqdn"] not in json.dumps(template)
    foundation_groups = [
        resource for resource in firewall["resources"].values()
        if resource["type"].lower() == "microsoft.network/firewallpolicies/rulecollectiongroups"
    ]
    assert {resource["properties"]["priority"] for resource in foundation_groups} == {200, 250, 300}
    assert GROUP_PRIORITY not in {resource["properties"]["priority"] for resource in foundation_groups}
    client = FakeNetwork()
    client.other_groups = copy.deepcopy(foundation_groups)
    before = copy.deepcopy(client.other_groups)
    egress.review_or_apply(plan(), context_env(), apply=True, client=client)
    assert client.other_groups == before
    assert len([call for call in client.calls if call[0] == "put"]) == 1


@pytest.mark.skipif(os.environ.get("AGENTLZ_TEST_TOKENIZER_COLD_CACHE") != "true",
                    reason="Explicit public HTTPS cold-cache check; no Azure access.")
def test_real_tokenizer_initialization_from_empty_cache(tmp_path):
    script = r'''
import importlib.metadata, json, os, pathlib, requests, tiktoken
from urllib.parse import urlsplit
cache = pathlib.Path(os.environ["TIKTOKEN_CACHE_DIR"])
assert importlib.metadata.version("tiktoken") in {"0.7.0", "0.14.0"}, "Use a runtime-pinned tiktoken version in an isolated validation environment."
assert not list(cache.iterdir())
actual = requests.get
downloads = []
def download(url, *args, **kwargs):
    parsed = urlsplit(url)
    assert parsed.scheme == "https" and parsed.hostname == "openaipublic.blob.core.windows.net"
    assert parsed.port in (None, 443)
    downloads.append(url)
    return actual(url, *args, **kwargs)
requests.get = download
models = ("text-embedding-3-large", "gpt-4o")
encodings = [tiktoken.encoding_for_model(model) for model in models]
for encoding in encodings:
    assert encoding.decode(encoding.encode("Cold-cache tokenizer initialization.")) == "Cold-cache tokenizer initialization."
assert len(downloads) == 2 and len(list(cache.iterdir())) == 2
print(json.dumps({"tiktoken": importlib.metadata.version("tiktoken"), "models": models,
                  "encodings": [item.name for item in encodings], "downloads": downloads}))
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "TIKTOKEN_CACHE_DIR": str(tmp_path)},
        capture_output=True, text=True, timeout=180, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["encodings"] == ["cl100k_base", "o200k_base"]
    print(canonical(evidence))
