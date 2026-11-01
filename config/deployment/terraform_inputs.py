"""Resolve product configuration to native azd Terraform inputs, never ARM tfvars.

CLI environment input is an explicit JSON snapshot from ``azd env get-values
--output json`` (``--environment -`` reads stdin), not ambient OS variables.
Preparation qualifies the Azure cloud, validates util.terraform_backend settings,
binds the state address locally (missing deployed bindings require restoration),
rejects process shared-key/SAS overrides, resolves a missing caller identity, and persists only normalized
safe fields to the selected azd environment before native init. Process ARM_*
credentials are used only to match the actual Terraform caller, never as input
configuration or output. Hooks reload the store after a successful preparation.
An explicit --app-definition carries the hook's validated selection only in the
local resolver context; its ID must match AGENTLZ_APP_ID when bound. The path is
never added to the normalized azd fields.
The output is the generated, ignored selected <module>.tfvars.json file. JSON
unicode escaping removes every '$' before native azd's envsubst pass; Terraform
JSON decoding restores arbitrary strings without re-interpolating their contents.
The template contains environment-local values, potentially secrets. Hooks must
generate it locally before native azd provision, never commit it, and coordinate
concurrent checkout use. The root owns omitted defaults and null name/token/
password derivation; $(secretOrRandomPassword) means persistent root generation.

Resource-group ownership is a separate, persisted lifecycle assertion, not an
existence guess: {"managedResourceGroupNames": [...]}. It maps to the root's
createResourceGroup/createApplicationResourceGroup/createNetworkResourceGroup
booleans. Freshly requested groups are Terraform-managed; existing groups must
be omitted. Binding, existence and down guards remain the common lifecycle's
responsibility.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
from pathlib import Path
import re
import sys
from typing import Mapping, Sequence
from uuid import UUID

from config import find_repo_root
from config.appdefinition.binding import APP_ID_ENV, env_file_path
from config.appdefinition.errors import AppDefinitionError, BindingMismatchError
from config.appdefinition.loader import DEFINITION_ENV, load_selected_definition
from config.deployment.app_settings import substitute_values as _substitute
from config.deployment.composition import is_truthy, resolve_mode
from config.deployment.existing_images import apply_existing_images, discover_existing_images
from config.deployment.input_types import INPUT_TYPES, NULLABLE_BOOLEANS
from config.deployment.resolution import resolve_parameters
from config.deployment.resource_groups import (
    ResourceGroupError, _legacy_deployed, _run_azd, resolve_resource_groups,
)
from config.deployment.terraform_cloud import cloud_context, resolve_cloud
from config.deployment.terraform_identity import resolve_principal
from util.terraform_backend import TerraformBackendError, ensure_backend_binding, resolve_backend

LOGGER = logging.getLogger(__name__)
_VNET_ID = re.compile(
    r"^/subscriptions/([^/]+)/resourceGroups/[^/]+/providers/"
    r"Microsoft\.Network/virtualNetworks/[^/]+/?$", re.IGNORECASE,
)


def _native_value(name: str, value: object) -> object:
    kind = INPUT_TYPES[name]
    if value is None:
        if (
            kind == "bool" and name not in NULLABLE_BOOLEANS
            or kind == "int" and name != "dbDatabaseThroughput"
            or kind in ("array", "object")
        ):
            raise ValueError(f"{name} requires a native {kind} value, not null.")
        return None
    if kind == "bool":
        if type(value) is bool:
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("true", "false"):
                return normalized == "true"
            if normalized == "null" and name in NULLABLE_BOOLEANS:
                return None
    elif kind == "int":
        if type(value) is int:
            return value
        if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
            return int(value)
        if value == "null" and name == "dbDatabaseThroughput":
            return None
    elif kind == "string" and isinstance(value, str):
        return value
    elif kind in ("array", "object"):
        expected = list if kind == "array" else dict
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                raise ValueError(f"{name} requires valid JSON for a native {kind}.") from None
        if isinstance(value, expected):
            return value
    raise ValueError(f"{name} requires a native {kind} value; check its product input or azd setting.")


def _uuid(value: str, name: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise ValueError(f"{name} must be a UUID from the selected azd environment.") from None


def compose_inputs(
    source: Mapping[str, object],
    environment: Mapping[str, str],
    *,
    expected_hosted_source_commit: str | None = None,
    existing_images: Mapping[str, str] | None = None,
    managed_resource_group_names: Sequence[str] | None = None,
) -> dict[str, object]:
    """Accept plain product values; emit native camelCase values and context.

    All foundation inputs are accepted, including open collection fields.
    Pure composition defaults cloud context to Public; actual CLI preparation
    qualifies ARM_ENVIRONMENT before calling this boundary.
    Omitted inputs remain omitted so Terraform owns its declared defaults.
    No process environment, Azure calls, parameter envelope or shell evaluation.
    """
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in environment.items()):
        raise ValueError("The azd environment snapshot must be an object of string values.")
    bound_app_id = (environment.get(APP_ID_ENV) or "").strip()
    if bound_app_id:
        selected = load_selected_definition(environment)
        if selected.id != bound_app_id:
            raise BindingMismatchError(bound_app_id, selected.id)
    unknown = source.keys() - INPUT_TYPES.keys() - {"aiFoundryLocation"}
    if unknown:
        raise ValueError("Unknown infrastructure input names; compare the product configuration with the foundation interface.")
    substituted = _substitute(copy.deepcopy(dict(source)), environment)
    if "aiFoundryLocation" in substituted:
        foundry_location = substituted.pop("aiFoundryLocation")
        if foundry_location and foundry_location != substituted.get("location"):
            raise ValueError(
                "aiFoundryLocation is not a declared foundation input. Select the "
                "Foundry region with location/AZURE_LOCATION; a separate region is unsupported."
            )
        LOGGER.info("aiFoundryLocation has no foundation declaration; location selects Foundry.")
    # This azd/Bicep expression is not a Terraform expression. A null value
    # explicitly requests persistent root-owned generation, never a new random
    # password per hook run. An explicit store value remains sensitive data.
    if substituted.get("vmAdminPassword") == "$(secretOrRandomPassword)":
        substituted["vmAdminPassword"] = environment.get("VM_ADMIN_PASSWORD") or None
    native = {name: _native_value(name, value) for name, value in substituted.items()}
    resolved = resolve_parameters(
        native, environment,
        expected_hosted_source_commit=expected_hosted_source_commit,
        existing_images=existing_images,
    )
    groups = resolve_resource_groups(environment)
    if not resolved.get("principalId"):
        raise ValueError(
            "principalId/AZURE_PRINCIPAL_ID must be resolved into the azd snapshot "
            "before rendering; native azd cannot resolve a token-free template."
        )
    tenant = (environment.get("AZURE_TENANT_ID") or environment.get("TENANT_ID") or "").strip()
    if environment.get("AZURE_TENANT_ID") and environment.get("TENANT_ID"):
        if _uuid(environment["AZURE_TENANT_ID"], "AZURE_TENANT_ID") != _uuid(environment["TENANT_ID"], "TENANT_ID"):
            raise ValueError("AZURE_TENANT_ID and TENANT_ID conflict; select one tenant.")
    if groups.create_resource_groups and managed_resource_group_names is None:
        raise ValueError(
            "Terraform resource-group ownership must be classified and persisted "
            "before provision; supply managedResourceGroupNames, using [] for BYO."
        )
    names = managed_resource_group_names if managed_resource_group_names is not None else []
    if isinstance(names, (str, bytes)) or any(not isinstance(name, str) for name in names):
        raise ValueError("managedResourceGroupNames must be an array of selected destination names.")
    destinations = {name.casefold(): name for name in groups.unique_groups}
    if any(name.casefold() not in destinations for name in names):
        raise ValueError("Managed resource groups must be selected workload destinations.")
    if names and not groups.create_resource_groups:
        raise ValueError("Managing new groups requires explicit CREATE_RESOURCE_GROUPS=true authorization.")
    managed = {name.casefold() for name in names}
    # Environment-local context must agree with the shared binding selection,
    # not a stale product parameter or ambient `az account` default.
    for name, selected in (
        ("environmentName", environment.get("AZURE_ENV_NAME", "")),
        ("applicationResourceGroupName", groups.application),
        ("networkResourceGroupName", groups.network),
    ):
        current = resolved.get(name)
        if name != "environmentName":
            selected = destinations[selected.casefold()]
        agrees = current == selected if name == "environmentName" else (
            not current or current.casefold() == selected.casefold()
        )
        if current and not agrees:
            raise ValueError(f"{name} conflicts with the selected azd environment or resource-group binding.")
        resolved[name] = selected
    if not resolved["environmentName"]:
        raise ValueError("AZURE_ENV_NAME is required for stable Terraform deployment context.")
    resolved.update({
        "subscriptionId": groups.subscription,
        "tenantId": _uuid(tenant, "AZURE_TENANT_ID/TENANT_ID") if tenant else None,
        "resourceGroupName": groups.foundry,
        "deploymentName": environment.get("AZURE_DEPLOYMENT_NAME") or resolved["environmentName"],
        "azureCloud": cloud_context(environment.get("ARM_ENVIRONMENT", "public")),
        "createResourceGroup": groups.foundry.casefold() in managed,
        "createApplicationResourceGroup": (
            groups.application.casefold() in managed
            and groups.application.casefold() != groups.foundry.casefold()
        ),
        "createNetworkResourceGroup": (
            groups.network.casefold() in managed
            and groups.network.casefold() != groups.foundry.casefold()
        ),
    })
    existing_vnet = resolved.get("existingVnetResourceId")
    if existing_vnet:
        match = _VNET_ID.fullmatch(existing_vnet)
        if not match:
            raise ValueError("existingVnetResourceId must be a full Azure virtual network resource ID.")
        resolved["existingVnetSubscriptionId"] = _uuid(match[1], "existingVnetResourceId subscription")
    else:
        resolved["existingVnetSubscriptionId"] = None
    return resolved


def render_template(inputs: Mapping[str, object]) -> str:
    """Complete native azd template with no tokens, including in strings/keys."""
    return json.dumps(inputs, ensure_ascii=True, indent=2, allow_nan=False).replace("$", r"\u0024") + "\n"


def diagnostic_parameters(inputs: Mapping[str, object]) -> dict[str, object]:
    """Same semantic values for existing regional/security/egress preflight.

    This artifact is diagnostic only: never a Terraform input or a second
    application-resolution path. Terraform context has no ARM parameter analogue.
    """
    return {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
        "contentVersion": "1.0.0.0",
        "parameters": {
            name: {"value": value}
            for name, value in inputs.items() if name in INPUT_TYPES
        },
    }


def _read_json(path: str) -> object:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8-sig")
        return json.loads(text.lstrip("\ufeff"))
    except (OSError, ValueError):
        raise ValueError("Cannot read the requested JSON input; check file availability and JSON syntax.") from None


def prepare_environment(
    environment: Mapping[str, str],
    *,
    principal_required: bool = True,
) -> tuple[dict[str, str], dict[str, str]]:
    """Validate backend/auth and return normalized snapshot plus safe store fields.

    Application inputs still come only from the explicit azd snapshot. The actual
    process environment is inspected solely for native cloud/credential selection and
    forbidden backend credential overrides; none of those credentials is emitted.
    """
    for key in ("ARM_ACCESS_KEY", "ARM_SAS_TOKEN"):
        if os.environ.get(key):
            raise TerraformBackendError(
                f"Remove {key} from the actual Terraform process environment; "
                "remote state requires Entra authentication."
            )
    cloud = resolve_cloud(environment, os.environ)
    backend = resolve_backend({**environment, "ARM_ENVIRONMENT": cloud["environment"]})
    fields = backend.azd_environment()
    normalized = {**environment, **fields}
    if principal_required and not (environment.get("AZURE_PRINCIPAL_ID") or "").strip():
        principal = resolve_principal(normalized, os.environ)
        configured_type = environment.get("AZURE_PRINCIPAL_TYPE")
        if configured_type and configured_type != principal["AZURE_PRINCIPAL_TYPE"]:
            raise ValueError(
                "AZURE_PRINCIPAL_TYPE conflicts with the authenticated Terraform "
                "identity. Correct it or explicitly select the intended principal."
            )
        fields.update(principal)
        normalized.update(principal)
    return normalized, fields


def _persist_environment(
    project_root: Path, original: Mapping[str, str], fields: Mapping[str, str],
) -> None:
    """Persist only validated, non-secret defaults before native backend init."""
    for key, value in fields.items():
        if original.get(key) == value:
            continue
        try:
            _run_azd(project_root / ".azure", [
                "env", "set", key, value, "--environment", original["AZURE_ENV_NAME"], "--no-prompt",
            ])
        except ResourceGroupError:
            raise ValueError(
                "Cannot persist normalized Terraform settings in the selected azd "
                "environment. Restore azd access and retry before native init; "
                "no usable input artifact has been emitted."
            ) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--environment", required=True, help="azd env get-values JSON file, or - for stdin.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--diagnostic-output", type=Path, help="ARM-shaped artifact for existing shared preflight/egress only.")
    parser.add_argument("--resource-group-ownership", type=Path)
    parser.add_argument("--app-definition", type=Path, help="Validated definition file/folder for this invocation only; never persisted.")
    parser.add_argument("--hosted-source-commit")
    parser.add_argument("--no-preserve-images", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.diagnostic_output and args.diagnostic_output.resolve() == args.output.resolve():
            raise ValueError("Native Terraform and diagnostic outputs must be different files.")
        if args.output.resolve() == args.input.resolve() or (
            args.diagnostic_output and args.diagnostic_output.resolve() == args.input.resolve()
        ):
            raise ValueError("Generated outputs must not overwrite the product parameter source.")
        document = _read_json(str(args.input))
        if (
            not isinstance(document, dict) or not isinstance(document.get("parameters"), dict)
            or any(not isinstance(entry, dict) or "value" not in entry for entry in document["parameters"].values())
        ):
            raise ValueError("Product parameter source must contain parameters with explicit value entries.")
        source = {name: entry["value"] for name, entry in document["parameters"].items()}
        original_environment = _read_json(args.environment)
        if not isinstance(original_environment, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in original_environment.items()
        ):
            raise ValueError("The azd environment snapshot must be an object of string values.")
        resolver_environment = dict(original_environment)
        if args.app_definition is not None:
            resolver_environment[DEFINITION_ENV] = str(args.app_definition)
        environment, normalized_fields = prepare_environment(
            resolver_environment,
            principal_required=not bool(_substitute(source.get("principalId"), original_environment)),
        )
        managed = None
        if args.resource_group_ownership:
            ownership = _read_json(str(args.resource_group_ownership))
            if (
                not isinstance(ownership, dict) or set(ownership) != {"managedResourceGroupNames"}
                or not isinstance(ownership["managedResourceGroupNames"], list)
            ):
                raise ValueError("Resource-group ownership must contain only managedResourceGroupNames (an array).")
            managed = ownership["managedResourceGroupNames"]
        # Validate before making the optional shared, read-only image lookup.
        inputs = compose_inputs(
            source, environment,
            expected_hosted_source_commit=args.hosted_source_commit,
            managed_resource_group_names=managed,
        )
        if "AZURE_PRINCIPAL_TYPE" in normalized_fields and inputs.get("principalType") != normalized_fields["AZURE_PRINCIPAL_TYPE"]:
            raise ValueError("principalType conflicts with the automatically resolved Terraform principal type.")
        if not args.no_preserve_images and not is_truthy(environment.get("RESET_CONTAINER_APP_IMAGES")):
            images = discover_existing_images(
                inputs["applicationResourceGroupName"],
                inputs["subscriptionId"], inputs["environmentName"],
            )
            apply_existing_images(inputs["containerAppsList"], images)
        # Render both before writing either: serialization failures cannot leave
        # a partial native artifact that looks usable to a later lifecycle step.
        template = render_template(inputs)
        diagnostic = (
            json.dumps(diagnostic_parameters(inputs), indent=2, allow_nan=False) + "\n"
            if args.diagnostic_output else None
        )
        project_root = find_repo_root(args.input, environment)
        azure_dir = project_root / ".azure"
        backend = resolve_backend(environment)
        env_file = env_file_path(azure_dir, backend.environment_name)
        if not (env_file.parent / "terraform-backend.json").exists() and _legacy_deployed(
            environment, env_file, resolve_resource_groups(environment), backend.environment_name,
        ):
            raise TerraformBackendError(
                "Deployment evidence exists but the Terraform backend binding is "
                "missing. Restore the original .azure/<env>/terraform-backend.json; "
                "never recreate a state address for an existing deployment."
            )
        ensure_backend_binding(backend, azure_dir, allow_create=True)
        _persist_environment(project_root, original_environment, normalized_fields)
        args.output.write_text(template, encoding="utf-8")
        if args.diagnostic_output:
            args.diagnostic_output.write_text(diagnostic, encoding="utf-8")
        sys.stdout.write(json.dumps({
            "topology": resolve_mode(environment).value,
            "inputCount": len(inputs),
            "normalizedEnvironment": normalized_fields,
        }) + "\n")
        return 0
    except BindingMismatchError as exc:
        LOGGER.error("%s Pass the validated --app-definition path matching AGENTLZ_APP_ID.", exc)
        return 1
    except (ValueError, OSError, RuntimeError, TypeError, AppDefinitionError) as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
