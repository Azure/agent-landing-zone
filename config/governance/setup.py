#!/usr/bin/env python3
"""Seed safe governance defaults and the audit pseudonymization key reference."""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import secrets
from collections.abc import Mapping
from typing import Any

from azure.appconfiguration import AzureAppConfigurationClient, ConfigurationSetting
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import (
    AzureCliCredential,
    ChainedTokenCredential,
    ManagedIdentityCredential,
)
from azure.keyvault.secrets import SecretClient
from config.deployment.setup_settings import load_setup_settings


LABEL = "agent-lz"
AUDIT_HMAC_CONFIG_KEY = "AUDIT_HMAC_KEY"
AUDIT_HMAC_SECRET_NAME = "AUDIT-HMAC-KEY"
KEY_VAULT_REFERENCE_CONTENT_TYPE = (
    "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8"
)

DEFAULT_SETTINGS: Mapping[str, str] = {
    "AUDIT_EVENTS_ENABLED": "false",
    "AUDIT_SENSITIVE_CONTENT_ENABLED": "false",
    "AUDIT_SENSITIVE_CONTENT_FIELDS": "",
    "AUDIT_ACTOR_PSEUDONYM_ENABLED": "false",
    "AUDIT_SOURCE_EVENT_LIMIT": "25",
    "AUDIT_HMAC_KEY_ID": "v1",
    "AUDIT_ADDITIONAL_REDACTED_KEYS": "",
    "INGESTION_PROVENANCE_ENABLED": "false",
    "INGESTION_REQUIRE_GOVERNANCE_METADATA": "false",
    "INGESTION_DEFAULT_CLASSIFICATION": "unclassified",
    "INGESTION_DEFAULT_RIGHT_TO_USE": "not_asserted",
}


def create_credential() -> ChainedTokenCredential:
    return ChainedTokenCredential(
        AzureCliCredential(process_timeout=30),
        ManagedIdentityCredential(process_timeout=30),
    )


def generate_audit_hmac_key() -> str:
    """Return a Base64URL encoding of exactly 256 random bits."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def _decode_audit_hmac_key(value: str) -> bytes:
    candidate = value.strip()
    if len(candidate) == 64:
        try:
            decoded = bytes.fromhex(candidate)
        except ValueError:
            decoded = b""
        if len(decoded) == 32:
            return decoded

    padded = candidate + ("=" * (-len(candidate) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        decoded = b""
    if len(decoded) != 32:
        raise ValueError(
            "The existing AUDIT-HMAC-KEY secret is not an encoding of exactly "
            "32 bytes. Rotate it explicitly before enabling audit events."
        )
    return decoded


def ensure_audit_hmac_secret(
    secret_client: Any,
    initial_value: str | None = None,
) -> bool:
    """Create the key once and return whether a new secret version was written."""
    try:
        current = secret_client.get_secret(AUDIT_HMAC_SECRET_NAME)
    except ResourceNotFoundError:
        value = initial_value or generate_audit_hmac_key()
        _decode_audit_hmac_key(value)
        secret_client.set_secret(
            AUDIT_HMAC_SECRET_NAME,
            value,
            content_type="application/octet-stream",
        )
        return True

    current_key = _decode_audit_hmac_key(current.value)
    if initial_value is not None:
        initial_key = _decode_audit_hmac_key(initial_value)
        if not hmac.compare_digest(current_key, initial_key):
            raise ValueError(
                "The existing AUDIT-HMAC-KEY does not match the operator-managed "
                "AUDIT_HMAC_KEY value. Resolve the conflict explicitly."
            )
    return False


def audit_hmac_key_uri(vault_uri: str) -> str:
    """URI-only AUDIT_HMAC_KEY_URI handoff; never resolve the secret value."""
    return f"{vault_uri.rstrip('/')}/secrets/{AUDIT_HMAC_SECRET_NAME}"


def key_vault_reference(vault_uri: str) -> str:
    return json.dumps({"uri": audit_hmac_key_uri(vault_uri)}, separators=(",", ":"))


def resolve_vault_uri(environ: Mapping[str, str] = os.environ) -> str:
    configured_uri = environ.get("KEY_VAULT_URI", "").strip()
    if configured_uri:
        return configured_uri.rstrip("/") + "/"

    vault_name = environ.get("KEY_VAULT_NAME", "").strip()
    if vault_name:
        return f"https://{vault_name}.vault.azure.net/"

    raise RuntimeError(
        "KEY_VAULT_URI or KEY_VAULT_NAME is required to provision the audit "
        "HMAC key reference."
    )


def seed_governance_settings(
    app_config_client: Any,
    environ: Mapping[str, str] = os.environ,
) -> None:
    """Seed missing defaults while preserving operator-managed values."""
    for key, default in DEFAULT_SETTINGS.items():
        if key in environ:
            value = environ[key]
        else:
            try:
                app_config_client.get_configuration_setting(key=key, label=LABEL)
            except ResourceNotFoundError:
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


def get_configuration_setting_or_none(app_config_client: Any, key: str) -> Any:
    try:
        return app_config_client.get_configuration_setting(key=key, label=LABEL)
    except ResourceNotFoundError:
        return None


def effective_setting(
    app_config_client: Any,
    key: str,
    default: str,
    environ: Mapping[str, str] = os.environ,
) -> str:
    if key in environ:
        return environ[key]
    setting = get_configuration_setting_or_none(app_config_client, key)
    return default if setting is None else str(setting.value)


def is_truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def apply_governance_configuration(
    app_config_client: Any,
    secret_client: Any,
    vault_uri: str,
    environ: Mapping[str, str] = os.environ,
) -> bool:
    """Apply plaintext defaults and a Key Vault reference without exposing the key."""
    seed_governance_settings(app_config_client, environ)
    current_setting = get_configuration_setting_or_none(
        app_config_client,
        AUDIT_HMAC_CONFIG_KEY,
    )
    desired_reference = key_vault_reference(vault_uri)

    if current_setting is not None and (
        current_setting.content_type or ""
    ).startswith("application/vnd.microsoft.appconfig.keyvaultref+json"):
        if current_setting.value == desired_reference:
            return ensure_audit_hmac_secret(secret_client)
        return False

    initial_value = None
    if current_setting is not None and current_setting.value:
        initial_value = str(current_setting.value)
        _decode_audit_hmac_key(initial_value)

    created = ensure_audit_hmac_secret(secret_client, initial_value)

    app_config_client.set_configuration_setting(
        ConfigurationSetting(
            key=AUDIT_HMAC_CONFIG_KEY,
            label=LABEL,
            value=desired_reference,
            content_type=KEY_VAULT_REFERENCE_CONTENT_TYPE,
        )
    )
    return created


def main() -> str | None:
    settings = load_setup_settings()
    # Governance owns only these operational settings, never resource aliases.
    intent = {
        key: str(settings[key]).lower() if isinstance(settings[key], bool) else str(settings[key])
        for key in DEFAULT_SETTINGS if key in settings
    }
    app_config_client = None
    credential = create_credential()
    if settings.get("APP_RUNTIME_CONFIGURATION_MODE") == "appConfig":
        endpoint = settings.get("APP_CONFIG_ENDPOINT")
        if not endpoint:
            raise RuntimeError("appConfig governance requires a verified APP_CONFIG_ENDPOINT.")
        app_config_client = AzureAppConfigurationClient(endpoint, credential)
    if not is_truthy(settings.get("DEPLOY_KEY_VAULT", True)):
        audit_enabled = (
            effective_setting(app_config_client, "AUDIT_EVENTS_ENABLED", "false", intent)
            if app_config_client is not None else intent.get("AUDIT_EVENTS_ENABLED", "false")
        )
        if is_truthy(audit_enabled):
            raise RuntimeError(
                "AUDIT_EVENTS_ENABLED cannot be true when Key Vault is disabled."
            )
        if app_config_client is not None:
            seed_governance_settings(app_config_client, intent)
        logging.info("Audit is disabled and no Key Vault is selected.")
        return

    vault_uri = resolve_vault_uri(settings)
    if settings.get("AUDIT_HMAC_KEY_URI", audit_hmac_key_uri(vault_uri)) != audit_hmac_key_uri(vault_uri):
        raise RuntimeError("AUDIT_HMAC_KEY_URI conflicts with the verified audit vault binding.")
    secret_client = SecretClient(vault_url=vault_uri, credential=credential)
    created = (
        apply_governance_configuration(app_config_client, secret_client, vault_uri, intent)
        if app_config_client is not None else ensure_audit_hmac_secret(secret_client)
    )

    action = "created" if created else "reused"
    logging.info(
        "Governance configuration applied: audit HMAC secret %s.",
        action,
    )
    # appConfig retains its existing owner-managed reference (which may point
    # elsewhere); only store-free setup hands off the exact key ensured above.
    return audit_hmac_key_uri(vault_uri) if app_config_client is None else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
