"""Provider metadata is a bound, non-secret setup interface, not a settings bag."""

import copy
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from config.deployment import metadata

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def candidate(request):
    source = (
        ROOT / "tests" / "fixtures" / "deployment-metadata-v1.json"
    ).read_text(encoding="utf-8")
    group = getattr(request, "param", "rg-example")
    document = json.loads(source.replace("/resourceGroups/rg-example/", f"/resourceGroups/{group}/"))
    document["context"]["resourceGroups"]["foundry"] = group
    return document


def test_closed_shape_accepts_disabled_slots_and_system_identity(candidate):
    metadata.validate_shape(candidate)
    candidate["containerApps"][0]["identity"]["clientId"] = "33333333-3333-3333-3333-333333333333"
    with pytest.raises(metadata.MetadataError, match="schema"):
        metadata.validate_shape(candidate)


@pytest.mark.parametrize("change", [
    lambda d: d.update(schemaVersion=2),
    lambda d: d.update(secret="canary-secret"),
    lambda d: d["resources"]["appConfig"].update(resource={}),
    lambda d: d["resources"]["registry"]["resource"].update(endpoint="https://user:canary@example.azurecr.io"),
    lambda d: d["modelDeployments"][0].update(endpoint="https://example.openai.azure.com/?token=canary"),
    lambda d: d["containerApps"].append(copy.deepcopy(d["containerApps"][0])),
])
def test_bad_shapes_do_not_disclose_values(candidate, change):
    change(candidate)
    with pytest.raises(metadata.MetadataError) as error:
        metadata.validate_shape(candidate)
    assert "canary" not in str(error.value)


@pytest.mark.parametrize("declaration", [
    '', 'output "DEPLOYMENT_METADATA" { value = {} }',
    'output "DEPLOYMENT_METADATA" { value = {} sensitive = true }',
    'output "DEPLOYMENT_METADATA" { value = {} sensitive = var.safe }',
    'output "DEPLOYMENT_METADATA" { value = {} sensitive = false }\n'
    'output "DEPLOYMENT_METADATA" { value = {} sensitive = false }',
    'output "DEPLOYMENT_METADATA" { value = nonsensitive(var.secret) sensitive = false }',
    'output "DEPLOYMENT_METADATA" { value = ',
])
def test_terraform_source_rejected_before_value_request(tmp_path, declaration):
    (tmp_path / "outputs.tf").write_text(declaration, encoding="utf-8")
    with pytest.raises(metadata.MetadataError, match="source"):
        metadata.approve_terraform_source(tmp_path)


def test_terraform_literal_false_and_unrelated_sensitive_output(tmp_path):
    (tmp_path / "outputs.tf").write_text(
        'output "DEPLOYMENT_METADATA" { value = local.metadata sensitive = false }\n'
        'output "password" { value = var.password sensitive = true }\n',
        encoding="utf-8",
    )
    metadata.approve_terraform_source(tmp_path)


@pytest.mark.parametrize("reference", ["local.binding", 'local["binding"]'])
def test_terraform_transitive_declassification_rejected(tmp_path, reference):
    (tmp_path / "outputs.tf").write_text(
        'output "DEPLOYMENT_METADATA" { value = local.metadata sensitive = false }\n'
        f'locals {{ metadata = {reference} binding = nonsensitive(var.secret) }}\n',
        encoding="utf-8",
    )
    with pytest.raises(metadata.MetadataError, match="source"):
        metadata.approve_terraform_source(tmp_path)


@pytest.mark.parametrize("failure", [
    subprocess.CompletedProcess(["az"], 1, "canary-secret", "canary-secret"),
    subprocess.TimeoutExpired(["az"], 1, output="canary-secret"),
    subprocess.CompletedProcess(["az"], 0, "canary-secret", ""),
])
def test_command_errors_are_redacted(monkeypatch, failure):
    def run(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return failure
    monkeypatch.setattr(metadata.subprocess, "run", run)
    with pytest.raises(metadata.MetadataError) as error:
        metadata.run_json(["az", "resource", "show"])
    assert "canary" not in str(error.value)


def test_bicep_requests_only_named_output_and_success(candidate):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return "Succeeded" if command[command.index("--query") + 1] == "properties.provisioningState" else candidate

    environment = {
        "AZURE_SUBSCRIPTION_ID": candidate["context"]["subscriptionId"],
        "AZURE_RESOURCE_GROUP": "rg-example",
        "DEPLOYMENT_NAME": "example-foundation",
    }
    assert metadata.read_bicep(environment, run) == candidate
    assert len(calls) == 2
    assert {command[command.index("--query") + 1] for command in calls} == {
        "properties.provisioningState", "properties.outputs.DEPLOYMENT_METADATA.value",
    }
    assert all("--subscription" in command and "--resource-group" in command for command in calls)


@pytest.mark.parametrize("state", ["Failed", "Running", "Accepted", None])
def test_failed_provision_does_not_read_old_value(state):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return state
    with pytest.raises(metadata.MetadataError, match="provision"):
        metadata.read_bicep({
            "AZURE_SUBSCRIPTION_ID": "22222222-2222-2222-2222-222222222222",
            "AZURE_RESOURCE_GROUP": "rg-example", "DEPLOYMENT_NAME": "example-foundation",
        }, run)
    assert len(calls) == 1


@pytest.mark.parametrize("field,value", [
    ("environmentName", "another"),
    ("provider", "terraform"),
    ("runtimeConfigurationMode", "appConfig"),
    ("applicationId", "another-application"),
    ("deploymentName", "another-deployment"),
    ("tenantId", "55555555-5555-5555-5555-555555555555"),
    ("subscriptionId", "55555555-5555-5555-5555-555555555555"),
])
def test_each_context_binding_is_independent_of_candidate(candidate, field, value):
    context = candidate["context"]
    environment = {
        "AZURE_ENV_NAME": context["environmentName"],
        "AZURE_SUBSCRIPTION_ID": context["subscriptionId"],
        "AZURE_TENANT_ID": context["tenantId"],
        "AZURE_RESOURCE_GROUP": context["resourceGroups"]["foundry"],
        "AZURE_APP_RESOURCE_GROUP": context["resourceGroups"]["application"],
        "AZURE_NETWORK_RESOURCE_GROUP": context["resourceGroups"]["network"],
        "DEPLOYMENT_NAME": context["deploymentName"], "AGENTLZ_APP_ID": context["applicationId"],
    }
    parameters = {"appRuntimeConfigurationMode": context["runtimeConfigurationMode"]}
    context[field] = value
    with pytest.raises(metadata.MetadataError, match="context." + field):
        metadata.validate_context(candidate, environment, parameters, "bicep")


@pytest.mark.parametrize("alias", [
    "LOG_ANALYTICS_RESOURCE_ID", "APP_INSIGHTS_RESOURCE_ID",
    "AZURE_SPEECH_RESOURCE_ID", "AZURE_SPEECH_RESOURCE_NAME", "AZURE_SPEECH_ENDPOINT",
])
def test_legacy_root_aliases_cannot_keep_disabled_destinations(candidate, alias):
    context = candidate["context"]
    environment = {
        "AZURE_ENV_NAME": context["environmentName"], "AZURE_TENANT_ID": context["tenantId"],
        "AZURE_SUBSCRIPTION_ID": context["subscriptionId"], "AGENTLZ_APP_ID": context["applicationId"],
        "AZURE_RESOURCE_GROUP": context["resourceGroups"]["foundry"],
        "AZURE_APP_RESOURCE_GROUP": context["resourceGroups"]["application"],
        "AZURE_NETWORK_RESOURCE_GROUP": context["resourceGroups"]["network"],
        "DEPLOYMENT_NAME": context["deploymentName"], alias: "stale-destination",
    }
    with pytest.raises(metadata.MetadataError, match="cache." + alias):
        metadata.validate_context(candidate, environment, {
            "appRuntimeConfigurationMode": context["runtimeConfigurationMode"],
        }, "bicep")


def test_context_does_not_claim_unrelated_runtime_application_id(candidate):
    environment = {
        **metadata.aliases(candidate),
        "APPLICATION_ID": "55555555-5555-5555-5555-555555555555",
    }
    metadata.validate_context(candidate, environment, {
        "appRuntimeConfigurationMode": candidate["context"]["runtimeConfigurationMode"],
    }, "bicep")


def test_context_and_cache_conflicts_fail_before_live_reads(candidate):
    environment = {
        "AZURE_ENV_NAME": "example",
        "AZURE_SUBSCRIPTION_ID": candidate["context"]["subscriptionId"],
        "AZURE_TENANT_ID": candidate["context"]["tenantId"],
        "AZURE_RESOURCE_GROUP": "rg-example", "AZURE_APP_RESOURCE_GROUP": "rg-example-app",
        "AZURE_NETWORK_RESOURCE_GROUP": "rg-example-network",
        "DEPLOYMENT_NAME": "example-foundation", "AGENTLZ_APP_ID": "existing-application",
    }
    parameters = {"appRuntimeConfigurationMode": "containerEnv"}
    metadata.validate_context(candidate, environment, parameters, "bicep")
    models = [{
        "canonical_name": row["canonicalName"], "id": row["resourceId"].upper(),
        "name": row["name"], "model": row["model"], "endpoint": row["endpoint"],
        "api_version": row["apiVersion"],
    } for row in candidate["modelDeployments"]]
    apps = [{
        "canonical_name": row["canonicalName"], "name": row["name"].upper(),
        "id": row["resourceId"].upper(), "identity": row["identity"],
        "service_name": row["serviceName"], "fqdn": row["fqdn"],
    } for row in candidate["containerApps"]]
    metadata.validate_context(candidate, {
        **environment, "MODEL_DEPLOYMENTS": json.dumps(models), "CONTAINER_APPS": json.dumps(apps),
    }, parameters, "bicep")
    legacy_apps = [{
        "canonical_name": row["canonicalName"], "name": row["name"],
        "serviceName": row["serviceName"], "fqdn": row["fqdn"],
        "principalId": row["identity"]["principalId"],
    } for row in candidate["containerApps"]]
    metadata.validate_context(candidate, {
        **environment, "CONTAINER_APPS": json.dumps(legacy_apps),
    }, parameters, "bicep")
    for key, value in [
        ("AZURE_ENV_NAME", "another"), ("DEPLOYMENT_NAME", "another"),
        ("AZURE_TENANT_ID", "33333333-3333-3333-3333-333333333333"),
        ("AGENTLZ_APP_ID", "another"),
        ("DEPLOYMENT_METADATA", json.dumps({**candidate, "schemaVersion": 99})),
        ("AI_FOUNDRY_ACCOUNT_NAME", "another"),
        ("APP_CONFIG_ENDPOINT", "https://stale.azconfig.io"),
        ("DATABASE_ACCOUNT_NAME", "stale-cosmos"),
        ("AZURE_AI_PROJECT_RESOURCE_ID", candidate["resources"]["foundryProject"]["resource"]["resourceId"].replace("/rg-example/", "/rg-example-app/")),
        ("AZURE_AI_PROJECT_ENDPOINT", "https://foreign.services.ai.azure.com/api/projects/example-project"),
        ("MODEL_DEPLOYMENTS", json.dumps([{**models[0], "endpoint": "https://foreign.openai.azure.com"}])),
        ("CONTAINER_APPS", json.dumps([{**apps[0], "identity": {
            **apps[0]["identity"], "principalId": "55555555-5555-5555-5555-555555555555",
        }}])),
        ("CONTAINER_APPS", json.dumps({})),
        ("CONTAINER_APPS", json.dumps([{**legacy_apps[0], "principalId": "55555555-5555-5555-5555-555555555555"}])),
    ]:
        with pytest.raises(metadata.MetadataError):
            metadata.validate_context(candidate, {**environment, key: value}, parameters, "bicep")


@pytest.fixture
def live_boundary(candidate):
    resources = candidate["resources"]
    context = candidate["context"]
    rows = {}
    for slot, binding in resources.items():
        if not binding["resource"]:
            continue
        resource = binding["resource"]
        rows[resource["resourceId"].lower()] = {
            "id": resource["resourceId"], "name": resource["name"],
            "type": metadata.parse_resource_id(resource["resourceId"]).resource_type,
            "properties": {"provisioningState": "Succeeded"},
        }
    rows[resources["foundryAccount"]["resource"]["resourceId"].lower()]["properties"].update(
        customSubDomainName="example-foundry",
    )
    rows[resources["registry"]["resource"]["resourceId"].lower()]["properties"].update(
        loginServer="exampleacr.azurecr.io",
    )
    for model in candidate["modelDeployments"]:
        rows[model["resourceId"].lower()] = {
            "id": model["resourceId"], "name": model["name"],
            "type": "Microsoft.CognitiveServices/accounts/deployments",
            "properties": {"provisioningState": "Succeeded", "model": model["model"]},
        }
    for app in candidate["containerApps"]:
        rows[app["resourceId"].lower()] = {
            "id": app["resourceId"], "name": app["name"], "type": "Microsoft.App/containerApps",
            "identity": {"type": "SystemAssigned", "principalId": app["identity"]["principalId"]},
            "properties": {
                "provisioningState": "Succeeded",
                "managedEnvironmentId": resources["containerEnvironment"]["resource"]["resourceId"],
                "configuration": {"ingress": {"fqdn": app["fqdn"]}, "registries": []},
            },
        }
    parameters = {
        **{metadata.SLOTS[slot][2]: False for slot, binding in resources.items()
           if binding["status"] == "disabled"},
        "deployAiFoundry": True, "deployContainerRegistry": True, "deployContainerEnv": True,
        "deployContainerApps": True, "networkIsolation": False, "deployAppConfig": False,
        "modelDeploymentList": [{
            "canonical_name": model["canonicalName"], "name": model["name"],
            "model": model["model"], "apiVersion": model["apiVersion"],
        } for model in candidate["modelDeployments"]],
        "containerAppsList": [{
            "canonical_name": app["canonicalName"], "service_name": app["serviceName"],
            "name": app["name"],
        } for app in candidate["containerApps"]],
    }

    def run(command, **kwargs):
        if command[1:3] == ["account", "show"]:
            return {"id": context["subscriptionId"], "tenantId": context["tenantId"]}
        if command[1:3] == ["group", "show"]:
            return {"id": f"/subscriptions/{context['subscriptionId']}/resourceGroups/{command[command.index('--name') + 1]}"}
        assert command[1:3] == ["resource", "show"]
        return rows[command[command.index("--ids") + 1].lower()]
    return parameters, rows, run


@pytest.mark.parametrize("candidate", ["rg-example", "rg-ai(team)", "rg-équipe", "rg-٣"], indirect=True)
def test_live_boundary_accepts_pre_registry_setup_app(candidate, live_boundary):
    parameters, _, run = live_boundary
    metadata.verify_live(candidate, parameters, run)


def test_generated_app_name_cannot_redirect_verified_arm_id(candidate, live_boundary):
    parameters, _, run = live_boundary
    parameters["containerAppsList"][0]["name"] = None
    candidate["containerApps"][0]["name"] = "another-live-app"
    with pytest.raises(metadata.MetadataError, match="resource.name"):
        metadata.verify_live(candidate, parameters, run)


@pytest.mark.parametrize("mismatch", [None, "principalId", "clientId", "id"])
def test_user_assigned_identity_requires_exact_app_and_live_identity(candidate, live_boundary, mismatch):
    parameters, rows, base_run = live_boundary
    parameters["useUAI"] = True
    app = candidate["containerApps"][0]
    identity_id = app["resourceId"].split("/providers/")[0] + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/example"
    app["identity"] = {
        "kind": "userAssigned", "resourceId": identity_id,
        "principalId": "33333333-3333-3333-3333-333333333333",
        "clientId": "44444444-4444-4444-4444-444444444444",
    }
    rows[app["resourceId"].lower()]["identity"] = {
        "type": "UserAssigned",
        "userAssignedIdentities": {identity_id: {
            key: app["identity"][key] for key in ("principalId", "clientId")
        }},
    }
    live_identity = {"id": identity_id, **{
        key: app["identity"][key] for key in ("principalId", "clientId")
    }}
    if mismatch:
        live_identity[mismatch] = (
            identity_id + "-other" if mismatch == "id" else "55555555-5555-5555-5555-555555555555"
        )

    def run(command, **kwargs):
        if command[1:3] == ["identity", "show"]:
            assert command[command.index("--ids") + 1] == identity_id
            return live_identity
        return base_run(command, **kwargs)

    if mismatch:
        with pytest.raises(metadata.MetadataError, match="identity resource"):
            metadata.verify_live(candidate, parameters, run)
    else:
        metadata.validate_shape(candidate)
        metadata.verify_live(candidate, parameters, run)


@pytest.mark.parametrize("change", [
    lambda d: d["modelDeployments"][0].update(canonicalName="UNDECLARED_MODEL"),
    lambda d: d["modelDeployments"][0].update(apiVersion="unexpected"),
    lambda d: d["modelDeployments"][0].update(endpoint="https://another.openai.azure.com"),
    lambda d: d["containerApps"][0].update(serviceName="another"),
    lambda d: d["containerApps"].clear(),
    lambda d: d["resources"]["registry"]["resource"].update(name="another"),
])
def test_declared_mappings_cannot_be_substituted(candidate, live_boundary, change):
    parameters, _, run = live_boundary
    change(candidate)
    with pytest.raises(metadata.MetadataError):
        metadata.verify_live(candidate, parameters, run)


def test_foundry_endpoint_requires_live_domain(candidate, live_boundary):
    parameters, rows, run = live_boundary
    rows[candidate["resources"]["foundryAccount"]["resource"]["resourceId"].lower()]["properties"].clear()
    with pytest.raises(metadata.MetadataError, match="endpoint"):
        metadata.verify_live(candidate, parameters, run)


@pytest.mark.parametrize("provider", ["bicep", "terraform"])
def test_foundry_endpoints_from_actual_provider_expressions(candidate, live_boundary, provider):
    parameters, _, run = live_boundary
    candidate["context"]["provider"] = provider
    if provider == "bicep":
        source = (ROOT / "infra" / "bicep" / "main.bicep").read_text(encoding="utf-8")
        expressions = [
            re.search(rf"^var aiFoundry{kind}Endpoint = '([^']+)'", source, re.M)[1]
            for kind in ("Account", "Project")
        ]
        assert "endpoint: aiFoundryAccountEndpoint" in source
        assert "endpoint: aiFoundryProjectEndpoint" in source
    else:
        source = (ROOT / "infra" / "terraform" / "main.foundry.tf").read_text(encoding="utf-8")
        expressions = [
            re.search(rf'^\s+{kind}_endpoint\s*=.*?"(https://[^"]+)"', source, re.M)[1]
            for kind in ("account", "project")
        ]
        outputs = (ROOT / "infra" / "terraform" / "outputs.tf").read_text(encoding="utf-8")
        assert "endpoint   = local.foundry_context.account_endpoint" in outputs
        assert "endpoint   = local.foundry_context.project_endpoint" in outputs
    bindings = {
        "aiFoundry!.outputs.aiServicesName": "example-foundry",
        "aiFoundry!.outputs.aiProjectName": "example-project",
        "local.resource_names.aiFoundryAccountName": "example-foundry",
        "local.resource_names.aiFoundryProjectName": "example-project",
    }
    for slot, expression in zip(("foundryAccount", "foundryProject"), expressions):
        candidate["resources"][slot]["resource"]["endpoint"] = re.sub(
            r"\$\{([^}]+)\}", lambda match: bindings[match[1]], expression,
        )
    metadata.verify_live(candidate, parameters, run)


@pytest.mark.parametrize("slot,url", [
    ("foundryAccount", "https://another.cognitiveservices.azure.com/"),
    ("foundryAccount", "https://example-foundry.services.ai.azure.com/"),
    ("foundryProject", "https://another.services.ai.azure.com/api/projects/example-project"),
    ("foundryProject", "https://example-foundry.cognitiveservices.azure.com/api/projects/example-project"),
    ("foundryProject", "https://example-foundry.services.ai.azure.com/api/projects/another"),
])
def test_foundry_service_endpoints_cannot_be_substituted(candidate, live_boundary, slot, url):
    parameters, _, run = live_boundary
    candidate["resources"][slot]["resource"]["endpoint"] = url
    with pytest.raises(metadata.MetadataError, match="endpoint"):
        metadata.verify_live(candidate, parameters, run)


@pytest.mark.parametrize("provider", ["bicep", "terraform"])
@pytest.mark.parametrize("change", ["", "canonical", "model", "extra", "disabled"])
def test_evaluated_native_model_defaults(candidate, live_boundary, provider, change):
    parameters, rows, run = live_boundary
    candidate["context"]["provider"] = provider
    parameters["modelDeploymentList"] = []
    account_id = candidate["resources"]["foundryAccount"]["resource"]["resourceId"]
    candidate["modelDeployments"] = []
    for canonical, name, version in (
        ("GPT_MODEL", "gpt-5-nano", "2025-08-07"),
        ("EMBEDDING_MODEL", "text-embedding-3-large", "1"),
    ):
        model = {
            "canonicalName": canonical, "resourceId": account_id + "/deployments/" + name,
            "name": name, "model": {"format": "OpenAI", "name": name, "version": version},
            "apiVersion": "2025-01-01-preview", "endpoint": "https://example-foundry.openai.azure.com/",
        }
        candidate["modelDeployments"].append(model)
        rows[model["resourceId"].lower()] = {
            "id": model["resourceId"], "name": name,
            "type": "Microsoft.CognitiveServices/accounts/deployments",
            "properties": {"model": model["model"], "provisioningState": "Succeeded"},
        }
    if change == "canonical":
        candidate["modelDeployments"][0]["canonicalName"] = "UNDECLARED"
    elif change == "model":
        candidate["modelDeployments"][0]["model"]["version"] = "unexpected"
    elif change == "extra":
        candidate["modelDeployments"].append(copy.deepcopy(candidate["modelDeployments"][0]))
    elif change == "disabled":
        parameters.update(deployAiFoundry=False, deployAfProject=False)
        for slot in ("foundryAccount", "foundryProject"):
            candidate["resources"][slot] = {"status": "disabled", "resource": None}
        candidate["modelDeployments"] = []
    if change in ("canonical", "model", "extra"):
        with pytest.raises(metadata.MetadataError, match="mapping|modelDeployments"):
            metadata.verify_live(candidate, parameters, run)
    else:
        metadata.validate_shape(candidate)
        metadata.verify_live(candidate, parameters, run)


@pytest.mark.parametrize("provider,api_version", [
    ("bicep", "omitted"), ("bicep", None),
    ("terraform", "omitted"), ("terraform", None), ("terraform", ""),
])
def test_declared_models_use_provider_api_version_default(candidate, live_boundary, provider, api_version):
    parameters, _, run = live_boundary
    candidate["context"]["provider"] = provider
    declaration = parameters["modelDeploymentList"][0]
    if api_version == "omitted":
        declaration.pop("apiVersion")
    else:
        declaration["apiVersion"] = api_version
    candidate["modelDeployments"][0]["apiVersion"] = "2025-01-01-preview"
    metadata.verify_live(candidate, parameters, run)


def test_non_openai_model_preserves_provider_openai_endpoint(candidate, live_boundary):
    parameters, _, run = live_boundary
    candidate["modelDeployments"][0]["model"]["format"] = "Microsoft"
    metadata.verify_live(candidate, parameters, run)


@pytest.mark.parametrize("declared_empty", [False, True])
def test_external_gateway_mode_accepts_zero_models_and_rejects_unexpected_models(
    candidate, live_boundary, declared_empty,
):
    parameters, _, run = live_boundary
    parameters["deployModelDeployments"] = False
    if declared_empty:
        parameters["modelDeploymentList"] = []
    unexpected = copy.deepcopy(candidate["modelDeployments"])
    candidate["modelDeployments"] = []
    metadata.validate_shape(candidate)
    metadata.verify_live(candidate, parameters, run)
    candidate["modelDeployments"] = unexpected
    with pytest.raises(metadata.MetadataError, match="mappings"):
        metadata.verify_live(candidate, parameters, run)


@pytest.mark.parametrize("stale_key,stale_value", [
    ("CHAT_DEPLOYMENT_NAME", "stale-chat"),
    ("EMBEDDING_DEPLOYMENT_NAME", "stale-embedding"),
    ("GPT_MODEL", "gpt-5-nano"),
    ("EMBEDDING_MODEL", "text-embedding-3-large"),
    ("CUSTOM_GATEWAY_MODEL", "custom"),
    ("MODEL_DEPLOYMENTS", json.dumps([{"canonical_name": "CHAT_DEPLOYMENT_NAME", "name": "chat"}])),
])
def test_validate_context_rejects_stale_model_cache_when_model_deployments_empty(
    candidate, stale_key, stale_value,
):
    candidate["modelDeployments"] = []
    context = candidate["context"]
    environment = {
        "AZURE_ENV_NAME": context["environmentName"],
        "AZURE_SUBSCRIPTION_ID": context["subscriptionId"],
        "AZURE_TENANT_ID": context["tenantId"],
        "AZURE_RESOURCE_GROUP": context["resourceGroups"]["foundry"],
        "AZURE_APP_RESOURCE_GROUP": context["resourceGroups"]["application"],
        "AZURE_NETWORK_RESOURCE_GROUP": context["resourceGroups"]["network"],
        "DEPLOYMENT_NAME": context["deploymentName"],
        "AGENTLZ_APP_ID": context["applicationId"],
    }
    parameters = {
        "appRuntimeConfigurationMode": context["runtimeConfigurationMode"],
        "deployModelDeployments": False,
        "modelDeploymentList": [{"canonical_name": "CUSTOM_GATEWAY_MODEL", "name": "custom"}],
    }
    metadata.validate_context(candidate, {**environment, "MODEL_DEPLOYMENTS": "[]"}, parameters, "bicep")
    with pytest.raises(metadata.MetadataError, match="cache." + stale_key):
        metadata.validate_context(candidate, {**environment, stale_key: stale_value}, parameters, "bicep")


def test_declared_resource_name_cannot_select_another_same_group_resource(candidate, live_boundary):
    parameters, _, run = live_boundary
    parameters["containerRegistryName"] = "another-registry"
    with pytest.raises(metadata.MetadataError, match="registry.name"):
        metadata.verify_live(candidate, parameters, run)


@pytest.mark.parametrize("mismatch", [False, True])
def test_speech_endpoint_is_verified_against_returned_service_endpoint(candidate, live_boundary, mismatch):
    parameters, rows, run = live_boundary
    resource = {
        "name": "example-speech", "endpoint": "https://example-speech.cognitiveservices.azure.com",
        "resourceId": (
            f"/subscriptions/{candidate['context']['subscriptionId']}/resourceGroups/rg-example/"
            "providers/Microsoft.CognitiveServices/accounts/example-speech"
        ),
    }
    candidate["resources"]["speech"] = {"status": "managed", "resource": resource}
    parameters["deploySpeechService"] = True
    rows[resource["resourceId"].lower()] = {
        "id": resource["resourceId"], "name": resource["name"],
        "type": "Microsoft.CognitiveServices/accounts",
        "properties": {"endpoint": "https://another.cognitiveservices.azure.com" if mismatch else resource["endpoint"]},
    }
    if mismatch:
        with pytest.raises(metadata.MetadataError, match="speech.endpoint"):
            metadata.verify_live(candidate, parameters, run)
    else:
        metadata.verify_live(candidate, parameters, run)


@pytest.mark.parametrize("mismatch", ["", "missing", "extra", "canonical", "declared"])
def test_cosmos_database_requires_single_selected_canonical_binding(candidate, live_boundary, mismatch):
    parameters, rows, run = live_boundary
    resource = {
        "name": "example-cosmos", "endpoint": "https://example-cosmos.documents.azure.com",
        "resourceId": (
            f"/subscriptions/{candidate['context']['subscriptionId']}/resourceGroups/rg-example-app/"
            "providers/Microsoft.DocumentDB/databaseAccounts/example-cosmos"
        ),
    }
    candidate["resources"]["cosmos"] = {"status": "managed", "resource": resource}
    parameters.update(deployCosmosDb=True, dbDatabaseName="selected-database")
    rows[resource["resourceId"].lower()] = {
        "id": resource["resourceId"], "name": resource["name"],
        "type": "Microsoft.DocumentDB/databaseAccounts",
        "properties": {"documentEndpoint": resource["endpoint"]},
    }
    database = {
        "canonicalName": "DATABASE_NAME", "name": "selected-database",
        "resourceId": resource["resourceId"] + "/sqlDatabases/selected-database",
    }
    rows[database["resourceId"].lower()] = {
        "id": database["resourceId"], "name": database["name"],
        "type": "Microsoft.DocumentDB/databaseAccounts/sqlDatabases", "properties": {},
    }
    candidate["dataResources"]["cosmosDatabases"] = [database]
    if mismatch == "missing":
        candidate["dataResources"]["cosmosDatabases"] = []
    elif mismatch == "extra":
        candidate["dataResources"]["cosmosDatabases"].append(copy.deepcopy(database))
    elif mismatch == "canonical":
        database["canonicalName"] = "ANOTHER_DATABASE"
    elif mismatch == "declared":
        parameters["dbDatabaseName"] = "another-database"
    if mismatch:
        with pytest.raises(metadata.MetadataError, match="cosmosDatabases"):
            metadata.verify_live(candidate, parameters, run)
    else:
        metadata.verify_live(candidate, parameters, run)


def test_wrong_live_type_is_rejected(candidate, live_boundary):
    parameters, rows, run = live_boundary
    rows[candidate["resources"]["registry"]["resource"]["resourceId"].lower()]["type"] = "Microsoft.Storage/storageAccounts"
    with pytest.raises(metadata.MetadataError, match="type"):
        metadata.verify_live(candidate, parameters, run)


def test_disabled_and_enabled_selection_are_bidirectional(candidate, live_boundary):
    parameters, _, run = live_boundary
    parameters["deployContainerRegistry"] = False
    with pytest.raises(metadata.MetadataError, match="selection"):
        metadata.verify_live(candidate, parameters, run)


def test_null_ingress_does_not_hide_endpoint_mismatch(candidate, live_boundary):
    parameters, rows, run = live_boundary
    app = candidate["containerApps"][0]
    rows[app["resourceId"].lower()]["properties"]["configuration"]["ingress"] = None
    with pytest.raises(metadata.MetadataError, match="fqdn"):
        metadata.verify_live(candidate, parameters, run)


def test_omitted_enabled_provider_default_is_not_an_opt_out(candidate, live_boundary):
    parameters, _, run = live_boundary
    parameters.pop("deployKeyVault")
    with pytest.raises(metadata.MetadataError, match="keyVault.selection"):
        metadata.verify_live(candidate, parameters, run)


def test_foundry_backing_inputs_do_not_select_solution_resources(candidate, live_boundary):
    parameters, _, run = live_boundary
    parameters.update(
        aiSearchResourceId="/subscriptions/other/providers/unrelated",
        aiFoundryStorageAccountResourceId="/subscriptions/other/providers/unrelated",
        aiFoundryCosmosDBAccountResourceId="/subscriptions/other/providers/unrelated",
    )
    metadata.verify_live(candidate, parameters, run)


@pytest.mark.parametrize("mismatch", [False, True])
def test_hosted_registry_reference_uses_exact_declared_binding(candidate, live_boundary, mismatch):
    parameters, _, run = live_boundary
    binding = candidate["resources"]["registry"]
    binding["status"] = "referenced"
    parameters.update(
        deployContainerRegistry=False, prepareHostedAgent=True,
        hostedAgentContainerRegistryResourceId=binding["resource"]["resourceId"],
        hostedAgentContainerRegistryEndpoint="foreign.azurecr.io" if mismatch else "exampleacr.azurecr.io",
    )
    if mismatch:
        with pytest.raises(metadata.MetadataError, match="registry.endpoint"):
            metadata.verify_live(candidate, parameters, run)
    else:
        metadata.verify_live(candidate, parameters, run)


@pytest.mark.parametrize("group", ["rg-example", "rg-example-app"])
def test_solution_storage_stays_in_foundry_destination(candidate, live_boundary, group):
    parameters, rows, run = live_boundary
    resource = {
        "resourceId": f"/subscriptions/{candidate['context']['subscriptionId']}/resourceGroups/{group}/providers/Microsoft.Storage/storageAccounts/example",
        "name": "example", "endpoint": "https://example.blob.core.windows.net",
    }
    candidate["resources"]["storage"] = {"status": "managed", "resource": resource}
    parameters["deployStorageAccount"] = True
    rows[resource["resourceId"].lower()] = {
        "id": resource["resourceId"], "name": "example", "type": "Microsoft.Storage/storageAccounts",
        "properties": {"primaryEndpoints": {"blob": resource["endpoint"]}},
    }
    if group == "rg-example-app":
        with pytest.raises(metadata.MetadataError, match="resource.binding"):
            metadata.verify_live(candidate, parameters, run)
    else:
        metadata.verify_live(candidate, parameters, run)


def test_postgresql_requires_its_selected_network_even_without_isolation(candidate, live_boundary):
    parameters, _, run = live_boundary
    parameters.update(networkIsolation=False, deployPostgreSql=True)
    with pytest.raises(metadata.MetadataError, match="network.selection"):
        metadata.verify_live(candidate, parameters, run)


@pytest.fixture
def native_terraform(tmp_path, monkeypatch, request):
    for key in ("ARM_ACCESS_KEY", "ARM_SAS_TOKEN", "TF_CLI_ARGS", "TF_CLI_ARGS_init", "TF_CLI_ARGS_output", "TF_WORKSPACE"):
        monkeypatch.delenv(key, raising=False)
    environment = {
        "AZURE_ENV_NAME": "example", "AZURE_SUBSCRIPTION_ID": "22222222-2222-2222-2222-222222222222",
        "AZURE_RESOURCE_GROUP": "rg-example", "ARM_ENVIRONMENT": "public",
        "TF_STATE_RESOURCE_GROUP": "rg-state", "TF_STATE_STORAGE_ACCOUNT": "examplestate",
        "TF_STATE_CONTAINER": "tfstate",
    }
    relative_directory = getattr(request, "param", ("infra", "terraform"))
    directory = tmp_path.joinpath(*relative_directory)
    directory.mkdir(parents=True)
    (directory / "outputs.tf").write_text(
        'output "DEPLOYMENT_METADATA" { value = {} sensitive = false }', encoding="utf-8",
    )
    native = (tmp_path / ".azure" / "example").joinpath(*relative_directory)
    (native / ".terraform").mkdir(parents=True)
    backend = metadata.resolve_backend(environment)
    metadata.ensure_backend_binding(backend, tmp_path / ".azure", allow_create=True)
    config = native / "example.conf.json"
    config.write_text(json.dumps(backend.terraform_config()), encoding="utf-8")
    return tmp_path, directory, native, config, environment


@pytest.mark.parametrize("native_terraform", [("infra", "terraform"), ("custom", "foundation")], indirect=True)
def test_terraform_reuses_native_initialized_backend_before_named_output(native_terraform, candidate):
    root, directory, native, config, environment = native_terraform
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return candidate if command[1] == "output" else None

    assert metadata.read_terraform(root, directory, environment, run) == candidate
    assert [command[1] for command, _ in calls] == ["init", "output"]
    assert calls[0][0] == [
        "terraform", "init", "-input=false", "-get=false", "-lockfile=readonly",
        "-backend-config=" + str(config.resolve()),
    ]
    assert calls[1][0] == ["terraform", "output", "-json", "DEPLOYMENT_METADATA"]
    assert all(kwargs["cwd"] == directory for _, kwargs in calls)
    assert all(kwargs["environment"]["TF_DATA_DIR"] == str((native / ".terraform").resolve())
               for _, kwargs in calls)
    assert calls[0][1]["decode_json"] is False


@pytest.mark.parametrize("failure", ["configuration", "uninitialized", "backend_changed", "process_secret", "workspace"])
def test_terraform_backend_failures_never_request_output(native_terraform, monkeypatch, failure):
    root, directory, native, config, environment = native_terraform
    calls = []
    if failure == "configuration":
        config.write_text('{"key":"another"}', encoding="utf-8")
    elif failure == "uninitialized":
        (native / ".terraform").rmdir()
    elif failure == "process_secret":
        monkeypatch.setenv("ARM_ACCESS_KEY", "canary-secret")
    elif failure == "workspace":
        monkeypatch.setenv("TF_WORKSPACE", "another")

    def run(command, **kwargs):
        calls.append(command)
        raise metadata.MetadataError("source.backend: Native backend configuration changed.")

    with pytest.raises(metadata.MetadataError) as error:
        metadata.read_terraform(root, directory, environment, run)
    assert not any(command[1] == "output" for command in calls)
    assert "canary" not in str(error.value)


@pytest.mark.parametrize("provider", ["bicep", "terraform"])
@pytest.mark.parametrize("mode,store", [
    ("containerEnv", False), ("appConfig", True), ("containerEnv", True), ("none", False),
])
def test_persisted_selection_revalidates_in_independent_processes(
    native_terraform, candidate, live_boundary, provider, mode, store,
):
    root, directory, _, _, environment = native_terraform
    parameters, rows, _ = live_boundary
    context = candidate["context"]
    context.update(provider=provider, runtimeConfigurationMode=mode)
    if provider == "terraform":
        context["deploymentName"] = context["environmentName"]
    parameters.update(appRuntimeConfigurationMode=mode, deployAppConfig=store)
    if store:
        resource_id = (
            f"/subscriptions/{context['subscriptionId']}/resourceGroups/"
            f"{context['resourceGroups']['application']}/providers/"
            "Microsoft.AppConfiguration/configurationStores/example-config"
        )
        candidate["resources"]["appConfig"] = {
            "status": "managed", "resource": {
                "resourceId": resource_id, "name": "example-config",
                "endpoint": "https://example-config.azconfig.io",
            },
        }
        rows[resource_id.lower()] = {
            "id": resource_id, "name": "example-config",
            "type": "Microsoft.AppConfiguration/configurationStores",
            "properties": {"endpoint": "https://example-config.azconfig.io"},
        }
    environment.update(
        AZURE_TENANT_ID=context["tenantId"], AGENTLZ_APP_ID=context["applicationId"],
        DEPLOYMENT_NAME=context["deploymentName"],
        ORCHESTRATION_HOST="container_apps", APPLICATION_MODE="conversational",
        DEPLOY_INGESTION_CONTAINER_APP="false",
        AZURE_APP_RESOURCE_GROUP=context["resourceGroups"]["application"],
        AZURE_NETWORK_RESOURCE_GROUP=context["resourceGroups"]["network"],
        DEPLOYMENT_METADATA=json.dumps(candidate),
    )
    (root / "azure.yaml").write_text(json.dumps({
        "infra": {"provider": provider, "path": str(directory.relative_to(root))},
    }), encoding="utf-8")
    (directory / ("main.bicep" if provider == "bicep" else "main.tf")).write_text("", encoding="utf-8")
    (root / "main.parameters.json").write_text(json.dumps({
        "parameters": {key: {"value": value} for key, value in parameters.items()},
    }), encoding="utf-8")
    binding = root / ".azure" / context["environmentName"] / "resource-groups.json"
    binding.write_text(json.dumps({
        "version": 2, "environment": context["environmentName"],
        "subscription": context["subscriptionId"], **context["resourceGroups"],
    }), encoding="utf-8")
    snapshot = root / "persisted-selection.json"
    snapshot.write_text(json.dumps({
        "environment": environment, "document": candidate, "rows": rows,
    }), encoding="utf-8")
    driver = r"""
import json
from pathlib import Path
import sys
from config.deployment import metadata
from config.deployment.setup_settings import resolve_setup_settings
root = Path(sys.argv[1])
saved = json.loads((root / "persisted-selection.json").read_text(encoding="utf-8"))
metadata.selected_environment = lambda root, name: dict(saved["environment"])
calls = []
def run(command, **kwargs):
    calls.append(command)
    if command[0] == "terraform":
        return saved["document"] if command[1] == "output" else None
    if command[1:4] == ["deployment", "group", "show"]:
        return "Succeeded" if command[-1] == "properties.provisioningState" else saved["document"]
    context = saved["document"]["context"]
    if command[1:3] == ["account", "show"]:
        return {"id": context["subscriptionId"], "tenantId": context["tenantId"]}
    if command[1:3] == ["group", "show"]:
        return {"id": "/subscriptions/" + context["subscriptionId"] + "/resourceGroups/" + command[command.index("--name") + 1]}
    assert command[1:3] == ["resource", "show"], "Unexpected provider/store request"
    return saved["rows"][command[command.index("--ids") + 1].lower()]
verified = metadata.load_metadata(
    {"AZURE_ENV_NAME": saved["environment"]["AZURE_ENV_NAME"]}, project_root=root, runner=run,
)
settings = resolve_setup_settings(verified)
assert ("APP_CONFIG_ENDPOINT" in settings) == (settings["APP_RUNTIME_CONFIGURATION_MODE"] == "appConfig")
print(json.dumps(calls))
"""
    observed = []
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-c", driver, str(root)], cwd=ROOT,
            capture_output=True, text=True, timeout=30, check=False,
        )
        assert result.returncode == 0, result.stderr
        calls = json.loads(result.stdout)
        named = [
            command for command in calls
            if command[-1] == "properties.outputs.DEPLOYMENT_METADATA.value"
            or command[:4] == ["terraform", "output", "-json", "DEPLOYMENT_METADATA"]
        ]
        assert len(named) == 1
        assert not any(command[1:2] == ["appconfig"] for command in calls)
        observed.append(calls)
    assert observed[0] == observed[1]
