"""Fail-closed readiness for deployment-owned Search outbound private links.

No credentials or service payloads are created here. The caller supplies its
existing CLI/managed-identity credential and rendered native-source definitions.
Search's exact shared-link GET is authoritative for approval/readiness. Target
PECs may reference Microsoft-managed Network endpoints, with no public binding
to the source Search/link identity. Never infer that binding to auto-approve.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
import time
import unicodedata
from typing import Any, Mapping

import requests
from azure.core.credentials import TokenCredential
from azure.core.exceptions import AzureError


ARM_ENDPOINT = "https://management.azure.com"
SEARCH_API_VERSION = "2025-05-01"
FOUNDRY_GROUPS = ("openai_account", "foundry_account", "cognitiveservices_account")
TIMEOUT_SECONDS = 600
POLL_SECONDS = 10
GUID = r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
NAME = r"[a-z0-9][a-z0-9_.-]{0,127}"
# Resource groups have different rules from service names: 1..90 Unicode
# letters/decimal digits or _-.(), and cannot end with a period. Capture one
# exact path segment, then validate its original (not lowercased) characters.
RESOURCE_PREFIX = rf"/subscriptions/{GUID}/resourcegroups/(?P<resource_group>[^/]{{1,90}})/providers/"
LOG = logging.getLogger(__name__)


class PrivateLinkReadinessError(RuntimeError):
    """Private native ingestion cannot safely proceed."""


@dataclass(frozen=True)
class ExpectedLink:
    name: str
    target: str
    group: str

    def resource_id(self, search_id: str) -> str:
        return f"{search_id}/sharedPrivateLinkResources/{self.name}"


def _same(value: object, expected: str) -> bool:
    return isinstance(value, str) and value.casefold() == expected.casefold()


def _resource_id(value: object, resource_type: str, setting: str) -> str:
    match = re.fullmatch(
        RESOURCE_PREFIX + re.escape(resource_type) + "/" + NAME, value,
        flags=re.IGNORECASE | re.ASCII,
    ) if isinstance(value, str) else None
    group = match.group("resource_group") if match else ""
    if not match or group.endswith(".") or any(
        character not in "_-.()"
        and not unicodedata.category(character).startswith("L")
        and unicodedata.category(character) != "Nd"
        for character in group
    ):
        raise PrivateLinkReadinessError(f"{setting} must contain an exact ARM resource ID.")
    return value


def _expected_links(context: Mapping[str, Any]) -> tuple[str, tuple[ExpectedLink, ...]]:
    search = _resource_id(
        context.get("SEARCH_SERVICE_RESOURCE_ID"), "Microsoft.Search/searchServices",
        "SEARCH_SERVICE_RESOURCE_ID",
    )
    storage = _resource_id(
        context.get("STORAGE_ACCOUNT_RESOURCE_ID"), "Microsoft.Storage/storageAccounts",
        "STORAGE_ACCOUNT_RESOURCE_ID",
    )
    foundry = _resource_id(
        context.get("AI_FOUNDRY_ACCOUNT_RESOURCE_ID"), "Microsoft.CognitiveServices/accounts",
        "AI_FOUNDRY_ACCOUNT_RESOURCE_ID",
    )
    targets = {"blob": storage, **{group: foundry for group in FOUNDRY_GROUPS}}
    manifest = context.get("SEARCH_SHARED_PRIVATE_LINKS")
    if isinstance(manifest, str):
        try:
            manifest = json.loads(manifest)
        except ValueError:
            raise PrivateLinkReadinessError("SEARCH_SHARED_PRIVATE_LINKS must be a JSON array.") from None
    if manifest is None:
        # Compatibility with the prior template. Do not guess ARM uniqueString
        # for long names: the new template publishes those exact names.
        search_name = search.rsplit("/", 1)[1]
        manifest = [
            {"name": f"spl-{search_name}-{group}-{'0' if group == 'blob' else '1'}",
             "groupId": group, "privateLinkResourceId": target}
            for group, target in targets.items()
        ]
        if any(len(item["name"]) > 60 for item in manifest):
            raise PrivateLinkReadinessError(
                "Exact bounded shared-link names are missing. Re-provision with the updated "
                "template to publish SEARCH_SHARED_PRIVATE_LINKS (agent-lz); do not approve by prefix."
            )
    if not isinstance(manifest, list) or len(manifest) != len(targets):
        raise PrivateLinkReadinessError("SEARCH_SHARED_PRIVATE_LINKS must describe the four deployment-owned links.")
    links = []
    groups = set()
    names = set()
    for item in manifest:
        if not isinstance(item, dict):
            raise PrivateLinkReadinessError("Invalid SEARCH_SHARED_PRIVATE_LINKS entry.")
        group, name = item.get("groupId"), item.get("name")
        if (
            not isinstance(group, str) or group not in targets or group in groups
            or not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,59}", name)
            or name.casefold() in names
            or not _same(item.get("privateLinkResourceId"), targets[group])
        ):
            raise PrivateLinkReadinessError("Shared-link manifest has an unexpected target, group or name.")
        groups.add(group)
        names.add(name.casefold())
        links.append(ExpectedLink(name, targets[group], group))
    return search, tuple(links)


class _Arm:
    def __init__(self, credential: TokenCredential, deadline: float):
        self.credential = credential
        self.deadline = deadline

    def get(self, resource_id: str) -> dict | None:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise PrivateLinkReadinessError(
                "Timed out waiting for Search private links. Check exact target approval and "
                "Search shared-link status/provisioningState; rerun configuration after propagation."
            )
        try:
            token = self.credential.get_token(f"{ARM_ENDPOINT}/.default").token
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise PrivateLinkReadinessError("Private-link readiness deadline expired during authentication.")
            response = requests.request(
                "GET", f"{ARM_ENDPOINT}{resource_id}?api-version={SEARCH_API_VERSION}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=min(30, remaining), allow_redirects=False,
            )
        except PrivateLinkReadinessError:
            raise
        except (AzureError, requests.RequestException) as exc:
            # Provider/token bodies can include sensitive details.
            LOG.error("Search private-link ARM GET failed (%s)", type(exc).__name__)
            raise PrivateLinkReadinessError(
                "Search private-link ARM request failed. Check CLI/managed-identity authentication "
                "and ARM connectivity, then rerun configuration."
            ) from None
        if response.status_code in (401, 403):
            raise PrivateLinkReadinessError(
                f"Search private-link ARM GET denied (HTTP {response.status_code}) for {resource_id}. "
                "Use the existing CLI/managed identity with Microsoft.Search/searchServices/"
                "sharedPrivateLinkResources/read permission. Target administrator approval does not "
                "replace the runner's Search read permission; correct access and rerun configuration."
            )
        if response.status_code == 404:
            return None
        if response.status_code in (429, 500, 502, 503, 504):
            return None
        if not 200 <= response.status_code < 300:
            raise PrivateLinkReadinessError(
                f"Search private-link ARM GET failed (HTTP {response.status_code}) for {resource_id}. "
                "Check provider support and Search read access; rerun after correcting the cause."
            )
        try:
            value = response.json()
        except ValueError:
            raise PrivateLinkReadinessError("Invalid JSON in private-link ARM response.") from None
        if not isinstance(value, dict):
            raise PrivateLinkReadinessError("Expected an object in private-link ARM response.")
        return value


def _properties(resource: dict) -> dict:
    properties = resource.get("properties")
    if not isinstance(properties, dict):
        raise PrivateLinkReadinessError("Missing properties in private-link ARM response.")
    return properties


def _reconcile_link(arm: _Arm, search: str, link: ExpectedLink) -> bool:
    """Validate the exact source GET; do not depend on target PEC list shapes.

    Public evidence: Microsoft Learn search-indexer-howto-access-private,
    sections 2 (Microsoft-managed tenant endpoint) and 3 (Search GET status).
    That example omits id; the requested exact URI, name, target and group
    bind identity. If the provider includes id, it must also match.
    """
    source_id = link.resource_id(search)
    source = arm.get(source_id)
    if source is None:
        return False
    props = _properties(source)
    if not (
        ("id" not in source or _same(source["id"], source_id)) and _same(source.get("name"), link.name)
        and _same(props.get("privateLinkResourceId"), link.target)
        and _same(props.get("groupId"), link.group)
    ):
        raise PrivateLinkReadinessError(f"Search shared-link identity mismatch for {source_id}; configuration stopped.")
    status_value, provisioning_value = props.get("status"), props.get("provisioningState")
    if not (
        isinstance(status_value, str) and status_value.strip()
        and isinstance(provisioning_value, str) and provisioning_value.strip()
    ):
        raise PrivateLinkReadinessError(f"Missing status/provisioningState in Search shared link {source_id}.")
    status, provisioning = status_value.lower(), provisioning_value.lower()
    if status in {"rejected", "disconnected"} or provisioning in {"failed", "canceled"}:
        raise PrivateLinkReadinessError(
            f"Search shared link {source_id} is rejected/disconnected/failed. Ask the target administrator "
            "to resolve the exact link and rerun; it will not be automatically overridden."
        )
    if status not in {"approved", "pending"}:
        raise PrivateLinkReadinessError(
            f"Unsupported approval status in Search shared link {source_id}. "
            "Check provider support with the administrator before retrying."
        )
    if status != "approved":
        raise PrivateLinkReadinessError(
            f"Administrator approval required for Search shared link {source_id}: target {link.target}, "
            f"group {link.group}, name {link.name}, status {status}. The target private endpoint can "
            "be in a Microsoft-managed tenant; its opaque ID/name or requestMessage cannot prove "
            "source ownership. An authorized target administrator must verify and approve the exact "
            "deployment request using Microsoft Learn's Search shared-private-link approval procedure, "
            "then rerun configuration. No target requests are automatically approved."
        )
    return provisioning == "succeeded"


def _ensure_native_blob_private_links(
    definitions: Mapping[str, Any], context: Mapping[str, Any], credential: TokenCredential,
    *, timeout_seconds: float = TIMEOUT_SECONDS, poll_seconds: float = POLL_SECONDS,
) -> None:
    """Bounded source readiness; pending approval is an immediate admin gate."""
    native_sources = [
        source for source in definitions.get("knowledgeSources", [])
        if str(source.get("kind", "")).lower() == "azureblob"
    ]
    if (
        str(context.get("NETWORK_ISOLATION", "")).strip().lower() not in {"1", "true", "t", "yes", "y"}
        or str(context.get("RETRIEVAL_BACKEND", "")).lower() != "foundry_iq"
        or str(context.get("FOUNDRY_IQ_PATTERN", "")).lower() == "searchindex"
        or not native_sources
    ):
        return
    if not (0 < timeout_seconds <= 3600 and 0 < poll_seconds <= timeout_seconds):
        raise ValueError("Private-link timeout must be 0..3600 seconds and polling positive and within the timeout.")
    search, links = _expected_links(context)
    # Rendered sources must actually use the deployment's storage, not an
    # unrelated target selected through an alternate template.
    for source in native_sources:
        connection = source.get("azureBlobParameters", {}).get("connectionString")
        if not _same(connection, f"ResourceId={context['STORAGE_ACCOUNT_RESOURCE_ID']}"):
            raise PrivateLinkReadinessError("Native Blob source does not reference deployment storage; no approval performed.")
    deadline = time.monotonic() + timeout_seconds
    arm = _Arm(credential, deadline)
    pending = list(links)
    while pending:
        pending = [link for link in pending if not _reconcile_link(arm, search, link)]
        if pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PrivateLinkReadinessError(
                    "Timed out waiting for verified Search private links: "
                    + ", ".join(link.name for link in pending)
                    + ". Target administrator approval may be needed, or ARM propagation is incomplete. "
                    "Verify exact Search/target/name/group identities and approved/succeeded state, then rerun."
                )
            time.sleep(min(poll_seconds, remaining))
    LOG.info("Deployment-owned native Blob Search private links are approved and succeeded.")


def ensure_native_blob_private_links(
    definitions: Mapping[str, Any], context: Mapping[str, Any], credential: TokenCredential,
    *, timeout_seconds: float = TIMEOUT_SECONDS, poll_seconds: float = POLL_SECONDS,
) -> None:
    """Report readiness failures through the existing configuration logger."""
    try:
        _ensure_native_blob_private_links(
            definitions, context, credential,
            timeout_seconds=timeout_seconds, poll_seconds=poll_seconds,
        )
    except PrivateLinkReadinessError as exc:
        LOG.error("Native Blob private-link readiness failed: %s", exc)
        raise
