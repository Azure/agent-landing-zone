"""Wire selected custom Container Apps to the platform ACR before image rollout."""

from __future__ import annotations

import logging
import json
from typing import Mapping
from config.deployment.resource_groups import resource_group_for
from config.deployment.setup_settings import load_setup_settings

LOGGER = logging.getLogger(__name__)


def configure_service_registry(
    service: str, image: str | None, environment: Mapping[str, str],
) -> None:
    """Reuse the registry setup with the uniquely tagged app's existing identity.

    Normal azd builds retain their own registry setup. External prebuilt images
    are not implicitly granted access or rebound to the platform registry.
    """
    if not image:
        return
    environment = load_setup_settings(environment)
    server = (
        environment.get("AZURE_CONTAINER_REGISTRY_ENDPOINT")
        or environment.get("CONTAINER_REGISTRY_LOGIN_SERVER") or ""
    ).strip()
    if not image or not server or image.split("/", 1)[0].lower() != server.lower():
        return
    subscription = (environment.get("AZURE_SUBSCRIPTION_ID") or "").strip()
    if not subscription or not (environment.get("AZURE_RESOURCE_GROUP") or "").strip():
        raise ValueError("Custom registry configuration requires AZURE_SUBSCRIPTION_ID and AZURE_RESOURCE_GROUP.")
    group = resource_group_for(environment, "application")

    # Keep SDK dependencies lazy for ordinary azd builds and external images.
    from azure.core.exceptions import AzureError
    from config.containerapps.setup import (
        ContainerAppsAPIClient, get_credentials, update_single_container_app,
    )

    credential = get_credentials()
    client = ContainerAppsAPIClient(credential, subscription)
    try:
        apps = [
            app for app in client.container_apps.list_by_resource_group(group)
            if (app.tags or {}).get("azd-service-name") == service
        ]
    except AzureError as error:
        raise RuntimeError(f"Cannot discover Container App registry target for {service}: {error}") from error
    if len(apps) != 1:
        raise RuntimeError(f"Expected exactly one Container App tagged azd-service-name={service}; found {len(apps)}.")
    app = apps[0]
    mappings = environment.get("CONTAINER_APPS", [])
    if isinstance(mappings, str):
        mappings = json.loads(mappings)
    mapped = next((entry for entry in mappings if entry["name"] == app.name), None)
    if mapped is None:
        raise RuntimeError(f"Container App tagged for {service} conflicts with verified app mappings.")
    identity = app.identity
    assigned = getattr(identity, "user_assigned_identities", None) or {}
    system = bool(getattr(identity, "principal_id", None))
    if len(assigned) + int(system) != 1:
        raise RuntimeError(f"Container App {app.name} must have exactly one existing managed identity for registry access.")
    expected = mapped.get("identity")
    if expected:
        attached = identity
        if expected["kind"] == "userAssigned":
            if expected["resourceId"] not in assigned:
                raise RuntimeError(f"Container App {app.name} registry identity conflicts with verified mapping.")
            attached = assigned[expected["resourceId"]]
        if getattr(attached, "principal_id", None) != expected["principalId"]:
            raise RuntimeError(f"Container App {app.name} principal conflicts with verified mapping.")
    _, success, detail = update_single_container_app(
        subscription, group, app.name, server, "true" if assigned else "false", credential,
        preserve_other_registries=True,
    )
    if not success:
        raise RuntimeError(f"Registry configuration failed for {service}: {detail}")
    LOGGER.info("Configured platform registry access for custom service %s using its existing managed identity.", service)
