"""Offline prerequisites for an existing, Entra-authenticated Terraform backend.

The input adapter calls resolve_backend after workload destinations are resolved,
then persists backend.azd_environment() into the selected azd environment BEFORE
native init. azd 1.37.1 renders provider.conf.json from its environment store,
not arbitrary process variables. No storage, RBAC or authentication is created.
The adapter supplies canonical ARM_ENVIRONMENT matching azureCloud.environment;
cloud context is never inferred from workload DNS suffixes.

The standalone check reads the process environment (for example an azd hook's
environment). It requires the state subscription to be materialized already.
It does NOT verify remote existence, data-plane permissions or connectivity.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re
from typing import Mapping
from uuid import UUID

from config.appdefinition.binding import env_file_path
from config.deployment.resource_groups import ResourceGroupError, resource_group_for

LOGGER = logging.getLogger(__name__)


class TerraformBackendError(ValueError):
    """Missing or unsafe remote-state prerequisites; local state is not allowed."""


def _required(environment: Mapping[str, str], key: str) -> str:
    value = environment.get(key)
    if not isinstance(value, str) or not value or value.strip() != value:
        raise TerraformBackendError(
            f"{key} must be a non-empty value without surrounding whitespace. "
            "Set it in the selected azd environment before Terraform initialization."
        )
    return value


def _subscription(value: str, key: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value):
        raise TerraformBackendError(f"{key} must be a hyphenated subscription UUID.")
    return str(UUID(value))


@dataclass(frozen=True)
class BackendConfig:
    resource_group_name: str
    storage_account_name: str
    container_name: str
    subscription_id: str
    environment_name: str
    azure_environment: str

    def azd_environment(self) -> dict[str, str]:
        """Only non-secret backend settings to persist via the existing adapter."""
        return {
            "TF_STATE_RESOURCE_GROUP": self.resource_group_name,
            "TF_STATE_STORAGE_ACCOUNT": self.storage_account_name,
            "TF_STATE_CONTAINER": self.container_name,
            "TF_STATE_SUBSCRIPTION_ID": self.subscription_id,
            "ARM_ENVIRONMENT": self.azure_environment,
        }

    def terraform_config(self) -> dict[str, str | bool]:
        """Expected native JSON rendering, including actual boolean values."""
        return {
            "resource_group_name": self.resource_group_name,
            "storage_account_name": self.storage_account_name,
            "container_name": self.container_name,
            "subscription_id": self.subscription_id,
            "environment": self.azure_environment,
            "key": f"agent-landing-zone/{self.environment_name}.tfstate",
            "use_azuread_auth": True,
            "use_cli": True,
            # Resolve the account in the declared subscription/resource group,
            # not just by its globally unique name. Requires account Reader.
            "lookup_blob_endpoint": True,
        }


def resolve_backend(environment: Mapping[str, str]) -> BackendConfig:
    """Validate existing-backend settings without I/O or changing the input.

    Only the subscription may default, to the validated deployment subscription.
    Backend storage must live outside ALL workload resource-group destinations
    in that subscription, even if a workload group is currently reused.
    Callers must also reject ARM_ACCESS_KEY / ARM_SAS_TOKEN in the Terraform
    process environment; either would override Entra authentication.
    """
    for key in ("ARM_ACCESS_KEY", "ARM_SAS_TOKEN"):
        if environment.get(key):
            raise TerraformBackendError(
                f"Remove {key} from the Terraform environment; state requires Entra authentication."
            )
    azure_environment = _required(environment, "ARM_ENVIRONMENT")
    if azure_environment not in {"public", "usgovernment", "china"}:
        raise TerraformBackendError(
            "ARM_ENVIRONMENT must be normalized by the input adapter to public, "
            "usgovernment or china, matching azureCloud.environment."
        )
    deployment_subscription = _subscription(
        _required(environment, "AZURE_SUBSCRIPTION_ID"), "AZURE_SUBSCRIPTION_ID",
    )
    subscription = environment.get("TF_STATE_SUBSCRIPTION_ID")
    if subscription is None or subscription == "":
        subscription = deployment_subscription
    else:
        subscription = _subscription(
            _required(environment, "TF_STATE_SUBSCRIPTION_ID"), "TF_STATE_SUBSCRIPTION_ID",
        )

    name = _required(environment, "AZURE_ENV_NAME")
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name)
        or ".." in name
        or len(f"agent-landing-zone/{name}.tfstate") > 1024
    ):
        raise TerraformBackendError(
            "AZURE_ENV_NAME must be a safe single blob-key segment, with letters, "
            "digits, underscores, hyphens or single periods; no paths or substitutions."
        )
    account = _required(environment, "TF_STATE_STORAGE_ACCOUNT")
    if not re.fullmatch(r"[a-z0-9]{3,24}", account):
        raise TerraformBackendError(
            "TF_STATE_STORAGE_ACCOUNT must contain 3-24 lowercase letters or digits."
        )
    container = _required(environment, "TF_STATE_CONTAINER")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]", container) or "--" in container:
        raise TerraformBackendError(
            "TF_STATE_CONTAINER must be a 3-63 character Azure container name, "
            "with lowercase letters, digits and non-consecutive internal hyphens."
        )
    group = _required(environment, "TF_STATE_RESOURCE_GROUP")
    _required(environment, "AZURE_RESOURCE_GROUP")
    for key in ("AZURE_APP_RESOURCE_GROUP", "AZURE_NETWORK_RESOURCE_GROUP",
                "AZURE_FOUNDRY_RESOURCE_GROUP"):
        if key in environment and not isinstance(environment[key], str):
            raise TerraformBackendError(f"{key} must be a string when supplied.")
    try:
        # Reuse the public destination/name contract rather than inventing a
        # second definition of an Azure resource-group name.
        resource_group_for({"AZURE_RESOURCE_GROUP": group}, "foundry")
        workload_groups = {
            resource_group_for(environment, area).casefold()
            for area in ("foundry", "application", "network")
        }
    except ResourceGroupError as exc:
        # Do not echo raw environment values, which may contain secrets by mistake.
        raise TerraformBackendError(
            "Resolve valid Foundry/application/network resource-group destinations "
            "and TF_STATE_RESOURCE_GROUP before backend preparation."
        ) from exc
    if subscription == deployment_subscription and group.casefold() in workload_groups:
        raise TerraformBackendError(
            "TF_STATE_RESOURCE_GROUP must be outside every workload resource-group "
            "destination in the deployment subscription, so azd down cannot delete state."
        )
    return BackendConfig(group, account, container, subscription, name, azure_environment)


def ensure_backend_binding(
    backend: BackendConfig, azure_dir: Path, *, allow_create: bool = False,
) -> None:
    """Keep the selected state address immutable; teardown may only verify it."""
    path = env_file_path(azure_dir, backend.environment_name).parent / "terraform-backend.json"
    expected = {
        "version": 1,
        "subscription": backend.subscription_id,
        "resourceGroup": backend.resource_group_name.casefold(),
        "storageAccount": backend.storage_account_name,
        "container": backend.container_name,
        "key": f"agent-landing-zone/{backend.environment_name}.tfstate",
        "environment": backend.azure_environment,
    }
    if path.exists():
        try:
            recorded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TerraformBackendError("The recorded Terraform backend binding is unreadable.") from exc
        if recorded != expected:
            raise TerraformBackendError(
                "Terraform backend settings differ from the recorded state address. "
                "Restore the original backend settings and binding before continuing."
            )
        return
    if not allow_create:
        raise TerraformBackendError(
            "The Terraform backend binding is missing. Restore the environment's "
            "original terraform-backend.json before teardown."
        )
    staging = path.with_suffix(".json.pending")
    try:
        with staging.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(expected, indent=2) + "\n")
        staging.replace(path)
    except FileExistsError as exc:
        raise TerraformBackendError(
            "A Terraform backend binding write is pending; finish it before retrying."
        ) from exc


def main() -> int:
    """Check prerequisites only; never create a backend or change azd settings."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        backend = resolve_backend(os.environ)
        if any(os.environ.get(key) != value for key, value in backend.azd_environment().items()):
            raise TerraformBackendError(
                "Persist the validated backend.azd_environment() settings through the "
                "input adapter first; native azd does not render from process defaults."
            )
    except TerraformBackendError as exc:
        LOGGER.error("%s", exc)
        return 1
    LOGGER.info(
        "Offline backend prerequisites passed. Existing storage/container, account Reader "
        "and container-scoped Storage Blob Data Contributor access, recovery settings "
        "and network reachability still require "
        "independent verification. Native azd 1.37.1 plan/apply disable state locking "
        "including Blob lease protection; shared states require one authorized executor "
        "with queued, non-canceling serialization. These controls do not restore locking."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
