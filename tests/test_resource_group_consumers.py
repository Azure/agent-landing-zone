"""Destination routing, flat context compatibility and fail-closed bindings."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from config.deployment.context import context_settings, registry_resource_group
from config.deployment import metadata as deployment_metadata, outputs

SUB = "11111111-1111-1111-1111-111111111111"
BASE = {
    "AZURE_SUBSCRIPTION_ID": SUB,
    "AZURE_APP_RESOURCE_GROUP": "rg-app",
    "AZURE_RESOURCE_GROUP": "rg-ai",
    "AZURE_NETWORK_RESOURCE_GROUP": "rg-net",
    "AZURE_STORAGE_ACCOUNT_NAME": "sttest",
    "STORAGE_BLOB_ENDPOINT": "https://sttest.blob.core.windows.net/",
    "APP_CONFIG_ENDPOINT": "https://config.azconfig.io",
    "AZURE_AI_PROJECT_RESOURCE_ID": f"/subscriptions/{SUB}/resourceGroups/rg-ai/providers/Microsoft.CognitiveServices/accounts/account/projects/project",
    "AZURE_AI_PROJECT_ENDPOINT": "https://account.services.ai.azure.com/api/projects/project",
}


@pytest.mark.parametrize("failure", ["missing", "stale", "environment", "group", "resource", "identity"])
def test_direct_role_entry_rejects_invalid_native_metadata_before_assignment(failure, caplog):
    from config.appdefinition.__main__ import main

    root = Path(__file__).resolve().parents[1]
    document = json.loads((root / "tests" / "fixtures" / "deployment-metadata-v1.json").read_text(encoding="utf-8"))
    document["context"]["applicationId"] = "agent-lz-default"
    selected = {
        **deployment_metadata.aliases(document), "AGENTLZ_APP_DEFINITION": "",
        "ORCHESTRATION_HOST": "container_apps", "DEPLOYMENT_METADATA": json.dumps(document),
    }
    bound = deployment_metadata.resolve_resource_groups(selected)
    if failure == "missing":
        document = None
    elif failure == "stale":
        document["context"]["deploymentName"] = "stale-foundation"
    elif failure == "environment":
        document["context"]["environmentName"] = "foreign"
    elif failure == "group":
        selected["AZURE_APP_RESOURCE_GROUP"] = "foreign"
    elif failure == "resource":
        resource = document["resources"]["registry"]["resource"]
        resource["resourceId"] = resource["resourceId"].replace("/rg-example-app/", "/foreign/")
    else:
        document["containerApps"][0]["identity"]["principalId"] = "55555555-5555-5555-5555-555555555555"

    read_native = deployment_metadata.read_bicep

    def run(command, **kwargs):
        assert command[1:4] == ["deployment", "group", "show"]
        return "Succeeded" if command[-1] == "properties.provisioningState" else document

    with (
        patch.dict(os.environ, selected, clear=True),
        patch.object(deployment_metadata, "selected_environment", return_value=selected),
        patch.object(deployment_metadata, "resolve_provider", return_value={"provider": "bicep"}),
        patch.object(deployment_metadata, "resolve_az_command", return_value="az"),
        patch.object(deployment_metadata, "read_binding", return_value=bound),
        patch.object(deployment_metadata, "resolve_declared_parameters", return_value={
            "appRuntimeConfigurationMode": "containerEnv",
        }),
        patch.object(deployment_metadata, "read_bicep", side_effect=lambda env, runner: read_native(env, run)),
        patch("config.appdefinition.roles.assign_roles") as assign,
    ):
        assert main(["--assign-roles"]) == 3
    assert "Capability-profile role assignment failed" in caplog.text
    expected_error = {
        "missing": "source: Missing DEPLOYMENT_METADATA",
        "stale": "context.deploymentName", "environment": "context.environmentName",
        "group": "selection: Invalid declared inputs", "resource": "cache: Stale saved metadata",
        "identity": "cache: Stale saved metadata",
    }[failure]
    assert expected_error in caplog.text
    assign.assert_not_called()


@pytest.mark.parametrize("application,network", [("", ""), ("rg-app", ""), ("rg-app", "rg-net"), ("RG-AI", "rg-ai")])
def test_flat_destinations_preserve_json_v1(application, network):
    environment = {**BASE, "AZURE_APP_RESOURCE_GROUP": application, "AZURE_NETWORK_RESOURCE_GROUP": network}
    document = outputs.build_platform_outputs({
        **environment, "AI_FOUNDRY_ACCOUNT_NAME": "account",
        "AZURE_CONTAINER_REGISTRY_ENDPOINT": "registry.azurecr.io",
        "KEY_VAULT_URI": "https://vault.vault.azure.net",
    })
    settings = outputs.platform_settings(document, environment)
    assert json.loads(settings[outputs.PLATFORM_OUTPUTS_KEY]) == document
    outputs.validate_platform_outputs(document)
    assert settings["AZURE_APP_RESOURCE_GROUP"] == (application or "rg-ai")
    assert settings["AZURE_RESOURCE_GROUP"] == "rg-ai"
    assert settings["DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID"].lower() == (
        f"/subscriptions/{SUB}/resourceGroups/rg-ai/providers/"
        "Microsoft.Storage/storageAccounts/sttest/blobServices/default/containers/documents"
    ).lower()


@pytest.mark.parametrize("resource_id", [
    f"/subscriptions/{SUB}/resourceGroups/foreign/providers/Microsoft.Storage/storageAccounts/sttest",
    "/subscriptions/foreign/resourceGroups/rg-ai/providers/Microsoft.Storage/storageAccounts/sttest",
    f"/subscriptions/{SUB}/resourceGroups/rg-ai/providers/Microsoft.Storage/storageAccounts/wrong",
    "not-an-id",
])
def test_wrong_storage_ids_are_rejected(resource_id):
    with pytest.raises(ValueError):
        context_settings({**BASE, "STORAGE_ACCOUNT_RESOURCE_ID": resource_id})


def test_explicit_acr_id_does_not_use_foundry_group():
    env = {
        **BASE, "AZURE_CONTAINER_REGISTRY_ENDPOINT": "registry.azurecr.io",
        "AZURE_CONTAINER_REGISTRY_RESOURCE_ID": f"/subscriptions/{SUB}/resourceGroups/rg-registry/providers/Microsoft.ContainerRegistry/registries/registry",
    }
    assert registry_resource_group(env) == "rg-registry"
    assert registry_resource_group(BASE) == "rg-app"
    with pytest.raises(ValueError):
        registry_resource_group({**env, "AZURE_CONTAINER_REGISTRY_ENDPOINT": "wrong.azurecr.io"})


@pytest.mark.parametrize("external_registry", [False, True])
def test_postprovision_registry_lookup_supports_isolated_python(tmp_path, external_registry):
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "postProvision.ps1").read_text(encoding="utf-8-sig")
    # Discovery moved to Python. Exercise the shipped import bootstrap under
    # isolated Python, then the same shared destination resolver used by setup.
    code = re.search(r'& python -c "([^"\n]*sys\.path\.insert[^"\n]*)"', source)
    assert code is not None
    environment = {**os.environ, **BASE, "AGENTLZ_REPO_ROOT": str(root)}
    for key in (
        "AZURE_CONTAINER_REGISTRY_RESOURCE_ID", "CONTAINER_REGISTRY_RESOURCE_ID",
        "AZURE_CONTAINER_REGISTRY_ENDPOINT", "CONTAINER_REGISTRY_LOGIN_SERVER",
    ):
        environment.pop(key, None)
    if external_registry:
        environment.update(
            AZURE_CONTAINER_REGISTRY_ENDPOINT="registry.azurecr.io",
            AZURE_CONTAINER_REGISTRY_RESOURCE_ID=(
                f"/subscriptions/{SUB}/resourceGroups/rg-registry/providers/"
                "Microsoft.ContainerRegistry/registries/registry"
            ),
        )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code.group(1).replace(
            "runpy.run_module('$ModuleName', run_name='__main__')",
            "from config.deployment.context import registry_resource_group; print(registry_resource_group(os.environ))",
        )],
        cwd=tmp_path, env=environment, capture_output=True, text=True,
        timeout=20, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ("rg-registry" if external_registry else "rg-app")


def test_flat_context_does_not_clobber_bicep_document_scope_without_storage_outputs():
    env = {key: value for key, value in BASE.items() if key not in ("AZURE_STORAGE_ACCOUNT_NAME", "STORAGE_BLOB_ENDPOINT")}
    assert context_settings(env) == {
        "AZURE_APP_RESOURCE_GROUP": "rg-app",
        "AZURE_RESOURCE_GROUP": "rg-ai",
        "AZURE_NETWORK_RESOURCE_GROUP": "rg-net",
    }
    explicit = f"/subscriptions/{SUB}/resourceGroups/rg-ai/providers/Microsoft.Storage/storageAccounts/sttest/blobServices/default/containers/documents"
    assert context_settings({**env, "DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID": explicit})["DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID"] == explicit
    with pytest.raises(ValueError):
        context_settings({**env, "DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID": "invalid"})


@pytest.mark.parametrize("container", ["documents", "custom-documents"])
def test_platform_publication_uses_verified_native_metadata_without_store_hydration(container):
    environment = {
        **BASE, "AZURE_CONTAINER_REGISTRY_ENDPOINT": "registry.azurecr.io",
        "KEY_VAULT_URI": "https://vault.vault.azure.net",
    }
    environment.pop("STORAGE_BLOB_ENDPOINT")
    environment.pop("AZURE_STORAGE_ACCOUNT_NAME")
    storage_id = f"/subscriptions/{SUB}/resourceGroups/rg-ai/providers/Microsoft.Storage/storageAccounts/sttest"
    source = (Path(__file__).parent / "fixtures" / "deployment-metadata-v1.json").read_text()
    document = json.loads(source.replace("22222222-2222-2222-2222-222222222222", SUB)
                          .replace("/resourceGroups/rg-example/", "/resourceGroups/rg-ai/")
                          .replace("/resourceGroups/rg-example-app/", "/resourceGroups/rg-app/"))
    document["context"].update(subscriptionId=SUB, resourceGroups={
        "foundry": "rg-ai", "application": "rg-app", "network": "rg-net",
    })
    document["resources"]["storage"] = {"status": "managed", "resource": {
        "resourceId": storage_id, "name": "sttest", "endpoint": "https://sttest.blob.core.windows.net/",
    }}
    child_id = f"{storage_id}/blobServices/default/containers/{container}"
    document["dataResources"]["storageContainers"] = [{
        "canonicalName": "DOCUMENTS_STORAGE_CONTAINER", "name": container, "resourceId": child_id,
    }]
    verified = deployment_metadata.VerifiedMetadata(document, environment, {}, {})
    with patch.object(outputs, "load_metadata", return_value=verified), \
         patch("config.deployment.appconfig._run_az", side_effect=AssertionError("store discovery")):
        values = outputs.load_platform_environment(environment)
    settings = outputs.platform_settings(outputs.build_platform_outputs(values), values)
    assert settings["DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID"] == child_id
    assert settings["AZURE_APP_RESOURCE_GROUP"] == "rg-app"
    assert settings["AZURE_RESOURCE_GROUP"] == "rg-ai"
    assert "STORAGE_BLOB_ENDPOINT" not in environment
    assert "resourceGroups" not in settings[outputs.PLATFORM_OUTPUTS_KEY]


def test_explicit_custom_container_does_not_override_a_conflicting_configured_name():
    resource_id = (
        f"/subscriptions/{SUB}/resourceGroups/rg-ai/providers/Microsoft.Storage/"
        "storageAccounts/sttest/blobServices/default/containers/custom-documents"
    )
    assert context_settings({
        **BASE, "DOCUMENTS_STORAGE_CONTAINER": "custom-documents",
        "DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID": resource_id,
    })["DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID"] == resource_id
    with pytest.raises(ValueError, match="conflicts"):
        context_settings({
            **BASE, "DOCUMENTS_STORAGE_CONTAINER": "documents",
            "DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID": resource_id,
        })


def test_foundation_delegates_selected_destinations_without_changing_runtime():
    environment = {**BASE, "ORCHESTRATION_HOST": "hosted", "APPLICATION_MODE": "both"}
    original = dict(environment)
    with patch.object(outputs, "load_metadata") as verify:
        outputs.verify_foundation(environment)
    verify.assert_called_once_with(environment)
    assert environment["ORCHESTRATION_HOST"] == "hosted"
    assert environment == original


@pytest.mark.parametrize("group", ["rg-ai(team)", "rg-équipe", "rg-٣"])
def test_classic_foundation_accepts_shared_resolver_valid_foundry_groups(group):
    environment = {
        **BASE, "ORCHESTRATION_HOST": "container_apps",
        "AZURE_RESOURCE_GROUP": group,
        "AZURE_AI_PROJECT_RESOURCE_ID": BASE["AZURE_AI_PROJECT_RESOURCE_ID"].replace("rg-ai", group),
    }
    with patch.object(outputs, "load_metadata") as verify:
        outputs.verify_foundation(environment)
    verify.assert_called_once_with(environment)
    assert environment["ORCHESTRATION_HOST"] == "container_apps"


@pytest.mark.parametrize("wrong_binding", ["subscription", "group", "endpoint"])
def test_unicode_foundation_group_keeps_subscription_destination_and_endpoint_checks(wrong_binding):
    group = "rg-équipe"
    environment = {
        **BASE, "AZURE_RESOURCE_GROUP": group,
        "AZURE_AI_PROJECT_RESOURCE_ID": BASE["AZURE_AI_PROJECT_RESOURCE_ID"].replace("rg-ai", group),
    }
    if wrong_binding == "subscription":
        environment["AZURE_AI_PROJECT_RESOURCE_ID"] = environment["AZURE_AI_PROJECT_RESOURCE_ID"].replace(SUB, "22222222-2222-2222-2222-222222222222")
    elif wrong_binding == "group":
        environment["AZURE_AI_PROJECT_RESOURCE_ID"] = environment["AZURE_AI_PROJECT_RESOURCE_ID"].replace(group, "other-équipe")
    else:
        environment["AZURE_AI_PROJECT_ENDPOINT"] = environment["AZURE_AI_PROJECT_ENDPOINT"].replace("account.services", "foreign.services")
    with patch.object(outputs, "load_metadata", side_effect=deployment_metadata.MetadataError("resource.binding")) as verify, \
         pytest.raises(deployment_metadata.MetadataError, match="resource.binding"):
        outputs.verify_foundation(environment)
    verify.assert_called_once_with(environment)


@pytest.mark.parametrize("group", ["rg bad", "rg.", "rg-²", "a" * 91, "rg\\bad"])
def test_scope_guard_rejects_groups_rejected_by_shared_resolver(group):
    from config.deployment.hosted_access import AccessError, PROJECT_PATH, _bound_scope
    project = BASE["AZURE_AI_PROJECT_RESOURCE_ID"].replace("rg-ai", group)
    with pytest.raises(AccessError):
        _bound_scope(project, PROJECT_PATH, SUB, group)


@pytest.mark.parametrize("segment,invalid", [
    ("accounts/account", "accounts/account(team)"),
    ("accounts/account", "accounts/équipe"),
    ("projects/project", "projects/project(team)"),
    ("projects/project", "projects/équipe"),
])
def test_valid_group_support_does_not_relax_account_or_project_segments(segment, invalid):
    from config.deployment.hosted_access import AccessError, PROJECT_PATH, _bound_scope
    group = "rg-ai(team)"
    project = BASE["AZURE_AI_PROJECT_RESOURCE_ID"].replace("rg-ai", group).replace(segment, invalid)
    with pytest.raises(AccessError):
        _bound_scope(project, PROJECT_PATH, SUB, group)


def test_foundation_rejects_project_in_app_group_before_reading_azure():
    environment = {**BASE, "AZURE_AI_PROJECT_RESOURCE_ID": BASE["AZURE_AI_PROJECT_RESOURCE_ID"].replace("rg-ai", "rg-app")}
    with patch.object(outputs, "load_metadata", side_effect=deployment_metadata.MetadataError("resource.binding")), \
         patch("config.deployment.appconfig._run_az") as run, pytest.raises(deployment_metadata.MetadataError):
        outputs.verify_foundation(environment)
    run.assert_not_called()


def test_foundation_never_falls_back_when_destination_read_fails():
    with patch.object(outputs, "load_metadata", side_effect=deployment_metadata.MetadataError("provider/access")) as verify, \
         pytest.raises(deployment_metadata.MetadataError, match="provider/access"):
        outputs.verify_foundation(BASE)
    verify.assert_called_once_with(BASE)


@pytest.mark.parametrize("groups", [("rg-app",), ("rg-app", "rg-ai"), ("rg-app", "rg-ai", "rg-net")])
def test_capability_roles_discover_actual_target_across_unique_destinations(groups):
    from config.appdefinition.roles import resolve_scope
    env = {
        **BASE, "AZURE_RESOURCE_GROUP": groups[min(1, len(groups) - 1)],
        "AZURE_NETWORK_RESOURCE_GROUP": groups[-1], "SEARCH_SERVICE_NAME": "search",
    }
    target = f"/subscriptions/{SUB}/resourceGroups/{env['AZURE_RESOURCE_GROUP']}/providers/Microsoft.Search/searchServices/search"
    calls = []
    def read(arguments, **kwargs):
        calls.append(arguments)
        group = arguments[arguments.index("--resource-group") + 1]
        return json.dumps([{"id": target, "name": "search"}] if group == env["AZURE_RESOURCE_GROUP"] else [])
    assert resolve_scope("searchService", env, "rg-app", read) == target
    assert len(calls) == len(groups)
    assert all(SUB in call and "create" not in call for call in calls)


def test_capability_roles_reject_ambiguous_foreign_and_malformed_resources():
    from config.appdefinition.roles import resolve_scope, RoleAssignmentError
    for mode in ("ambiguous", "foreign", "malformed"):
        def read(arguments, **kwargs):
            group = arguments[arguments.index("--resource-group") + 1]
            if mode == "malformed":
                return "{}"
            owner = "foreign" if mode == "foreign" else group
            return json.dumps([{
                "name": "search",
                "id": f"/subscriptions/{SUB}/resourceGroups/{owner}/providers/Microsoft.Search/searchServices/search",
            }])
        with pytest.raises(RoleAssignmentError):
            resolve_scope("searchService", BASE, "rg-app", read)


@pytest.mark.parametrize("failure", ["denied", "invalid-json", "timeout", "invalid-shape"])
def test_image_discovery_failures_cannot_reset_existing_images(failure):
    from config.deployment.existing_images import discover_existing_images
    existence = SimpleNamespace(returncode=0, stdout="true")
    result = {
        "denied": SimpleNamespace(returncode=1, stdout=""),
        "invalid-json": SimpleNamespace(returncode=0, stdout="invalid"),
        "invalid-shape": SimpleNamespace(returncode=0, stdout="{}"),
        "timeout": subprocess.TimeoutExpired("az", 180),
    }[failure]
    with patch("config.deployment.existing_images.resolve_az_command", return_value="az"), \
            patch("config.deployment.existing_images.subprocess.run", side_effect=[existence, result]), \
            pytest.raises(RuntimeError):
        discover_existing_images("rg-app", SUB)


@pytest.mark.parametrize("application,network", [("", ""), ("rg-app", ""), ("rg-app", "rg-net")])
def test_image_discovery_and_runtime_selection_remain_application_owned(application, network):
    from config.deployment.existing_images import definition_placeholder_plan
    from config.deployment.composition import resolve_mode
    env = {
        **BASE, "AZURE_APP_RESOURCE_GROUP": application, "AZURE_NETWORK_RESOURCE_GROUP": network,
        "ORCHESTRATION_HOST": "hosted", "AGENTLZ_APP_DEFINITION": "",
    }
    with patch("config.deployment.existing_images.discover_existing_images", return_value={"frontend": "cr.azurecr.io/ui@sha256:" + "a" * 64}) as read:
        plan = definition_placeholder_plan(env)
    assert plan["ui"].endswith("a" * 64)
    assert resolve_mode(env).value == "hosted"
    assert read.call_args.args[0] == (application or "rg-ai")


@pytest.mark.parametrize("configured", ["rg-ai", "rg-app", "rg-ai(team)"])
def test_foundry_configuration_uses_the_root_destination(configured):
    from config.aifoundry import setup
    client = object()
    settings = {"AZURE_APP_RESOURCE_GROUP": "rg-app", "AZURE_RESOURCE_GROUP": configured}
    with patch.object(setup, "cfg", side_effect=lambda client, key, **kwargs: settings.get(key, "")), \
            patch.dict("os.environ", {}, clear=True):
        assert setup.foundry_resource_group(client) == configured


def test_foundry_configuration_does_not_fallback_after_permission_failure():
    from config.aifoundry import setup
    from azure.core.exceptions import HttpResponseError
    from unittest.mock import Mock
    client = Mock()
    client.get_configuration_setting.side_effect = HttpResponseError("denied")
    with pytest.raises(SystemExit):
        setup.cfg(client, "AZURE_RESOURCE_GROUP", required=False)


def test_powershell_discovery_honors_destination_and_exact_external_monitoring_ids():
    """The hook now delegates exact destination checks to the shared verifier."""
    from config.deployment import metadata

    document = {"context": {
        "subscriptionId": SUB, "resourceGroups": {"foundry": "rg-ai", "application": "rg-app"},
    }}
    search = f"/subscriptions/{SUB}/resourceGroups/rg-ai/providers/Microsoft.Search/searchServices/search"
    metadata._arm(search, "Microsoft.Search/searchServices", document, area="foundry")
    for wrong in (
        search.replace("rg-ai", "rg-app"),
        search.replace("rg-ai", "foreign"),
        search.replace(SUB, "foreign-sub"),
    ):
        with pytest.raises(metadata.MetadataError, match="binding"):
            metadata._arm(wrong, "Microsoft.Search/searchServices", document, area="foundry")
    external = "/subscriptions/central-sub/resourceGroups/central-rg/providers/Microsoft.Insights/components/central"
    metadata._arm(external, "Microsoft.Insights/components", document, area="application", external=external)
    for wrong in (external.replace("/central", "/other"), search):
        with pytest.raises(metadata.MetadataError, match="binding"):
            metadata._arm(wrong, "Microsoft.Insights/components", document, area="application", external=external)
