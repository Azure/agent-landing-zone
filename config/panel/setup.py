#!/usr/bin/env python3
"""Grant the bundled frontend access to its native UI metadata container.

Workflows, history, feedback or private attachment descriptors require metadata.
The grant is Data Contributor at exactly one container scope, never account
scope. Neither the runtime nor ingestion receives UI metadata access here.
Assignments are idempotent; this configurator never removes resources or grants.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

from util.azure_cli import resolve_az_command
from config.deployment.resource_groups import ResourceGroupError, resource_group_for


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


def panel_container_grants(environment: Mapping[str, str] | None = None) -> tuple[PanelContainerGrant, ...]:
    """Return the single frontend-only native metadata grant."""
    return (PanelContainerGrant(
        FRONTEND_APP_SERVICE_NAME,
        COSMOS_DATA_CONTRIBUTOR_ROLE_GUID,
        (environment or {}).get("NATIVE_UI_METADATA_CONTAINER", "native-ui-metadata"),
    ),)


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
    """Assign native metadata access when selected; return newly created grants."""
    from config.deployment.native import resolve_application
    from config.deployment.composition import is_bundled_application
    metadata = is_bundled_application(environment) and resolve_application(environment).metadata
    if not metadata:
        logging.info(
            "[panel.setup] Native frontend metadata is not required; no container role assignment."
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
                f"Native frontend metadata requires {name}; cannot assign Cosmos RBAC."
            )
    try:
        resource_group = resource_group_for(environment, "application")
    except ResourceGroupError as error:
        raise PanelRbacError(str(error)) from error
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
            "Native frontend metadata requires DATABASE_ACCOUNT_NAME; cannot assign Cosmos RBAC."
        )
    subscription_id = resolve_subscription_id(environment)
    if not subscription_id:
        raise PanelRbacError(
            "Native frontend metadata requires an AZURE_SUBSCRIPTION_ID; cannot assign Cosmos RBAC."
        )
    database_name = database_name or account_name

    app_names = {
        FRONTEND_APP_SERVICE_NAME: f"ca-{resource_token}-frontend",
    }
    principal_ids = {
        service_name: resolve_container_app_principal_id(resource_group, app_name)
        for service_name, app_name in app_names.items()
    }

    created = 0
    grants = panel_container_grants(environment)
    for grant in grants:
        if grant.service_name not in principal_ids:
            continue
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
