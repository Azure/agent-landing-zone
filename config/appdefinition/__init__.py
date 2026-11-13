"""Application definitions for Agent Landing Zone (FR-015, ADR-0017).

Public API: load, validate, and bind an ``app-definition.json`` and expand
its capability profiles into role assignments. Nothing exported here calls
Azure; :mod:`config.appdefinition.roles` (``--assign-roles``) applies the
expanded roles through the Azure CLI during ``postProvision``.
"""

from __future__ import annotations

from .binding import APP_ID_ENV, BindingResult, bind, check_binding, env_file_path, resolve_env_name
from .errors import (
    AppDefinitionError,
    AppDefinitionValidationError,
    BindingMismatchError,
    DefinitionNotFoundError,
    EnvironmentNotFoundError,
    ValidationIssue,
)
from .loader import (
    DEFINITION_ENV,
    DEFINITION_FILENAME,
    KIND_CONTAINER_APP,
    KIND_HOSTED_AGENT,
    AppDefinition,
    component_service_name,
    effective_components,
    load_definition,
    load_selected_definition,
    resolve_definition_path,
)
from .profiles import PROFILES, SELECTABLE_PROFILES, RoleAssignment, expand_profiles, role_names
from .validator import collect_issues, is_reserved_hosted_agent_env, validate_definition

__all__ = [
    "APP_ID_ENV",
    "DEFINITION_ENV",
    "DEFINITION_FILENAME",
    "KIND_CONTAINER_APP",
    "KIND_HOSTED_AGENT",
    "PROFILES",
    "SELECTABLE_PROFILES",
    "AppDefinition",
    "AppDefinitionError",
    "AppDefinitionValidationError",
    "BindingMismatchError",
    "BindingResult",
    "DefinitionNotFoundError",
    "EnvironmentNotFoundError",
    "RoleAssignment",
    "ValidationIssue",
    "bind",
    "check_binding",
    "collect_issues",
    "component_service_name",
    "effective_components",
    "env_file_path",
    "expand_profiles",
    "is_reserved_hosted_agent_env",
    "load_definition",
    "load_selected_definition",
    "resolve_definition_path",
    "resolve_env_name",
    "role_names",
    "validate_definition",
]
