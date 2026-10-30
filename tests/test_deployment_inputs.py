"""Offline contracts for provider selection and native Terraform input transport."""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from config.deployment.composition import compose_parameters, panel_database_containers
from config.deployment.app_settings import substitute_values
from config.deployment.provider import resolve_provider
from config.deployment.resolution import resolve_parameters
from config.deployment.terraform_inputs import compose_inputs, render_template

ROOT = Path(__file__).resolve().parents[1]
SUBSCRIPTION = "11111111-1111-1111-1111-111111111111"
ENVIRONMENT = {
    "AZURE_ENV_NAME": "fixture",
    "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION,
    "AZURE_TENANT_ID": "22222222-2222-2222-2222-222222222222",
    "AZURE_RESOURCE_GROUP": "rg-fixture",
    "AZURE_LOCATION": "swedencentral",
    "AZURE_COSMOS_LOCATION": "swedencentral",
    "AZURE_PRINCIPAL_ID": "33333333-3333-3333-3333-333333333333",
    "NETWORK_ISOLATION": "false",
    "USE_UAI": "true",
    "ENABLE_AGENTIC_RETRIEVAL": "false",
    "USE_EXISTING_VNET": "false",
    "SIDE_BY_SIDE": "true",
    "DEPLOYMENT_TOPOLOGY": "classic",
    "TF_STATE_RESOURCE_GROUP": "rg-independent-state",
    "TF_STATE_STORAGE_ACCOUNT": "fixturestate001",
    "TF_STATE_CONTAINER": "tfstate",
    "TF_STATE_SUBSCRIPTION_ID": SUBSCRIPTION,
    "ARM_ENVIRONMENT": "public",
}


def source() -> dict:
    return json.loads((ROOT / "main.parameters.json").read_text(encoding="utf-8"))


def values() -> dict:
    return {key: entry["value"] for key, entry in source()["parameters"].items()}


def test_embedding_defaults_match_tracked_bicep_seed():
    seed = json.loads(
        (ROOT / "infra/bicep/main.parameters.json").read_text(encoding="utf-8")
    )
    models = values()["modelDeploymentList"]
    assert models == seed["parameters"]["modelDeploymentList"]["value"]
    assert models[1] == {
        "name": "text-embedding",
        "model": {"format": "OpenAI", "name": "text-embedding-3-large", "version": "1"},
        "sku": {"name": "GlobalStandard", "capacity": 100},
        "canonical_name": "EMBEDDING_DEPLOYMENT_NAME",
        "apiVersion": "2025-01-01-preview",
    }


@pytest.mark.parametrize("selection", ["default", "standard", "empty"])
def test_embedding_sku_survives_both_provider_input_adapters(selection):
    template = source()
    models = template["parameters"]["modelDeploymentList"]["value"]
    if selection == "standard":
        models[1]["sku"]["name"] = "Standard"
    elif selection == "empty":
        models.clear()
    before = copy.deepcopy(template)
    terraform = compose_inputs(
        {key: entry["value"] for key, entry in template["parameters"].items()},
        ENVIRONMENT,
    )
    bicep = compose_parameters(template, ENVIRONMENT)["parameters"]
    assert terraform["modelDeploymentList"] == models
    assert bicep["modelDeploymentList"]["value"] == models
    assert template == before
    if selection == "default":
        assert terraform["modelDeploymentList"][1]["sku"] == {
            "name": "GlobalStandard", "capacity": 100,
        }


@pytest.mark.parametrize("topology", ["classic", "hosted-panel", "hosted-no-panel"])
def test_common_resolution_preserves_bicep_composition(topology):
    environment = {
        **ENVIRONMENT, "DEPLOYMENT_TOPOLOGY": topology,
        "HOSTED_AGENT_RESOURCE_SCOPE": "api://fixture/.default",
    }
    original = values()
    # This boundary receives data, not deployment expressions. The adapters
    # resolve explicit settings placeholders exactly once before the merge.
    original["additionalAppConfigurationSettings"] = substitute_values(
        original["additionalAppConfigurationSettings"], environment,
    )
    before = copy.deepcopy(original)
    resolved = resolve_parameters(original, environment)
    expected = compose_parameters(source(), environment)["parameters"]
    assert resolved == {key: entry["value"] for key, entry in expected.items()}
    assert original == before


@pytest.mark.parametrize("topology,enabled", [
    ("classic", True), ("hosted-panel", True), ("hosted-no-panel", False),
])
@pytest.mark.parametrize("ingestion", ["true", "false"])
def test_cosmos_is_selected_by_consumers_in_both_providers(topology, enabled, ingestion):
    environment = {
        **ENVIRONMENT, "DEPLOYMENT_TOPOLOGY": topology,
        "DEPLOY_INGESTION_CONTAINER_APP": ingestion,
        "HOSTED_AGENT_RESOURCE_SCOPE": "api://fixture/.default",
    }
    bicep = compose_parameters(source(), environment)["parameters"]
    terraform = compose_inputs(values(), environment)
    assert bicep["deployCosmosDb"]["value"] is enabled
    assert terraform["deployCosmosDb"] is enabled
    assert terraform["databaseContainersList"] == bicep["databaseContainersList"]["value"]
    assert bool(terraform["databaseContainersList"]) is enabled
    assert bicep["deployAAfAgentSvc"]["value"] == "${DEPLOY_AAF_AGENT_SVC=true}"
    assert terraform["deployAAfAgentSvc"] is True
    assert terraform["aiFoundryCosmosDBAccountResourceId"] is None


@pytest.mark.parametrize("selection,enabled", [("true", True), ("false", False)])
def test_hosted_cosmos_explicit_opt_in_and_opt_out(selection, enabled):
    environment = {
        **ENVIRONMENT, "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
        "HOSTED_AGENT_RESOURCE_SCOPE": "api://fixture/.default",
        "DEPLOY_COSMOS_DB": selection,
    }
    assert compose_parameters(source(), environment)["parameters"]["deployCosmosDb"]["value"] is enabled
    assert compose_inputs(values(), environment)["deployCosmosDb"] is enabled


@pytest.mark.parametrize("topology", ["classic", "hosted-panel", "hosted-no-panel"])
def test_required_cosmos_cannot_be_explicitly_disabled(topology):
    environment = {
        **ENVIRONMENT, "DEPLOYMENT_TOPOLOGY": topology,
        "HOSTED_AGENT_RESOURCE_SCOPE": "api://fixture/.default",
        "DEPLOY_COSMOS_DB": "false",
    }
    if topology == "hosted-no-panel":
        environment["PRESERVE_CLASSIC_RUNTIME"] = "true"
    with pytest.raises(ValueError, match="DEPLOY_COSMOS_DB=false conflicts"):
        compose_parameters(source(), environment)
    with pytest.raises(ValueError, match="DEPLOY_COSMOS_DB=false conflicts"):
        compose_inputs(values(), environment)


@pytest.mark.parametrize("selection", ["", "yes", "1", "invalid"])
def test_cosmos_selection_rejects_non_boolean_values(selection):
    environment = {**ENVIRONMENT, "DEPLOY_COSMOS_DB": selection}
    with pytest.raises(ValueError, match="DEPLOY_COSMOS_DB must be"):
        compose_parameters(source(), environment)
    with pytest.raises(ValueError, match="deployCosmosDb|DEPLOY_COSMOS_DB"):
        compose_inputs(values(), environment)


@pytest.mark.parametrize("kind", ["containerapp", "azure.ai.agent"])
@pytest.mark.parametrize("topology", ["hosted-no-panel", "hosted-panel"])
def test_custom_conversation_store_retains_its_containers(tmp_path, kind, topology):
    definition = tmp_path / "app-definition.json"
    definition.write_text(json.dumps({
        "id": "custom-cosmos",
        "components": [{
            "name": "worker", "path": "worker", "kind": kind,
            "profiles": ["conversation-store"],
        }],
    }), encoding="utf-8")
    environment = {
        **ENVIRONMENT, "DEPLOYMENT_TOPOLOGY": topology,
        "HOSTED_AGENT_RESOURCE_SCOPE": "api://fixture/.default",
        "AGENTLZ_APP_DEFINITION": str(definition),
    }
    bicep = compose_parameters(source(), environment)["parameters"]
    terraform = compose_inputs(values(), environment)
    assert bicep["deployCosmosDb"]["value"] is True
    assert terraform["deployCosmosDb"] is True
    assert terraform["databaseContainersList"] == bicep["databaseContainersList"]["value"]
    expected_names = {container["name"] for container in values()["databaseContainersList"]}
    assert expected_names <= {container["name"] for container in terraform["databaseContainersList"]}
    if topology == "hosted-panel":
        assert {container["name"] for container in panel_database_containers()} <= {
            container["name"] for container in terraform["databaseContainersList"]
        }
    environment["DEPLOY_COSMOS_DB"] = "false"
    with pytest.raises(ValueError, match="DEPLOY_COSMOS_DB=false conflicts"):
        compose_parameters(source(), environment)
    with pytest.raises(ValueError, match="DEPLOY_COSMOS_DB=false conflicts"):
        compose_inputs(values(), environment)


def test_custom_component_without_cosmos_capability_does_not_enable_storage():
    environment = {
        **ENVIRONMENT, "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
        "HOSTED_AGENT_RESOURCE_SCOPE": "api://fixture/.default",
        "AGENTLZ_APP_DEFINITION": "samples/custom-app/containerapp",
    }
    assert compose_parameters(source(), environment)["parameters"]["deployCosmosDb"]["value"] is False
    assert compose_inputs(values(), environment)["deployCosmosDb"] is False


def test_native_types_context_collections_and_no_arm_envelope():
    original = values()
    original["acrTaskAgentPoolCount"] = "3"
    original["dbDatabaseThroughput"] = "1200"
    original["deployBastion"] = "null"
    result = compose_inputs(original, ENVIRONMENT)
    assert result["networkIsolation"] is False
    assert result["useUAI"] is True
    assert result["acrTaskAgentPoolCount"] == 3
    assert type(result["acrTaskAgentPoolCount"]) is int
    assert result["dbDatabaseThroughput"] == 1200
    assert result["deployBastion"] is None
    assert result["modelDeploymentList"] == original["modelDeploymentList"]
    assert result["subscriptionId"] == SUBSCRIPTION
    assert result["tenantId"] == ENVIRONMENT["AZURE_TENANT_ID"]
    assert result["resourceGroupName"] == "rg-fixture"
    assert result["deploymentName"] == "fixture"
    assert result["vmAdminPassword"] is None  # root owns persistent generation
    assert "parameters" not in result
    assert "aiFoundryLocation" not in result  # not a declared infrastructure input
    assert result["createResourceGroup"] is False  # BYO by default, safe down
    assert result["createApplicationResourceGroup"] is False
    assert result["createNetworkResourceGroup"] is False


def test_all_declared_inputs_are_accepted_with_native_types():
    # Test the current executable interface, not a copied baseline inventory.
    declarations = re.findall(r"^param (\w+) ([\w.\[\]?]+)", (ROOT / "infra/bicep/main.bicep").read_text(), re.M)
    assert len(declarations) == 217
    original = values()
    for name, kind in declarations:
        if name in original:
            continue
        if kind.startswith("bool"):
            original[name] = None if kind.endswith("?") else True
        elif kind.startswith("int"):
            original[name] = 2
        elif kind.endswith("[]") or kind == "array":
            original[name] = []
        else:
            original[name] = "fixture"
    result = compose_inputs(original, ENVIRONMENT)
    assert {name for name, _ in declarations} <= result.keys()


@pytest.mark.parametrize("sku", ["Basic", "Standard"])
@pytest.mark.parametrize("isolation,local", [(False, True), (True, True), (True, False)])
def test_firewall_selection_is_identical_in_provider_transports(sku, isolation, local):
    environment = {
        **ENVIRONMENT,
        "NETWORK_ISOLATION": str(isolation).lower(),
        "DEPLOY_AZURE_FIREWALL": str(local).lower(),
        "AZURE_FIREWALL_SKU": sku,
        "DEPLOYMENT_MODE": "standalone" if local else "ailz-integrated",
    }
    bicep = compose_parameters(source(), environment)["parameters"]
    terraform = compose_inputs(values(), environment)
    expected = {
        "azureFirewallSku": sku,
        "deployAzureFirewallSubnet": isolation and local,
        "deployAzureFirewallManagementSubnet": isolation and local and sku == "Basic",
        "deployGatewaySubnet": False,
    }
    for name, value in expected.items():
        assert bicep[name]["value"] == value
        assert terraform[name] == value


def test_json_transport_round_trips_arbitrary_values_without_native_substitution():
    original = values()
    text = 'quotes " slash \\ newline\nUnicode: café; ${NOT_AN_ENV}; $HOME; $(x)'
    original["deploymentTags"] = {"literal": text}
    original["modelDeploymentList"][0]["extension"] = {"open": [True, None, 2.5, text]}
    environment = {**ENVIRONMENT, "HOSTED_AGENT_BASE_URL": text}
    result = compose_inputs(original, environment)
    template = render_template(result)
    assert "$" not in template  # native azd envsubst has nothing to substitute
    assert json.loads(template) == result
    assert result["deploymentTags"]["literal"] == text
    assert result["modelDeploymentList"][0]["extension"]["open"][-1] == text


def test_store_strings_are_not_recursively_substituted_and_json_arrays_are_typed():
    original = values()
    original["allowedIpRanges"] = "${TEST_IP_RANGES}"
    environment = {
        **ENVIRONMENT, "TEST_IP_RANGES": '["203.0.113.0/24"]',
        "FOUNDRY_IQ_BASE_FILTER": "${LITERAL_NOT_AN_ENV}",
        "HOSTED_AGENT_BASE_URL": "${LITERAL_NOT_AN_ENV}",
    }
    result = compose_inputs(original, environment)
    assert result["allowedIpRanges"] == ["203.0.113.0/24"]
    assert result["foundryIqBaseFilter"] == "${LITERAL_NOT_AN_ENV}"
    settings = {item["name"]: item["value"] for item in result["additionalAppConfigurationSettings"]}
    assert settings["HOSTED_AGENT_BASE_URL"] == "${LITERAL_NOT_AN_ENV}"
    assert "$" not in render_template(result)


def test_settings_preserve_labels_and_reject_reserved_or_duplicate_keys():
    original = values()
    original["additionalAppConfigurationSettings"] = [
        {"name": "CUSTOM", "value": "a", "label": "other", "contentType": "application/json"},
        {"name": "CUSTOM", "value": "b", "label": ""},
    ]
    settings = compose_inputs(original, ENVIRONMENT)["additionalAppConfigurationSettings"]
    assert original["additionalAppConfigurationSettings"][0] in settings
    assert {**original["additionalAppConfigurationSettings"][1], "contentType": "text/plain"} in settings
    for entry in (
        {"name": "COSMOS_DB_ENDPOINT", "value": "unsafe"},
        {"name": "ORCHESTRATOR_APP_APIKEY", "value": "unsafe"},
    ):
        original["additionalAppConfigurationSettings"] = [entry]
        with pytest.raises(ValueError, match="reserved"):
            compose_inputs(original, ENVIRONMENT)
    original["additionalAppConfigurationSettings"] = [
        {"name": "CUSTOM", "value": "a"},
        {"name": "CUSTOM", "value": "b", "label": "agent-lz"},
    ]
    with pytest.raises(ValueError, match="Duplicate"):
        compose_inputs(original, ENVIRONMENT)


@pytest.mark.parametrize("name,value,match", [
    ("networkIsolation", "yes", "networkIsolation"),
    ("acrTaskAgentPoolCount", "1.5", "acrTaskAgentPoolCount"),
    ("unexpectedInput", True, "Unknown"),
    ("aiFoundryLocation", "different-region", "aiFoundryLocation"),
])
def test_invalid_inputs_fail_explicitly(name, value, match):
    original = values()
    original[name] = value
    with pytest.raises(ValueError, match=match):
        compose_inputs(original, ENVIRONMENT)


def test_hosted_guards_and_custom_apps_and_images_remain_common():
    with pytest.raises(ValueError, match="HOSTED_AGENT_RESOURCE_SCOPE"):
        compose_inputs(values(), {**ENVIRONMENT, "DEPLOYMENT_TOPOLOGY": "hosted-panel"})
    result = compose_inputs(values(), {
        **ENVIRONMENT, "AGENTLZ_APP_DEFINITION": "samples/custom-app/containerapp",
    }, existing_images={"web": "example.azurecr.io/web@sha256:" + "a" * 64})
    assert next(app for app in result["containerAppsList"] if app["service_name"] == "web")["image"].startswith("example.azurecr.io/")


def test_group_ownership_is_explicit_and_bound_to_selected_destinations():
    environment = {
        **ENVIRONMENT, "CREATE_RESOURCE_GROUPS": "true",
        "AZURE_APP_RESOURCE_GROUP": "rg-fixture-app",
        "AZURE_NETWORK_RESOURCE_GROUP": "rg-fixture-network",
    }
    with pytest.raises(ValueError, match="ownership"):
        compose_inputs(values(), environment)
    result = compose_inputs(values(), environment, managed_resource_group_names=["rg-fixture", "rg-fixture-app"])
    assert result["createResourceGroup"] is True
    assert result["createApplicationResourceGroup"] is True
    assert result["createNetworkResourceGroup"] is False
    assert "managedResourceGroupNames" not in result  # local assertion, not a root variable
    assert result["applicationResourceGroupName"] == "rg-fixture-app"
    with pytest.raises(ValueError, match="destination"):
        compose_inputs(values(), environment, managed_resource_group_names=["rg-unrelated"])
    with pytest.raises(ValueError, match="CREATE_RESOURCE_GROUPS"):
        compose_inputs(values(), ENVIRONMENT, managed_resource_group_names=["rg-fixture"])


def test_aliased_groups_are_managed_exactly_once():
    environment = {
        **ENVIRONMENT, "CREATE_RESOURCE_GROUPS": "true",
        "AZURE_APP_RESOURCE_GROUP": "rg-shared",
        "AZURE_NETWORK_RESOURCE_GROUP": "rg-shared",
    }
    result = compose_inputs(values(), environment, managed_resource_group_names=["RG-SHARED"])
    # Root requires matching flags, and deduplicates the actual resource key.
    assert result["createApplicationResourceGroup"] is True
    assert result["createNetworkResourceGroup"] is True
    environment["AZURE_NETWORK_RESOURCE_GROUP"] = "RG-SHARED"
    result = compose_inputs(values(), environment, managed_resource_group_names=["rg-shared"])
    assert result["networkResourceGroupName"] == result["applicationResourceGroupName"] == "rg-shared"


def test_missing_principal_requires_explicit_materialization_not_os_fallback(monkeypatch):
    environment = {key: value for key, value in ENVIRONMENT.items() if key != "AZURE_PRINCIPAL_ID"}
    monkeypatch.setenv("AZURE_PRINCIPAL_ID", ENVIRONMENT["AZURE_PRINCIPAL_ID"])
    with pytest.raises(ValueError, match="AZURE_PRINCIPAL_ID"):
        compose_inputs(values(), environment)


def test_provider_defaults_and_native_custom_path(tmp_path):
    (tmp_path / "azure.yaml").write_text("name: fixture\n", encoding="utf-8")
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra/main.bicep").touch()
    selected = resolve_provider(tmp_path)
    assert selected == {
        "provider": "bicep", "path": "infra", "module": "main",
        "entrypoint": str((tmp_path / "infra/main.bicep").resolve()),
    }
    (tmp_path / "azure.yaml").write_text('infra: {provider: terraform, path: "custom tf", module: foundation}\n', encoding="utf-8")
    (tmp_path / "custom tf").mkdir()
    (tmp_path / "custom tf/foundation.tf").touch()
    assert resolve_provider(tmp_path)["entrypoint"] == str((tmp_path / "custom tf/foundation.tf").resolve())
    (tmp_path / "azure.yaml").write_text(
        'infra: {provider: bicep, path: "custom bicep", module: platform}\n',
        encoding="utf-8",
    )
    (tmp_path / "custom bicep").mkdir()
    (tmp_path / "custom bicep/platform.bicep").touch()
    assert resolve_provider(tmp_path)["entrypoint"] == str((tmp_path / "custom bicep/platform.bicep").resolve())


def test_checked_in_project_selects_moved_bicep_entrypoint():
    selected = resolve_provider(ROOT)
    assert selected == {
        "provider": "bicep", "path": "infra/bicep", "module": "main",
        "entrypoint": str((ROOT / "infra/bicep/main.bicep").resolve()),
    }


@pytest.mark.parametrize("configuration", [
    "infra: {provider: arm}", "infra: {provider: terraform, path: missing}",
    "infra: {provider: ''}", "infra: {path: ../outside}", "infra: []",
    "infra: {module: ../outside}", "infra: {provider: '${PROVIDER}'}",
])
def test_provider_rejects_invalid_or_missing_selected_entrypoints(tmp_path, configuration):
    (tmp_path / "azure.yaml").write_text(configuration, encoding="utf-8")
    with pytest.raises(ValueError):
        resolve_provider(tmp_path)


def test_cli_uses_explicit_azd_store_snapshot_and_never_logs_values(tmp_path):
    # Native preparation now persists an environment-local backend binding.
    # Give the subprocess an isolated, valid project rather than the worktree.
    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "azure.yaml").write_text("name: fixture\n")
    environment_dir = tmp_path / ".azure/fixture"
    environment_dir.mkdir(parents=True)
    (environment_dir / ".env").touch()
    environment = {**ENVIRONMENT, "AGENTLZ_REPO_ROOT": str(tmp_path)}
    snapshot = tmp_path / "environment.json"
    snapshot.write_text(json.dumps(environment), encoding="utf-8")
    output = tmp_path / "main.tfvars.json"
    diagnostic = tmp_path / "diagnostic.parameters.json"
    command = [
        sys.executable, "-m", "config.deployment.terraform_inputs",
        "--input", str(ROOT / "main.parameters.json"),
        "--environment", str(snapshot), "--output", str(output),
        "--diagnostic-output", str(diagnostic),
        "--no-preserve-images",
    ]
    # Explicit native process-auth mode plus an explicit principal requires no
    # CLI login or token to exercise offline preparation/rendering.
    process_environment = {**os.environ, "ARM_USE_OIDC": "true", "ARM_ENVIRONMENT": "public"}
    for key in ("ARM_ACCESS_KEY", "ARM_SAS_TOKEN"):
        process_environment.pop(key, None)
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, env=process_environment)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text())["networkIsolation"] is False
    native = json.loads(output.read_text())
    diagnostic_values = json.loads(diagnostic.read_text())["parameters"]
    assert diagnostic_values
    assert all(entry["value"] == native[name] for name, entry in diagnostic_values.items())
    assert "subscriptionId" not in diagnostic_values
    assert "33333333" not in completed.stdout + completed.stderr
    environment["NETWORK_ISOLATION"] = "sensitive-invalid-value"
    snapshot.write_text(json.dumps(environment), encoding="utf-8")
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, env=process_environment)
    assert completed.returncode != 0
    assert "networkIsolation" in completed.stderr
    assert "sensitive-invalid-value" not in completed.stderr


def test_provider_cli_parent_flag():
    completed = subprocess.run(
        [sys.executable, "-m", "config.deployment.provider", "--repo-root", str(ROOT)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["provider"] in ("bicep", "terraform")


def test_catalogue_types_match_the_entire_current_interface():
    from config.deployment.input_types import INPUT_TYPES

    declarations = re.findall(r"^param (\w+) ([\w.\[\]?]+)", (ROOT / "infra/bicep/main.bicep").read_text(), re.M)
    expected = {}
    for name, kind in declarations:
        expected[name] = (
            "array" if kind == "array" or kind.endswith("[]")
            else "bool" if kind.startswith("bool")
            else "int" if kind.startswith("int")
            else "object" if kind in ("object", "hostedAgentConfigurationType", "publicIngressType")
            else "string"
        )
    assert INPUT_TYPES == expected


def test_existing_vnet_context_and_tenant_aliases():
    foreign = "44444444-4444-4444-4444-444444444444"
    environment = {**ENVIRONMENT, "EXISTING_VNET_RESOURCE_ID": (
        f"/subscriptions/{foreign}/resourceGroups/shared/providers/Microsoft.Network/virtualNetworks/shared"
    )}
    result = compose_inputs(values(), environment)
    assert result["existingVnetSubscriptionId"] == foreign
    environment["TENANT_ID"] = foreign
    with pytest.raises(ValueError, match="conflict"):
        compose_inputs(values(), environment)
