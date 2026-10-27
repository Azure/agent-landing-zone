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
from config.deployment import outputs

SUB = "11111111-1111-1111-1111-111111111111"
BASE = {
    "AZURE_SUBSCRIPTION_ID": SUB,
    "AZURE_RESOURCE_GROUP": "rg-app",
    "AZURE_FOUNDRY_RESOURCE_GROUP": "rg-ai",
    "AZURE_NETWORK_RESOURCE_GROUP": "rg-net",
    "AZURE_STORAGE_ACCOUNT_NAME": "sttest",
    "STORAGE_BLOB_ENDPOINT": "https://sttest.blob.core.windows.net/",
    "APP_CONFIG_ENDPOINT": "https://config.azconfig.io",
    "AZURE_AI_PROJECT_RESOURCE_ID": f"/subscriptions/{SUB}/resourceGroups/rg-ai/providers/Microsoft.CognitiveServices/accounts/account/projects/project",
    "AZURE_AI_PROJECT_ENDPOINT": "https://account.services.ai.azure.com/api/projects/project",
}


@pytest.mark.parametrize("foundry,network", [("", ""), ("rg-ai", ""), ("rg-ai", "rg-net"), ("RG-APP", "rg-app")])
def test_flat_destinations_preserve_json_v1(foundry, network):
    environment = {**BASE, "AZURE_FOUNDRY_RESOURCE_GROUP": foundry, "AZURE_NETWORK_RESOURCE_GROUP": network}
    document = outputs.build_platform_outputs({
        **environment, "AI_FOUNDRY_ACCOUNT_NAME": "account",
        "AZURE_CONTAINER_REGISTRY_ENDPOINT": "registry.azurecr.io",
        "KEY_VAULT_URI": "https://vault.vault.azure.net",
    })
    settings = outputs.platform_settings(document, environment)
    assert json.loads(settings[outputs.PLATFORM_OUTPUTS_KEY]) == document
    outputs.validate_platform_outputs(document)
    assert settings["AZURE_RESOURCE_GROUP"] == "rg-app"
    assert settings["AZURE_FOUNDRY_RESOURCE_GROUP"] == (foundry or "rg-app")
    assert settings["DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID"].lower() == (
        f"/subscriptions/{SUB}/resourceGroups/{foundry or 'rg-app'}/providers/"
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
    code = re.search(r'& python -c "([^"\n]*registry_resource_group[^"\n]*)"', source)
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
        [sys.executable, "-I", "-S", "-c", code.group(1)],
        cwd=tmp_path, env=environment, capture_output=True, text=True,
        timeout=20, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ("rg-registry" if external_registry else "rg-app")


def test_flat_context_does_not_clobber_bicep_document_scope_without_storage_outputs():
    env = {key: value for key, value in BASE.items() if key not in ("AZURE_STORAGE_ACCOUNT_NAME", "STORAGE_BLOB_ENDPOINT")}
    assert context_settings(env) == {
        "AZURE_RESOURCE_GROUP": "rg-app",
        "AZURE_FOUNDRY_RESOURCE_GROUP": "rg-ai",
        "AZURE_NETWORK_RESOURCE_GROUP": "rg-net",
    }
    explicit = f"/subscriptions/{SUB}/resourceGroups/rg-ai/providers/Microsoft.Storage/storageAccounts/sttest/blobServices/default/containers/documents"
    assert context_settings({**env, "DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID": explicit})["DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID"] == explicit
    with pytest.raises(ValueError):
        context_settings({**env, "DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID": "invalid"})


@pytest.mark.parametrize("container", ["documents", "custom-documents"])
def test_shell_platform_publication_hydrates_missing_azd_outputs_from_flat_agent_lz_metadata(container):
    environment = {
        **BASE, "AZURE_CONTAINER_REGISTRY_ENDPOINT": "registry.azurecr.io",
        "KEY_VAULT_URI": "https://vault.vault.azure.net",
    }
    environment.pop("STORAGE_BLOB_ENDPOINT")
    environment.pop("AZURE_STORAGE_ACCOUNT_NAME")
    storage_id = f"/subscriptions/{SUB}/resourceGroups/rg-ai/providers/Microsoft.Storage/storageAccounts/sttest"
    metadata = {
        "AI_FOUNDRY_ACCOUNT_NAME": "account",
        "STORAGE_BLOB_ENDPOINT": "https://sttest.blob.core.windows.net/",
        "STORAGE_ACCOUNT_RESOURCE_ID": storage_id,
        "DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID": f"{storage_id}/blobServices/default/containers/{container}",
    }
    calls = []
    def read(arguments):
        calls.append(arguments)
        assert arguments[:3] == ["appconfig", "kv", "list"]
        assert arguments[arguments.index("--label") + 1] == "agent-lz"
        key = arguments[arguments.index("--key") + 1]
        return json.dumps([{"key": key, "label": "agent-lz", "value": metadata[key]}] if key in metadata else [])
    values = outputs.load_platform_environment(environment, run_az=read)
    settings = outputs.platform_settings(outputs.build_platform_outputs(values), values)
    assert settings["DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID"] == metadata["DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID"]
    assert settings["AZURE_RESOURCE_GROUP"] == "rg-app"
    assert settings["AZURE_FOUNDRY_RESOURCE_GROUP"] == "rg-ai"
    assert "STORAGE_BLOB_ENDPOINT" not in environment
    assert all("set" not in call and "secret" not in str(call).lower() for call in calls)
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


def _foundation_reader(environment, calls):
    def read(arguments):
        calls.append(arguments)
        if arguments[:2] == ["group", "show"]:
            group = arguments[arguments.index("--name") + 1]
            return json.dumps({"id": f"/subscriptions/{SUB}/resourceGroups/{group}"})
        if arguments[:2] == ["resource", "show"]:
            resource_id = arguments[arguments.index("--ids") + 1]
            return json.dumps({"id": resource_id, "properties": {"customSubDomainName": "account"}})
        return json.dumps({
            "id": f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.AppConfiguration/configurationStores/config",
            "endpoint": environment["APP_CONFIG_ENDPOINT"],
        })
    return read


def test_foundation_verifies_every_destination_and_project_without_changing_runtime():
    calls = []
    environment = {**BASE, "DEPLOYMENT_TOPOLOGY": "hosted-panel"}
    outputs.verify_foundation(environment, run_az=_foundation_reader(environment, calls))
    assert {c[c.index("--name") + 1] for c in calls if c[:2] == ["group", "show"]} == {"rg-app", "rg-ai", "rg-net"}
    assert environment["DEPLOYMENT_TOPOLOGY"] == "hosted-panel"
    assert any(c[:2] == ["resource", "show"] and BASE["AZURE_AI_PROJECT_RESOURCE_ID"] in c for c in calls)
    assert not any("create" in c or "set" in c for c in calls)


@pytest.mark.parametrize("group", ["rg-ai(team)", "rg-équipe", "rg-٣"])
def test_classic_foundation_accepts_shared_resolver_valid_foundry_groups(group):
    environment = {
        **BASE, "DEPLOYMENT_TOPOLOGY": "classic",
        "AZURE_FOUNDRY_RESOURCE_GROUP": group,
        "AZURE_AI_PROJECT_RESOURCE_ID": BASE["AZURE_AI_PROJECT_RESOURCE_ID"].replace("rg-ai", group),
    }
    calls = []
    outputs.verify_foundation(environment, run_az=_foundation_reader(environment, calls))
    assert any(call[:2] == ["group", "show"] and group in call for call in calls)
    assert environment["AZURE_AI_PROJECT_RESOURCE_ID"] in next(
        call for call in calls if call[:2] == ["resource", "show"]
    )
    assert environment["DEPLOYMENT_TOPOLOGY"] == "classic"


@pytest.mark.parametrize("wrong_binding", ["subscription", "group", "endpoint"])
def test_unicode_foundation_group_keeps_subscription_destination_and_endpoint_checks(wrong_binding):
    group = "rg-équipe"
    environment = {
        **BASE, "AZURE_FOUNDRY_RESOURCE_GROUP": group,
        "AZURE_AI_PROJECT_RESOURCE_ID": BASE["AZURE_AI_PROJECT_RESOURCE_ID"].replace("rg-ai", group),
    }
    if wrong_binding == "subscription":
        environment["AZURE_AI_PROJECT_RESOURCE_ID"] = environment["AZURE_AI_PROJECT_RESOURCE_ID"].replace(SUB, "22222222-2222-2222-2222-222222222222")
    elif wrong_binding == "group":
        environment["AZURE_AI_PROJECT_RESOURCE_ID"] = environment["AZURE_AI_PROJECT_RESOURCE_ID"].replace(group, "other-équipe")
    else:
        environment["AZURE_AI_PROJECT_ENDPOINT"] = environment["AZURE_AI_PROJECT_ENDPOINT"].replace("account.services", "foreign.services")
    calls = []
    with pytest.raises(RuntimeError):
        outputs.verify_foundation(environment, run_az=_foundation_reader(environment, calls))
    if wrong_binding != "endpoint":
        assert calls == []
    assert not any("create" in call or "set" in call for call in calls)


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
    with patch("config.deployment.appconfig._run_az") as run, pytest.raises(RuntimeError):
        outputs.verify_foundation(environment)
    run.assert_not_called()


def test_foundation_never_falls_back_when_destination_read_fails():
    def denied(arguments):
        raise RuntimeError("read denied")
    with pytest.raises(RuntimeError, match="read denied"):
        outputs.verify_foundation(BASE, run_az=denied)


@pytest.mark.parametrize("groups", [("rg-app",), ("rg-app", "rg-ai"), ("rg-app", "rg-ai", "rg-net")])
def test_capability_roles_discover_actual_target_across_unique_destinations(groups):
    from config.appdefinition.roles import resolve_scope
    env = {
        **BASE, "AZURE_FOUNDRY_RESOURCE_GROUP": groups[min(1, len(groups) - 1)],
        "AZURE_NETWORK_RESOURCE_GROUP": groups[-1], "SEARCH_SERVICE_NAME": "search",
    }
    target = f"/subscriptions/{SUB}/resourceGroups/{env['AZURE_FOUNDRY_RESOURCE_GROUP']}/providers/Microsoft.Search/searchServices/search"
    calls = []
    def read(arguments, **kwargs):
        calls.append(arguments)
        group = arguments[arguments.index("--resource-group") + 1]
        return json.dumps([{"id": target, "name": "search"}] if group == env["AZURE_FOUNDRY_RESOURCE_GROUP"] else [])
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


@pytest.mark.parametrize("foundry,network", [("", ""), ("rg-ai", ""), ("rg-ai", "rg-net")])
def test_image_discovery_and_runtime_selection_remain_application_owned(foundry, network):
    from config.deployment.existing_images import definition_placeholder_plan
    from config.deployment.composition import resolve_mode
    env = {
        **BASE, "AZURE_FOUNDRY_RESOURCE_GROUP": foundry, "AZURE_NETWORK_RESOURCE_GROUP": network,
        "DEPLOYMENT_TOPOLOGY": "hosted-no-panel", "AGENTLZ_APP_DEFINITION": "",
    }
    with patch("config.deployment.existing_images.discover_existing_images", return_value={"frontend": "cr.azurecr.io/ui@sha256:" + "a" * 64}) as read:
        plan = definition_placeholder_plan(env)
    assert plan["ui"].endswith("a" * 64)
    assert resolve_mode(env).value == "hosted-no-panel"
    assert read.call_args.args[0] == "rg-app"


@pytest.mark.parametrize("configured", ["", "rg-ai", "rg-app"])
def test_foundry_configuration_uses_its_destination_with_legacy_fallback(configured):
    from config.aifoundry import setup
    client = object()
    settings = {"AZURE_RESOURCE_GROUP": "rg-app", "AZURE_FOUNDRY_RESOURCE_GROUP": configured}
    with patch.object(setup, "cfg", side_effect=lambda client, key, **kwargs: settings[key]), \
            patch.dict("os.environ", {}, clear=True):
        assert setup.foundry_resource_group(client) == (configured or "rg-app")


def test_foundry_configuration_does_not_fallback_after_permission_failure():
    from config.aifoundry import setup
    from azure.core.exceptions import HttpResponseError
    from unittest.mock import Mock
    client = Mock()
    client.get_configuration_setting.side_effect = HttpResponseError("denied")
    with pytest.raises(SystemExit):
        setup.cfg(client, "AZURE_FOUNDRY_RESOURCE_GROUP", required=False)


def test_powershell_discovery_honors_destination_and_exact_external_monitoring_ids():
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell is unavailable")
    driver = r"""
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:RG_CONSUMER_SOURCE, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Hook syntax failed' }
$node = $ast.FindAll({
    param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq '_resolveResource'
}, $true)[0]
Invoke-Expression $node.Extent.Text
$resourceGroup = 'rg-app'
$subscriptionId = 'selected-sub'
$script:Mode = 'split'
function az {
    if ($script:Mode -eq 'external') {
        if ($args[0] -ne 'resource' -or $args[1] -ne 'show' -or '--ids' -notin $args) { throw 'External ID was replaced by root discovery' }
        '{"id":"/subscriptions/central-sub/resourceGroups/central-rg/providers/Microsoft.Insights/components/central","type":"Microsoft.Insights/components"}'
    } else {
        if ($args[0] -ne 'resource' -or $args[1] -ne 'list') { throw 'Unexpected operation' }
        $group = $args[[array]::IndexOf($args, '-g') + 1]
        if ($group -ne 'rg-ai') { throw 'Foundry discovery used application RG' }
        $owner = if ($script:Mode -eq 'foreign') { 'foreign-rg' } else { 'rg-ai' }
        '[{"id":"/subscriptions/selected-sub/resourceGroups/' + $owner + '/providers/Microsoft.Search/searchServices/search","name":"search"}]'
    }
    $global:LASTEXITCODE = 0
}
if ((_resolveResource -Type 'Microsoft.Search/searchServices' -Group 'rg-ai' -PreferredName 'search') -ne 'search') { throw 'Wrong Foundry name' }
$script:Mode = 'foreign'
$denied = $false
try { _resolveResource -Type 'Microsoft.Search/searchServices' -Group 'rg-ai' | Out-Null } catch { $denied = $true }
if (-not $denied) { throw 'Foreign ID was accepted' }
$script:Mode = 'external'
$id = '/subscriptions/central-sub/resourceGroups/central-rg/providers/Microsoft.Insights/components/central'
if ((_resolveResource -Type 'Microsoft.Insights/components' -ResourceId $id) -ne 'central') { throw 'Central monitoring override was replaced' }
Write-Output 'destination/exact-ID checks passed'
"""
    source = Path(__file__).resolve().parents[1] / "scripts" / "postProvision.ps1"
    result = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-Command", driver],
        env={**os.environ, "RG_CONSUMER_SOURCE": str(source)},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "destination/exact-ID checks passed" in result.stdout
