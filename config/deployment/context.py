"""Flat deployment context and exact ARM resource ownership checks."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping
from urllib.parse import urlsplit

from config.deployment.resource_groups import resource_group_for


@dataclass(frozen=True)
class ResourceContext:
    subscription: str
    resource_group: str
    resource_type: str
    name: str


def parse_resource_id(value: str) -> ResourceContext:
    if any(character in value for character in ("?", "#", "\\")):
        raise ValueError("Expected an exact ARM resource ID without query or fragment.")
    match = re.fullmatch(
        r"/subscriptions/([^/\s]+)/resourceGroups/([^/\s]+)/providers/"
        r"([^/\s]+)((?:/[^/\s]+/[^/\s]+)+)", value, re.IGNORECASE,
    )
    if not match:
        raise ValueError("Expected an exact ARM resource ID.")
    segments = match[4].strip("/").split("/")
    return ResourceContext(
        match[1], match[2], match[3] + "/" + "/".join(segments[::2]),
        "/".join(segments[1::2]),
    )


def bound_resource_id(
    value: str, environment: Mapping[str, str], resource_type: str,
    *, area: str | None = None,
) -> ResourceContext:
    context = parse_resource_id(value)
    subscription = (
        environment.get("AZURE_SUBSCRIPTION_ID") or environment.get("SUBSCRIPTION_ID") or ""
    ).strip()
    aliases = {
        environment[key].strip().lower() for key in ("AZURE_SUBSCRIPTION_ID", "SUBSCRIPTION_ID")
        if (environment.get(key) or "").strip()
    }
    if len(aliases) > 1:
        raise ValueError("Deployment subscription aliases conflict.")
    if not subscription or context.subscription.lower() != subscription.lower():
        raise ValueError("Resource ID belongs to a different or missing deployment subscription.")
    groups = (
        [resource_group_for(environment, area)] if area else
        [resource_group_for(environment, owner) for owner in ("application", "foundry", "network")]
    )
    if context.resource_group.lower() not in {group.lower() for group in groups}:
        raise ValueError("Resource ID belongs to a different deployment resource group.")
    if context.resource_type.lower() != resource_type.lower():
        raise ValueError("Resource ID has an unexpected resource type.")
    return context


def context_settings(environment: Mapping[str, str]) -> dict[str, str]:
    """Publish destinations outside the closed v1 JSON contract.

    The pinned ingestion consumer already accepts an exact document-container
    ID; publishing it avoids its legacy application-RG scope fallback.
    """
    settings = {
        "AZURE_RESOURCE_GROUP": resource_group_for(environment, "application"),
        "AZURE_FOUNDRY_RESOURCE_GROUP": resource_group_for(environment, "foundry"),
        "AZURE_NETWORK_RESOURCE_GROUP": resource_group_for(environment, "network"),
    }
    account_id = (environment.get("STORAGE_ACCOUNT_RESOURCE_ID") or "").strip()
    explicit = (environment.get("DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID") or "").strip()
    explicit_container = ""
    if explicit:
        document_context = bound_resource_id(
            explicit, environment, "Microsoft.Storage/storageAccounts/blobServices/containers",
        )
        if document_context.name.split("/")[1] != "default":
            raise ValueError("Documents container ID must use the default blob service.")
        explicit_container = document_context.name.split("/")[-1]
        explicit_account = explicit.rsplit("/blobServices/", 1)[0]
        if account_id and account_id.lower() != explicit_account.lower():
            raise ValueError("Documents container resource ID conflicts with the storage account.")
        account_id = account_id or explicit_account
    name = (
        environment.get("AZURE_STORAGE_ACCOUNT_NAME") or environment.get("STORAGE_ACCOUNT_NAME") or ""
    ).strip()
    endpoint = (
        environment.get("STORAGE_BLOB_ENDPOINT") or environment.get("STORAGE_ACCOUNT_BLOB_ENDPOINT") or ""
    ).strip()
    if endpoint:
        host = urlsplit(endpoint).hostname or ""
        endpoint_name = host.split(".", 1)[0]
        if name and endpoint_name.lower() != name.lower():
            raise ValueError("Storage name and endpoint conflict.")
        name = name or endpoint_name
    subscription = (
        environment.get("AZURE_SUBSCRIPTION_ID") or environment.get("SUBSCRIPTION_ID") or ""
    ).strip()
    if not account_id and name and subscription:
        account_id = (
            f"/subscriptions/{subscription}/resourceGroups/{settings['AZURE_FOUNDRY_RESOURCE_GROUP']}"
            f"/providers/Microsoft.Storage/storageAccounts/{name}"
        )
    if account_id:
        context = bound_resource_id(account_id, environment, "Microsoft.Storage/storageAccounts")
        if name and context.name.lower() != name.lower():
            raise ValueError("Storage resource ID and configured account conflict.")
        container = (
            environment.get("DOCUMENTS_STORAGE_CONTAINER") or explicit_container or "documents"
        ).strip()
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])", container):
            raise ValueError("Invalid documents storage container name.")
        container_id = f"{account_id}/blobServices/default/containers/{container}"
        if explicit and explicit.lower() != container_id.lower():
            raise ValueError("Documents container resource ID conflicts with the storage account.")
        settings["DOCUMENTS_STORAGE_CONTAINER_RESOURCE_ID"] = container_id
    # Bicep also publishes the exact container key. Do not replace it when a
    # hook has only destination metadata rather than storage outputs.
    return settings


def registry_resource_group(environment: Mapping[str, str]) -> str:
    """Use app ACR, or the explicitly declared registry's exact ARM context."""
    resource_id = (
        environment.get("AZURE_CONTAINER_REGISTRY_RESOURCE_ID")
        or environment.get("CONTAINER_REGISTRY_RESOURCE_ID") or ""
    ).strip()
    if not resource_id:
        return resource_group_for(environment, "application")
    context = parse_resource_id(resource_id)
    if context.resource_type.lower() != "microsoft.containerregistry/registries":
        raise ValueError("Declared registry ID is not a container registry.")
    subscription = (environment.get("AZURE_SUBSCRIPTION_ID") or "").strip()
    if context.subscription.lower() != subscription.lower():
        raise ValueError("Declared registry belongs to a different deployment subscription.")
    server = (
        environment.get("AZURE_CONTAINER_REGISTRY_ENDPOINT")
        or environment.get("CONTAINER_REGISTRY_LOGIN_SERVER") or ""
    ).strip()
    if not server or server.lower() != f"{context.name}.azurecr.io".lower():
        raise ValueError("Declared registry ID and login server conflict.")
    return context.resource_group
