"""Assign capability-profile roles to application identities (FR-015e, T077).

Runs in ``postProvision`` through ``python -m config.appdefinition
--assign-roles``. For every ``containerapp`` component of the selected
definition, it expands the component profiles with
:func:`~config.appdefinition.profiles.expand_profiles`, resolves the component
Container App identity by its ``azd-service-name`` tag, resolves each scope to
the single matching resource in ``AZURE_RESOURCE_GROUP``, and creates only the
assignments that do not already exist (directly or inherited). Re-runs converge.
Custom hosted components use the same profile reconciliation after deployment,
with an instance identity verified by :mod:`config.deployment.hosted_access`.
The bundled hosted orchestrator retains its feature-owned access bootstrap.

Every Azure call goes through ``az`` (:func:`config.deployment.appconfig._run_az`)
so unit tests replace one boundary.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

from config import find_repo_root

from .loader import KIND_CONTAINER_APP, AppDefinition, component_service_name, effective_components
from .profiles import (
    SCOPE_APP_CONFIG,
    SCOPE_CONTAINER_REGISTRY,
    SCOPE_COSMOS,
    SCOPE_FOUNDRY_ACCOUNT,
    SCOPE_KEY_VAULT,
    SCOPE_SEARCH,
    SCOPE_STORAGE,
    RoleAssignment,
    expand_profiles,
)

LOGGER = logging.getLogger("config.appdefinition.roles")

RunAz = Callable[..., str]

ROLES_RELATIVE_PATH = Path("infra") / "constants" / "roles.json"
#: Cosmos DB data-plane roles use SQL role assignments, not Azure RBAC.
COSMOS_DATA_ROLES = frozenset({"CosmosDBBuiltInDataContributor", "CosmosDBBuiltInDataReader"})


@dataclass(frozen=True)
class ScopeSpec:
    resource_type: str
    #: azd environment values naming the resource, in preference order. URLs
    #: are reduced to their first host label (for example ``<name>.vault.azure.net``).
    name_sources: tuple[str, ...]
    #: Name prefixes of resources of the same type that are never the target.
    excluded_prefixes: tuple[str, ...] = ()


SCOPES: dict[str, ScopeSpec] = {
    SCOPE_APP_CONFIG: ScopeSpec("Microsoft.AppConfiguration/configurationStores", ("APP_CONFIG_ENDPOINT",)),
    SCOPE_CONTAINER_REGISTRY: ScopeSpec(
        "Microsoft.ContainerRegistry/registries",
        ("AZURE_CONTAINER_REGISTRY_NAME", "AZURE_CONTAINER_REGISTRY_ENDPOINT"),
    ),
    SCOPE_KEY_VAULT: ScopeSpec(
        "Microsoft.KeyVault/vaults",
        ("AZURE_KEY_VAULT_NAME", "KEY_VAULT_NAME", "KEY_VAULT_URI", "AZURE_KEY_VAULT_ENDPOINT"),
    ),
    SCOPE_FOUNDRY_ACCOUNT: ScopeSpec(
        "Microsoft.CognitiveServices/accounts", ("AI_FOUNDRY_ACCOUNT_NAME", "AZURE_AI_ACCOUNT_NAME")
    ),
    SCOPE_SEARCH: ScopeSpec("Microsoft.Search/searchServices", ("SEARCH_SERVICE_NAME", "SEARCH_SERVICE_ENDPOINT")),
    # The Foundry account storage ("staif...") is never an application data store.
    SCOPE_STORAGE: ScopeSpec("Microsoft.Storage/storageAccounts", ("AZURE_STORAGE_ACCOUNT_NAME", "STORAGE_ACCOUNT_NAME"), ("staif",)),
    SCOPE_COSMOS: ScopeSpec("Microsoft.DocumentDB/databaseAccounts", ("AZURE_COSMOS_DB_NAME", "COSMOS_DB_ENDPOINT")),
}


class RoleAssignmentError(RuntimeError):
    """Raised when an identity, scope, or role cannot be resolved or assigned."""


@dataclass(frozen=True)
class PlannedAssignment:
    component: str
    service: str
    assignment: RoleAssignment


def plan_assignments(definition: AppDefinition, *, hosted_orchestration: bool) -> list[PlannedAssignment]:
    """Return the profile role assignments for every ``containerapp`` component."""
    planned: list[PlannedAssignment] = []
    for component in effective_components(definition, hosted_orchestration=hosted_orchestration):
        if component.get("kind") != KIND_CONTAINER_APP:
            continue
        service = component_service_name(definition, component)
        for assignment in expand_profiles(component.get("profiles") or ()):
            planned.append(PlannedAssignment(str(component.get("name")), service, assignment))
    return planned


def load_role_guids(repo_root: Path | None = None) -> dict[str, str]:
    data = json.loads(((repo_root or find_repo_root()) / ROLES_RELATIVE_PATH).read_text(encoding="utf-8"))
    return {name: str(entry["guid"]) for name, entry in data.items() if isinstance(entry, dict) and "guid" in entry}


def _host_label(value: str) -> str:
    value = value.strip()
    if "://" in value:
        value = urlsplit(value).hostname or ""
    return value.split(".", 1)[0]


def _json(run_az: RunAz, arguments: list[str]) -> Any:
    output = run_az([*arguments, "--output", "json", "--only-show-errors"], required=False)
    try:
        return json.loads(output or "null")
    except json.JSONDecodeError as error:
        raise RoleAssignmentError(f"Azure CLI returned invalid JSON for az {' '.join(arguments)}: {error}") from error


def resolve_scope(scope: str, environment: Mapping[str, str], resource_group: str, run_az: RunAz) -> str:
    """Return the resource id of ``scope``; fail unless exactly one resource matches."""
    spec = SCOPES.get(scope)
    if spec is None:
        raise RoleAssignmentError(f"Scope {scope} has no resource mapping.")
    items = _json(run_az, ["resource", "list", "--resource-group", resource_group, "--resource-type", spec.resource_type])
    items = [item for item in items or [] if isinstance(item, dict) and item.get("id") and item.get("name")]
    preferred = next((_host_label(environment[name]) for name in spec.name_sources if (environment.get(name) or "").strip()), "")
    if preferred:
        items = [item for item in items if str(item["name"]).lower() == preferred.lower()]
    else:
        items = [item for item in items if not str(item["name"]).lower().startswith(spec.excluded_prefixes)]
    if len(items) != 1:
        hint = f"named {preferred}" if preferred else f"(set {spec.name_sources[0]} to choose one)"
        raise RoleAssignmentError(
            f"Expected exactly one {spec.resource_type} {hint} in resource group {resource_group} "
            f"for scope {scope}; found {len(items)}."
        )
    return str(items[0]["id"])


def _resolve_identity(service: str, resource_group: str, run_az: RunAz) -> tuple[str, str, str]:
    apps = _json(run_az, ["containerapp", "list", "--resource-group", resource_group, "--query",
                          f"[?tags.\"azd-service-name\"=='{service}'].{{name:name,identity:identity}}"])
    apps = [app for app in apps or [] if isinstance(app, dict)]
    if len(apps) != 1:
        raise RoleAssignmentError(
            f"Expected one Container App tagged azd-service-name={service} in resource group "
            f"{resource_group}; found {len(apps)}. Run azd provision for this application first."
        )
    identity = apps[0].get("identity") or {}
    identities = [(str(identity["principalId"]), "", "")] if identity.get("principalId") else []
    identities += [
        (str(value["principalId"]), str(value.get("clientId") or ""), str(resource_id))
        for resource_id, value in (identity.get("userAssignedIdentities") or {}).items()
        if isinstance(value, dict) and value.get("principalId")
    ]
    if len(identities) != 1:
        raise RoleAssignmentError(
            f"Container App {apps[0].get('name')} must have exactly one managed identity to receive "
            f"profile roles; found {len(identities)}."
        )
    return identities[0]


def resolve_principal(service: str, resource_group: str, run_az: RunAz) -> str:
    """Return the single managed identity principal of the service's Container App."""
    return _resolve_identity(service, resource_group, run_az)[0]


def discover_component_identities(
    definition: AppDefinition,
    environment: Mapping[str, str],
    *,
    hosted_orchestration: bool,
    run_az: RunAz | None = None,
) -> dict[str, str]:
    """Read Container App client IDs for platform outputs, without role writes."""
    components = [
        component
        for component in effective_components(definition, hosted_orchestration=hosted_orchestration)
        if component.get("kind") == KIND_CONTAINER_APP
    ]
    if not components:
        return {}
    resource_group = (environment.get("AZURE_RESOURCE_GROUP") or "").strip()
    if not resource_group:
        raise RoleAssignmentError("AZURE_RESOURCE_GROUP is required to discover component identities.")
    if run_az is None:
        from config.deployment.appconfig import _run_az as run_az
    identities: dict[str, str] = {}
    for component in components:
        service = component_service_name(definition, component)
        principal, client, resource_id = _resolve_identity(service, resource_group, run_az)
        if not client:
            arguments = (
                ["identity", "show", "--ids", resource_id, "--query", "clientId"]
                if resource_id else
                ["ad", "sp", "show", "--id", principal, "--query", "appId"]
            )
            client = _json(run_az, arguments)
        if not isinstance(client, str) or not client.strip():
            raise RoleAssignmentError(f"Cannot resolve the managed identity client ID for service {service}.")
        identities[str(component["name"])] = client.strip()
    return identities


def _ensure_rbac(principal: str, role_guid: str, scope_id: str, run_az: RunAz) -> bool:
    existing = _json(run_az, ["role", "assignment", "list", "--assignee", principal, "--role", role_guid,
                              "--scope", scope_id, "--include-inherited"])
    if existing:
        return False
    run_az(["role", "assignment", "create", "--assignee-object-id", principal,
            "--assignee-principal-type", "ServicePrincipal", "--role", role_guid,
            "--scope", scope_id, "--output", "none", "--only-show-errors"], required=False)
    return True


def _ensure_cosmos(principal: str, role_guid: str, account_id: str, resource_group: str, run_az: RunAz) -> bool:
    account = account_id.rstrip("/").rsplit("/", 1)[-1]
    definition_id = f"{account_id}/sqlRoleDefinitions/{role_guid}"
    existing = _json(run_az, ["cosmosdb", "sql", "role", "assignment", "list", "--account-name", account,
                              "--resource-group", resource_group])
    for row in existing or []:
        if (isinstance(row, dict) and str(row.get("principalId", "")).lower() == principal.lower()
                and str(row.get("roleDefinitionId", "")).lower() == definition_id.lower()
                and str(row.get("scope", "")).rstrip("/").lower() == account_id.rstrip("/").lower()):
            return False
    run_az(["cosmosdb", "sql", "role", "assignment", "create", "--account-name", account,
            "--resource-group", resource_group, "--role-definition-id", role_guid,
            "--principal-id", principal, "--scope", "/", "--output", "none", "--only-show-errors"], required=False)
    return True


def assign_roles(
    definition: AppDefinition,
    environment: Mapping[str, str],
    *,
    hosted_orchestration: bool,
    run_az: RunAz | None = None,
    role_guids: Mapping[str, str] | None = None,
) -> list[PlannedAssignment]:
    """Create missing profile role assignments; return the ones created."""
    planned = plan_assignments(definition, hosted_orchestration=hosted_orchestration)
    return _assign_planned(planned, environment, run_az=run_az, role_guids=role_guids)


def assign_hosted_roles(
    component: Mapping[str, Any],
    principal: str,
    environment: Mapping[str, str],
    *,
    run_az: RunAz | None = None,
    role_guids: Mapping[str, str] | None = None,
) -> list[PlannedAssignment]:
    """Apply the selected component profiles to its verified hosted identity."""
    from uuid import UUID

    if UUID(principal).int == 0:
        raise RoleAssignmentError("Hosted runtime principal must be a nonzero GUID.")
    name = str(component["name"])
    planned = [
        PlannedAssignment(name, name, assignment)
        for assignment in expand_profiles(component.get("profiles") or ())
    ]
    return _assign_planned(
        planned, environment, run_az=run_az, role_guids=role_guids,
        principals={name: principal},
    )


def _assign_planned(
    planned: list[PlannedAssignment],
    environment: Mapping[str, str],
    *,
    run_az: RunAz | None,
    role_guids: Mapping[str, str] | None,
    principals: Mapping[str, str] | None = None,
) -> list[PlannedAssignment]:
    if not planned:
        return []
    resource_group = (environment.get("AZURE_RESOURCE_GROUP") or "").strip()
    if not resource_group:
        raise RoleAssignmentError("AZURE_RESOURCE_GROUP is required to assign capability-profile roles.")
    if run_az is None:
        from config.deployment.appconfig import _run_az as run_az
    guids = dict(role_guids) if role_guids is not None else load_role_guids()
    unknown = sorted({item.assignment.role for item in planned} - guids.keys())
    if unknown:
        raise RoleAssignmentError(f"Role {', '.join(unknown)} is not defined in {ROLES_RELATIVE_PATH.as_posix()}.")
    # Resolve every identity and scope before the first write so an ambiguous
    # or missing resource fails with no partial assignment.
    principals = principals if principals is not None else {
        service: resolve_principal(service, resource_group, run_az)
        for service in dict.fromkeys(item.service for item in planned)
    }
    scopes = {
        scope: resolve_scope(scope, environment, resource_group, run_az)
        for scope in dict.fromkeys(item.assignment.scope for item in planned)
    }
    created: list[PlannedAssignment] = []
    for item in planned:
        role, scope = item.assignment.role, item.assignment.scope
        principal, scope_id = principals[item.service], scopes[scope]
        if role in COSMOS_DATA_ROLES:
            changed = _ensure_cosmos(principal, guids[role], scope_id, resource_group, run_az)
        else:
            changed = _ensure_rbac(principal, guids[role], scope_id, run_az)
        LOGGER.info("%s: %s on %s %s.", item.component, role, scope, "assigned" if changed else "already assigned")
        if changed:
            created.append(item)
    return created
