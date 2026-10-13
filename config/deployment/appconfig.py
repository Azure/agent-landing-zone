"""Publish mode-specific Agent Landing Zone runtime references to App Configuration."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from typing import Mapping

from config.continuity.settings import public_settings as continuity_public_settings
from config.deployment.composition import (
    APP_CONFIG_LABEL,
    DeploymentMode,
    requires_hosted_foundation,
    resolve_mode,
    resolve_runtime_mode,
    validate_hosted_prerequisites,
)
from util.azure_cli import resolve_az_command


def _resolve_az_command() -> str:
    return resolve_az_command()


def _run_az(arguments: list[str], *, required: bool = True) -> str:
    completed = subprocess.run(
        [_resolve_az_command(), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    output = completed.stdout.strip()
    if completed.returncode != 0 or (required and not output):
        detail = completed.stderr.strip() or output
        raise RuntimeError(
            f"Azure CLI command failed: az {' '.join(arguments)}: {detail}"
        )
    return output


def _container_app(
    resource_group: str,
    name: str,
    *,
    required: bool,
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
    hosted = mode is not DeploymentMode.CLASSIC
    resource_group = _required(environment, "AZURE_RESOURCE_GROUP")
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
        if not hosted_base_url:
            raise ValueError(
                "Hosted deployment completed without HOSTED_AGENT_BASE_URL."
            )
    runtime_mode = resolve_runtime_mode(mode, environment)
    runtime_hosted = runtime_mode is not DeploymentMode.CLASSIC

    frontend = _container_app(
        resource_group, app_names["frontend"], required=True
    )
    dataingest = _container_app(
        resource_group, app_names["dataingest"], required=True
    )
    orchestrator = (
        _container_app(
            resource_group, app_names["orchestrator"], required=True
        )
        if runtime_mode is DeploymentMode.CLASSIC
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
        {
            "name": app_names["dataingest"],
            "serviceName": "dataingest",
            "canonical_name": "DATA_INGEST_APP",
            "principalId": dataingest["principalId"],
            "fqdn": dataingest["fqdn"],
        },
    ]
    if runtime_mode is DeploymentMode.CLASSIC:
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
        "DEPLOY_HOSTED_AGENT_ORCHESTRATION": str(runtime_hosted).lower(),
        "PREPARE_HOSTED_AGENT": str(prepare_hosted).lower(),
        "DEPLOY_HOSTED_AGENT": (
            environment.get("DEPLOY_HOSTED_AGENT") or "false"
        ).strip().lower(),
        "HOSTED_AGENT_PREPARED": (
            environment.get("HOSTED_AGENT_PREPARED")
            or str(prepare_hosted)
        ).strip().lower(),
        "DEPLOY_ADMINISTRATIVE_PANEL": str(
            runtime_mode is DeploymentMode.HOSTED_PANEL
        ).lower(),
        "DEPLOYMENT_TOPOLOGY": runtime_mode.value,
        "CHAT_BACKEND": (
            "hosted_agent" if runtime_hosted else "orchestrator"
        ),
        "ORCHESTRATOR_BASE_URL": (
            f"https://{orchestrator['fqdn']}" if orchestrator["fqdn"] else ""
        ),
        "INGESTION_BASE_URL": f"https://{dataingest['fqdn']}",
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
        "DATA_INGEST_APP_ENDPOINT": f"https://{dataingest['fqdn']}",
        "ORCHESTRATOR_APP_NAME": (
            app_names["orchestrator"]
            if runtime_mode is DeploymentMode.CLASSIC
            else ""
        ),
        "FRONTEND_APP_NAME": app_names["frontend"],
        "DATA_INGEST_APP_NAME": app_names["dataingest"],
        "CONTAINER_APPS": json.dumps(
            container_apps, separators=(",", ":")
        ),
        **(
            orchestrator_caller_settings(environment, frontend)
            if runtime_mode is DeploymentMode.CLASSIC
            else {}
        ),
        **continuity_public_settings(environment),
    }


KEYLESS_AUTH_KEYS = frozenset(
    {"ORCHESTRATOR_AUTH_AUDIENCE", "ORCHESTRATOR_ALLOWED_CALLER_IDS"}
)


def publish_settings(endpoint: str, settings: Mapping[str, str]) -> None:
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

    for key, value in ordered_settings:
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
                APP_CONFIG_LABEL,
                "--content-type",
                "text/plain",
                "--auth-mode",
                "login",
                "--yes",
                "--output",
                "none",
            ],
            required=False,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-hosted-endpoint", action="store_true")
    args = parser.parse_args()
    endpoint = _required(os.environ, "APP_CONFIG_ENDPOINT")
    settings = build_settings(
        os.environ,
        require_hosted_endpoint=args.require_hosted_endpoint,
    )
    publish_settings(endpoint, settings)
    print(resolve_mode(os.environ).value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
