"""Capability profile catalog (FR-015e, R12).

This fixed table is the only source of role assignments for application
identities. Application definitions name profiles, never roles. Role names
match the ``roles`` vocabulary of ``containerAppsList`` in
``main.parameters.json`` so the bundled trio keeps its current permissions.

Feature-owned assignments (continuity, administrative panel, hosted-agent
access) stay in their own modules and are intentionally not modeled here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RoleAssignment:
    """One role granted to a component identity on one platform resource."""

    role: str
    scope: str


@dataclass(frozen=True)
class CapabilityProfile:
    name: str
    description: str
    roles: tuple[RoleAssignment, ...]


# Scope identifiers name platform resources, not Azure resource IDs.
SCOPE_APP_CONFIG = "appConfiguration"
SCOPE_CONTAINER_REGISTRY = "containerRegistry"
SCOPE_KEY_VAULT = "keyVault"
SCOPE_FOUNDRY_ACCOUNT = "aiFoundryAccount"
SCOPE_SEARCH = "searchService"
SCOPE_STORAGE = "storageAccount"
SCOPE_COSMOS = "cosmosDbAccount"

BASE_PROFILE = "base"

PROFILES: dict[str, CapabilityProfile] = {
    profile.name: profile
    for profile in (
        CapabilityProfile(
            BASE_PROFILE,
            "Implicit for every component: read configuration and pull images; no secret access.",
            (
                RoleAssignment("AppConfigurationDataReader", SCOPE_APP_CONFIG),
                RoleAssignment("AcrPull", SCOPE_CONTAINER_REGISTRY),
            ),
        ),
        CapabilityProfile(
            "secret-reader",
            "Resolve explicitly required Key Vault secrets. App Configuration access alone does not grant this.",
            (RoleAssignment("KeyVaultSecretsUser", SCOPE_KEY_VAULT),),
        ),
        CapabilityProfile(
            "model-user",
            "Call models deployed in the Foundry account.",
            (
                RoleAssignment("CognitiveServicesUser", SCOPE_FOUNDRY_ACCOUNT),
                RoleAssignment("CognitiveServicesOpenAIUser", SCOPE_FOUNDRY_ACCOUNT),
            ),
        ),
        CapabilityProfile(
            "retrieval-reader",
            "Query search indexes and read source documents.",
            (
                RoleAssignment("SearchIndexDataReader", SCOPE_SEARCH),
                RoleAssignment("StorageBlobDataReader", SCOPE_STORAGE),
            ),
        ),
        CapabilityProfile(
            "conversation-store",
            "Read and write conversation data in Cosmos DB.",
            (RoleAssignment("CosmosDBBuiltInDataContributor", SCOPE_COSMOS),),
        ),
        CapabilityProfile(
            "blob-delegator",
            "Read blobs and issue user delegation SAS links.",
            (
                RoleAssignment("StorageBlobDataReader", SCOPE_STORAGE),
                RoleAssignment("StorageBlobDelegator", SCOPE_STORAGE),
            ),
        ),
        CapabilityProfile(
            "ingestion-writer",
            "Write search index content and source documents.",
            (
                RoleAssignment("SearchIndexDataContributor", SCOPE_SEARCH),
                RoleAssignment("StorageBlobDataContributor", SCOPE_STORAGE),
            ),
        ),
    )
}

#: Profiles a definition may list explicitly (``base`` is always implicit).
SELECTABLE_PROFILES: tuple[str, ...] = tuple(
    name for name in PROFILES if name != BASE_PROFILE
)


class UnknownProfileError(ValueError):
    """Raised when a profile name is not in the catalog."""


def expand_profiles(
    profiles: Iterable[str], *, runtime_mode: str = "appConfig",
) -> tuple[RoleAssignment, ...]:
    """Return the de-duplicated role assignments for ``base`` plus ``profiles``.

    Order is stable: catalog order of the profiles, then role order within
    each profile.
    """
    if runtime_mode not in {"appConfig", "containerEnv", "none"}:
        raise ValueError("APP_RUNTIME_CONFIGURATION_MODE must be appConfig, containerEnv or none.")
    requested = {BASE_PROFILE, *profiles}
    unknown = sorted(requested - PROFILES.keys())
    if unknown:
        raise UnknownProfileError(
            f"Profile {', '.join(unknown)} is not supported. Supported: "
            + ", ".join(PROFILES)
            + "."
        )
    assignments: list[RoleAssignment] = []
    for name, profile in PROFILES.items():
        if name not in requested:
            continue
        for assignment in profile.roles:
            if assignment.scope == SCOPE_APP_CONFIG and runtime_mode != "appConfig":
                continue
            if assignment not in assignments:
                assignments.append(assignment)
    return tuple(assignments)


def role_names(profiles: Iterable[str]) -> frozenset[str]:
    """Return the set of role names granted by ``base`` plus ``profiles``."""
    return frozenset(assignment.role for assignment in expand_profiles(profiles))
