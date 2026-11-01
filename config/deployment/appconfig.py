"""Publish mode-specific Agent Landing Zone runtime references to App Configuration."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Mapping

from config import find_repo_root
from config.deployment.appconfig_intent import Setting, prepare_publication, resolve_intent
from config.deployment.egress import selected_environment
from config.deployment.composition import (
    APP_CONFIG_LABEL,
    DEPLOY_INGESTION_CONTAINER_APP,
    custom_container_apps,
    is_bundled_application,
    requires_hosted_foundation,
    resolve_mode,
    resolve_ingestion_selection,
    validate_hosted_prerequisites,
    validate_ingestion_selection,
)
from config.deployment.native import OrchestrationHost, resolve_application, scheduler_settings
from util.azure_cli import resolve_az_command
from config.deployment.context import context_settings
from config.deployment.resource_groups import resource_group_for
from config.retrieval.settings import (
    public_settings as retrieval_public_settings,
    source_public_settings,
)


def _resolve_az_command() -> str:
    return resolve_az_command()


def _run_az(arguments: list[str], *, required: bool = True) -> str:
    try:
        completed = subprocess.run(
            [_resolve_az_command(), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Azure CLI App Configuration/runtime request could not complete; check CLI availability and connectivity.") from None
    output = completed.stdout.strip()
    if completed.returncode != 0 or (required and not output):
        # Arguments and provider error bodies can contain private setting values.
        raise RuntimeError("Azure CLI App Configuration/runtime request failed; check destination, access and CLI diagnostics securely.")
    return output


def _container_app(
    resource_group: str,
    name: str,
    *,
    required: bool,
    subscription: str = "",
) -> dict[str, str]:
    query = (
        "{fqdn:properties.configuration.ingress.fqdn,"
        "principalId:identity.principalId,"
        "userAssigned:identity.userAssignedIdentities}"
    )
    output = _run_az(
        [
            "containerapp",
            "show",
            "--resource-group",
            resource_group,
            "--name",
            name,
            *(["--subscription", subscription] if subscription else []),
            "--query",
            query,
            "--output",
            "json",
        ],
        required=required,
    )
    if not output:
        return {"fqdn": "", "principalId": ""}
    value = json.loads(output)
    result = {
        "fqdn": value.get("fqdn") or "",
        "principalId": value.get("principalId") or "",
    }
    user_assigned = value.get("userAssigned") or {}
    if isinstance(user_assigned, dict):
        for identity in user_assigned.values():
            if isinstance(identity, dict) and identity.get("clientId"):
                result["uaiClientId"] = identity.get("clientId") or ""
                result["uaiPrincipalId"] = identity.get("principalId") or ""
                break
    return result


SYSTEM_IDENTITY_FALLBACK_AUDIENCE = "https://management.azure.com"


def orchestrator_caller_settings(
    environment: Mapping[str, str],
    frontend: Mapping[str, str],
) -> dict[str, str]:
    """Resolve keyless (Entra) orchestrator auth settings (ADR-0019).

    The UI calls the orchestrator with a token from its user-assigned managed
    identity; the token audience is that identity's client ID and the caller
    is that identity's principal ID. A frontend with only a system-assigned
    identity falls back to ``SYSTEM_IDENTITY_FALLBACK_AUDIENCE`` so keyless
    auth still works; the caller check (``oid`` equals the frontend system
    principal) is what binds the token to the UI. Prefer a user-assigned
    identity or an explicit audience for a narrower token.
    """
    audience = (
        (environment.get("ORCHESTRATOR_AUTH_AUDIENCE") or "").strip()
        or frontend.get("uaiClientId", "")
        or (SYSTEM_IDENTITY_FALLBACK_AUDIENCE if frontend.get("principalId") else "")
    )
    callers = (
        (environment.get("ORCHESTRATOR_ALLOWED_CALLER_IDS") or "").strip()
        or frontend.get("uaiPrincipalId", "")
        or frontend.get("principalId", "")
    )
    return {
        "ORCHESTRATOR_AUTH_AUDIENCE": audience,
        "ORCHESTRATOR_ALLOWED_CALLER_IDS": callers,
    }


def _required(environment: Mapping[str, str], name: str) -> str:
    value = (environment.get(name) or "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable {name}.")
    return value


def build_settings(
    environment: Mapping[str, str],
    *,
    require_hosted_endpoint: bool = False,
) -> dict[str, str]:
    mode = resolve_mode(environment)
    if not is_bundled_application(environment):
        # Custom definitions own their services and consumers; never discover
        # an undeclared bundled frontend/worker or require a native DTS binding.
        group = resource_group_for(environment, "application")
        subscription = (environment.get("AZURE_SUBSCRIPTION_ID") or "").strip()
        token = _required(environment, "RESOURCE_TOKEN")
        applications = custom_container_apps(environment, [], hosted_orchestration=False)
        settings = {**resolve_application(environment).settings(), **context_settings(environment)}
        containers = []
        for application in applications:
            service = application["service_name"]
            name = f"ca-{token}-{service}"
            discovered = _container_app(group, name, required=True, subscription=subscription)
            canonical = application["canonical_name"]
            endpoint = f"https://{discovered['fqdn']}" if discovered["fqdn"] else ""
            settings[canonical + "_NAME"] = name
            settings[canonical + "_ENDPOINT"] = endpoint
            containers.append({
                "name": name, "serviceName": service, "canonical_name": canonical,
                "principalId": discovered["principalId"], "fqdn": discovered["fqdn"],
            })
        settings["CONTAINER_APPS"] = json.dumps(containers, separators=(",", ":"))
        settings.update(source_public_settings(environment))
        return settings
    deploy_ingestion = resolve_ingestion_selection(environment)
    validate_ingestion_selection(environment, deploy_ingestion)
    hosted = mode is OrchestrationHost.HOSTED
    native = resolve_application(environment)
    resource_group = resource_group_for(environment, "application")
    subscription = (environment.get("AZURE_SUBSCRIPTION_ID") or environment.get("SUBSCRIPTION_ID") or "").strip()
    deployment_context = context_settings(environment)
    resource_token = _required(environment, "RESOURCE_TOKEN")
    prepare_hosted = requires_hosted_foundation(
        environment, hosted_orchestration=hosted
    )

    app_names = {
        "frontend": f"ca-{resource_token}-frontend",
        "dataingest": f"ca-{resource_token}-dataingest",
        "orchestrator": f"ca-{resource_token}-orchestrator",
    }
    hosted_base_url = (environment.get("HOSTED_AGENT_BASE_URL") or "").strip()
    hosted_scope = (environment.get("HOSTED_AGENT_RESOURCE_SCOPE") or "").strip()
    hosted_image_version = (
        environment.get("HOSTED_AGENT_IMAGE_VERSION") or ""
    ).strip()
    if hosted:
        validate_hosted_prerequisites(
            environment,
            require_image_digest=False,
        )
    if hosted and require_hosted_endpoint:
        required_endpoints = (
            [("HOSTED_AGENT_BASE_URL" if kind == "conversational" else "HOSTED_WORKFLOW_BASE_URL")
             for kind in native.publications]
        )
        if any(not environment.get(key, "").strip() for key in required_endpoints):
            raise ValueError(
                "Hosted deployment completed without required publication endpoints: " + ", ".join(required_endpoints)
            )
    retrieval_settings = retrieval_public_settings(environment, hosted=hosted)
    source_settings = source_public_settings(environment)

    frontend = _container_app(
        resource_group, app_names["frontend"], required=True, subscription=subscription
    )
    dataingest = (
        _container_app(resource_group, app_names["dataingest"], required=True, subscription=subscription)
        if deploy_ingestion else {"fqdn": "", "principalId": ""}
    )
    orchestrator = (
        _container_app(
            resource_group, app_names["orchestrator"], required=True, subscription=subscription
        )
        if mode is OrchestrationHost.CONTAINER_APPS
        else {"fqdn": "", "principalId": ""}
    )

    container_apps = [
        {
            "name": app_names["frontend"],
            "serviceName": "frontend",
            "canonical_name": "FRONTEND_APP",
            "principalId": frontend["principalId"],
            "fqdn": frontend["fqdn"],
        },
    ]
    if deploy_ingestion:
        container_apps.append({
            "name": app_names["dataingest"],
            "serviceName": "dataingest",
            "canonical_name": "DATA_INGEST_APP",
            "principalId": dataingest["principalId"],
            "fqdn": dataingest["fqdn"],
        })
    if mode is OrchestrationHost.CONTAINER_APPS:
        container_apps.insert(
            0,
            {
                "name": app_names["orchestrator"],
                "serviceName": "orchestrator",
                "canonical_name": "ORCHESTRATOR_APP",
                "principalId": orchestrator["principalId"],
                "fqdn": orchestrator["fqdn"],
            },
        )

    return {
        **native.settings(),
        **({
            "HOSTED_WORKFLOW_BASE_URL": environment.get("HOSTED_WORKFLOW_BASE_URL", "").strip(),
            "NATIVE_UI_METADATA_CONTAINER": environment.get("NATIVE_UI_METADATA_CONTAINER", "native-ui-metadata"),
            "DATASOURCES_CONTAINER": "datasources" if environment.get("NL2SQL_ENABLED", "").lower() == "true" else "",
            "NL2SQL_ENABLED": environment.get("NL2SQL_ENABLED", "false"),
            "NL2SQL_SOURCE_REGISTRY": environment.get("NL2SQL_SOURCE_REGISTRY", ""),
            "NATIVE_TOOL_SECRET_NAMES": environment.get("NATIVE_TOOL_SECRET_NAMES", "[]"),
        }),
        **(
            scheduler_settings(environment)
            if native.host == "container_apps" else {}
        ),
        **({
            "DURABLE_AGENT_NAME": environment.get("DURABLE_AGENT_NAME", "agent-lz-conversation"),
            "DURABLE_WORKFLOW_NAME": environment.get("DURABLE_WORKFLOW_NAME", "agent-lz-research-review"),
        }),
        **deployment_context,
        DEPLOY_INGESTION_CONTAINER_APP: str(deploy_ingestion).lower(),
        **(
            {"SEARCH_RAG_INDEX_NAME": environment["SEARCH_RAG_INDEX_NAME"].strip()}
            if (environment.get("SEARCH_RAG_INDEX_NAME") or "").strip() else {}
        ),
        "INGESTION_BASE_URL": (
            f"https://{dataingest['fqdn']}" if dataingest["fqdn"] else ""
        ),
        "HOSTED_AGENT_BASE_URL": hosted_base_url,
        "HOSTED_AGENT_RESOURCE_SCOPE": hosted_scope,
        "HOSTED_AGENT_IMAGE_VERSION": (
            hosted_image_version if hosted else ""
        ),
        "HOSTED_AGENT_SSE_IDLE_TIMEOUT_SECONDS": (
            environment.get("HOSTED_AGENT_SSE_IDLE_TIMEOUT_SECONDS") or "60"
        ),
        "ORCHESTRATOR_APP_ENDPOINT": (
            f"https://{orchestrator['fqdn']}" if orchestrator["fqdn"] else ""
        ),
        "FRONTEND_APP_ENDPOINT": f"https://{frontend['fqdn']}",
        "DATA_INGEST_APP_ENDPOINT": (
            f"https://{dataingest['fqdn']}" if dataingest["fqdn"] else ""
        ),
        "ORCHESTRATOR_APP_NAME": (
            app_names["orchestrator"]
            if mode is OrchestrationHost.CONTAINER_APPS
            else ""
        ),
        "FRONTEND_APP_NAME": app_names["frontend"],
        "DATA_INGEST_APP_NAME": app_names["dataingest"] if deploy_ingestion else "",
        "CONTAINER_APPS": json.dumps(
            container_apps, separators=(",", ":")
        ),
        **retrieval_settings,
        **source_settings,
    }


KEYLESS_AUTH_KEYS = frozenset(
    {"ORCHESTRATOR_AUTH_AUDIENCE", "ORCHESTRATOR_ALLOWED_CALLER_IDS"}
)


def publish_settings(
    endpoint: str,
    settings: Mapping[str, str],
    *,
    entries: list[Setting] | None = None,
) -> None:
    # Empty keyless-auth values are not published so values set by
    # infrastructure or an operator are never clobbered.
    ordered_settings = [
        (key, value)
        for key, value in settings.items()
        if key != "CHAT_BACKEND"
        and not (key in KEYLESS_AUTH_KEYS and not value)
    ]
    if "CHAT_BACKEND" in settings:
        ordered_settings.append(("CHAT_BACKEND", settings["CHAT_BACKEND"]))

    publication = entries if entries is not None else [
        Setting(name=key, value=value, label=APP_CONFIG_LABEL, contentType="text/plain")
        for key, value in ordered_settings
    ]
    for setting in publication:
        key, value = setting["name"], setting["value"]
        if key in KEYLESS_AUTH_KEYS and not value:
            continue
        _run_az(
            [
                "appconfig",
                "kv",
                "set",
                "--endpoint",
                endpoint,
                "--key",
                key,
                "--value",
                value,
                "--label",
                setting["label"],
                "--content-type",
                setting["contentType"],
                "--auth-mode",
                "login",
                "--yes",
                "--output",
                "none",
            ],
            required=False,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-hosted-endpoint", action="store_true")
    parser.add_argument(
        "--input", type=Path,
        help="Declared parameter source used for provision; defaults to root main.parameters.json. Never generated tfvars/state.",
    )
    args = parser.parse_args(argv)
    try:
        root = find_repo_root()
        selected = selected_environment(root, _required(os.environ, "AZURE_ENV_NAME"))
        intent = resolve_intent(args.input if args.input is not None else root / "main.parameters.json", selected)
        authority_environment = dict(selected)
        settings = build_settings(
            authority_environment,
            require_hosted_endpoint=args.require_hosted_endpoint,
        )
        entries = prepare_publication(intent, settings)
        publish_settings(_required(selected, "APP_CONFIG_ENDPOINT"), settings, entries=entries)
    except (ValueError, OSError, RuntimeError) as exc:
        logging.error("%s", exc)
        return 1
    print(resolve_mode(authority_environment).value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
