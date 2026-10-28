"""SharePoint Indexed knowledge source preflight and helpers (preview).

The SharePoint Indexed knowledge source (kind: ``indexedSharePoint``, API
``2026-08-01-preview``) is registered through the standard j2 template +
``provision_knowledge_sources`` path in ``config/search/setup.py``. This
module intentionally does NOT PUT the KS itself; it only owns:

This module validates required identifiers and logs administrator prerequisites.
It never removes an enabled source to make provisioning succeed. Search setup
also validates source completeness before mutating any Azure resource.

The secretless connection string identifies the ingestion application and
Search managed identity. Native permission ingestion and delegated query-time
authorization are separate from that application's Graph indexing access.
"""

from __future__ import annotations

import logging
from typing import Any


SHAREPOINT_INDEXED_KIND = "indexedSharePoint"
SHAREPOINT_INDEXED_PARAMS_KEY = "indexedSharePointParameters"
SHAREPOINT_INDEXED_ADMIN_CONSENT_DOCS = (
    "https://azure.github.io/AI-Landing-Zones/agent-landing-zone/sharepoint/"
)


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y", "t"}


def sharepoint_indexed_required_context_keys() -> tuple[str, ...]:
    """Return the App Configuration keys required to enable the KS."""

    return (
        "SHAREPOINT_INDEXED_ENABLED",
        "SHAREPOINT_INDEXED_KNOWLEDGE_SOURCE_NAME",
        "SHAREPOINT_INDEXED_SITE_URL",
        "SHAREPOINT_INDEXED_TENANT_ID",
        "SHAREPOINT_INDEXED_APPLICATION_ID",
        "SHAREPOINT_INDEXED_FEDERATED_CREDENTIAL_APPLICATION_ID",
    )


def sharepoint_indexed_is_configured(context: dict) -> bool:
    """Return True when the operator has enabled the KS and set the
    required identifiers. Empty strings count as unset.
    """

    if not _is_truthy(context.get("SHAREPOINT_INDEXED_ENABLED")):
        return False
    required = sharepoint_indexed_required_context_keys()[1:]
    return all((context.get(k) or "").strip() for k in required)


def log_sharepoint_indexed_prerequisites_warning() -> None:
    """Emit an advisory warning listing the manual prerequisites that must
    be completed before the SharePoint Indexed KS can retrieve results.
    """

    logging.warning(
        "SharePoint Indexed is enabled in configuration but not all "
        "prerequisites can be verified from the deployment identity. "
        "The knowledge source will still be registered; retrieval will fail "
        "until the manual steps below have been completed."
    )
    logging.warning(
        "   Prerequisites: 1) Register an Entra app for SharePoint Indexed. "
        "2) Add a Federated Identity Credential on that app for the User "
        "Assigned Managed Identity used by Search (or its system identity). "
        "3) Grant admin consent for Microsoft Graph Sites.Selected (preferred) "
        "or Sites.Read.All. 4) If using Sites.Selected, grant the app read "
        "access to the target SharePoint site."
    )
    logging.warning(
        f"   See {SHAREPOINT_INDEXED_ADMIN_CONSENT_DOCS} for source setup "
        "and protected-retrieval acceptance."
    )


def filter_sharepoint_indexed_sources(defs: dict, context: dict) -> None:
    """Retained validation entrypoint; enabled sources are never filtered out."""

    if not _is_truthy(context.get("SHAREPOINT_INDEXED_ENABLED")):
        return
    if sharepoint_indexed_is_configured(context):
        log_sharepoint_indexed_prerequisites_warning()
        return

    raise ValueError(
        "SharePoint Indexed is enabled but required source/app identity "
        "settings are missing. The configured source was not removed."
    )
