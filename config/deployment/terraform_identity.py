"""Determine the caller object ID without Graph grants or credential fallback.

Only a token returned by the selected Azure CLI/SDK credential is inspected.
Its object ID is not a client/application ID. Tokens and upstream diagnostics
never leave this module. This is local claim extraction from a trusted credential
result, not a general JWT verification endpoint or an authorization decision.
"""

from __future__ import annotations

import base64
import json
import subprocess
from typing import Mapping, TypedDict
from uuid import UUID

from util.azure_cli import resolve_az_command
from config.deployment.terraform_cloud import credential_endpoints


class PrincipalEnvironment(TypedDict):
    AZURE_PRINCIPAL_ID: str
    AZURE_PRINCIPAL_TYPE: str


def _failure() -> ValueError:
    return ValueError(
        "Cannot determine the Terraform caller identity safely. Verify the selected "
        "subscription/tenant and its Azure CLI or ARM_* authentication, or set "
        "AZURE_PRINCIPAL_ID (object ID, not client ID) and AZURE_PRINCIPAL_TYPE "
        "(User or ServicePrincipal) explicitly in the selected azd environment. "
        "No different credential or interactive-user fallback was attempted."
    )


def _guid(value: object) -> str:
    if not isinstance(value, str):
        raise _failure()
    try:
        return str(UUID(value))
    except ValueError:
        raise _failure() from None


def _enabled(process: Mapping[str, str], key: str) -> bool:
    value = process.get(key, "").lower()
    if value in ("", "false", "0", "f"):
        return False
    if value in ("true", "1", "t"):
        return True
    raise _failure()


def _run_cli(arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            [resolve_az_command(), *arguments, "--only-show-errors"],
            capture_output=True, text=True, check=False, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        raise _failure() from None
    if result.returncode:
        raise _failure()
    return result.stdout.strip()


def _token_principal(token: str, kind: str, tenants: set[str]) -> PrincipalEnvironment:
    try:
        if not isinstance(token, str) or len(token) > 131072:
            raise ValueError
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.b64decode(payload, altchars=b"-_", validate=True))
        oid, tenant = _guid(claims["oid"]), _guid(claims["tid"])
        if tenants and tenant not in tenants:
            raise ValueError
        idtyp = claims.get("idtyp")
        if idtyp is not None and idtyp != ("user" if kind == "User" else "app"):
            raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise _failure() from None
    return {"AZURE_PRINCIPAL_ID": oid, "AZURE_PRINCIPAL_TYPE": kind}


def resolve_principal(
    environment: Mapping[str, str], process_environment: Mapping[str, str],
) -> PrincipalEnvironment:
    """Match native Terraform auth, never an ambient application's credential chain.

    CLI login supports users, SPs and `az login --identity`. Explicit process
    client-secret or MSI authentication uses that exact Azure Identity credential.
    Other native auth modes remain usable with an explicit principal ID/type;
    automatic resolution fails closed rather than pretending CLI is equivalent.
    """
    tenants = {
        _guid(value) for value in (
            environment.get("AZURE_TENANT_ID"), environment.get("TENANT_ID"),
            process_environment.get("ARM_TENANT_ID"),
        ) if value
    }
    if len(tenants) > 1:
        raise _failure()
    process = process_environment
    if (
        _enabled(process, "ARM_USE_OIDC")
        or _enabled(process, "ARM_USE_AKS_WORKLOAD_IDENTITY")
        or any(process.get(key) for key in (
            "ARM_CLIENT_CERTIFICATE", "ARM_CLIENT_CERTIFICATE_PATH",
            "ARM_OIDC_TOKEN", "ARM_OIDC_TOKEN_FILE_PATH",
        ))
    ):
        raise _failure()
    secret = process.get("ARM_CLIENT_SECRET")
    managed = _enabled(process, "ARM_USE_MSI")
    client = process.get("ARM_CLIENT_ID")
    if secret and managed:
        raise _failure()  # ambiguous configuration is not permission to guess
    if managed and (
        process.get("ARM_MSI_ENDPOINT") or process.get("AZURE_FEDERATED_TOKEN_FILE")
    ):
        # A custom Terraform MSI endpoint is not an Azure Identity SDK option.
        # The SDK can also auto-select workload identity inside its MSI class;
        # neither is permission to look up a different identity than Terraform.
        raise _failure()
    if secret or managed:
        # Match the explicitly selected credential; do not use DefaultAzureCredential
        # or a chain whose user/SP/MI ordering differs from the native provider.
        cloud = environment.get("ARM_ENVIRONMENT") or process.get("ARM_ENVIRONMENT", "public")
        if process.get("ARM_METADATA_HOSTNAME"):
            raise _failure()
        authority, scope = credential_endpoints(cloud)
        credential = None
        try:
            from azure.identity import ClientSecretCredential, ManagedIdentityCredential

            options = {"connection_timeout": 10, "read_timeout": 30, "retry_total": 0}
            if secret:
                if not client or not tenants:
                    raise _failure()
                credential = ClientSecretCredential(
                    tenant_id=next(iter(tenants)), client_id=client,
                    client_secret=secret, authority=authority, **options,
                )
            else:
                credential = ManagedIdentityCredential(client_id=client, **options)
            try:
                result = _token_principal(
                    credential.get_token(scope).token, "ServicePrincipal", tenants,
                )
            finally:
                credential.close()
            return result
        except Exception:
            # SDK exception text may contain credential, tenant or token details.
            # Failure is fatal; it is never converted into a fallback credential.
            raise _failure() from None
    if client:
        raise _failure()  # client ID alone does not identify an effective credential
    subscription = _guid(environment.get("AZURE_SUBSCRIPTION_ID"))
    try:
        account = json.loads(_run_cli([
            "account", "show", "--subscription", subscription, "--output", "json",
            "--query", "{id:id,tenantId:tenantId,userType:user.type}",
        ]))
        if _guid(account["id"]) != subscription:
            raise ValueError
        tenant = _guid(account["tenantId"])
        if tenants and tenant not in tenants:
            raise ValueError
        kind = {"user": "User", "servicePrincipal": "ServicePrincipal"}[account["userType"]]
    except (ValueError, TypeError, KeyError):
        raise _failure() from None
    return _token_principal(_run_cli([
        "account", "get-access-token", "--subscription", subscription,
        "--resource-type", "arm", "--query", "accessToken", "--output", "tsv",
    ]), kind, {tenant})
