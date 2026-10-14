#!/usr/bin/env python3
"""Assign container-scoped Cosmos RBAC for the optional administrative panel.

Issue #611 / ADR-0004. This script is the *only* place that grants Cosmos
data-plane access for the panel's owner-index and feedback metadata
containers. It never uses the generic AILZ account-scope role-assignment
loop (``containerAppsList[].roles`` + ``modules/security/cosmos-data-plane-
role-assignment.bicep`` in the ``infra`` submodule): that loop only supports
whole-account scope, which would also grant access to any other container in
the shared account/database -- including, in a migrated environment, the
classic ``conversations`` chat-content container. Panel Cosmos RBAC must
never risk exposing chat content, so every assignment here is scoped to
exactly one container path (``/dbs/{database}/colls/{container}``) using the
same built-in Cosmos SQL role GUIDs AILZ already uses
(``00000000-0000-0000-0000-000000000002`` Data Contributor,
``00000000-0000-0000-0000-000000000001`` Data Reader). This keeps the
AI Landing Zone submodule generic while all application-specific narrowing lives
here, in an Agent Landing Zone config/hook, per AGENTS.md.

Identity/role matrix (ADR-0004):

- **agent-app-ui (frontend)** -- the only component holding the user token and
  the exclusive owner of managed-Conversation create/read/append/delete and
  the owner index -- gets **Cosmos DB Built-in Data Contributor**, scoped to
  *only* the two panel containers.
- **agent-app-ingestion (dataingest)** -- the operator overview surface reads
  aggregate counts over panel metadata only -- gets **Cosmos DB Built-in
  Data Reader**, scoped to the *same* two containers. It never gets write
  access and never gets the classic ``conversations``/``datasources``/
  ``prompts``/``mcp`` containers through this script.
- **agent-app-orchestrator (hosted agent/container)** -- stateless, holds
  **zero** managed-Conversations RBAC per ADR-0001/0003/0004 -- gets
  *nothing* here. This script has no code path that resolves or assigns a
  role to the orchestrator/hosted-agent identity.

Idempotent: every assignment is looked up by (principalId, roleDefinitionId,
scope) before creating, so re-running this script (every ``postProvision``)
never fails on an assignment that already exists and never duplicates one.

Reversible: deleting the two container-scoped assignments (or simply setting
``DEPLOY_ADMINISTRATIVE_PANEL=false`` and re-running provisioning, which never
calls this script) fully revokes panel Cosmos access without touching any
other container, account, or identity.

No-op unless ``DEPLOY_ADMINISTRATIVE_PANEL`` is ``true``. This script implements
the platform contract -- the exact,
reviewed, narrow-scope RBAC shape -- is ready the moment that gate lifts.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

from util.azure_cli import resolve_az_command


LABEL = "agent-lz"

COSMOS_DATA_CONTRIBUTOR_ROLE_GUID = "00000000-0000-0000-0000-000000000002"
COSMOS_DATA_READER_ROLE_GUID = "00000000-0000-0000-0000-000000000001"

FRONTEND_APP_SERVICE_NAME = "frontend"
DATA_INGEST_APP_SERVICE_NAME = "dataingest"
# The hosted agent/orchestrator identity is deliberately absent from this
# module: it must never be resolved or assigned a Cosmos role here.


class PanelRbacError(RuntimeError):
    """Raised when panel Cosmos RBAC cannot be safely assigned or verified."""


@dataclass(frozen=True)
class PanelContainerGrant:
    """One (principal, role, container) triple to reconcile."""

    service_name: str
    role_definition_guid: str
    container_name: str


def is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "t", "yes", "y"}


def container_scope_path(
    subscription_id: str,
    resource_group: str,
    account_name: str,
    database_name: str,
    container_name: str,
) -> str:
    """Return the exact container-scoped Cosmos SQL RBAC scope path.

    Deliberately narrower than the account-root scope the generic AILZ
    ``containerAppsList``-driven role loop uses, so a grant here can never
    reach any other container in the shared account/database -- including a
    classic ``conversations`` chat-content container that may still exist
    from a prior topology.
    """
    for value, name in (
        (subscription_id, "subscription_id"),
        (resource_group, "resource_group"),
        (account_name, "account_name"),
        (database_name, "database_name"),
        (container_name, "container_name"),
    ):
        if not (value or "").strip():
            raise PanelRbacError(f"container_scope_path requires a non-empty {name}.")
    return (
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.DocumentDB/databaseAccounts/{account_name}"
        f"/dbs/{database_name}/colls/{container_name}"
    )


def role_definition_id(
    subscription_id: str,
    resource_group: str,
    account_name: str,
    role_definition_guid: str,
) -> str:
    return (
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.DocumentDB/databaseAccounts/{account_name}"
        f"/sqlRoleDefinitions/{role_definition_guid}"
    )


def panel_container_grants() -> tuple[PanelContainerGrant, ...]:
    """Return the exact, reviewed grants this script ever assigns.

    Frontend (UI BFF) gets read/write (Data Contributor) on both panel
    containers -- it is the exclusive owner of the owner index and feedback
    metadata. Ingestion (operator overview) gets read-only (Data Reader) on
    the same two containers -- aggregate counts only, never a write. The
    hosted agent/orchestrator identity is never a grant target.
    """
    from config.panel.settings import FEEDBACK_CONTAINER_NAME, OWNER_INDEX_CONTAINER_NAME

    containers = (OWNER_INDEX_CONTAINER_NAME, FEEDBACK_CONTAINER_NAME)
    grants = []
    for container_name in containers:
        grants.append(
            PanelContainerGrant(
                service_name=FRONTEND_APP_SERVICE_NAME,
                role_definition_guid=COSMOS_DATA_CONTRIBUTOR_ROLE_GUID,
                container_name=container_name,
            )
        )
    for container_name in containers:
        grants.append(
            PanelContainerGrant(
                service_name=DATA_INGEST_APP_SERVICE_NAME,
                role_definition_guid=COSMOS_DATA_READER_ROLE_GUID,
                container_name=container_name,
            )
        )
    return tuple(grants)


def _run_az(arguments: list[str], *, required: bool = True) -> str:
    completed = subprocess.run(
        [resolve_az_command(), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    output = completed.stdout.strip()
    if completed.returncode != 0 or (required and not output):
        detail = completed.stderr.strip() or output
        raise PanelRbacError(f"Azure CLI command failed: az {' '.join(arguments)}: {detail}")
    return output


def resolve_container_app_principal_id(resource_group: str, app_name: str) -> str:
    output = _run_az(
        [
            "containerapp",
            "show",
            "--resource-group",
            resource_group,
            "--name",
            app_name,
            "--query",
            "identity.principalId",
            "--output",
            "tsv",
        ],
        required=False,
    )
    principal_id = output.strip()
    if principal_id and principal_id.lower() != "none":
        return principal_id

    identities_json = _run_az(
        [
            "containerapp",
            "show",
            "--resource-group",
            resource_group,
            "--name",
            app_name,
            "--query",
            "identity.userAssignedIdentities",
            "--output",
            "json",
        ]
    )
    try:
        identities = json.loads(identities_json)
    except json.JSONDecodeError as exc:
        raise PanelRbacError(
            f"Container app {app_name!r} returned malformed managed identities."
        ) from exc
    principal_ids = {
        str(identity.get("principalId") or "").strip()
        for identity in identities.values()
        if isinstance(identity, Mapping)
    }
    principal_ids.discard("")
    if len(principal_ids) != 1:
        raise PanelRbacError(
            f"Container app {app_name!r} must expose exactly one managed-identity "
            "principal for panel Cosmos RBAC."
        )
    return principal_ids.pop()


def existing_cosmos_sql_role_assignment(
    account_name: str,
    resource_group: str,
    principal_id: str,
    scope: str,
) -> Mapping[str, object] | None:
    output = _run_az(
        [
            "cosmosdb",
            "sql",
            "role",
            "assignment",
            "list",
            "--account-name",
            account_name,
            "--resource-group",
            resource_group,
            "--output",
            "json",
        ],
        required=False,
    )
    if not output:
        return None
    for assignment in json.loads(output):
        if (
            str(assignment.get("principalId") or "").lower() == principal_id.lower()
            and str(assignment.get("scope") or "").rstrip("/").lower()
            == scope.rstrip("/").lower()
        ):
            return assignment
    return None


def ensure_cosmos_sql_role_assignment(
    account_name: str,
    resource_group: str,
    subscription_id: str,
    principal_id: str,
    role_definition_guid: str,
    scope: str,
) -> bool:
    """Create the container-scoped role assignment if it is not already present.

    Returns ``True`` when a new assignment was created, ``False`` when a
    matching assignment (any role at this exact scope for this principal)
    already existed and was left untouched -- idempotent by design.
    """
    existing = existing_cosmos_sql_role_assignment(
        account_name, resource_group, principal_id, scope
    )
    if existing is not None:
        return False
    _run_az(
        [
            "cosmosdb",
            "sql",
            "role",
            "assignment",
            "create",
            "--account-name",
            account_name,
            "--resource-group",
            resource_group,
            "--role-definition-id",
            role_definition_id(
                subscription_id, resource_group, account_name, role_definition_guid
            ),
            "--principal-id",
            principal_id,
            "--scope",
            scope,
        ],
        required=False,
    )
    return True


def resolve_subscription_id(environment: Mapping[str, str]) -> str:
    """Return the subscription ID, falling back to ``az account show``.

    Mirrors ``scripts/postProvision.ps1``'s ``Set-AgentLzAppConfiguration``,
    which resolves ``AZURE_SUBSCRIPTION_ID`` the same way when the azd
    environment does not carry it explicitly.
    """
    subscription_id = (environment.get("AZURE_SUBSCRIPTION_ID") or "").strip()
    if subscription_id:
        return subscription_id
    return _run_az(["account", "show", "--query", "id", "--output", "tsv"]).strip()


def configure_panel_rbac(environment: Mapping[str, str]) -> int:
    """Reconcile every panel Cosmos container-scoped grant.

    No-op (returns 0) unless ``DEPLOY_ADMINISTRATIVE_PANEL`` is ``true``.
    Returns the number of newly created assignments.
    """
    if not is_truthy(environment.get("DEPLOY_ADMINISTRATIVE_PANEL")):
        logging.info(
            "[panel.setup] DEPLOY_ADMINISTRATIVE_PANEL is not true; skipping "
            "panel Cosmos RBAC (no container, no role assignment)."
        )
        return 0

    # Validate every environment-supplied requirement before making any
    # Azure CLI call (including the AZURE_SUBSCRIPTION_ID fallback below),
    # so a misconfigured environment fails fast and deterministically.
    resource_group = (environment.get("AZURE_RESOURCE_GROUP") or "").strip()
    account_name = (environment.get("DATABASE_ACCOUNT_NAME") or "").strip()
    resource_token = (environment.get("RESOURCE_TOKEN") or "").strip()
    for value, name in (
        (resource_group, "AZURE_RESOURCE_GROUP"),
        (resource_token, "RESOURCE_TOKEN"),
    ):
        if not value:
            raise PanelRbacError(
                f"DEPLOY_ADMINISTRATIVE_PANEL is true but {name} is not set; "
                "cannot assign panel Cosmos RBAC."
            )
    database_name = (environment.get("DATABASE_NAME") or "").strip()
    if not account_name and (environment.get("APP_CONFIG_ENDPOINT") or "").strip():
        endpoint = environment["APP_CONFIG_ENDPOINT"].strip()
        for key in ("DATABASE_ACCOUNT_NAME", "DATABASE_NAME"):
            value = _run_az([
                "appconfig", "kv", "show", "--endpoint", endpoint,
                "--key", key, "--label", LABEL, "--auth-mode", "login",
                "--query", "value", "--output", "tsv",
            ]).strip()
            if not value:
                raise PanelRbacError(f"App Configuration {key} is empty; cannot assign panel Cosmos RBAC.")
            if key == "DATABASE_ACCOUNT_NAME":
                account_name = value
            elif not database_name:
                database_name = value
    if not account_name:
        raise PanelRbacError(
            "DEPLOY_ADMINISTRATIVE_PANEL is true but DATABASE_ACCOUNT_NAME is not set; "
            "cannot assign panel Cosmos RBAC."
        )
    subscription_id = resolve_subscription_id(environment)
    if not subscription_id:
        raise PanelRbacError(
            "DEPLOY_ADMINISTRATIVE_PANEL is true but AZURE_SUBSCRIPTION_ID "
            "could not be determined; cannot assign panel Cosmos RBAC."
        )
    database_name = database_name or account_name

    app_names = {
        FRONTEND_APP_SERVICE_NAME: f"ca-{resource_token}-frontend",
        DATA_INGEST_APP_SERVICE_NAME: f"ca-{resource_token}-dataingest",
    }
    principal_ids = {
        service_name: resolve_container_app_principal_id(resource_group, app_name)
        for service_name, app_name in app_names.items()
    }

    created = 0
    for grant in panel_container_grants():
        scope = container_scope_path(
            subscription_id,
            resource_group,
            account_name,
            database_name,
            grant.container_name,
        )
        if ensure_cosmos_sql_role_assignment(
            account_name,
            resource_group,
            subscription_id,
            principal_ids[grant.service_name],
            grant.role_definition_guid,
            scope,
        ):
            created += 1
            logging.info(
                "[panel.setup] granted %s role %s on container %s scope-only.",
                grant.service_name,
                grant.role_definition_guid,
                grant.container_name,
            )
        else:
            logging.info(
                "[panel.setup] %s already has a role assignment at container "
                "%s scope; left untouched.",
                grant.service_name,
                grant.container_name,
            )
    return created


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    created = configure_panel_rbac(os.environ)
    logging.info("[panel.setup] finished; %d new role assignment(s) created.", created)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
