"""Wire selected custom Container Apps to the platform ACR before image rollout."""

from __future__ import annotations

import logging
from typing import Mapping

LOGGER = logging.getLogger(__name__)


def configure_service_registry(
    service: str, image: str | None, environment: Mapping[str, str],
) -> None:
    """Reuse the registry setup with the uniquely tagged app's existing identity.

    Normal azd builds retain their own registry setup. External prebuilt images
    are not implicitly granted access or rebound to the platform registry.
    """
    server = (
        environment.get("AZURE_CONTAINER_REGISTRY_ENDPOINT")
        or environment.get("CONTAINER_REGISTRY_LOGIN_SERVER") or ""
    ).strip()
    if not image or not server or image.split("/", 1)[0].lower() != server.lower():
        return
    subscription = (environment.get("AZURE_SUBSCRIPTION_ID") or "").strip()
    group = (environment.get("AZURE_RESOURCE_GROUP") or "").strip()
    if not subscription or not group:
        raise ValueError("Custom registry configuration requires AZURE_SUBSCRIPTION_ID and AZURE_RESOURCE_GROUP.")

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
    identity = app.identity
    assigned = getattr(identity, "user_assigned_identities", None) or {}
    system = bool(getattr(identity, "principal_id", None))
    if len(assigned) + int(system) != 1:
        raise RuntimeError(f"Container App {app.name} must have exactly one existing managed identity for registry access.")
    _, success, detail = update_single_container_app(
        subscription, group, app.name, server, "true" if assigned else "false", credential,
        preserve_other_registries=True,
    )
    if not success:
        raise RuntimeError(f"Registry configuration failed for {service}: {detail}")
    LOGGER.info("Configured platform registry access for custom service %s using its existing managed identity.", service)
