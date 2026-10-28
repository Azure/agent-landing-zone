"""Public settings for the implemented native Search delegation route.

An empty mode denotes no hosted route (classic, including pre-cutover migration).
It is not a service-identity fallback. Source credentials remain request-local in
the UI/runtime; provisioning publishes neither tokens nor an identity envelope.
"""

from __future__ import annotations

from typing import Mapping
from uuid import UUID

from config.deployment.composition import is_truthy


NATIVE_SEARCH = "native_search"
RETRIEVAL_AUTH_MODE = "RETRIEVAL_AUTH_MODE"
SEARCH_BACKENDS = frozenset({"foundry_iq", "ai_search"})
SOURCE_ID_KEYS = (
    "WORK_IQ_APPLICATION_ID",
    "WORK_IQ_FEDERATED_CREDENTIAL_ID",
    "WORK_IQ_TENANT_ID",
    "SHAREPOINT_INDEXED_APPLICATION_ID",
    "SHAREPOINT_INDEXED_FEDERATED_CREDENTIAL_APPLICATION_ID",
)


def source_public_settings(environment: Mapping[str, str]) -> dict[str, str]:
    """Validate/publish only explicitly supplied nonsecret source identity IDs.

    Empty values deliberately clear existing settings. Work IQ's federated
    credential ID identifies the FIC object; SharePoint's federated credential
    application ID identifies the managed identity client. Never substitute one
    for the other. Source completeness and enablement belong to Search setup.
    """
    settings: dict[str, str] = {}
    for key in SOURCE_ID_KEYS:
        if key not in environment:
            continue
        value = environment[key]
        try:
            if not isinstance(value, str):
                raise ValueError
            if value:
                UUID(value)
        except ValueError:
            raise ValueError(f"{key} must be a UUID or empty; value omitted.") from None
        settings[key] = value
    return settings


def validate_auth_mode(environment: Mapping[str, str]) -> None:
    """Reject candidate/unimplemented modes, without reflecting operator values."""
    raw = environment.get(RETRIEVAL_AUTH_MODE, "")
    if not isinstance(raw, str) or raw.strip() not in {"", NATIVE_SEARCH}:
        raise ValueError(
            "RETRIEVAL_AUTH_MODE must be native_search (or empty for automatic "
            "hosted selection / no classic route). No other route is implemented."
        )


def public_settings(
    environment: Mapping[str, str], *, hosted: bool,
) -> dict[str, str]:
    """Resolve the route before discovery/publication, preserving classic auth."""
    validate_auth_mode(environment)
    if not hosted:
        return {RETRIEVAL_AUTH_MODE: ""}
    if (environment.get("HOSTED_AGENT_AUTH_MODE") or "user_delegated").strip() != "user_delegated":
        raise ValueError(
            "Native protected retrieval requires HOSTED_AGENT_AUTH_MODE=user_delegated; "
            "service credentials authenticate Search transport only."
        )
    if is_truthy(environment.get("ALLOW_ANONYMOUS")):
        raise ValueError("Native protected retrieval requires ALLOW_ANONYMOUS=false.")
    backend = (environment.get("RETRIEVAL_BACKEND") or "foundry_iq").strip()
    if backend not in SEARCH_BACKENDS:
        raise ValueError("RETRIEVAL_BACKEND must be foundry_iq or ai_search for native Search retrieval.")
    if backend == "foundry_iq":
        forward = environment.get("FOUNDRY_IQ_FORWARD_SOURCE_AUTH")
        if forward is not None and not is_truthy(forward):
            raise ValueError(
                "Native protected retrieval requires FOUNDRY_IQ_FORWARD_SOURCE_AUTH=true."
            )
    # Source schemas, permission metadata and consent belong to Search setup's
    # template validation. Selecting this route is not proof of source readiness;
    # never change source flags, invent app audiences or remove a KB member here.
    return {
        RETRIEVAL_AUTH_MODE: NATIVE_SEARCH,
        "HOSTED_AGENT_AUTH_MODE": "user_delegated",
    }
