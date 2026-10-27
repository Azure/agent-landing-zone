#!/usr/bin/env python3
"""Configure secure hosted conversation continuity for the UI BFF."""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hmac
import json
import logging
import os
import re
import secrets
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

from azure.appconfiguration import AzureAppConfigurationClient, ConfigurationSetting
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import (
    AzureCliCredential,
    ChainedTokenCredential,
    ManagedIdentityCredential,
)
from azure.keyvault.secrets import SecretClient

from config.continuity.settings import (
    CONTINUITY_UNAVAILABLE_STATUS_CODE,
    DEFAULT_SETTINGS,
    DELEGATED_IDENTITY_HEADER,
    DELEGATED_IDENTITY_SOURCE,
    FOUNDRY_TOKEN_AUDIENCE,
    RESPONSES_PROTOCOL_VERSION,
)
from config.deployment.resource_groups import resource_group_for
from util.azure_cli import resolve_az_command


LABEL = "agent-lz"
CAPABILITY_CONFIG_KEY = "HOSTED_CONVERSATION_CAPABILITY_KEY"
CAPABILITY_SECRET_NAME = "HOSTED-CONVERSATION-CAPABILITY-KEY"
KEY_VAULT_REFERENCE_CONTENT_TYPE = (
    "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8"
)
FOUNDRY_AGENT_CONSUMER_ROLE_ID = "eed3b665-ab3a-47b6-8f48-c9382fb1dad6"
FOUNDRY_AGENT_CONSUMER_ROLE_NAME = "Foundry Agent Consumer"
FOUNDRY_AGENT_INTERACT_DATA_ACTION = (
    "Microsoft.CognitiveServices/accounts/AIServices/endpoints/interact/action"
)
USER_IDENTITY_IMPERSONATION_ROLE_ID = "bef66abe-a495-530a-be1d-5d882fecff03"
USER_IDENTITY_IMPERSONATION_ROLE_NAME = (
    "Agent Landing Zone Hosted Agent User Identity Impersonation"
)
LEGACY_USER_IDENTITY_IMPERSONATION_ROLE_NAMES = (
    "GPT-RAG Hosted Agent User Identity Impersonation",
)
USER_IDENTITY_IMPERSONATION_DATA_ACTION = (
    "Microsoft.CognitiveServices/accounts/AIServices/agents/endpoints/"
    "UserIdentityImpersonation/action"
)
FOUNDRY_DATA_PLANE_API_VERSION = "v1"
KEY_VAULT_SECRETS_USER_ROLE_ID = "4633458b-17de-408a-b874-0445c86b69e6"
KEY_VAULT_SECRET_GET_DATA_ACTION = (
    "Microsoft.KeyVault/vaults/secrets/getSecret/action"
)
KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
AGENT_SCOPE_PATTERN = re.compile(
    r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/"
    r"Microsoft\.CognitiveServices/accounts/[^/]+/projects/[^/]+/agents/[^/]+$",
    re.IGNORECASE,
)

@dataclass(frozen=True)
class ContinuitySettings:
    enabled: bool
    owner_binding: str
    owner_binding_validated: bool
    delegated_identity_header: str
    delegated_identity_source: str
    token_audience: str
    responses_protocol_version: str
    unavailable_status_code: int
    key_id: str
    capability_ttl_seconds: int
    history_max_items: int
    history_max_tokens: int
    history_truncation: str


def create_credential() -> ChainedTokenCredential:
    return ChainedTokenCredential(
        AzureCliCredential(process_timeout=30),
        ManagedIdentityCredential(process_timeout=30),
    )


def _strict_boolean(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{name} must be exactly 'true' or 'false'.")
    return normalized == "true"


def _bounded_integer(name: str, value: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise ValueError(f"{name} must be a base-10 integer.") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


def validate_continuity_settings(
    values: Mapping[str, str],
    *,
    deployment_topology: str = "",
    chat_backend: str = "",
    deploy_key_vault: bool = True,
) -> ContinuitySettings:
    settings = ContinuitySettings(
        enabled=_strict_boolean(
            "HOSTED_CONTINUITY_ENABLED",
            values["HOSTED_CONTINUITY_ENABLED"],
        ),
        owner_binding=values["HOSTED_CONVERSATION_OWNER_BINDING"].strip(),
        owner_binding_validated=_strict_boolean(
            "HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED",
            values["HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED"],
        ),
        delegated_identity_header=values[
            "HOSTED_CONVERSATION_DELEGATED_IDENTITY_HEADER"
        ].strip(),
        delegated_identity_source=values[
            "HOSTED_CONVERSATION_DELEGATED_IDENTITY_SOURCE"
        ].strip(),
        token_audience=values["HOSTED_CONVERSATIONS_TOKEN_AUDIENCE"].strip(),
        responses_protocol_version=values[
            "HOSTED_AGENT_RESPONSES_PROTOCOL_VERSION"
        ].strip(),
        unavailable_status_code=_bounded_integer(
            "HOSTED_CONTINUITY_UNAVAILABLE_STATUS_CODE",
            values["HOSTED_CONTINUITY_UNAVAILABLE_STATUS_CODE"],
            100,
            599,
        ),
        key_id=values["HOSTED_CONVERSATION_CAPABILITY_KEY_ID"].strip(),
        capability_ttl_seconds=_bounded_integer(
            "HOSTED_CONVERSATION_CAPABILITY_TTL_SECONDS",
            values["HOSTED_CONVERSATION_CAPABILITY_TTL_SECONDS"],
            60,
            3600,
        ),
        history_max_items=_bounded_integer(
            "HOSTED_HISTORY_MAX_ITEMS",
            values["HOSTED_HISTORY_MAX_ITEMS"],
            1,
            1000,
        ),
        history_max_tokens=_bounded_integer(
            "HOSTED_HISTORY_MAX_TOKENS",
            values["HOSTED_HISTORY_MAX_TOKENS"],
            1,
            1_000_000,
        ),
        history_truncation=values["HOSTED_HISTORY_TRUNCATION"].strip(),
    )

    if settings.owner_binding not in {"delegated", "capability"}:
        raise ValueError(
            "HOSTED_CONVERSATION_OWNER_BINDING must be 'delegated' or "
            "'capability'."
        )
    if settings.delegated_identity_header != DELEGATED_IDENTITY_HEADER:
        raise ValueError(
            "HOSTED_CONVERSATION_DELEGATED_IDENTITY_HEADER must be "
            f"{DELEGATED_IDENTITY_HEADER!r}."
        )
    if settings.delegated_identity_source != DELEGATED_IDENTITY_SOURCE:
        raise ValueError(
            "HOSTED_CONVERSATION_DELEGATED_IDENTITY_SOURCE must be "
            f"{DELEGATED_IDENTITY_SOURCE!r}; browser-supplied identities and "
            "OBO retrieval tokens are not ownership inputs."
        )
    if settings.token_audience != FOUNDRY_TOKEN_AUDIENCE:
        raise ValueError(
            "HOSTED_CONVERSATIONS_TOKEN_AUDIENCE must be "
            f"{FOUNDRY_TOKEN_AUDIENCE!r}."
        )
    if settings.responses_protocol_version != RESPONSES_PROTOCOL_VERSION:
        raise ValueError(
            "HOSTED_AGENT_RESPONSES_PROTOCOL_VERSION must be exactly "
            f"{RESPONSES_PROTOCOL_VERSION!r}."
        )
    if settings.unavailable_status_code != int(
        CONTINUITY_UNAVAILABLE_STATUS_CODE
    ):
        raise ValueError(
            "HOSTED_CONTINUITY_UNAVAILABLE_STATUS_CODE must be 503."
        )
    if not KEY_ID_PATTERN.fullmatch(settings.key_id):
        raise ValueError(
            "HOSTED_CONVERSATION_CAPABILITY_KEY_ID must contain 1-64 safe "
            "identifier characters."
        )
    if settings.history_truncation != "drop_oldest":
        raise ValueError("HOSTED_HISTORY_TRUNCATION must be 'drop_oldest'.")
    if settings.enabled:
        if settings.owner_binding == "capability" and not deploy_key_vault:
            raise ValueError(
                "Capability fallback requires DEPLOY_KEY_VAULT=true."
            )
        if deployment_topology not in {"hosted-no-panel", "hosted-panel"}:
            raise ValueError(
                "HOSTED_CONTINUITY_ENABLED requires a hosted deployment topology."
            )
        if chat_backend != "hosted_agent":
            raise ValueError(
                "HOSTED_CONTINUITY_ENABLED requires CHAT_BACKEND=hosted_agent."
            )
    return settings


def generate_capability_key() -> str:
    """Return a Base64URL encoding of exactly 256 random bits."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def _decode_capability_key(value: str) -> bytes:
    candidate = value.strip()
    padded = candidate + ("=" * (-len(candidate) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        decoded = b""
    if len(decoded) != 32:
        raise ValueError(
            f"The existing {CAPABILITY_SECRET_NAME} secret is not an encoding "
            "of exactly 32 bytes. Rotate it by advancing "
            "HOSTED_CONVERSATION_CAPABILITY_KEY_ID."
        )
    return decoded


def _secret_key_id(secret: Any) -> str:
    properties = getattr(secret, "properties", None)
    tags = getattr(properties, "tags", None) or {}
    return str(tags.get("key_id") or "")


def ensure_capability_secret(secret_client: Any, key_id: str) -> str:
    """Create or idempotently rotate the capability key for the requested key ID."""
    try:
        current = secret_client.get_secret(CAPABILITY_SECRET_NAME)
    except ResourceNotFoundError:
        current = None

    if current is not None:
        _decode_capability_key(current.value)
        current_key_id = _secret_key_id(current)
        if current_key_id and hmac.compare_digest(current_key_id, key_id):
            return "reused"

    secret_client.set_secret(
        CAPABILITY_SECRET_NAME,
        generate_capability_key(),
        content_type="application/octet-stream",
        tags={"key_id": key_id, "contract": "hosted-conversation-capability-v1"},
    )
    return "rotated" if current is not None else "created"


def key_vault_reference(vault_uri: str) -> str:
    uri = f"{vault_uri.rstrip('/')}/secrets/{CAPABILITY_SECRET_NAME}"
    return json.dumps({"uri": uri}, separators=(",", ":"))


def _same_key_vault_reference(left: str, right: str) -> bool:
    try:
        left_uri = urlparse(str(json.loads(left).get("uri") or ""))
        right_uri = urlparse(str(json.loads(right).get("uri") or ""))
    except (AttributeError, json.JSONDecodeError):
        return False
    return (
        left_uri.scheme.lower() == right_uri.scheme.lower() == "https"
        and (left_uri.hostname or "").lower()
        == (right_uri.hostname or "").lower()
        and not left_uri.username
        and not right_uri.username
        and not left_uri.password
        and not right_uri.password
        and left_uri.port in {None, 443}
        and right_uri.port in {None, 443}
        and left_uri.path.rstrip("/") == right_uri.path.rstrip("/")
        and not left_uri.params
        and not right_uri.params
        and not left_uri.query
        and not right_uri.query
        and not left_uri.fragment
        and not right_uri.fragment
    )


def resolve_capability_vault_uri(environ: Mapping[str, str] = os.environ) -> str:
    configured_uri = environ.get("HOSTED_CONTINUITY_KEY_VAULT_URI", "").strip()
    if configured_uri:
        vault_uri = configured_uri.rstrip("/") + "/"
    else:
        vault_name = environ.get("HOSTED_CONTINUITY_KEY_VAULT_NAME", "").strip()
        if not vault_name:
            raise RuntimeError(
                "HOSTED_CONTINUITY_KEY_VAULT_URI or "
                "HOSTED_CONTINUITY_KEY_VAULT_NAME is required when hosted "
                "continuity is enabled."
            )
        vault_uri = f"https://{vault_name}.vault.azure.net/"

    parsed = urlparse(vault_uri)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".vault.azure.net")
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "HOSTED_CONTINUITY_KEY_VAULT_URI must be an Azure Key Vault URI."
        )

    shared_uri = environ.get("KEY_VAULT_URI", "").strip()
    shared_hostname = urlparse(shared_uri).hostname if shared_uri else None
    if shared_hostname and hmac.compare_digest(
        parsed.hostname.lower(),
        shared_hostname.lower(),
    ):
        raise ValueError(
            "Hosted continuity requires a dedicated UI BFF Key Vault; the "
            "shared workload Key Vault is not permitted."
        )
    return vault_uri


def capability_secret_scope(vault_uri: str) -> str:
    vault_name = urlparse(vault_uri).hostname.split(".", 1)[0]
    vault_id = _run_az(
        [
            "keyvault",
            "show",
            "--name",
            vault_name,
            "--query",
            "id",
            "--output",
            "tsv",
        ]
    )
    return f"{vault_id.rstrip('/')}/secrets/{CAPABILITY_SECRET_NAME}"


def ensure_frontend_capability_secret_access(
    frontend_principal_id: str,
    secret_scope: str,
    *,
    hosted_agent_principal_id: str = "",
) -> bool:
    assignments = _role_assignments(
        frontend_principal_id,
        secret_scope,
        include_inherited=True,
    )
    has_approved_assignment = False
    for assignment in assignments:
        role_id = str(assignment.get("roleDefinitionId") or "")
        if not role_id or not _role_grants_data_action(
            role_id,
            KEY_VAULT_SECRET_GET_DATA_ACTION,
        ):
            continue
        if _assignment_has_role(
            assignment,
            KEY_VAULT_SECRETS_USER_ROLE_ID,
        ) and _same_scope(
            assignment.get("scope"),
            secret_scope,
        ) and _is_direct_service_principal_assignment(
            assignment,
            frontend_principal_id,
        ):
            has_approved_assignment = True
            continue
        raise RuntimeError(
            "The UI BFF capability secret permission must use Key Vault "
            "Secrets User at the individual secret scope."
        )

    if hosted_agent_principal_id:
        for assignment in _role_assignments(
            hosted_agent_principal_id,
            secret_scope,
            include_inherited=True,
        ):
            role_id = str(assignment.get("roleDefinitionId") or "")
            if role_id and _role_grants_data_action(
                role_id,
                KEY_VAULT_SECRET_GET_DATA_ACTION,
            ):
                raise RuntimeError(
                    "The hosted container identity must not have effective "
                    "access to the capability secret."
                )
    if has_approved_assignment:
        return False
    _run_az(
        [
            "role",
            "assignment",
            "create",
            "--assignee-object-id",
            frontend_principal_id,
            "--assignee-principal-type",
            "ServicePrincipal",
            "--role",
            KEY_VAULT_SECRETS_USER_ROLE_ID,
            "--scope",
            secret_scope,
            "--output",
            "none",
        ],
        required=False,
    )
    if not any(
        _assignment_has_role(assignment, KEY_VAULT_SECRETS_USER_ROLE_ID)
        and _same_scope(assignment.get("scope"), secret_scope)
        and _is_direct_service_principal_assignment(
            assignment,
            frontend_principal_id,
        )
        for assignment in _role_assignments(
            frontend_principal_id,
            secret_scope,
            include_inherited=True,
        )
    ):
        raise RuntimeError("Failed to verify UI BFF capability secret access.")
    return True


def get_configuration_setting_or_none(app_config_client: Any, key: str) -> Any:
    try:
        return app_config_client.get_configuration_setting(key=key, label=LABEL)
    except ResourceNotFoundError:
        return None


def seed_continuity_settings(
    app_config_client: Any,
    environ: Mapping[str, str] = os.environ,
    *,
    excluded_keys: frozenset[str] = frozenset(),
) -> None:
    """Seed missing safe defaults while preserving explicit operator values."""
    for key, default in DEFAULT_SETTINGS.items():
        if key in excluded_keys:
            continue
        if key in environ:
            value = environ[key]
        elif get_configuration_setting_or_none(app_config_client, key) is None:
            value = default
        else:
            continue
        app_config_client.set_configuration_setting(
            ConfigurationSetting(
                key=key,
                label=LABEL,
                value=value,
                content_type="text/plain",
            )
        )


def set_continuity_enabled(app_config_client: Any, enabled: bool) -> None:
    _set_boolean_setting(app_config_client, "HOSTED_CONTINUITY_ENABLED", enabled)


def set_owner_binding_validated(app_config_client: Any, validated: bool) -> None:
    _set_boolean_setting(
        app_config_client,
        "HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED",
        validated,
    )


def _set_boolean_setting(
    app_config_client: Any,
    key: str,
    value: bool,
) -> None:
    app_config_client.set_configuration_setting(
        ConfigurationSetting(
            key=key,
            label=LABEL,
            value=str(value).lower(),
            content_type="text/plain",
        )
    )


def effective_continuity_values(
    app_config_client: Any,
    environ: Mapping[str, str] = os.environ,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, default in DEFAULT_SETTINGS.items():
        if key in environ:
            values[key] = environ[key]
            continue
        setting = get_configuration_setting_or_none(app_config_client, key)
        values[key] = default if setting is None else str(setting.value)
    return values


def apply_capability_key_reference(
    app_config_client: Any,
    secret_client: Any,
    vault_uri: str,
    key_id: str,
) -> str:
    current = get_configuration_setting_or_none(
        app_config_client,
        CAPABILITY_CONFIG_KEY,
    )
    desired_reference = key_vault_reference(vault_uri)
    if current is not None:
        if not (current.content_type or "").startswith(
            "application/vnd.microsoft.appconfig.keyvaultref+json"
        ):
            raise ValueError(
                f"{CAPABILITY_CONFIG_KEY} must be a Key Vault reference; "
                "plaintext capability keys are prohibited."
            )
        if not _same_key_vault_reference(current.value, desired_reference):
            raise ValueError(
                f"{CAPABILITY_CONFIG_KEY} must reference {CAPABILITY_SECRET_NAME} "
                "in the configured UI BFF Key Vault."
            )

    action = ensure_capability_secret(secret_client, key_id)
    if current is None:
        app_config_client.set_configuration_setting(
            ConfigurationSetting(
                key=CAPABILITY_CONFIG_KEY,
                label=LABEL,
                value=desired_reference,
                content_type=KEY_VAULT_REFERENCE_CONTENT_TYPE,
            )
        )
    return action


def publish_capability_key_reference(
    app_config_client: Any,
    vault_uri: str,
) -> None:
    current = get_configuration_setting_or_none(
        app_config_client,
        CAPABILITY_CONFIG_KEY,
    )
    desired_reference = key_vault_reference(vault_uri)
    if current is not None and (
        not (current.content_type or "").startswith(
            "application/vnd.microsoft.appconfig.keyvaultref+json"
        )
        or not _same_key_vault_reference(current.value, desired_reference)
    ):
        raise ValueError(
            f"{CAPABILITY_CONFIG_KEY} must remain a Key Vault reference to "
            f"{CAPABILITY_SECRET_NAME} in the dedicated UI BFF vault."
        )
    if current is None:
        app_config_client.set_configuration_setting(
            ConfigurationSetting(
                key=CAPABILITY_CONFIG_KEY,
                label=LABEL,
                value=desired_reference,
                content_type=KEY_VAULT_REFERENCE_CONTENT_TYPE,
            )
        )


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
        raise RuntimeError(
            f"Azure CLI command failed: az {' '.join(arguments)}: {detail}"
        )
    return output


def validate_foundry_agent_consumer_role(role_definition: Mapping[str, Any]) -> None:
    permissions = role_definition.get("permissions") or []
    if len(permissions) != 1:
        raise RuntimeError("Foundry Agent Consumer role has an unexpected permission set.")
    permission = permissions[0]
    expected = {FOUNDRY_AGENT_INTERACT_DATA_ACTION.lower()}
    actual = {str(item).lower() for item in permission.get("dataActions") or []}
    if (
        role_definition.get("name") != FOUNDRY_AGENT_CONSUMER_ROLE_ID
        or role_definition.get("roleName") != FOUNDRY_AGENT_CONSUMER_ROLE_NAME
        or role_definition.get("roleType") != "BuiltInRole"
        or permission.get("actions")
        or permission.get("notActions")
        or permission.get("notDataActions")
        or actual != expected
    ):
        raise RuntimeError(
            "The live Foundry Agent Consumer role definition no longer matches "
            "the reviewed least-privilege endpoint interaction contract."
        )


def verify_live_foundry_agent_consumer_role() -> None:
    result = json.loads(
        _run_az(
            [
                "role",
                "definition",
                "list",
                "--name",
                FOUNDRY_AGENT_CONSUMER_ROLE_ID,
                "--output",
                "json",
            ]
        )
    )
    if len(result) != 1:
        raise RuntimeError("Foundry Agent Consumer built-in role was not found uniquely.")
    validate_foundry_agent_consumer_role(result[0])


def hosted_agent_scope(project_resource_id: str, agent_name: str) -> str:
    scope = f"{project_resource_id.rstrip('/')}/agents/{agent_name.strip()}"
    if not AGENT_SCOPE_PATTERN.fullmatch(scope):
        raise ValueError(
            "The Foundry hosted agent scope must identify exactly one agent "
            "under a Microsoft.CognitiveServices account project."
        )
    return scope


def foundry_role_assignable_scope(project_resource_id: str) -> str:
    marker = "/providers/"
    normalized = project_resource_id.rstrip("/")
    position = normalized.lower().find(marker)
    if position <= 0 or "/projects/" not in normalized.lower():
        raise ValueError(
            "AI_FOUNDRY_PROJECT_RESOURCE_ID must identify a Foundry project."
        )
    return normalized[:position]


def validate_user_identity_impersonation_role(
    role_definition: Mapping[str, Any],
    assignable_scope: str,
    allowed_role_names: tuple[str, ...] = (
        USER_IDENTITY_IMPERSONATION_ROLE_NAME,
    ),
) -> None:
    permissions = role_definition.get("permissions") or []
    permission = permissions[0] if len(permissions) == 1 else {}
    data_actions = {
        str(item).lower() for item in permission.get("dataActions") or []
    }
    assignable_scopes = {
        str(item).rstrip("/").lower()
        for item in role_definition.get("assignableScopes") or []
    }
    if (
        role_definition.get("name") != USER_IDENTITY_IMPERSONATION_ROLE_ID
        or role_definition.get("roleName") not in allowed_role_names
        or role_definition.get("roleType") != "CustomRole"
        or len(permissions) != 1
        or permission.get("actions")
        or permission.get("notActions")
        or permission.get("notDataActions")
        or data_actions
        != {USER_IDENTITY_IMPERSONATION_DATA_ACTION.lower()}
        or assignable_scopes != {assignable_scope.rstrip("/").lower()}
    ):
        raise RuntimeError(
            "The Agent Landing Zone user-identity impersonation role must have no Actions "
            "and exactly the reviewed UserIdentityImpersonation DataAction."
        )


def ensure_user_identity_impersonation_role(
    project_resource_id: str,
) -> bool:
    assignable_scope = foundry_role_assignable_scope(project_resource_id)
    result = json.loads(
        _run_az(
            [
                "role",
                "definition",
                "list",
                "--name",
                USER_IDENTITY_IMPERSONATION_ROLE_ID,
                "--output",
                "json",
            ],
            required=False,
        )
        or "[]"
    )
    if result:
        if len(result) != 1:
            raise RuntimeError(
                "The Agent Landing Zone user-identity impersonation role was not found uniquely."
            )
        existing = result[0]
        if existing.get("roleName") == USER_IDENTITY_IMPERSONATION_ROLE_NAME:
            validate_user_identity_impersonation_role(existing, assignable_scope)
            return False
        validate_user_identity_impersonation_role(
            existing,
            assignable_scope,
            LEGACY_USER_IDENTITY_IMPERSONATION_ROLE_NAMES,
        )
        operation = "update"
    else:
        operation = "create"

    definition = {
        "Name": USER_IDENTITY_IMPERSONATION_ROLE_NAME,
        "Id": USER_IDENTITY_IMPERSONATION_ROLE_ID,
        "IsCustom": True,
        "Description": (
            "Allows the Agent Landing Zone UI BFF to assert a server-derived hosted-agent "
            "user identity. Assign only at an individual hosted-agent scope."
        ),
        "Actions": [],
        "NotActions": [],
        "DataActions": [USER_IDENTITY_IMPERSONATION_DATA_ACTION],
        "NotDataActions": [],
        "AssignableScopes": [assignable_scope],
    }
    _run_az(
        [
            "role",
            "definition",
            operation,
            "--role-definition",
            json.dumps(definition, separators=(",", ":")),
            "--output",
            "none",
        ],
        required=False,
    )
    created = json.loads(
        _run_az(
            [
                "role",
                "definition",
                "list",
                "--name",
                USER_IDENTITY_IMPERSONATION_ROLE_ID,
                "--output",
                "json",
            ]
        )
    )
    if len(created) != 1:
        raise RuntimeError(
            "Failed to verify the Agent Landing Zone user-identity impersonation role."
        )
    validate_user_identity_impersonation_role(created[0], assignable_scope)
    return True


@dataclass(frozen=True)
class HostedAgentContract:
    principal_id: str
    routed_version: str


def verify_live_hosted_agent_contract(
    project_endpoint: str,
    agent_name: str,
) -> HostedAgentContract:
    endpoint = project_endpoint.strip().rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("AI_FOUNDRY_PROJECT_ENDPOINT must be an HTTPS endpoint.")
    agent_url = (
        f"{endpoint}/agents/{quote(agent_name.strip(), safe='')}"
        f"?api-version={FOUNDRY_DATA_PLANE_API_VERSION}"
    )
    agent = json.loads(
        _run_az(
            [
                "rest",
                "--method",
                "GET",
                "--url",
                agent_url,
                "--resource",
                FOUNDRY_TOKEN_AUDIENCE,
                "--output",
                "json",
            ]
        )
    )
    identity = agent.get("instance_identity") or {}
    principal_id = str(identity.get("principal_id") or "").strip()
    endpoint_config = agent.get("agent_endpoint") or {}
    protocol_config = endpoint_config.get("protocol_configuration") or {}
    selector = endpoint_config.get("version_selector") or {}
    rules = selector.get("version_selection_rules") or []
    if (
        not principal_id
        or not isinstance(protocol_config, Mapping)
        or "responses" not in protocol_config
        or len(rules) != 1
        or str(rules[0].get("type") or "").lower() != "fixedratio"
        or int(rules[0].get("traffic_percentage") or 0) != 100
    ):
        raise RuntimeError(
            "The live hosted-agent endpoint does not expose one fully routed "
            "Responses protocol version."
        )
    routed_version = str(rules[0].get("agent_version") or "").strip()
    if not routed_version:
        raise RuntimeError("The live hosted-agent routed version is missing.")
    version_url = (
        f"{endpoint}/agents/{quote(agent_name.strip(), safe='')}/versions/"
        f"{quote(routed_version, safe='')}"
        f"?api-version={FOUNDRY_DATA_PLANE_API_VERSION}"
    )
    version = json.loads(
        _run_az(
            [
                "rest",
                "--method",
                "GET",
                "--url",
                version_url,
                "--resource",
                FOUNDRY_TOKEN_AUDIENCE,
                "--output",
                "json",
            ]
        )
    )
    definition = version.get("definition") or {}
    protocol_versions = definition.get("protocol_versions") or []
    responses = [
        item
        for item in protocol_versions
        if str(item.get("protocol") or "").lower() == "responses"
    ]
    if (
        len(responses) != 1
        or str(responses[0].get("version") or "")
        != RESPONSES_PROTOCOL_VERSION
    ):
        raise RuntimeError(
            "The routed hosted agent must declare Responses protocol version "
            f"{RESPONSES_PROTOCOL_VERSION} exactly."
        )
    return HostedAgentContract(
        principal_id=principal_id,
        routed_version=routed_version,
    )


def _role_assignments(
    principal_id: str,
    scope: str,
    *,
    include_inherited: bool = False,
) -> list[Mapping[str, Any]]:
    arguments = [
        "role",
        "assignment",
        "list",
        "--assignee",
        principal_id,
        "--scope",
        scope,
    ]
    if include_inherited:
        arguments.extend(["--include-inherited", "--include-groups"])
    arguments.extend(["--output", "json"])
    output = _run_az(arguments)
    return json.loads(output)


def _all_direct_role_assignments(principal_id: str) -> list[Mapping[str, Any]]:
    return json.loads(
        _run_az(
            [
                "role",
                "assignment",
                "list",
                "--assignee",
                principal_id,
                "--all",
                "--output",
                "json",
            ]
        )
    )


def _delete_assignment(assignment: Mapping[str, Any]) -> None:
    assignment_id = str(assignment.get("id") or "").strip()
    if not assignment_id:
        raise RuntimeError("Cannot remove an RBAC assignment without its resource ID.")
    _run_az(
        [
            "role",
            "assignment",
            "delete",
            "--ids",
            assignment_id,
            "--output",
            "none",
        ],
        required=False,
    )


def _assignment_has_role(assignment: Mapping[str, Any], role_id: str) -> bool:
    return (
        str(assignment.get("roleDefinitionId") or "")
        .rstrip("/")
        .lower()
        .endswith(f"/{role_id.lower()}")
    )


def _same_scope(left: Any, right: str) -> bool:
    return str(left or "").rstrip("/").lower() == right.rstrip("/").lower()


def _is_direct_service_principal_assignment(
    assignment: Mapping[str, Any],
    principal_id: str,
) -> bool:
    return (
        hmac.compare_digest(
            str(assignment.get("principalId") or "").lower(),
            principal_id.lower(),
        )
        and str(assignment.get("principalType") or "").lower()
        == "serviceprincipal"
    )


def _role_grants_data_action(role_id: str, required_action: str) -> bool:
    normalized_role = role_id.rstrip("/").lower()
    required = required_action.lower()
    reviewed_roles = {
        FOUNDRY_AGENT_CONSUMER_ROLE_ID: FOUNDRY_AGENT_INTERACT_DATA_ACTION,
        USER_IDENTITY_IMPERSONATION_ROLE_ID: (
            USER_IDENTITY_IMPERSONATION_DATA_ACTION
        ),
        KEY_VAULT_SECRETS_USER_ROLE_ID: KEY_VAULT_SECRET_GET_DATA_ACTION,
    }
    for reviewed_role_id, reviewed_action in reviewed_roles.items():
        if normalized_role.endswith(f"/{reviewed_role_id}"):
            return required == reviewed_action.lower()
    definitions = json.loads(
        _run_az(
            [
                "role",
                "definition",
                "list",
                "--name",
                role_id.rsplit("/", 1)[-1],
                "--output",
                "json",
            ]
        )
    )
    if len(definitions) != 1:
        raise RuntimeError(f"Role definition {role_id!r} was not found uniquely.")
    for permission in definitions[0].get("permissions") or []:
        allowed = any(
            fnmatch.fnmatchcase(required, str(pattern).lower())
            for pattern in permission.get("dataActions") or []
        )
        denied = any(
            fnmatch.fnmatchcase(required, str(pattern).lower())
            for pattern in permission.get("notDataActions") or []
        )
        if allowed and not denied:
            return True
    return False


def _is_approved_continuity_assignment(
    assignment: Mapping[str, Any],
    principal_id: str,
    agent_scope: str,
) -> bool:
    approved_roles = {
        FOUNDRY_AGENT_CONSUMER_ROLE_ID,
        USER_IDENTITY_IMPERSONATION_ROLE_ID,
    }
    return (
        any(_assignment_has_role(assignment, role_id) for role_id in approved_roles)
        and _same_scope(assignment.get("scope"), agent_scope)
        and _is_direct_service_principal_assignment(assignment, principal_id)
    )


def _reject_broad_or_unapproved_continuity_access(
    principal_id: str,
    agent_scope: str,
    *,
    identity_name: str,
) -> list[Mapping[str, Any]]:
    assignments = _role_assignments(
        principal_id,
        agent_scope,
        include_inherited=True,
    )
    for assignment in assignments:
        role_name = str(assignment.get("roleDefinitionName") or "")
        if role_name in {"Foundry User", "Project Runtime User"}:
            raise RuntimeError(
                f"{identity_name} must not receive the broad {role_name} role."
            )
        role_id = str(assignment.get("roleDefinitionId") or "")
        grants_continuity = role_id and any(
            _role_grants_data_action(role_id, action)
            for action in (
                FOUNDRY_AGENT_INTERACT_DATA_ACTION,
                USER_IDENTITY_IMPERSONATION_DATA_ACTION,
            )
        )
        if not grants_continuity:
            continue
        if (
            identity_name == "UI BFF"
            and _is_approved_continuity_assignment(
                assignment,
                principal_id,
                agent_scope,
            )
        ):
            continue
        raise RuntimeError(
            f"{identity_name} has unapproved, inherited, group-derived, or "
            "broader Foundry continuity access."
        )
    return assignments


def _reconcile_hosted_container_continuity_access(
    principal_id: str,
    agent_scope: str,
) -> None:
    assignments = _role_assignments(
        principal_id,
        agent_scope,
        include_inherited=True,
    )
    for assignment in assignments:
        role_id = str(assignment.get("roleDefinitionId") or "")
        if not role_id or not any(
            _role_grants_data_action(role_id, action)
            for action in (
                FOUNDRY_AGENT_INTERACT_DATA_ACTION,
                USER_IDENTITY_IMPERSONATION_DATA_ACTION,
            )
        ):
            continue
        removable = (
            any(
                _assignment_has_role(assignment, approved_role)
                for approved_role in (
                    FOUNDRY_AGENT_CONSUMER_ROLE_ID,
                    USER_IDENTITY_IMPERSONATION_ROLE_ID,
                )
            )
            and _same_scope(assignment.get("scope"), agent_scope)
            and _is_direct_service_principal_assignment(
                assignment,
                principal_id,
            )
        )
        if not removable:
            raise RuntimeError(
                "hosted container identity has inherited, group-derived, custom, "
                "or broader Foundry continuity access."
            )
        _delete_assignment(assignment)
    _reject_broad_or_unapproved_continuity_access(
        principal_id,
        agent_scope,
        identity_name="hosted container identity",
    )


def ensure_frontend_continuity_assignments(
    frontend_principal_id: str,
    agent_scope: str,
    project_resource_id: str,
    *,
    hosted_agent_principal_id: str,
) -> dict[str, str]:
    """Assign the two approved roles directly to the UI BFF at one agent."""
    verify_live_foundry_agent_consumer_role()
    ensure_user_identity_impersonation_role(project_resource_id)
    if hmac.compare_digest(
        frontend_principal_id.lower(),
        hosted_agent_principal_id.lower(),
    ):
        raise RuntimeError(
            "The UI BFF and hosted container must not share an identity."
        )
    _reconcile_hosted_container_continuity_access(
        hosted_agent_principal_id,
        agent_scope,
    )
    frontend_assignments = _reject_broad_or_unapproved_continuity_access(
        frontend_principal_id,
        agent_scope,
        identity_name="UI BFF",
    )
    role_ids = (
        FOUNDRY_AGENT_CONSUMER_ROLE_ID,
        USER_IDENTITY_IMPERSONATION_ROLE_ID,
    )
    actions: dict[str, str] = {}
    for role_id in role_ids:
        direct = any(
            _assignment_has_role(assignment, role_id)
            and _is_approved_continuity_assignment(
                assignment,
                frontend_principal_id,
                agent_scope,
            )
            for assignment in frontend_assignments
        )
        actions[role_id] = "reused" if direct else "created"
        if direct:
            continue
        _run_az(
            [
                "role",
                "assignment",
                "create",
                "--assignee-object-id",
                frontend_principal_id,
                "--assignee-principal-type",
                "ServicePrincipal",
                "--role",
                role_id,
                "--scope",
                agent_scope,
                "--output",
                "none",
            ],
            required=False,
        )

    verified = _reject_broad_or_unapproved_continuity_access(
        frontend_principal_id,
        agent_scope,
        identity_name="UI BFF",
    )
    for role_id in role_ids:
        if not any(
            _assignment_has_role(assignment, role_id)
            and _is_approved_continuity_assignment(
                assignment,
                frontend_principal_id,
                agent_scope,
            )
            for assignment in verified
        ):
            raise RuntimeError(
                f"Failed to verify direct UI BFF role {role_id} at agent scope."
            )
    return actions


def _app_config_value(app_config_client: Any, key: str) -> str:
    setting = get_configuration_setting_or_none(app_config_client, key)
    return "" if setting is None else str(setting.value or "").strip()


def _application_resource_group(
    app_config_client: Any, environ: Mapping[str, str],
) -> str:
    context = {
        key: environ.get(key) or _app_config_value(app_config_client, key)
        for key in ("AZURE_RESOURCE_GROUP", "AZURE_APP_RESOURCE_GROUP")
    }
    return resource_group_for(context, "application")


@dataclass(frozen=True)
class ContinuityAccess:
    frontend_principal_id: str
    hosted_agent_principal_id: str
    agent_scope: str
    routed_version: str
    role_actions: Mapping[str, str]


def configure_frontend_roles(
    app_config_client: Any,
    environ: Mapping[str, str] = os.environ,
) -> ContinuityAccess:
    project_resource_id = (
        environ.get("AI_FOUNDRY_PROJECT_RESOURCE_ID")
        or _app_config_value(app_config_client, "AI_FOUNDRY_PROJECT_RESOURCE_ID")
    ).strip()
    resource_group = _application_resource_group(app_config_client, environ)
    resource_token = (
        environ.get("RESOURCE_TOKEN")
        or _app_config_value(app_config_client, "RESOURCE_TOKEN")
    ).strip()
    frontend_name = (
        environ.get("FRONTEND_APP_NAME")
        or _app_config_value(app_config_client, "FRONTEND_APP_NAME")
        or (f"ca-{resource_token}-frontend" if resource_token else "")
    ).strip()
    agent_name = (environ.get("HOSTED_AGENT_NAME") or "agent-app-orchestrator").strip()
    project_endpoint = (
        environ.get("AI_FOUNDRY_PROJECT_ENDPOINT")
        or _app_config_value(app_config_client, "AI_FOUNDRY_PROJECT_ENDPOINT")
    ).strip()
    if (
        not project_resource_id
        or not project_endpoint
        or not resource_group
        or not frontend_name
    ):
        raise RuntimeError(
            "AI_FOUNDRY_PROJECT_RESOURCE_ID, AI_FOUNDRY_PROJECT_ENDPOINT, "
            "AZURE_RESOURCE_GROUP (with optional AZURE_APP_RESOURCE_GROUP), "
            "and FRONTEND_APP_NAME are required for "
            "hosted continuity RBAC."
        )

    frontend_principal_id = _run_az(
        [
            "containerapp",
            "show",
            "--resource-group",
            resource_group,
            "--name",
            frontend_name,
            "--query",
            "identity.principalId",
            "--output",
            "tsv",
        ]
    )
    scope = hosted_agent_scope(project_resource_id, agent_name)
    contract = verify_live_hosted_agent_contract(
        project_endpoint,
        agent_name,
    )
    role_actions = ensure_frontend_continuity_assignments(
        frontend_principal_id=frontend_principal_id,
        agent_scope=scope,
        project_resource_id=project_resource_id,
        hosted_agent_principal_id=contract.principal_id,
    )
    return ContinuityAccess(
        frontend_principal_id=frontend_principal_id,
        hosted_agent_principal_id=contract.principal_id,
        agent_scope=scope,
        routed_version=contract.routed_version,
        role_actions=role_actions,
    )


def reconcile_disabled_continuity(
    app_config_client: Any,
    environ: Mapping[str, str] = os.environ,
) -> None:
    """Remove continuity-specific access and indirection while retaining key history."""
    resource_group = _application_resource_group(app_config_client, environ)
    frontend_name = (
        environ.get("FRONTEND_APP_NAME")
        or _app_config_value(app_config_client, "FRONTEND_APP_NAME")
    ).strip()
    capability_reference = get_configuration_setting_or_none(
        app_config_client,
        CAPABILITY_CONFIG_KEY,
    )
    if not resource_group or not frontend_name:
        raise RuntimeError(
            "An application resource group and FRONTEND_APP_NAME are required to "
            "reconcile disabled hosted continuity."
        )
    frontend_principal_id = _run_az(
        [
            "containerapp",
            "show",
            "--resource-group",
            resource_group,
            "--name",
            frontend_name,
            "--query",
            "identity.principalId",
            "--output",
            "tsv",
        ],
        required=False,
    )
    if not frontend_principal_id:
        if capability_reference is not None:
            raise RuntimeError(
                "The frontend managed identity is unavailable while a hosted "
                "conversation capability reference still exists; refusing "
                "incomplete continuity cleanup."
            )
        return
    assignments = _all_direct_role_assignments(frontend_principal_id)

    project_resource_id = (
        environ.get("AI_FOUNDRY_PROJECT_RESOURCE_ID")
        or _app_config_value(app_config_client, "AI_FOUNDRY_PROJECT_RESOURCE_ID")
    ).strip()
    if project_resource_id:
        agent_name = (
            environ.get("HOSTED_AGENT_NAME") or "agent-app-orchestrator"
        ).strip()
        agent_scope = hosted_agent_scope(project_resource_id, agent_name)
        for assignment in assignments:
            if (
                _assignment_has_role(
                    assignment,
                    FOUNDRY_AGENT_CONSUMER_ROLE_ID,
                )
                or _assignment_has_role(
                    assignment,
                    USER_IDENTITY_IMPERSONATION_ROLE_ID,
                )
            ) and _same_scope(assignment.get("scope"), agent_scope):
                _delete_assignment(assignment)

    if capability_reference is None:
        return
    _remove_capability_fallback(
        app_config_client,
        capability_reference,
        frontend_principal_id,
        hosted_agent_principal_id="",
    )


def _capability_secret_scope_from_reference(
    capability_reference: Any,
) -> str:
    if not (capability_reference.content_type or "").startswith(
        "application/vnd.microsoft.appconfig.keyvaultref+json"
    ):
        raise ValueError(
            f"{CAPABILITY_CONFIG_KEY} is plaintext or malformed; refusing cleanup."
        )
    reference = json.loads(capability_reference.value)
    secret_uri = str(reference.get("uri") or "")
    expected_suffix = f"/secrets/{CAPABILITY_SECRET_NAME}"
    if not secret_uri.endswith(expected_suffix):
        raise ValueError(
            f"{CAPABILITY_CONFIG_KEY} does not reference the capability secret."
        )
    vault_uri = secret_uri[: -len(expected_suffix)].rstrip("/") + "/"
    return capability_secret_scope(vault_uri)


def _remove_capability_fallback(
    app_config_client: Any,
    capability_reference: Any,
    frontend_principal_id: str,
    *,
    hosted_agent_principal_id: str,
) -> None:
    secret_scope = _capability_secret_scope_from_reference(capability_reference)
    frontend_assignments = _role_assignments(
        frontend_principal_id,
        secret_scope,
        include_inherited=True,
    )
    for assignment in frontend_assignments:
        role_id = str(assignment.get("roleDefinitionId") or "")
        if not role_id or not _role_grants_data_action(
            role_id,
            KEY_VAULT_SECRET_GET_DATA_ACTION,
        ):
            continue
        if (
            _assignment_has_role(
                assignment,
                KEY_VAULT_SECRETS_USER_ROLE_ID,
            )
            and _same_scope(assignment.get("scope"), secret_scope)
            and _is_direct_service_principal_assignment(
                assignment,
                frontend_principal_id,
            )
        ):
            _delete_assignment(assignment)
            continue
        raise RuntimeError(
            "UI BFF has inherited, group-derived, custom, or broader capability "
            "secret access that cannot be safely reconciled."
        )
    if hosted_agent_principal_id:
        for assignment in _role_assignments(
            hosted_agent_principal_id,
            secret_scope,
            include_inherited=True,
        ):
            role_id = str(assignment.get("roleDefinitionId") or "")
            if role_id and _role_grants_data_action(
                role_id,
                KEY_VAULT_SECRET_GET_DATA_ACTION,
            ):
                removable = (
                    _assignment_has_role(
                        assignment,
                        KEY_VAULT_SECRETS_USER_ROLE_ID,
                    )
                    and _same_scope(assignment.get("scope"), secret_scope)
                    and _is_direct_service_principal_assignment(
                        assignment,
                        hosted_agent_principal_id,
                    )
                )
                if not removable:
                    raise RuntimeError(
                        "Hosted container identity has inherited, group-derived, "
                        "custom, or broader capability secret access."
                    )
                _delete_assignment(assignment)
        for assignment in _role_assignments(
            hosted_agent_principal_id,
            secret_scope,
            include_inherited=True,
        ):
            role_id = str(assignment.get("roleDefinitionId") or "")
            if role_id and _role_grants_data_action(
                role_id,
                KEY_VAULT_SECRET_GET_DATA_ACTION,
            ):
                raise RuntimeError(
                    "Failed to remove capability secret access from the hosted "
                    "container identity."
                )
    app_config_client.delete_configuration_setting(
        key=CAPABILITY_CONFIG_KEY,
        label=LABEL,
    )


def reconcile_delegated_binding(
    app_config_client: Any,
    access: ContinuityAccess,
) -> None:
    """Remove active capability indirection when delegated ownership is selected."""
    capability_reference = get_configuration_setting_or_none(
        app_config_client,
        CAPABILITY_CONFIG_KEY,
    )
    if capability_reference is None:
        return
    _remove_capability_fallback(
        app_config_client,
        capability_reference,
        access.frontend_principal_id,
        hosted_agent_principal_id=access.hosted_agent_principal_id,
    )


def main(*, activate: bool = False) -> None:
    app_config_endpoint = os.environ.get("APP_CONFIG_ENDPOINT", "").strip()
    if not app_config_endpoint:
        raise RuntimeError("APP_CONFIG_ENDPOINT is required for continuity setup.")

    credential = create_credential()
    app_config_client = AzureAppConfigurationClient(app_config_endpoint, credential)
    values = effective_continuity_values(app_config_client)
    deploy_key_vault = not (
        os.environ.get("DEPLOY_KEY_VAULT", "true").strip().lower()
        in {"0", "false", "no", "off"}
    )
    try:
        settings = validate_continuity_settings(
            values,
            deployment_topology=(
                os.environ.get("DEPLOYMENT_TOPOLOGY")
                or _app_config_value(app_config_client, "DEPLOYMENT_TOPOLOGY")
            ).strip(),
            chat_backend=(
                os.environ.get("CHAT_BACKEND")
                or _app_config_value(app_config_client, "CHAT_BACKEND")
            ).strip(),
            deploy_key_vault=deploy_key_vault,
        )
    except (KeyError, ValueError):
        set_continuity_enabled(app_config_client, False)
        set_owner_binding_validated(app_config_client, False)
        raise

    if not settings.enabled:
        set_continuity_enabled(app_config_client, False)
        set_owner_binding_validated(app_config_client, False)
        reconcile_disabled_continuity(app_config_client)
        seed_continuity_settings(
            app_config_client,
            excluded_keys=frozenset(
                {
                    "HOSTED_CONTINUITY_ENABLED",
                    "HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED",
                }
            ),
        )
        logging.info(
            "Hosted continuity remains disabled with the 503 contract; "
            "continuity credentials and data-plane role assignments were removed."
        )
        return

    set_continuity_enabled(app_config_client, False)
    set_owner_binding_validated(app_config_client, False)
    if not activate:
        seed_continuity_settings(
            app_config_client,
            excluded_keys=frozenset(
                {
                    "HOSTED_CONTINUITY_ENABLED",
                    "HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED",
                }
            ),
        )
        logging.info(
            "Hosted continuity activation deferred until the hosted agent "
            "deployment completes."
        )
        return

    access = configure_frontend_roles(app_config_client)
    capability_action = "disabled"
    if settings.owner_binding == "delegated":
        reconcile_delegated_binding(app_config_client, access)
    else:
        vault_uri = resolve_capability_vault_uri()
        secret_scope = capability_secret_scope(vault_uri)
        secret_client = SecretClient(vault_url=vault_uri, credential=credential)
        secret_action = ensure_capability_secret(secret_client, settings.key_id)
        secret_role_action = (
            "created"
            if ensure_frontend_capability_secret_access(
                access.frontend_principal_id,
                secret_scope,
                hosted_agent_principal_id=access.hosted_agent_principal_id,
            )
            else "reused"
        )
        publish_capability_key_reference(app_config_client, vault_uri)
        capability_action = (
            f"secret {secret_action}, UI BFF secret role {secret_role_action}"
        )

    seed_continuity_settings(
        app_config_client,
        excluded_keys=frozenset(
            {
                "HOSTED_CONTINUITY_ENABLED",
                "HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED",
            }
        ),
    )
    set_owner_binding_validated(app_config_client, True)
    set_continuity_enabled(app_config_client, True)

    logging.info(
        "Hosted continuity enabled with binding=%s after Responses %s validation; "
        "agent scope=%s, consumer role=%s, impersonation role=%s, capability=%s.",
        settings.owner_binding,
        RESPONSES_PROTOCOL_VERSION,
        access.agent_scope,
        access.role_actions[FOUNDRY_AGENT_CONSUMER_ROLE_ID],
        access.role_actions[USER_IDENTITY_IMPERSONATION_ROLE_ID],
        capability_action,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Apply credentials and RBAC after the hosted agent exists.",
    )
    main(activate=parser.parse_args().activate)
