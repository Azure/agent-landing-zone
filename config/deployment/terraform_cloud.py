"""Qualified native Terraform cloud context; never derived from workload DNS.

Contract evidence: AzureRM v4.81.0 internal/provider/provider.go and vendored
go-azure-sdk/sdk/environments/{from_name,azure_public,azure_gov,azure_china}.go;
AzAPI v2.13.0 internal/provider/provider.go. These three canonical identifiers
are shared by both providers. Their storage suffixes and ARM/authority endpoints
also match the installed Azure CLI's KNOWN_CLOUDS metadata.

CLI authentication is qualified using selected-subscription account metadata
and the active CLI cloud's actual endpoints/suffix, without changing cloud/login.
Process-authenticated runs require explicit ARM_ENVIRONMENT instead of borrowing
an unrelated CLI account. Custom endpoints/clouds are not silently approximated.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import Mapping, TypedDict
from uuid import UUID

from util.azure_cli import resolve_az_command


class AzureCloud(TypedDict):
    environment: str
    storage_dns_suffix: str


@dataclass(frozen=True)
class _Definition:
    cli_name: str
    storage_suffix: str
    resource_manager: str
    authority: str


_CLOUDS = {
    "public": _Definition("AzureCloud", "core.windows.net", "https://management.azure.com", "https://login.microsoftonline.com"),
    "usgovernment": _Definition("AzureUSGovernment", "core.usgovcloudapi.net", "https://management.usgovcloudapi.net", "https://login.microsoftonline.us"),
    "china": _Definition("AzureChinaCloud", "core.chinacloudapi.cn", "https://management.chinacloudapi.cn", "https://login.chinacloudapi.cn"),
}


def _canonical(value: str) -> str:
    if not isinstance(value, str) or value.lower() not in _CLOUDS:
        raise ValueError("ARM_ENVIRONMENT must select public, usgovernment or china.")
    return value.lower()


def cloud_context(environment: str = "public") -> AzureCloud:
    """Pure context for a qualified canonical name; composition defaults Public."""
    name = _canonical(environment)
    return {"environment": name, "storage_dns_suffix": _CLOUDS[name].storage_suffix}


def credential_endpoints(environment: str) -> tuple[str, str]:
    """Use the same qualified cloud for automatic SDK principal lookup."""
    definition = _CLOUDS[_canonical(environment)]
    return definition.authority, definition.resource_manager + "/.default"


def _metadata_error() -> ValueError:
    return ValueError(
        "Cannot qualify the selected subscription and active Azure CLI cloud metadata. "
        "Verify Azure CLI availability, subscription/cloud selection and ARM_ENVIRONMENT "
        "agreement. Only public, usgovernment and china are supported; "
        "no global cloud or authentication setting was changed."
    )


def _run_cli(arguments: list[str]) -> object:
    try:
        result = subprocess.run(
            [resolve_az_command(), *arguments, "--output", "json", "--only-show-errors"],
            capture_output=True, text=True, check=False, timeout=60,
        )
        if result.returncode:
            raise _metadata_error()
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        raise _metadata_error() from None


def _process_authentication(process: Mapping[str, str]) -> bool:
    selected = any(process.get(key) for key in (
        "ARM_CLIENT_ID", "ARM_CLIENT_SECRET", "ARM_CLIENT_CERTIFICATE",
        "ARM_CLIENT_CERTIFICATE_PATH", "ARM_OIDC_TOKEN", "ARM_OIDC_TOKEN_FILE_PATH",
    ))
    for key in ("ARM_USE_MSI", "ARM_USE_OIDC", "ARM_USE_AKS_WORKLOAD_IDENTITY"):
        value = process.get(key, "").lower()
        if value not in ("", "false", "0", "f", "true", "1", "t"):
            raise ValueError(f"{key} must be a Terraform boolean authentication selector.")
        selected = selected or value in ("true", "1", "t")
    return selected


def resolve_cloud(
    environment: Mapping[str, str], process_environment: Mapping[str, str],
) -> AzureCloud:
    """Bind the cloud before backend init, independently of ACR suffix overrides."""
    if any(values.get(key) for values in (environment, process_environment) for key in (
        "ARM_METADATA_HOSTNAME", "ARM_RESOURCE_MANAGER_ENDPOINT", "ARM_ACTIVE_DIRECTORY_AUTHORITY_HOST",
    )):
        raise ValueError("Endpoint overrides cannot be qualified by this canonical Azure cloud contract.")
    configured = [
        _canonical(values["ARM_ENVIRONMENT"])
        for values in (environment, process_environment) if values.get("ARM_ENVIRONMENT")
    ]
    if len(set(configured)) > 1:
        raise ValueError("ARM_ENVIRONMENT conflicts between the azd store and actual process environment.")
    if _process_authentication(process_environment):
        if not configured:
            raise ValueError(
                "Set explicit ARM_ENVIRONMENT to public, usgovernment or china for "
                "process authentication; an unrelated CLI cloud is not a fallback."
            )
        return cloud_context(configured[0])
    try:
        subscription = str(UUID(environment["AZURE_SUBSCRIPTION_ID"]))
        account = _run_cli([
            "account", "show", "--subscription", subscription,
            "--query", "{id:id,environmentName:environmentName}",
        ])
        if str(UUID(account["id"])) != subscription:
            raise _metadata_error()
        name = next(key for key, definition in _CLOUDS.items() if definition.cli_name == account["environmentName"])
        definition = _CLOUDS[name]
        metadata = _run_cli([
            "cloud", "show", "--query", "{name:name,suffixes:suffixes,endpoints:endpoints}",
        ])
        if (
            metadata["name"] != definition.cli_name
            or metadata["suffixes"]["storageEndpoint"] != definition.storage_suffix
            or metadata["endpoints"]["resourceManager"].rstrip("/").lower() != definition.resource_manager
            or metadata["endpoints"]["activeDirectory"].rstrip("/").lower() != definition.authority
        ):
            raise _metadata_error()
    except (ValueError, KeyError, TypeError, AttributeError, StopIteration):
        raise _metadata_error() from None
    if configured and configured[0] != name:
        raise ValueError("ARM_ENVIRONMENT conflicts with the qualified selected-subscription Azure CLI cloud.")
    return cloud_context(name)
