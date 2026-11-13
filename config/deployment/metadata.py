"""Read and verify the selected provider's closed deployment metadata."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

import hcl2
from jsonschema import Draft202012Validator
from lark.exceptions import LarkError

from config import find_repo_root
from config.deployment.appconfig_intent import resolve_declared_parameters
from config.deployment.context import parse_resource_id
from config.deployment.egress import selected_environment
from config.deployment.provider import resolve_provider
from config.deployment.resource_groups import (
    check_binding, read_binding, resolve_resource_groups, resource_group_for,
)
from util.azure_cli import resolve_az_command
from util.terraform_backend import ensure_backend_binding, resolve_backend

LOGGER = logging.getLogger(__name__)
SCHEMA = Path(__file__).resolve().parents[2] / "contracts" / "deployment-metadata-v1.schema.json"
SLOTS = {
    "foundryAccount": ("Microsoft.CognitiveServices/accounts", "foundry", "deployAiFoundry"),
    "foundryProject": ("Microsoft.CognitiveServices/accounts/projects", "foundry", "deployAiFoundry"),
    "registry": ("Microsoft.ContainerRegistry/registries", "application", "deployContainerRegistry"),
    "appConfig": ("Microsoft.AppConfiguration/configurationStores", "application", "deployAppConfig"),
    "keyVault": ("Microsoft.KeyVault/vaults", "application", "deployKeyVault"),
    "storage": ("Microsoft.Storage/storageAccounts", "foundry", "deployStorageAccount"),
    "search": ("Microsoft.Search/searchServices", "foundry", "deploySearchService"),
    "cosmos": ("Microsoft.DocumentDB/databaseAccounts", "application", "deployCosmosDb"),
    "containerEnvironment": ("Microsoft.App/managedEnvironments", "application", "deployContainerEnv"),
    "network": ("Microsoft.Network/virtualNetworks", "network", "networkIsolation"),
    "speech": ("Microsoft.CognitiveServices/accounts", "foundry", "deploySpeechService"),
    "logAnalytics": ("Microsoft.OperationalInsights/workspaces", "application", "deployLogAnalytics"),
    "appInsights": ("Microsoft.Insights/components", "application", "deployAppInsights"),
}
EXTERNAL_INPUTS = {
    "registry": "hostedAgentContainerRegistryResourceId", "network": "existingVnetResourceId",
    "logAnalytics": "existingLogAnalyticsWorkspaceResourceId",
    "appInsights": "existingApplicationInsightsResourceId",
}
NAME_INPUTS = {
    "foundryAccount": "aiFoundryAccountName", "foundryProject": "aiFoundryProjectName",
    "registry": "containerRegistryName", "appConfig": "appConfigName", "keyVault": "keyVaultName",
    "storage": "storageAccountName", "search": "searchServiceName", "cosmos": "dbAccountName",
    "containerEnvironment": "containerEnvName", "network": "vnetName", "speech": "speechServiceName",
    "logAnalytics": "logAnalyticsWorkspaceName", "appInsights": "appInsightsName",
}
_RESOURCE_ALIASES = {
    "foundryAccount": ("AI_FOUNDRY_ACCOUNT_RESOURCE_ID", "AI_FOUNDRY_ACCOUNT_NAME", "AI_FOUNDRY_ACCOUNT_ENDPOINT"),
    "foundryProject": ("AZURE_AI_PROJECT_RESOURCE_ID", "AI_FOUNDRY_PROJECT_NAME", "AZURE_AI_PROJECT_ENDPOINT"),
    "registry": ("AZURE_CONTAINER_REGISTRY_RESOURCE_ID", "AZURE_CONTAINER_REGISTRY_NAME", "AZURE_CONTAINER_REGISTRY_ENDPOINT"),
    "appConfig": ("APP_CONFIG_RESOURCE_ID", "APP_CONFIG_NAME", "APP_CONFIG_ENDPOINT"),
    "keyVault": ("KEY_VAULT_RESOURCE_ID", "KEY_VAULT_NAME", "KEY_VAULT_URI"),
    "storage": ("STORAGE_ACCOUNT_RESOURCE_ID", "STORAGE_ACCOUNT_NAME", "STORAGE_BLOB_ENDPOINT"),
    "search": ("SEARCH_SERVICE_RESOURCE_ID", "SEARCH_SERVICE_NAME", "SEARCH_SERVICE_QUERY_ENDPOINT"),
    "cosmos": ("COSMOS_DB_ACCOUNT_RESOURCE_ID", "DATABASE_ACCOUNT_NAME", "COSMOS_DB_ENDPOINT"),
    "containerEnvironment": ("CONTAINER_ENVIRONMENT_RESOURCE_ID", "CONTAINER_ENVIRONMENT_NAME", ""),
    "network": ("VNET_RESOURCE_ID", "VNET_NAME", ""),
    "speech": ("SPEECH_SERVICE_RESOURCE_ID", "SPEECH_SERVICE_NAME", "SPEECH_SERVICE_ENDPOINT"),
    "logAnalytics": ("LOG_ANALYTICS_WORKSPACE_RESOURCE_ID", "LOG_ANALYTICS_WORKSPACE_NAME", ""),
    "appInsights": ("APPLICATION_INSIGHTS_RESOURCE_ID", "APPLICATION_INSIGHTS_NAME", ""),
}
_ALIAS_EQUIVALENTS = {
    "AI_FOUNDRY_PROJECT_RESOURCE_ID": "AZURE_AI_PROJECT_RESOURCE_ID",
    "AI_FOUNDRY_PROJECT_ENDPOINT": "AZURE_AI_PROJECT_ENDPOINT",
    "CONTAINER_REGISTRY_RESOURCE_ID": "AZURE_CONTAINER_REGISTRY_RESOURCE_ID",
    "CONTAINER_REGISTRY_NAME": "AZURE_CONTAINER_REGISTRY_NAME",
    "CONTAINER_REGISTRY_LOGIN_SERVER": "AZURE_CONTAINER_REGISTRY_ENDPOINT",
    "AZURE_STORAGE_ACCOUNT_NAME": "STORAGE_ACCOUNT_NAME",
    "STORAGE_ACCOUNT_BLOB_ENDPOINT": "STORAGE_BLOB_ENDPOINT",
    "SEARCH_SERVICE_ENDPOINT": "SEARCH_SERVICE_QUERY_ENDPOINT",
    "KEY_VAULT_ENDPOINT": "KEY_VAULT_URI", "AZURE_KEY_VAULT_ENDPOINT": "KEY_VAULT_URI",
    "LOG_ANALYTICS_RESOURCE_ID": "LOG_ANALYTICS_WORKSPACE_RESOURCE_ID",
    "APP_INSIGHTS_RESOURCE_ID": "APPLICATION_INSIGHTS_RESOURCE_ID",
    "AZURE_SPEECH_RESOURCE_ID": "SPEECH_SERVICE_RESOURCE_ID",
    "AZURE_SPEECH_RESOURCE_NAME": "SPEECH_SERVICE_NAME",
    "AZURE_SPEECH_ENDPOINT": "SPEECH_SERVICE_ENDPOINT",
}
JsonRunner = Callable[..., Any]
_DEFAULT_MODELS = (
    ("GPT_MODEL", "gpt-5-nano", "2025-08-07"),
    ("EMBEDDING_MODEL", "text-embedding-3-large", "1"),
)


def _selection(slot: str, parameters: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Mirror foundation ownership, not similarly named Foundry backing inputs."""
    flag = SLOTS[slot][2]
    enabled = parameters.get(flag, slot not in ("cosmos", "network", "speech")) is True
    external = None
    if slot == "foundryProject":
        enabled = enabled and parameters.get("deployAfProject", True) is True
    elif slot == "network":
        enabled = enabled or parameters.get("deployPostgreSql", False) is True
        if enabled and parameters.get("useExistingVNet", False) is True:
            external = parameters.get(EXTERNAL_INPUTS[slot]) or None
            if not external:
                raise MetadataError("resources.network: Selected existing network requires its declared ARM ID.")
    elif slot == "registry":
        if not enabled and any(parameters.get(key, False) is True for key in ("prepareHostedAgent", "deployHostedAgent")):
            external = parameters.get(EXTERNAL_INPUTS[slot]) or None
            if not external:
                raise MetadataError("resources.registry: Selected hosted registry requires its declared ARM ID.")
            enabled = True
    elif slot in ("logAnalytics", "appInsights"):
        external = parameters.get(EXTERNAL_INPUTS[slot]) or None
        if external:
            enabled = True
        elif slot == "appInsights":
            enabled = enabled and (
                parameters.get("deployLogAnalytics", True) is True
                or bool(parameters.get(EXTERNAL_INPUTS["logAnalytics"]))
            )
    return enabled, external


class MetadataError(ValueError):
    """A redacted boundary error, safe for hook diagnostics."""


@dataclass(frozen=True)
class VerifiedMetadata:
    document: dict[str, Any]
    environment: Mapping[str, str]
    parameters: Mapping[str, Any]
    live_resources: Mapping[str, dict[str, Any]]


def run_json(
    command: list[str], *, cwd: Path | None = None,
    environment: Mapping[str, str] | None = None, decode_json: bool = True,
) -> Any:
    try:
        result = subprocess.run(
            command, cwd=cwd, env=environment, capture_output=True, text=True, timeout=90, check=False,
        )
        if result.returncode:
            raise MetadataError(
                "provider/access: Read failed. Restore selected provider permissions, "
                "backend and runner connectivity, then retry."
            )
        return json.loads(result.stdout) if decode_json else None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        raise MetadataError(
            "provider/access: Read unavailable or invalid JSON. Restore provider/backend "
            "access and connectivity, then retry."
        ) from None


def validate_shape(document: object) -> None:
    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise MetadataError("schema: Restore the deployment metadata v1 contract.") from None
    validator = Draft202012Validator(schema)
    if not validator.is_valid(document):
        raise MetadataError("schema: Invalid deployment metadata v1. Reprovision with a compatible foundation.")
    # uniqueItems alone cannot reject distinct rows with the same canonical binding.
    arrays = [document["modelDeployments"], document["containerApps"], *document["dataResources"].values()]
    for rows in arrays:
        for field in ("canonicalName", "resourceId", "name"):
            values = [row[field].casefold() for row in rows]
            if len(values) != len(set(values)):
                raise MetadataError("schema: Duplicate metadata mapping. Correct declarations and reprovision.")
    for slot in document["resources"].values():
        if slot["resource"] and slot["resource"]["endpoint"]:
            endpoint(slot["resource"]["endpoint"])
    for model in document["modelDeployments"]:
        endpoint(model["endpoint"])


def endpoint(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.port not in (None, 443)
        ):
            raise ValueError
    except ValueError:
        raise MetadataError("endpoint: Expected a credential-free HTTPS service endpoint.") from None
    return f"https://{parsed.hostname.lower()}{parsed.path.rstrip('/')}"


def aliases(document: Mapping[str, Any]) -> dict[str, str]:
    context = document["context"]
    groups = context["resourceGroups"]
    values = {
        "AZURE_ENV_NAME": context["environmentName"], "ENVIRONMENT_NAME": context["environmentName"],
        "AZURE_TENANT_ID": context["tenantId"], "TENANT_ID": context["tenantId"],
        "AZURE_SUBSCRIPTION_ID": context["subscriptionId"], "SUBSCRIPTION_ID": context["subscriptionId"],
        "AZURE_RESOURCE_GROUP": groups["foundry"], "AZURE_FOUNDRY_RESOURCE_GROUP": groups["foundry"],
        "AZURE_APP_RESOURCE_GROUP": groups["application"], "AZURE_NETWORK_RESOURCE_GROUP": groups["network"],
        "DEPLOYMENT_NAME": context["deploymentName"], "AGENTLZ_APP_ID": context["applicationId"],
        "APP_RUNTIME_CONFIGURATION_MODE": context["runtimeConfigurationMode"],
    }
    for slot, keys in _RESOURCE_ALIASES.items():
        resource = document["resources"][slot]["resource"]
        if not resource:
            continue
        for key, field in zip(keys, ("resourceId", "name", "endpoint")):
            if key and resource[field]:
                values[key] = resource[field]
    for old, new in _ALIAS_EQUIVALENTS.items():
        if new in values:
            values[old] = values[new]
    for model in document["modelDeployments"]:
        values[model["canonicalName"]] = model["name"]
    for category, rows in document["dataResources"].items():
        for row in rows:
            values[row["canonicalName"]] = row["name"]
            values[row["canonicalName"] + "_RESOURCE_ID"] = row["resourceId"]
    for app in document["containerApps"]:
        values[app["canonicalName"]] = app["name"]
        values[app["canonicalName"] + "_NAME"] = app["name"]
        values[app["canonicalName"] + "_RESOURCE_ID"] = app["resourceId"]
        if app["fqdn"]:
            values[app["canonicalName"] + "_ENDPOINT"] = "https://" + app["fqdn"]
    if "AZURE_CONTAINER_REGISTRY_ENDPOINT" in values:
        server = urlsplit(values["AZURE_CONTAINER_REGISTRY_ENDPOINT"]).hostname
        values["AZURE_CONTAINER_REGISTRY_ENDPOINT"] = server
        values["CONTAINER_REGISTRY_LOGIN_SERVER"] = server
    return values


def _agrees(key: str, left: str, right: str) -> bool:
    if left.startswith("/subscriptions/") and right.startswith("/subscriptions/"):
        return left.casefold() == right.casefold()
    if left.startswith("https://") and right.startswith("https://"):
        return endpoint(left) == endpoint(right)
    if key.endswith(("_ID", "_NAME", "_RESOURCE_GROUP")) or key.startswith("AZURE_"):
        return left.casefold() == right.casefold()
    return left == right


def _normalized(value: Any, field: str = "") -> Any:
    if isinstance(value, dict):
        result = {key: _normalized(item, key) for key, item in value.items()}
        if field == "resourceGroups":
            return {key: item.casefold() if isinstance(item, str) else item for key, item in result.items()}
        if "resourceId" in value and isinstance(value.get("name"), str):
            result["name"] = value["name"].casefold()
        return result
    if isinstance(value, list):
        rows = [_normalized(item, field) for item in value]
        return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))
    if isinstance(value, str):
        if field in ("resourceId", "tenantId", "subscriptionId", "principalId", "clientId", "fqdn"):
            return value.casefold()
        if field == "resourceGroups":
            return value.casefold()
        if field == "endpoint":
            return endpoint(value)
    return value


def _check_cached_rows(key: str, cached: str, evaluated: list[dict[str, Any]]) -> None:
    try:
        rows = json.loads(cached)
        if not isinstance(rows, list) or len(rows) != len(evaluated):
            raise ValueError
        by_name = {row["canonicalName"]: row for row in evaluated}
        seen = set()
        fields = {
            "id": "resourceId", "resourceId": "resourceId", "name": "name",
            "model": "model", "api_version": "apiVersion", "apiVersion": "apiVersion",
            "endpoint": "endpoint", "service_name": "serviceName", "serviceName": "serviceName",
            "fqdn": "fqdn", "identity": "identity",
            "principalId": "principalId",
        }
        for saved in rows:
            if not isinstance(saved, dict):
                raise ValueError
            canonical = saved.get("canonical_name", saved.get("canonicalName"))
            if canonical in seen or canonical not in by_name:
                raise ValueError
            seen.add(canonical)
            actual = by_name[canonical]
            actual = {**actual, "principalId": (actual.get("identity") or {}).get("principalId")}
            for old, new in fields.items():
                if old not in saved or new not in actual:
                    continue
                left, right = saved[old], actual[new]
                if new == "name" and isinstance(left, str):
                    left, right = left.casefold(), right.casefold()
                if _normalized(left, new) != _normalized(right, new):
                    raise ValueError
    except (ValueError, KeyError, TypeError):
        raise MetadataError(f"cache.{key}: Conflicting saved mapping. Refresh the selected environment.") from None


def validate_context(
    document: dict[str, Any], environment: Mapping[str, str],
    parameters: Mapping[str, Any], provider: str,
) -> None:
    context = document["context"]
    expected = {
        "environmentName": environment.get("AZURE_ENV_NAME"),
        "tenantId": environment.get("AZURE_TENANT_ID") or environment.get("TENANT_ID"),
        "subscriptionId": environment.get("AZURE_SUBSCRIPTION_ID"),
        "provider": provider,
        "applicationId": environment.get("AGENTLZ_APP_ID") or parameters.get("applicationId") or "agent-lz-default",
        "runtimeConfigurationMode": parameters.get("appRuntimeConfigurationMode", "appConfig"),
        "deploymentName": (
            environment.get("DEPLOYMENT_NAME") if provider == "bicep" else
            environment.get("AZURE_DEPLOYMENT_NAME") or environment.get("AZURE_ENV_NAME")
        ),
    }
    for field, selected in expected.items():
        actual = context[field]
        if field in ("tenantId", "subscriptionId"):
            actual, selected = str(actual).casefold(), str(selected).casefold()
        if not selected or actual != selected:
            raise MetadataError(f"context.{field}: Selected declaration conflicts. Restore selection and reprovision.")
    for area in ("foundry", "application", "network"):
        if context["resourceGroups"][area].casefold() != resource_group_for(environment, area).casefold():
            raise MetadataError(f"context.resourceGroups.{area}: Restore the original destination binding.")
    cached = environment.get("DEPLOYMENT_METADATA")
    if cached:
        try:
            saved = json.loads(cached)
        except ValueError:
            raise MetadataError("cache: Invalid saved metadata. Run azd env refresh for the selected environment.") from None
        if _normalized(saved) != _normalized(document):
            raise MetadataError("cache: Stale saved metadata. Run azd env refresh for the selected environment.")
    evaluated = aliases(document)
    resource_keys = {key for keys in _RESOURCE_ALIASES.values() for key in keys if key}
    resource_keys.update(_ALIAS_EQUIVALENTS)
    for key in resource_keys - evaluated.keys():
        if environment.get(key):
            raise MetadataError(f"cache.{key}: Saved alias refers to a disabled resource. Refresh the selected environment.")
    for key, value in evaluated.items():
        if environment.get(key) and not _agrees(key, environment[key], value):
            raise MetadataError(f"cache.{key}: Conflicting saved alias. Restore selection and run azd env refresh.")
    for key, field in (("MODEL_DEPLOYMENTS", "modelDeployments"), ("CONTAINER_APPS", "containerApps")):
        if environment.get(key):
            _check_cached_rows(key, environment[key], document[field])


def read_bicep(environment: Mapping[str, str], runner: JsonRunner = run_json) -> dict[str, Any]:
    name = environment.get("DEPLOYMENT_NAME", "")
    if not re.fullmatch(r"[A-Za-z0-9_().-]{1,64}", name):
        raise MetadataError("source.deploymentName: Missing valid DEPLOYMENT_NAME. Reprovision the selected foundation.")
    command = [
        resolve_az_command(), "deployment", "group", "show",
        "--subscription", environment["AZURE_SUBSCRIPTION_ID"],
        "--resource-group", resource_group_for(environment, "foundry"),
        "--name", name, "--output", "json", "--only-show-errors", "--query",
    ]
    if runner([*command, "properties.provisioningState"]) != "Succeeded":
        raise MetadataError("provision: Selected deployment did not succeed. Complete same-provider provisioning first.")
    value = runner([*command, "properties.outputs.DEPLOYMENT_METADATA.value"])
    if not isinstance(value, dict):
        raise MetadataError("source: Missing DEPLOYMENT_METADATA. Reprovision the selected foundation.")
    return value


def approve_terraform_source(directory: Path) -> None:
    try:
        declarations = []
        local_values: dict[str, Any] = {}
        for path in directory.glob("*.tf"):
            document = hcl2.loads(path.read_text(encoding="utf-8"))
            for block in document.get("locals", []):
                local_values.update(block)
            for block in document.get("output", []):
                if "DEPLOYMENT_METADATA" in block:
                    declarations.append(block["DEPLOYMENT_METADATA"])
        if len(declarations) != 1 or declarations[0].get("sensitive") is not False:
            raise ValueError
        pending = [declarations[0].get("value", "")]
        visited: set[str] = set()
        while pending:
            expression = str(pending.pop())
            if re.search(r"\bnonsensitive\s*\(", expression):
                raise ValueError
            references = re.findall(
                r'\blocal(?:\.([A-Za-z_][A-Za-z0-9_]*)|\[\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*\])',
                expression,
            )
            for dotted, indexed in references:
                name = dotted or indexed
                if name not in visited:
                    visited.add(name)
                    pending.append(local_values.get(name, ""))
    except (OSError, ValueError, TypeError, KeyError, LarkError):
        raise MetadataError("source: Require one reviewed DEPLOYMENT_METADATA output with literal sensitive = false.") from None


def read_terraform(
    root: Path, directory: Path, environment: Mapping[str, str], runner: JsonRunner = run_json,
) -> dict[str, Any]:
    approve_terraform_source(directory)
    try:
        backend = resolve_backend(environment)
        ensure_backend_binding(backend, root / ".azure")
    except ValueError:
        raise MetadataError("source.backend: Restore the original selected Terraform backend binding.") from None
    try:
        relative_directory = directory.resolve().relative_to(root.resolve())
    except ValueError:
        raise MetadataError("source.backend: Selected provider directory must remain inside the project.") from None
    native = root / ".azure" / environment["AZURE_ENV_NAME"] / relative_directory
    data_directory = native / ".terraform"
    if not data_directory.is_dir():
        raise MetadataError("source.backend: Original Terraform working directory is not initialized. Restore it.")
    expected = backend.terraform_config()
    config = native / (environment["AZURE_ENV_NAME"] + ".conf.json")
    try:
        from config.deployment.app_settings import substitute_values
        rendered = substitute_values(json.loads(config.read_text(encoding="utf-8")), environment)
        rendered = {key: value == "true" if value in ("true", "false") else value for key, value in rendered.items()}
        if rendered != expected:
            raise ValueError
    except (OSError, ValueError, TypeError, AttributeError):
        raise MetadataError("source.backend: Native backend configuration conflicts with the original binding.") from None
    if any(os.environ.get(key) or environment.get(key) for key in ("ARM_ACCESS_KEY", "ARM_SAS_TOKEN")):
        raise MetadataError("source.backend: Remove shared-key/SAS overrides. Restore Entra-authenticated state access.")
    process_environment = {**os.environ, **environment, "TF_DATA_DIR": str(data_directory.resolve())}
    if any(process_environment.get(key) for key in ("TF_CLI_ARGS", "TF_CLI_ARGS_init", "TF_CLI_ARGS_output", "TF_WORKSPACE")):
        raise MetadataError("source.backend: Remove Terraform CLI/workspace overrides for the selected native backend.")
    # Native init rejects a different initialized backend without reading state
    # ourselves or accepting reconfiguration/migration.
    runner([
        "terraform", "init", "-input=false", "-get=false", "-lockfile=readonly",
        "-backend-config=" + str(config.resolve()),
    ], cwd=directory, environment=process_environment, decode_json=False)
    value = runner(
        ["terraform", "output", "-json", "DEPLOYMENT_METADATA"], cwd=directory,
        environment=process_environment,
    )
    if not isinstance(value, dict):
        raise MetadataError("source: Missing DEPLOYMENT_METADATA. Reprovision using the original backend.")
    return value


def _arm(
    resource_id: str, expected_type: str, document: Mapping[str, Any],
    *, area: str, external: str | None = None,
) -> None:
    try:
        parsed = parse_resource_id(resource_id)
        context = document["context"]
        permitted = (
            resource_id.casefold() == external.casefold() if external else
            parsed.subscription.casefold() == context["subscriptionId"].casefold()
            and parsed.resource_group.casefold() == context["resourceGroups"][area].casefold()
        )
        if not permitted or parsed.resource_type.casefold() != expected_type.casefold():
            raise ValueError
    except ValueError:
        raise MetadataError("resource.binding: Unexpected type or undeclared destination. Restore declarations and reprovision.") from None


def verify_live(
    document: dict[str, Any], parameters: Mapping[str, Any], runner: JsonRunner = run_json,
) -> dict[str, dict[str, Any]]:
    context = document["context"]
    subscription = context["subscriptionId"]
    live = {}

    def declared_rows(parameter: str, actual: list[dict[str, Any]], enabled: bool) -> None:
        declarations = parameters.get(parameter, [])
        if not isinstance(declarations, list):
            raise MetadataError("intent.mappings: Restore original typed resource declarations.")
        expected = declarations if enabled else []
        if parameter == "modelDeploymentList" and enabled and not declarations:
            expected = [{
                "canonical_name": canonical, "name": name,
                "model": {"format": "OpenAI", "name": name, "version": version},
            } for canonical, name, version in _DEFAULT_MODELS]
        if len(expected) != len(actual):
            raise MetadataError("intent.mappings: Missing or unexpected selected resource mapping. Reprovision.")
        by_name = {row.get("canonical_name"): row for row in expected}
        for row in actual:
            declaration = by_name.get(row["canonicalName"])
            if not isinstance(declaration, dict):
                raise MetadataError("intent.mappings: Undeclared canonical mapping. Restore selection and reprovision.")
            if parameter == "modelDeploymentList":
                api_version = declaration.get("apiVersion")
                if api_version is None or (
                    context["provider"] == "terraform" and api_version == ""
                ):
                    api_version = "2025-01-01-preview"
                if (
                    any(declaration.get(field) != row[field] for field in ("name", "model"))
                    or api_version != row["apiVersion"]
                ):
                    raise MetadataError("modelDeployments: Evaluated model conflicts with the original declaration.")
            elif parameter == "containerAppsList":
                if (
                    declaration.get("service_name") != row["serviceName"]
                    or declaration.get("name") and declaration["name"].casefold() != row["name"].casefold()
                ):
                    raise MetadataError("containerApps: Evaluated app conflicts with the original declaration.")
            elif declaration.get("name") != row["name"]:
                raise MetadataError("dataResources: Evaluated child conflicts with the original declaration.")

    declared_rows("modelDeploymentList", document["modelDeployments"],
                  document["resources"]["foundryAccount"]["status"] != "disabled")
    declared_rows("containerAppsList", document["containerApps"],
                  parameters.get("deployContainerApps", True) is True and parameters.get("deployContainerEnv", True) is True)
    declared_rows("storageAccountContainersList", document["dataResources"]["storageContainers"],
                  document["resources"]["storage"]["status"] == "managed")
    declared_rows("databaseContainersList", document["dataResources"]["cosmosContainers"],
                  document["resources"]["cosmos"]["status"] == "managed")
    databases = document["dataResources"]["cosmosDatabases"]
    cosmos_selected = document["resources"]["cosmos"]["status"] == "managed"
    if len(databases) != int(cosmos_selected) or (
        databases and databases[0]["canonicalName"] != "DATABASE_NAME"
    ):
        raise MetadataError("dataResources.cosmosDatabases: Restore the selected canonical database mapping.")
    declared_database = parameters.get("dbDatabaseName")
    if cosmos_selected and declared_database and databases[0]["name"] != declared_database:
        raise MetadataError("dataResources.cosmosDatabases: Database conflicts with its declared name.")

    def az(arguments: list[str]) -> Any:
        return runner([resolve_az_command(), *arguments, "--subscription", subscription,
                       "--output", "json", "--only-show-errors"])

    account = az(["account", "show", "--query", "{id:id,tenantId:tenantId}"])
    if not isinstance(account, dict) or any(
        str(account.get(key, "")).casefold() != context[field].casefold()
        for key, field in (("id", "subscriptionId"), ("tenantId", "tenantId"))
    ):
        raise MetadataError("context.tenantId: Authenticated tenant/subscription does not match the selected environment.")
    for group in dict.fromkeys(context["resourceGroups"].values()):
        row = az(["group", "show", "--name", group, "--query", "{id:id}"])
        expected = f"/subscriptions/{subscription}/resourceGroups/{group}"
        if not isinstance(row, dict) or str(row.get("id", "")).casefold() != expected.casefold():
            raise MetadataError("resourceGroups: Live destination mismatch or unavailable group.")

    def read(resource: Mapping[str, Any]) -> dict[str, Any]:
        if resource.get("name") and resource["resourceId"].rsplit("/", 1)[-1].casefold() != resource["name"].casefold():
            raise MetadataError("resource.name: Resource ID and mapped name disagree.")
        row = az(["resource", "show", "--ids", resource["resourceId"], "--query",
                  "{id:id,name:name,type:type,identity:identity,properties:{"
                  "provisioningState:properties.provisioningState,customSubDomainName:properties.customSubDomainName,"
                  "endpoint:properties.endpoint,endpoints:properties.endpoints,loginServer:properties.loginServer,"
                  "vaultUri:properties.vaultUri,primaryEndpoints:properties.primaryEndpoints,"
                  "documentEndpoint:properties.documentEndpoint,model:properties.model,"
                  "managedEnvironmentId:properties.managedEnvironmentId,configuration:{"
                  "ingress:properties.configuration.ingress,registries:properties.configuration.registries}}}"])
        if not isinstance(row, dict) or str(row.get("id", "")).casefold() != resource["resourceId"].casefold():
            raise MetadataError("resource.identity: Live ARM ID mismatch or unavailable target.")
        expected_type = parse_resource_id(resource["resourceId"]).resource_type
        if str(row.get("type", "")).casefold() != expected_type.casefold():
            raise MetadataError("resource.type: Live ARM type differs from the selected target.")
        if row.get("properties", {}).get("provisioningState") not in (None, "Succeeded", "succeeded"):
            raise MetadataError("resource.provisioningState: Target is not ready. Complete provisioning and retry.")
        return row

    for slot, (kind, area, _) in SLOTS.items():
        binding = document["resources"][slot]
        enabled, external = _selection(slot, parameters)
        expected_status = "referenced" if external else "managed" if enabled else "disabled"
        if binding["status"] != expected_status:
            raise MetadataError(f"resources.{slot}.selection: Evaluated ownership conflicts with original selection.")
        if not enabled:
            continue
        resource = binding["resource"]
        _arm(resource["resourceId"], kind, document, area=area, external=external)
        declared_name = parameters.get(NAME_INPUTS[slot])
        if binding["status"] == "managed" and declared_name and (
            not isinstance(declared_name, str) or resource["name"].casefold() != declared_name.casefold()
        ):
            raise MetadataError(f"resources.{slot}.name: Resource conflicts with its declared name.")
        if slot == "registry" and external:
            declared_endpoint = parameters.get("hostedAgentContainerRegistryEndpoint")
            if not isinstance(declared_endpoint, str) or not declared_endpoint:
                raise MetadataError("resources.registry.endpoint: Restore the declared hosted registry endpoint.")
            if "://" not in declared_endpoint:
                declared_endpoint = "https://" + declared_endpoint
            if endpoint(resource["endpoint"]) != endpoint(declared_endpoint):
                raise MetadataError("resources.registry.endpoint: Evaluated registry conflicts with its declared endpoint.")
        if parse_resource_id(resource["resourceId"]).name.rsplit("/", 1)[-1].casefold() != resource["name"].casefold():
            raise MetadataError(f"resources.{slot}.name: Resource ID and name disagree.")
        if slot == "appConfig" and context["runtimeConfigurationMode"] != "appConfig":
            continue
        row = read(resource)
        live[slot] = row
        properties = row.get("properties") or {}
        domain = properties.get("customSubDomainName")
        actual_endpoint = {
            "registry": "https://" + properties.get("loginServer", ""),
            "appConfig": properties.get("endpoint"),
            "keyVault": properties.get("vaultUri"),
            "storage": (properties.get("primaryEndpoints") or {}).get("blob"),
            "cosmos": properties.get("documentEndpoint"),
            "foundryAccount": f"https://{domain}.cognitiveservices.azure.com" if domain else None,
            "search": f"https://{resource['name']}.search.windows.net",
            "speech": properties.get("endpoint"),
        }.get(slot)
        if slot in ("registry", "appConfig", "keyVault", "storage", "cosmos", "foundryAccount", "search", "speech"):
            if not resource["endpoint"] or not actual_endpoint or endpoint(resource["endpoint"]) != endpoint(actual_endpoint):
                raise MetadataError(f"resources.{slot}.endpoint: Live service binding mismatch or missing endpoint.")
    resources = document["resources"]
    foundry = resources["foundryAccount"]["resource"]
    project = resources["foundryProject"]["resource"]
    if project:
        if not foundry or project["resourceId"].rsplit("/projects/", 1)[0].casefold() != foundry["resourceId"].casefold():
            raise MetadataError("resources.foundryProject: Project is not a child of the selected account.")
        domain = live["foundryAccount"]["properties"]["customSubDomainName"]
        expected_project_endpoint = f"https://{domain}.services.ai.azure.com/api/projects/{project['name']}"
        if endpoint(project["endpoint"]) != endpoint(expected_project_endpoint):
            raise MetadataError("resources.foundryProject.endpoint: Exact account/project endpoint mismatch.")
    for model in document["modelDeployments"]:
        if not foundry or model["resourceId"].casefold() != (foundry["resourceId"] + "/deployments/" + model["name"]).casefold():
            raise MetadataError("modelDeployments: Model is not a child of the selected account.")
        observed = read({"resourceId": model["resourceId"]})
        if observed["properties"].get("model") != model["model"]:
            raise MetadataError("modelDeployments.model: Live model differs from the declared mapping.")
        if endpoint(model["endpoint"]) != f"https://{foundry['name'].lower()}.openai.azure.com":
            raise MetadataError("modelDeployments.endpoint: Model endpoint is not bound to the selected account.")
    environment_resource = resources["containerEnvironment"]["resource"]
    registry = resources["registry"]["resource"]
    for app in document["containerApps"]:
        _arm(app["resourceId"], "Microsoft.App/containerApps", document, area="application")
        observed = read(app)
        properties = observed.get("properties") or {}
        if not environment_resource or str(properties.get("managedEnvironmentId", "")).casefold() != environment_resource["resourceId"].casefold():
            raise MetadataError("containerApps.environment: App belongs to a different managed environment.")
        if ((properties.get("configuration") or {}).get("ingress") or {}).get("fqdn") != app["fqdn"]:
            raise MetadataError("containerApps.fqdn: Live app endpoint mismatch.")
        identity = app["identity"]
        assigned = observed.get("identity") or {}
        if identity["kind"] == "systemAssigned":
            if (
                parameters.get("useUAI") is True
                or "SystemAssigned" not in str(assigned.get("type", ""))
                or assigned.get("principalId", "").casefold() != identity["principalId"].casefold()
            ):
                raise MetadataError("containerApps.identity: Live system-assigned principal mismatch.")
        else:
            if parameters.get("useUAI", False) is False:
                raise MetadataError("containerApps.identity: Identity kind conflicts with the selected input.")
            bindings = assigned.get("userAssignedIdentities") or {}
            selected = next((value for key, value in bindings.items() if key.casefold() == identity["resourceId"].casefold()), None)
            if not selected or any(
                str(selected.get(field, "")).casefold() != identity[field].casefold()
                for field in ("principalId", "clientId")
            ):
                raise MetadataError("containerApps.identity: Live user-assigned principal/client binding mismatch.")
            _arm(identity["resourceId"], "Microsoft.ManagedIdentity/userAssignedIdentities", document, area="application")
            observed_identity = az(["identity", "show", "--ids", identity["resourceId"],
                                    "--query", "{id:id,principalId:principalId,clientId:clientId}"])
            if not isinstance(observed_identity, dict) or any(
                str(observed_identity.get(field, "")).casefold() != identity[field].casefold()
                for field in ("principalId", "clientId")
            ) or str(observed_identity.get("id", "")).casefold() != identity["resourceId"].casefold():
                raise MetadataError("containerApps.identity: Live identity resource does not match the app association.")
        if registry:
            registries = (properties.get("configuration") or {}).get("registries") or []
            server = urlsplit(registry["endpoint"]).hostname
            for binding in registries:
                if binding.get("server") == server and binding.get("identity") not in (
                    "system" if identity["kind"] == "systemAssigned" else identity["resourceId"],
                ):
                    raise MetadataError("containerApps.registry: Registry identity conflicts with the selected app.")
    for category, parent_slot, suffix in (
        ("storageContainers", "storage", "/blobServices/default/containers/"),
        ("cosmosDatabases", "cosmos", "/sqlDatabases/"),
        ("cosmosContainers", "cosmos", "/sqlDatabases/"),
    ):
        parent = resources[parent_slot]["resource"]
        for child in document["dataResources"][category]:
            if category == "cosmosContainers":
                databases = document["dataResources"]["cosmosDatabases"]
                expected_ids = [database["resourceId"] + "/containers/" + child["name"] for database in databases]
            else:
                expected_ids = [parent["resourceId"] + suffix + child["name"]] if parent else []
            if not parent or child["resourceId"].casefold() not in [value.casefold() for value in expected_ids]:
                raise MetadataError(f"dataResources.{category}: Child belongs to a different account.")
            if child["resourceId"].rsplit("/", 1)[-1] != child["name"]:
                raise MetadataError(f"dataResources.{category}: Child name conflicts with its ARM ID.")
            read(child)
    if context["runtimeConfigurationMode"] == "appConfig" and resources["appConfig"]["status"] == "disabled":
        raise MetadataError("prerequisite.appConfig: appConfig mode requires a usable declared store. Correct the selection.")
    return live


def load_metadata(
    environment: Mapping[str, str] | None = None, *, project_root: Path | None = None,
    input_path: Path | None = None, runner: JsonRunner = run_json,
) -> VerifiedMetadata:
    root = project_root or find_repo_root()
    name = (environment or os.environ).get("AZURE_ENV_NAME", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name) or ".." in name:
        raise MetadataError("selection.environment: Select an explicit valid azd environment.")
    try:
        selected = selected_environment(root, name)
        provider = resolve_provider(root)
        selection = resolve_resource_groups(selected)
        bound = read_binding(root / ".azure", name)
        if bound is None:
            raise MetadataError("selection.binding: Restore the original resource-groups.json binding.")
        check_binding(selection, bound)
        parameters = resolve_declared_parameters(input_path or root / "main.parameters.json", selected)
        document = (
            read_bicep(selected, runner) if provider["provider"] == "bicep" else
            read_terraform(root, Path(provider["entrypoint"]).parent, selected, runner)
        )
        validate_shape(document)
        validate_context(document, selected, parameters, provider["provider"])
        live = verify_live(document, parameters, runner)
    except MetadataError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise MetadataError("selection: Invalid declared inputs or environment binding. Restore original selection and retry.") from None
    return VerifiedMetadata(document, selected, parameters, live)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--input", type=Path)
    args = parser.parse_args(argv)
    try:
        load_metadata({"AZURE_ENV_NAME": args.environment}, project_root=args.project_root, input_path=args.input)
    except MetadataError as exc:
        LOGGER.error("%s", exc)
        return 1
    LOGGER.info("Selected deployment metadata and live destinations verified.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
