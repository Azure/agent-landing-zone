"""Compose foundation inputs for the native application host and mode."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Mapping

from config.deployment.app_settings import merge_app_configuration_settings, substitute_values
from config.deployment.existing_images import apply_existing_images, discover_existing_images
from config.deployment.resource_groups import resource_group_for
from config.deployment import mcp_config
from config.deployment.firewall import resolve_firewall_inputs
from config.deployment.postgresql import resolve_inputs as resolve_postgresql_inputs
from config.deployment.native import (
    OBSOLETE_SELECTION_KEYS, OrchestrationHost, nl2sql_selected, resolve_application,
)

APP_CONFIG_LABEL = "agent-lz"
DEPLOY_INGESTION_CONTAINER_APP = "DEPLOY_INGESTION_CONTAINER_APP"
DEPLOY_COSMOS_DB = "DEPLOY_COSMOS_DB"
HOSTED_AGENT_NAME_DEFAULT = "agent-app-orchestrator"
HOSTED_IMAGE_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
HOSTED_STARTUP_COMMAND_DEFAULT = "python -m native.hosted"
HOSTED_RESOURCE_SCOPE_PATTERN = re.compile(r"^[^\s/](?:[^\s]*[^\s/])?/\.default$")


class DeploymentTopologyError(ValueError):
    """Invalid explicit application selection or deployment prerequisite."""


def is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "t", "yes", "y"}


def resolve_mode(environment: Mapping[str, str]) -> OrchestrationHost:
    """Resolve only the current product host; never inspect old runtime state."""
    try:
        return resolve_application(environment).host
    except ValueError as error:
        raise DeploymentTopologyError(str(error)) from error


def resolve_ingestion_selection(environment: Mapping[str, str]) -> bool:
    raw = environment.get(DEPLOY_INGESTION_CONTAINER_APP, "false").strip().lower()
    if raw not in {"true", "false"}:
        raise DeploymentTopologyError(f"{DEPLOY_INGESTION_CONTAINER_APP} must be 'true' or 'false'.")
    return raw == "true"


def validate_ingestion_selection(environment: Mapping[str, str], enabled: bool) -> None:
    """Reject app-dependent sources unless a deliberate external index is bound."""
    if enabled:
        return
    backend = (environment.get("RETRIEVAL_BACKEND") or "foundry_iq").strip()
    pattern = (environment.get("FOUNDRY_IQ_PATTERN") or "azureBlob").strip()
    kind = (environment.get("FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND") or "azureBlob").strip()
    external_index = (environment.get("SEARCH_RAG_INDEX_NAME") or "").strip()
    managed = backend == "foundry_iq" and pattern == "azureBlob" and kind == "azureBlob"
    index_bound = external_index and (
        backend == "ai_search"
        or (backend == "foundry_iq" and pattern == "searchIndex" and kind == "searchIndex")
    )
    if not managed and not index_bound:
        raise DeploymentTopologyError(
            f"{DEPLOY_INGESTION_CONTAINER_APP}=false requires supported native "
            "Foundry IQ azureBlob ingestion, or an explicitly supplied "
            "SEARCH_RAG_INDEX_NAME populated by an independent ingestion pipeline "
            "with ai_search / Foundry IQ searchIndex. Set the switch to true or review "
            "the retrieval/source/index bindings; selection never changes them."
        )


def hosted_startup_command(environment: Mapping[str, str]) -> str:
    return environment.get("HOSTED_AGENT_STARTUP_COMMAND") or HOSTED_STARTUP_COMMAND_DEFAULT


def hosted_startup_command_sha256(environment: Mapping[str, str]) -> str:
    return hashlib.sha256(hosted_startup_command(environment).encode("utf-8")).hexdigest()


def hosted_agent_configuration(environment: Mapping[str, str]) -> dict[str, object]:
    """Application-owned fields shared by provision and deploy handoffs."""
    return {
        "name": environment.get("HOSTED_AGENT_NAME") or HOSTED_AGENT_NAME_DEFAULT,
        "image": environment.get("HOSTED_AGENT_IMAGE") or HOSTED_AGENT_NAME_DEFAULT,
        "version": (environment.get("HOSTED_AGENT_IMAGE_VERSION") or "").strip(),
        "startupCommand": hosted_startup_command(environment),
        "runtime": {
            "cpu": environment.get("HOSTED_AGENT_CONTAINER_CPU") or "2",
            "memory": environment.get("HOSTED_AGENT_CONTAINER_MEMORY") or "4Gi",
        },
        "protocols": [{
            "protocol": "responses",
            "version": environment.get("HOSTED_AGENT_RESPONSES_PROTOCOL_VERSION") or "2.0.0",
        }],
    }


def validate_hosted_prerequisites(
    environment: Mapping[str, str], *, require_image_digest: bool = True,
    require_foundry_project: bool = False,
) -> None:
    configured = (environment.get("HOSTED_AGENT_STARTUP_COMMAND") or "").strip()
    if configured and configured != HOSTED_STARTUP_COMMAND_DEFAULT:
        raise DeploymentTopologyError(
            "Native Hosted requires the official hosting entrypoint: "
            "HOSTED_AGENT_STARTUP_COMMAND=python -m native.hosted."
        )
    scope = (environment.get("HOSTED_AGENT_RESOURCE_SCOPE") or "").strip()
    if not HOSTED_RESOURCE_SCOPE_PATTERN.fullmatch(scope):
        raise DeploymentTopologyError(
            "Hosted mode requires HOSTED_AGENT_RESOURCE_SCOPE as an explicit "
            "delegated-user data-plane scope with a non-empty resource "
            "identifier followed by '/.default'."
        )
    digest = (environment.get("HOSTED_AGENT_IMAGE_VERSION") or "").strip()
    if (require_image_digest or digest) and not HOSTED_IMAGE_DIGEST_PATTERN.fullmatch(digest):
        raise DeploymentTopologyError(
            "Hosted mode requires HOSTED_AGENT_IMAGE_VERSION as an immutable "
            "OCI digest in sha256:<64 hex characters> form."
        )
    if require_foundry_project:
        missing = [name for name in ("AZURE_AI_PROJECT_ENDPOINT", "AZURE_AI_PROJECT_RESOURCE_ID")
                   if not (environment.get(name) or "").strip()]
        if missing:
            raise DeploymentTopologyError("Hosted mode requires provisioned Foundry project configuration: " + ", ".join(missing) + ".")


def selected_components(
    host: OrchestrationHost, *, deploy_ingestion: bool = False, deploy_mcp: bool = False,
) -> tuple[str, ...]:
    components = ("agent-app-ui",)
    if host is OrchestrationHost.CONTAINER_APPS:
        components += ("agent-app-orchestrator",)
    if deploy_ingestion:
        components += ("agent-app-ingestion",)
    if deploy_mcp:
        components = (mcp_config.MCP_COMPONENT, *components)
    return components


def is_bundled_application(environment: Mapping[str, str]) -> bool:
    from config.appdefinition.loader import load_selected_definition
    return load_selected_definition(environment).bundled


def materialized_settings(environment: Mapping[str, str]) -> dict[str, str]:
    app = resolve_application(environment)
    ingestion = resolve_ingestion_selection(environment)
    validate_ingestion_selection(environment, ingestion)
    return {
        **app.settings(), DEPLOY_INGESTION_CONTAINER_APP: str(ingestion).lower(),
        mcp_config.DEPLOY_AGENT_APP_MCP: str(mcp_config.selected(environment)).lower(),
        "MCP_TOOLSETS": json.dumps(mcp_config.toolsets(environment)),
    }


def describe_application(environment: Mapping[str, str]) -> dict[str, object]:
    app = resolve_application(environment)
    ingestion = resolve_ingestion_selection(environment)
    validate_ingestion_selection(environment, ingestion)
    bundled = is_bundled_application(environment)
    return {
        **app.settings(), "native": True,
        "bundled_application": bundled,
        "ui_included": bundled,
        "metadata_required": app.metadata and bundled,
        "deploy_ingestion_container_app": ingestion,
        "deploy_cosmos_db": resolve_cosmos_selection(environment),
        "components": (
            list(selected_components(app.host, deploy_ingestion=ingestion, deploy_mcp=mcp_config.selected(environment)))
            if bundled else []
        ),
        "publications": list(app.publications) if bundled else [],
    }


def _setting(name: str, value: str) -> dict[str, str]:
    return {"name": name, "value": value, "label": APP_CONFIG_LABEL, "contentType": "text/plain"}


CUSTOM_CONTAINER_APP_ROLES = ["AcrPull"]


def requires_hosted_foundation(
    environment: Mapping[str, str], *, hosted_orchestration: bool,
) -> bool:
    """Custom Hosted components need shared foundation, not bundled routing."""
    from config.appdefinition.loader import (
        DEFINITION_ENV, KIND_HOSTED_AGENT, effective_components, load_selected_definition,
    )
    if hosted_orchestration:
        return True
    if not (environment.get(DEFINITION_ENV) or "").strip():
        return False
    definition = load_selected_definition(environment)
    return not definition.bundled and any(
        component.get("kind") == KIND_HOSTED_AGENT
        for component in effective_components(definition, hosted_orchestration=hosted_orchestration)
    )


def requires_custom_cosmos(environment: Mapping[str, str]) -> bool:
    from config.appdefinition.loader import DEFINITION_ENV, load_selected_definition
    from config.appdefinition.profiles import SCOPE_COSMOS, expand_profiles
    if not (environment.get(DEFINITION_ENV) or "").strip():
        return False
    definition = load_selected_definition(environment)
    return not definition.bundled and any(
        assignment.scope == SCOPE_COSMOS
        for component in definition.document.get("components", [])
        for assignment in expand_profiles(component.get("profiles") or ())
    )


def resolve_cosmos_selection(environment: Mapping[str, str]) -> bool:
    """Select actual native metadata/catalog/custom consumers, never checkpoints."""
    nl2sql_selected(environment)
    bundled = is_bundled_application(environment)
    required = (
        (resolve_application(environment).metadata and bundled)
        or requires_custom_cosmos(environment)
        or (mcp_config.vector_required(environment) if bundled else mcp_config.retained_catalog(environment))
    )
    raw = environment.get(DEPLOY_COSMOS_DB)
    if raw is None:
        return required
    normalized = raw.strip().lower()
    if normalized not in {"true", "false"}:
        raise DeploymentTopologyError(f"{DEPLOY_COSMOS_DB} must be 'true' or 'false'.")
    if required and normalized == "false":
        raise DeploymentTopologyError(
            f"{DEPLOY_COSMOS_DB}=false conflicts with required native frontend "
            "metadata, the MCP catalog or a custom Cosmos capability. "
            "Unset DEPLOY_COSMOS_DB to use automatic dependency selection."
        )
    return normalized == "true"


def custom_container_apps(
    environment: Mapping[str, str], existing_apps: list[object], *,
    hosted_orchestration: bool,
) -> list[dict[str, object]]:
    """Custom definitions contribute explicit entries to the bundled application."""
    from config.appdefinition.loader import (
        DEFINITION_ENV, KIND_CONTAINER_APP, component_service_name,
        effective_components, load_selected_definition,
    )
    if not (environment.get(DEFINITION_ENV) or "").strip():
        return []
    definition = load_selected_definition(environment)
    if definition.bundled:
        return []
    taken = {app.get("service_name") for app in existing_apps if isinstance(app, dict)}
    entries: list[dict[str, object]] = []
    for component in effective_components(definition, hosted_orchestration=hosted_orchestration):
        if component.get("kind") != KIND_CONTAINER_APP:
            continue
        service = component_service_name(definition, component)
        if not service or service in taken:
            continue
        taken.add(service)
        resources = component.get("resources") or {}
        entries.append({
            "name": None, "external": component.get("ingress", "internal") == "external",
            "service_name": service, "profile_name": "main", "min_replicas": 1,
            "max_replicas": 1, "cpu": str(float(resources.get("cpu", 0.5))),
            "memory": str(resources.get("memory", "1.0Gi")),
            "canonical_name": re.sub(r"[^A-Z0-9]", "_", service.upper()) + "_APP",
            "dapr": {"enabled": False}, "roles": list(CUSTOM_CONTAINER_APP_ROLES),
        })
    return entries


def compose_parameters(
    source: Mapping[str, object], environment: Mapping[str, str], *,
    expected_hosted_source_commit: str | None = None,
) -> dict[str, object]:
    result = copy.deepcopy(source)
    parameters = result.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("Parameter document must contain a 'parameters' object.")
    values = {name: entry.get("value") if isinstance(entry, dict) else None
              for name, entry in parameters.items()}
    if "additionalAppConfigurationSettings" in values:
        values["additionalAppConfigurationSettings"] = substitute_values(values["additionalAppConfigurationSettings"], environment)
    parameters.update({name: {"value": value} for name, value in _resolve_application_overrides(
        values, environment, expected_hosted_source_commit=expected_hosted_source_commit,
    ).items()})
    parameters.update({name: {"value": value} for name, value in resolve_firewall_inputs(values, environment).items()})
    parameters.update({name: {"value": value} for name, value in resolve_postgresql_inputs(values, environment).items()})
    return result


def _resolve_application_overrides(
    source: Mapping[str, object], environment: Mapping[str, str], *,
    expected_hosted_source_commit: str | None = None,
) -> dict[str, object]:
    """One host/mode boundary shared by Bicep and Terraform; foundation only."""
    app = resolve_application(environment)
    ingestion = resolve_ingestion_selection(environment)
    validate_ingestion_selection(environment, ingestion)
    for setting in source.get("additionalAppConfigurationSettings", []):
        if isinstance(setting, dict) and setting.get("name") in OBSOLETE_SELECTION_KEYS:
            raise DeploymentTopologyError(
                f"{setting['name']}: obsolete deployment setting; use only "
                "ORCHESTRATION_HOST and APPLICATION_MODE with explicit feature flags."
            )
    hosted = app.host is OrchestrationHost.HOSTED
    bundled = is_bundled_application(environment)
    deploy_mcp = mcp_config.selected(environment)
    if deploy_mcp and not bundled:
        raise DeploymentTopologyError(
            "DEPLOY_AGENT_APP_MCP selects the bundled MCP component. "
            "Custom definitions must explicitly declare their own MCP service and dependencies."
        )
    if bundled:
        mcp_config.validate_selection(environment)
    foundation_environment = environment if bundled else {**environment, "MCP_TOOLSETS": "[]"}
    nl2sql_selected(environment)  # Reject a selected retired direct SQL capability.
    prepare_hosted = requires_hosted_foundation(environment, hosted_orchestration=hosted and bundled)
    parameters: dict[str, object] = {
        "prepareHostedAgent": prepare_hosted,
        "deployDurableTaskScheduler": bundled and app.host is OrchestrationHost.CONTAINER_APPS,
        "deployHostedAgent": False,
        "deployCosmosDb": resolve_cosmos_selection(environment),
        "enableCosmosVectorSearch": mcp_config.vector_required(foundation_environment),
        "cosmosAccountCapabilities": mcp_config.account_capabilities(foundation_environment),
        "useCAppAPIKey": False,
    }
    if prepare_hosted and not (hosted and bundled):
        parameters["grantHostedAgentProjectManager"] = False
    if hosted and bundled:
        validate_hosted_prerequisites(environment, require_image_digest=False)
        agent = hosted_agent_configuration(environment)
        commit = (environment.get("HOSTED_AGENT_IMAGE_SOURCE_COMMIT") or "").strip()
        startup_hash = (environment.get("HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256") or "").strip()
        if ((commit and expected_hosted_source_commit and commit.lower() != expected_hosted_source_commit.lower())
                or (commit and startup_hash and startup_hash != hosted_startup_command_sha256(environment))):
            agent["version"] = ""
        parameters["hostedAgent"] = agent
        if is_truthy(environment.get("NETWORK_ISOLATION")):
            parameters["deployAcrTaskAgentPool"] = True

    apps = copy.deepcopy(source.get("containerAppsList"))
    if not isinstance(apps, list):
        raise ValueError("containerAppsList must contain an array value.")
    apps = [item for item in apps if isinstance(item, dict)
            and not (item.get("service_name") == "dataingest" and not ingestion)
            and not (item.get("service_name") == "orchestrator" and hosted)]
    if not bundled:
        apps = []
    if deploy_mcp:
        apps.append({
            "name": None, "external": True, "service_name": "mcp",
            "profile_name": "main", "min_replicas": 1, "max_replicas": 3,
            "cpu": "0.5", "memory": "1.0Gi", "canonical_name": "MCP_APP",
            "dapr": {"enabled": False}, "roles": ["AcrPull", "AppConfigurationDataReader"],
        })
    apps.extend(custom_container_apps(environment, apps, hosted_orchestration=hosted))
    for item in apps:
        if bundled and item.get("service_name") in {"orchestrator", "frontend", "dataingest"}:
            item["roles"] = [role for role in item.get("roles", [])
                             if role not in {"CosmosDBBuiltInDataContributor", "KeyVaultSecretsUser"}]
        if bundled and item.get("service_name") == "orchestrator":
            item["external"] = False
            item["disable_ingress"] = True
            item["dapr"] = {"enabled": False}
    parameters["containerAppsList"] = apps

    existing = copy.deepcopy(source.get("databaseContainersList", []))
    if not isinstance(existing, list):
        raise ValueError("databaseContainersList must contain an array value.")
    containers = (
        ([{"name": environment.get("NATIVE_UI_METADATA_CONTAINER", "native-ui-metadata"),
           "canonical_name": "NATIVE_UI_METADATA_CONTAINER", "partitionKey": "/principal_id"}]
         if app.metadata and bundled else [])
        + (existing if requires_custom_cosmos(environment) else [])
        + (mcp_config.cosmos_containers(environment) if bundled else [])
    )
    unique = {}
    for item in containers:
        unique.setdefault(item["name"], item)
    parameters["databaseContainersList"] = list(unique.values())

    settings = {
        **app.settings(), DEPLOY_INGESTION_CONTAINER_APP: str(ingestion).lower(),
        "NATIVE_TOOL_SECRET_NAMES": environment.get("NATIVE_TOOL_SECRET_NAMES", "[]"),
        "HOSTED_AGENT_BASE_URL": environment.get("HOSTED_AGENT_BASE_URL", ""),
        "HOSTED_WORKFLOW_BASE_URL": environment.get("HOSTED_WORKFLOW_BASE_URL", ""),
        "HOSTED_AGENT_RESOURCE_SCOPE": environment.get("HOSTED_AGENT_RESOURCE_SCOPE", ""),
        "HOSTED_AGENT_IMAGE_VERSION": environment.get("HOSTED_AGENT_IMAGE_VERSION", ""),
        "HOSTED_AGENT_SSE_IDLE_TIMEOUT_SECONDS": environment.get("HOSTED_AGENT_SSE_IDLE_TIMEOUT_SECONDS", "60"),
    }
    if bundled and (deploy_mcp or mcp_config.retained_catalog(environment)):
        settings.update(mcp_config.settings(environment))
    elif not bundled and "MCP_TOOLSETS" in environment:
        settings["MCP_TOOLSETS"] = json.dumps(mcp_config.toolsets(environment))
    if (environment.get("SEARCH_RAG_INDEX_NAME") or "").strip():
        settings["SEARCH_RAG_INDEX_NAME"] = environment["SEARCH_RAG_INDEX_NAME"].strip()
    parameters["additionalAppConfigurationSettings"] = merge_app_configuration_settings(
        source.get("additionalAppConfigurationSettings", []),
        [_setting(name, value) for name, value in settings.items()],
        default_label=source.get("appConfigLabel", APP_CONFIG_LABEL),
        application_names=[item["canonical_name"] for item in apps if isinstance(item.get("canonical_name"), str)],
    )
    return parameters


def compose_file(
    input_path: Path, output_path: Path, environment: Mapping[str, str], *,
    expected_hosted_source_commit: str | None = None,
    existing_images: Mapping[str, str] | None = None,
) -> OrchestrationHost:
    source = json.loads(input_path.read_text(encoding="utf-8-sig"))
    composed = compose_parameters(source, environment, expected_hosted_source_commit=expected_hosted_source_commit)
    if existing_images:
        for service in apply_existing_images(composed["parameters"]["containerAppsList"]["value"], existing_images):
            print(f"Preserving deployed image for {service}.", file=sys.stderr)
    output_path.write_text(json.dumps(composed, indent=2) + "\n", encoding="utf-8")
    return resolve_mode(environment)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hosted-source-commit", default=None)
    parser.add_argument("--no-preserve-images", action="store_true", help="Do not keep currently deployed Container Apps images (#708).")
    args = parser.parse_args()
    resolve_mode(os.environ)  # Reject obsolete controls before any Azure lookup.
    images = {}
    if not args.no_preserve_images and not is_truthy(os.environ.get("RESET_CONTAINER_APP_IMAGES")):
        images = discover_existing_images(
            resource_group_for(os.environ, "application")
            if os.environ.get("AZURE_RESOURCE_GROUP") or os.environ.get("AZURE_APP_RESOURCE_GROUP") else "",
            os.environ.get("AZURE_SUBSCRIPTION_ID") or None, os.environ.get("AZURE_ENV_NAME") or None,
        )
    print(compose_file(args.input, args.output, os.environ,
                       expected_hosted_source_commit=args.hosted_source_commit, existing_images=images).value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
