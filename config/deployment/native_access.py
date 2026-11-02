"""Feature-owned native grants, using existing scoped RBAC helpers.

No source provisioning, secret retrieval, SQL queries or runtime repair. Explicit
tool secret names belong to the operator/source configuration, not every app.
"""
from __future__ import annotations

import json
import re
from typing import Mapping
from urllib.parse import urlsplit

from config.appdefinition.roles import _ensure_rbac
from config.deployment.appconfig import _run_az
from config.deployment.context import bound_resource_id
from config.deployment.hosted_access import (
    KV_REFERENCE, Role, _endpoint, _setting, run_az,
)
from config.deployment.resource_groups import resource_group_for
from config.panel.setup import resolve_container_app_principal_id


def secret_names(environment: Mapping[str, str], keys: tuple[str, ...], *, run=run_az) -> tuple[str, ...]:
    endpoint = environment["APP_CONFIG_ENDPOINT"]
    names = []
    for key in keys:
        row = _setting(run, endpoint, key)
        if row is None:
            continue
        content_type = str(row.get("contentType", "")).split(";", 1)[0].lower()
        if content_type != KV_REFERENCE:
            # Ordinary nonsecret optional settings are not secret consumers.
            continue
        reference = json.loads(row["value"])
        if not isinstance(reference, dict):
            raise ValueError("Native Key Vault reference must be an object.")
        uri = _endpoint(reference.get("uri"), ".vault.azure.net", r"/secrets/[A-Za-z0-9-]{1,127}(?:/[A-Za-z0-9-]{1,127})?")
        vault_uri = _endpoint(environment.get("KEY_VAULT_URI"), ".vault.azure.net")
        if urlsplit(uri).hostname != urlsplit(vault_uri).hostname:
            raise ValueError("Native secret reference points outside the provisioned vault.")
        names.append(urlsplit(uri).path.split("/")[2])
    return tuple(dict.fromkeys(names))


def grant_secrets(environment: Mapping[str, str], principal: str, names: tuple[str, ...], *, run=_run_az) -> None:
    if not names:
        return
    vault_id = environment.get("KEY_VAULT_RESOURCE_ID", "")
    if not vault_id:
        # These are provisioned names/outputs, not discovered arbitrary vaults.
        vault_name = urlsplit(_endpoint(environment.get("KEY_VAULT_URI"), ".vault.azure.net")).hostname.split(".")[0]
        vault_id = (
            f"/subscriptions/{environment['AZURE_SUBSCRIPTION_ID']}"
            f"/resourceGroups/{resource_group_for(environment, 'application')}"
            f"/providers/Microsoft.KeyVault/vaults/{vault_name}"
        )
    bound_resource_id(vault_id, environment, "Microsoft.KeyVault/vaults", area="application")
    for name in names:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,127}", name):
            raise ValueError("Tool secret names must be explicit Key Vault secret names.")
    for name in dict.fromkeys(names):
        _ensure_rbac(principal, Role.SECRET.value, vault_id + "/secrets/" + name, run)


def tool_secret_names(environment: Mapping[str, str]) -> tuple[str, ...]:
    names = json.loads(environment.get("NATIVE_TOOL_SECRET_NAMES", "[]"))
    if not isinstance(names, list) or any(
        not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,127}", name) for name in names
    ):
        raise ValueError("NATIVE_TOOL_SECRET_NAMES must be a JSON array of explicit secret names, never values.")
    return tuple(dict.fromkeys(names))


def grant_runtime_features(environment: Mapping[str, str], principal: str) -> None:
    keys = ("AUDIT_HMAC_KEY",) + (("MCP_API_KEY",) if environment.get("MCP_ENABLED") == "true" else ())
    grant_secrets(environment, principal, (*secret_names(environment, keys), *tool_secret_names(environment)))


def grant_container_features(environment: Mapping[str, str]) -> None:
    group = resource_group_for(environment, "application")
    token = environment["RESOURCE_TOKEN"]
    ui = resolve_container_app_principal_id(group, f"ca-{token}-frontend")
    grant_secrets(environment, ui, secret_names(environment, (
        "CHAINLIT_AUTH_SECRET", "OAUTH_AZURE_AD_CLIENT_SECRET", "authClientSecret",
    )))
    from config.deployment.native import resolve_application
    if resolve_application(environment).host == "container_apps":
        worker = resolve_container_app_principal_id(group, f"ca-{token}-orchestrator")
        grant_runtime_features(environment, worker)
