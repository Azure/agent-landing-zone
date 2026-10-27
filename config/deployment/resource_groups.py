"""Initialize, resolve and bind the workload resource-group destinations.

New azd environments default to Foundry, application and network groups.
The CLI records their names before Bicep provider initialization; native azd
still creates the Foundry/root group. Existing bindings are never retargeted.
"""

from __future__ import annotations

import argparse
import hashlib
from ipaddress import IPv4Network
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Mapping
import unicodedata
from uuid import UUID

from config.appdefinition.binding import env_file_path, resolve_env_name
from config.appdefinition.errors import EnvironmentNotFoundError
from util.azure_cli import resolve_az_command

LOGGER = logging.getLogger(__name__)
BINDING_FILENAME = "resource-groups.json"
_AREA_KEYS = {
    "application": "AZURE_APP_RESOURCE_GROUP",
    "foundry": "AZURE_RESOURCE_GROUP",
    "network": "AZURE_NETWORK_RESOURCE_GROUP",
}
_DEPLOYED_MARKERS = (
    "APP_CONFIG_ENDPOINT",
    "AZURE_AI_PROJECT_ENDPOINT",
    "AI_FOUNDRY_PROJECT_ENDPOINT",
    "AZURE_AI_PROJECT_RESOURCE_ID",
    "AZURE_CONTAINER_REGISTRY_ENDPOINT",
    "AZURE_CONTAINER_REGISTRY_NAME",
    "ORCHESTRATOR_APP",
    "FRONTEND_APP",
    "KEY_VAULT_RESOURCE_ID",
)
# Only this shipped output is conditional on creating the application Key Vault.
# Foundry IDs prove another area; ACR, VNet and monitoring IDs can also be BYO.
_APPLICATION_RESOURCE_PATHS = {
    "KEY_VAULT_RESOURCE_ID": r"Microsoft\.KeyVault/vaults/[^/]+",
}
_SCOPE_PREFIX = (
    r"/subscriptions/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})/resourceGroups/([^/]+)"
)


class ResourceGroupError(ValueError):
    """Invalid, inaccessible, or conflicting workload resource-group context."""


def _name(value: str, key: str) -> str:
    name = value.strip()
    if (
        not 1 <= len(name) <= 90
        or name.endswith(".")
        or any(
            char not in "_-.()"
            and not unicodedata.category(char).startswith("L")
            and unicodedata.category(char) != "Nd"
            for char in name
        )
    ):
        raise ResourceGroupError(
            f"{key} must be an Azure resource-group name (1-90 letters, digits, "
            "underscores, hyphens, periods or parentheses; no trailing period), "
            "not an ARM ID or subscription-qualified path."
        )
    return name


def resource_group_for(environment: Mapping[str, str], area: str) -> str:
    """Return an area's destination, without Azure I/O or changing environment."""
    if area not in _AREA_KEYS:
        raise ResourceGroupError(
            "Resource-group area must be application, foundry or network."
        )
    root = (environment.get("AZURE_RESOURCE_GROUP") or "").strip()
    if not root:
        raise ResourceGroupError(
            "AZURE_RESOURCE_GROUP is not available. Let azd select its Foundry "
            "root, or select the intended root with `azd env set "
            "AZURE_RESOURCE_GROUP <name>` before using additional destinations. "
            "No root name is inferred and no additional group has been created."
        )
    root = _name(root, "AZURE_RESOURCE_GROUP")
    legacy_foundry = (environment.get("AZURE_FOUNDRY_RESOURCE_GROUP") or "").strip()
    if legacy_foundry and legacy_foundry.casefold() != root.casefold():
        raise ResourceGroupError(
            "AZURE_FOUNDRY_RESOURCE_GROUP is no longer an override. "
            "AZURE_RESOURCE_GROUP now selects Foundry/root and "
            "AZURE_APP_RESOURCE_GROUP selects the application. Keep an existing "
            "split environment on its original release, or create a new azd "
            "environment with the new settings; no implicit migration is performed."
        )
    key = _AREA_KEYS[area]
    override = (environment.get(key) or "").strip()
    return _name(override, key) if override else root


def _create_flag(environment: Mapping[str, str]) -> bool:
    if "CREATE_RESOURCE_GROUPS" not in environment:
        return False
    value = environment["CREATE_RESOURCE_GROUPS"].strip().lower()
    if value not in {"true", "false"}:
        raise ResourceGroupError(
            "CREATE_RESOURCE_GROUPS must be 'true' or 'false'. "
            "Empty values and numeric/truthy aliases are not accepted."
        )
    return value == "true"


def validate_application_pe_subnet(environment: Mapping[str, str]) -> None:
    """Reject malformed optional PE selection before any bootstrap Azure write."""
    name = (environment.get("AZURE_APPLICATION_PE_SUBNET_NAME") or "").strip()
    prefix = (environment.get("AZURE_APPLICATION_PE_SUBNET_PREFIX") or "").strip()
    if not name and not prefix:
        return
    if not name or not prefix:
        raise ResourceGroupError(
            "AZURE_APPLICATION_PE_SUBNET_NAME and AZURE_APPLICATION_PE_SUBNET_PREFIX "
            "must both be supplied, or both omitted for the legacy shared PE subnet."
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,78}[A-Za-z0-9_]|[A-Za-z0-9]", name):
        raise ResourceGroupError(
            "AZURE_APPLICATION_PE_SUBNET_NAME must be a valid subnet name: 1-80 "
            "letters, digits, underscores, periods or hyphens; start with a letter "
            "or digit and end with a letter, digit or underscore."
        )
    try:
        network = IPv4Network(prefix, strict=True)
        if "/" not in prefix or network.prefixlen > 29:
            raise ValueError
    except ValueError as exc:
        raise ResourceGroupError(
            "AZURE_APPLICATION_PE_SUBNET_PREFIX must be an aligned IPv4 CIDR "
            "with prefix length at most /29. VNet containment, subnet overlap and "
            "existing-network compatibility must also pass infrastructure validation."
        ) from exc


@dataclass(frozen=True)
class ResourceGroupSelection:
    subscription: str
    application: str | None
    foundry: str | None
    network: str | None
    create_resource_groups: bool = False

    @property
    def unique_groups(self) -> tuple[str, ...]:
        groups: dict[str, str] = {}
        for name in (self.foundry, self.application, self.network):
            if name:
                groups.setdefault(name.casefold(), name)
        return tuple(groups.values())

    @property
    def split(self) -> bool:
        return len(self.unique_groups) > 1


def resolve_resource_groups(
    environment: Mapping[str, str], *, allow_pending_root: bool = False
) -> ResourceGroupSelection:
    """Validate local selection; only native all-default startup may be pending."""
    create = _create_flag(environment)
    root = (environment.get("AZURE_RESOURCE_GROUP") or "").strip()
    additional = any(
        (environment.get(key) or "").strip()
        for key in ("AZURE_APP_RESOURCE_GROUP", "AZURE_NETWORK_RESOURCE_GROUP",
                    "AZURE_FOUNDRY_RESOURCE_GROUP")
    )
    subscription = (environment.get("AZURE_SUBSCRIPTION_ID") or "").strip()
    if subscription:
        try:
            subscription = str(UUID(subscription))
        except ValueError as exc:
            raise ResourceGroupError(
                "AZURE_SUBSCRIPTION_ID must be the selected workload subscription UUID."
            ) from exc
    if (
        not root and allow_pending_root and not additional
        and not any((environment.get(key) or "").strip() for key in _DEPLOYED_MARKERS)
    ):
        return ResourceGroupSelection(subscription, None, None, None, create)
    application = resource_group_for(environment, "application")
    if not subscription:
        raise ResourceGroupError(
            "AZURE_SUBSCRIPTION_ID is required once a Foundry root is selected. "
            "Select the workload subscription in the azd environment; the current "
            "Azure CLI default is not used implicitly."
        )
    return ResourceGroupSelection(
        subscription,
        application,
        resource_group_for(environment, "foundry"),
        resource_group_for(environment, "network"),
        create,
    )


def binding_path(azure_dir: Path, env_name: str) -> Path:
    """Return environment-local state shared with deployment and cleanup guards."""
    try:
        return env_file_path(azure_dir, env_name).parent / BINDING_FILENAME
    except EnvironmentNotFoundError as exc:
        raise ResourceGroupError(str(exc)) from exc


def read_binding(azure_dir: Path, env_name: str) -> ResourceGroupSelection | None:
    """Read a v2 binding or a compatible single-group/pending v1 binding."""
    path = binding_path(azure_dir, env_name)
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(document, dict)
            or type(document.get("version")) is not int
            or document["version"] not in (1, 2)
            or document.get("environment") != env_name
            or set(document) != {
                "version", "environment", "subscription", "application", "foundry", "network"
            }
            or not isinstance(document["subscription"], str)
        ):
            raise ValueError
        pending = document["application"] is None
        if pending:
            if document["foundry"] is not None or document["network"] is not None:
                raise ValueError
            environment = {"AZURE_SUBSCRIPTION_ID": document["subscription"]}
        else:
            if not all(isinstance(document[area], str) for area in _AREA_KEYS):
                raise ValueError
            environment = {
                "AZURE_SUBSCRIPTION_ID": document["subscription"],
                **{key: document[area] for area, key in _AREA_KEYS.items()},
            }
        selection = resolve_resource_groups(environment, allow_pending_root=pending)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ResourceGroupError(
            "The environment resource-group binding is invalid or unreadable. "
            "Restore its recorded state; do not delete it to retarget deployed resources."
        ) from exc
    if document["version"] == 1 and selection.split:
        raise ResourceGroupError(
            "This recorded v1 split binding uses the application-root contract. "
            "Keep the environment on its original release or create a new azd "
            "environment for the Foundry-root contract. Changing variables cannot "
            "migrate its native deployment root."
        )
    return selection


def _same(left: str | None, right: str | None) -> bool:
    return (left or "").casefold() == (right or "").casefold()


def check_binding(
    selection: ResourceGroupSelection,
    bound: ResourceGroupSelection | None,
) -> None:
    """Reject retargeting; a default pending binding can only acquire its root."""
    if bound is None:
        return
    valid = (
        (not bound.subscription or _same(bound.subscription, selection.subscription))
        and (
            (bound.application is None and not selection.split)
            or (
                bound.application is not None
                and all(
                    _same(getattr(bound, area), getattr(selection, area))
                    for area in _AREA_KEYS
                )
            )
        )
    )
    if not valid:
        raise ResourceGroupError(
            "The resource-group selection conflicts with this environment's binding. "
            "Restore the bound subscription/application/Foundry/network destinations "
            "or create a new azd environment. Resource moves and automatic migration "
            "are not supported."
        )


def _save_binding(
    azure_dir: Path, env_name: str, selection: ResourceGroupSelection
) -> None:
    path = binding_path(azure_dir, env_name)
    existing = read_binding(azure_dir, env_name)
    check_binding(selection, existing)
    if existing is not None and (
        existing.application is not None
        or (
            selection.application is None
            and _same(existing.subscription, selection.subscription)
        )
    ):
        return
    document = asdict(selection)
    del document["create_resource_groups"]
    document.update(version=2, environment=env_name)
    rendered = json.dumps(document, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == rendered:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(".json.pending")
    try:
        with staging.open("x", encoding="utf-8", newline="\n") as stream:
            current = read_binding(azure_dir, env_name)
            check_binding(selection, current)
            if current is None or current.application is None:
                stream.write(rendered)
        if current is not None and current.application is not None:
            staging.unlink()
        else:
            staging.replace(path)
    except FileExistsError as exc:
        raise ResourceGroupError(
            "Another resource-group binding write is pending. Finish that operation "
            "and review the environment-local state before retrying."
        ) from exc
    except BaseException:
        staging.unlink(missing_ok=True)
        raise


def _run_az(arguments: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            [resolve_az_command(), *arguments],
            capture_output=True, text=True, check=False, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ResourceGroupError(
            "Azure CLI could not complete the resource-group check. Restore CLI "
            "availability/connectivity and retry with the same selection."
        ) from exc
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _error_code(stderr: str) -> str:
    # Azure CLI diagnostics can include request details; never echo them verbatim.
    match = re.search(r"\(([A-Za-z][A-Za-z0-9]*)\)", stderr)
    return f" ({match.group(1)})" if match else ""


def _exists(name: str, subscription: str) -> bool:
    code, output, error = _run_az([
        "group", "exists", "--name", name, "--subscription", subscription,
        "--output", "tsv", "--only-show-errors",
    ])
    if code or output.lower() not in {"true", "false"}:
        raise ResourceGroupError(
            f"Cannot verify destination resource group '{name}'{_error_code(error)}. "
            "Check resourceGroups/read access in the selected subscription and CLI "
            "connectivity. Authorization errors are not absence; no creation attempted."
        )
    return output.lower() == "true"


def _legacy_deployed(
    environment: Mapping[str, str], env_file: Path,
    selection: ResourceGroupSelection, env_name: str,
    *, check_inventory: bool = False,
) -> bool:
    if any((environment.get(key) or "").strip() for key in _DEPLOYED_MARKERS):
        return True
    config_file = env_file.parent / "config.json"
    if config_file.is_file():
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ResourceGroupError(
                "Cannot verify prior provisioning state. Restore the azd environment "
                "config.json before selecting additional destinations."
            ) from exc
        if not isinstance(config, dict):
            raise ResourceGroupError("Invalid azd environment config.json.")
        if config.get("infra") or config.get("provisioning"):
            return True
    if not check_inventory or not selection.foundry:
        return False
    code, output, error = _run_az([
        "resource", "list", "--resource-group", selection.foundry,
        "--subscription", selection.subscription,
        "--output", "json", "--only-show-errors",
    ])
    if code:
        raise ResourceGroupError(
            f"Cannot verify existing deployment state{_error_code(error)}. Restore "
            "resource read access before selecting additional destinations."
        )
    try:
        resources = json.loads(output)
        if not isinstance(resources, list):
            raise ValueError
        for resource in resources:
            if not isinstance(resource, dict):
                raise ValueError
            tags = resource.get("tags")
            if tags is None:
                continue
            if not isinstance(tags, dict) or not all(
                isinstance(value, str) for value in tags.values()
            ):
                raise ValueError
            if any(
                key.casefold() == "azd-env-name" and value == env_name
                for key, value in tags.items()
            ):
                return True
    except ValueError as exc:
        raise ResourceGroupError("Azure CLI returned invalid deployment-state JSON.") from exc
    return False


def _check_legacy_root_scope(
    selection: ResourceGroupSelection, environment: Mapping[str, str], env_file: Path,
) -> None:
    """Anchor unbound/pending roots only to exact, application-owned ARM IDs."""
    evidence: list[tuple[str, object, str]] = [
        (key, environment.get(key, ""), path)
        for key, path in _APPLICATION_RESOURCE_PATHS.items()
    ]
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.partition("=")
        key = key.strip().removeprefix("export ")
        if separator and key in _APPLICATION_RESOURCE_PATHS:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            evidence.append((key, value, _APPLICATION_RESOURCE_PATHS[key]))
    for key, value, resource_path in evidence:
        if not isinstance(value, str):
            continue
        pattern = _SCOPE_PREFIX + "/providers/" + resource_path
        match = re.fullmatch(pattern, value.strip().rstrip("/"), re.IGNORECASE)
        if not match:
            continue
        subscription, group = match.groups()
        try:
            if _name(group, key) != group:
                continue
        except ResourceGroupError:
            continue
        if not _same(subscription, selection.subscription) or not _same(group, selection.application):
            raise ResourceGroupError(
                f"The application destination conflicts with verifiable persisted deployment scope "
                f"({key}). Restore its original subscription/resource group, or create a "
                "new azd environment; no implicit migration is performed."
            )


def _confirm_group_response(
    output: str, name: str, subscription: str, *, created: bool,
) -> None:
    try:
        result = json.loads(output)
        expected_id = f"/subscriptions/{subscription}/resourceGroups/{name}"
        if not isinstance(result, dict) or not _same(result.get("id"), expected_id):
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        kind = "created" if created else "existing"
        raise ResourceGroupError(
            f"Azure CLI did not confirm the exact {kind} destination '{name}'."
        ) from exc


def prepare_resource_groups(
    environment: Mapping[str, str], azure_dir: Path, env_name: str,
    *, bind_only: bool = False, check_only: bool = False,
) -> ResourceGroupSelection:
    """Bind selection before any create; retain it and partial progress on failure."""
    selected_env = (environment.get("AZURE_ENV_NAME") or "").strip()
    if selected_env and selected_env != env_name:
        raise ResourceGroupError(
            "AZURE_ENV_NAME does not match the selected azd environment. Reload "
            "that environment's values before preparing resource-group destinations."
        )
    validate_application_pe_subnet(environment)
    selection = resolve_resource_groups(
        environment, allow_pending_root=not (bind_only or check_only)
    )
    bound = read_binding(azure_dir, env_name)
    check_binding(selection, bound)
    env_file = env_file_path(azure_dir, env_name)
    if not env_file.is_file():
        raise ResourceGroupError("Selected azd environment has no .env file. Run `azd env select` first.")
    if bound is None or bound.application is None:
        _check_legacy_root_scope(selection, environment, env_file)
    if bound is None and selection.split and (
        bind_only or check_only
        or _legacy_deployed(environment, env_file, selection, env_name)
    ):
        raise ResourceGroupError(
            "An unbound or previously provisioned environment cannot adopt additional "
            "resource-group destinations. Create a new azd environment; no implicit "
            "migration is performed."
        )
    if check_only:
        return selection
    if bind_only or selection.application is None:
        _save_binding(azure_dir, env_name, selection)
        return selection
    existence = {name: _exists(name, selection.subscription) for name in selection.unique_groups}
    if bound is None and selection.split:
        if _legacy_deployed(
            environment, env_file, selection, env_name,
            check_inventory=existence[selection.foundry],
        ):
            raise ResourceGroupError(
                "This environment has an existing deployment without a resource-group "
                "binding. Additional destinations require a new azd environment; "
                "existing resources are not migrated."
            )
    missing = [
        name for name, exists in existence.items()
        if not exists and not _same(name, selection.foundry)
    ]
    if missing and not selection.create_resource_groups:
        raise ResourceGroupError(
            "Additional destination resource groups do not exist: " + ", ".join(missing)
            + ". Have an administrator pre-create them, or explicitly set "
            "CREATE_RESOURCE_GROUPS=true with subscription resourceGroups/write "
            "permission. Native azd root creation is unchanged."
        )
    location = (environment.get("AZURE_LOCATION") or "").strip()
    if missing and (not location or not re.fullmatch(r"[A-Za-z0-9-]+", location)):
        raise ResourceGroupError(
            "AZURE_LOCATION must be a selected Azure region before creating additional resource groups."
        )
    _save_binding(azure_dir, env_name, selection)
    created: list[str] = []
    try:
        for name in missing:
            # Recheck immediately before PUT: a concurrent creator must be reused.
            if _exists(name, selection.subscription):
                continue
            code, output, error = _run_az([
                "group", "create", "--name", name, "--location", location,
                "--subscription", selection.subscription, "--output", "json",
                "--only-show-errors",
            ])
            if code and _error_code(error) in {
                " (InvalidResourceGroupLocation)", " (ResourceGroupAlreadyExists)",
            }:
                # A concurrent creator may have used different metadata. Reuse the
                # exact destination read-only; never retry PUT to "repair" its location.
                read_code, existing, read_error = _run_az([
                    "group", "show", "--name", name, "--subscription", selection.subscription,
                    "--output", "json", "--only-show-errors",
                ])
                if read_code:
                    raise ResourceGroupError(
                        f"Cannot verify concurrently created destination '{name}'"
                        f"{_error_code(read_error)}. Restore resourceGroups/read access "
                        "and connectivity before retrying; no metadata mutation attempted."
                    )
                _confirm_group_response(existing, name, selection.subscription, created=False)
                continue
            if code:
                raise ResourceGroupError(
                    f"Creating additional resource group '{name}' failed{_error_code(error)}. "
                    "Check subscription resourceGroups/write permission and policy; "
                    "no privilege elevation was attempted."
                )
            # Record successful writes even when a malformed response prevents verification.
            created.append(name)
            _confirm_group_response(output, name, selection.subscription, created=True)
    except ResourceGroupError as exc:
        raise ResourceGroupError(
            f"{exc} Additional groups created in this attempt: "
            f"{', '.join(created) if created else 'none'}. "
            "The binding is retained. Retry with the same destinations after fixing "
            "the cause; no automatic rollback or deletion is performed."
        ) from exc
    return selection


def _run_azd(azure_dir: Path, arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["azd", *arguments], cwd=azure_dir.resolve().parent,
            capture_output=True, text=True, check=False, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ResourceGroupError(
            "Cannot access local azd environment settings. Restore Azure Developer "
            "CLI availability and retry; no Azure group creation was attempted."
        ) from exc
    if result.returncode:
        raise ResourceGroupError(
            "Cannot read or save local resource-group defaults in azd. Select the "
            "intended environment and retry; no Azure group creation was attempted."
        )
    return result.stdout


def _default_destination(root: str, suffix: str) -> str:
    candidate = f"{root}-{suffix}"
    if len(candidate) > 90:
        digest = hashlib.sha256(root.casefold().encode("utf-8")).hexdigest()[:16]
        candidate = f"{root[:90 - len(suffix) - 18]}-{digest}-{suffix}"
    return _name(candidate, f"generated {suffix} destination")


def initialize_defaults(
    environment: Mapping[str, str], azure_dir: Path, env_name: str,
) -> dict[str, str]:
    """Persist a new environment's three destinations before any Azure write."""
    selected = (environment.get("AZURE_ENV_NAME") or "").strip()
    if selected and selected != env_name:
        raise ResourceGroupError("AZURE_ENV_NAME does not match the selected azd environment.")
    bound = read_binding(azure_dir, env_name)
    raw = _run_azd(azure_dir, [
        "env", "get-values", "--output", "json", "--environment", env_name,
    ])
    try:
        stored = json.loads(raw)
        if not isinstance(stored, dict):
            raise ValueError
        for key in (*_AREA_KEYS.values(), "AZURE_FOUNDRY_RESOURCE_GROUP",
                    "CREATE_RESOURCE_GROUPS", "AZURE_SUBSCRIPTION_ID",
                    "AZURE_LOCATION", "AZURE_ENV_NAME"):
            if key in stored and not isinstance(stored[key], str):
                raise ValueError
    except (ValueError, TypeError) as exc:
        raise ResourceGroupError("azd returned invalid local resource-group settings.") from exc
    if stored.get("AZURE_ENV_NAME", "").strip() not in ("", env_name):
        raise ResourceGroupError("azd returned a different environment; no defaults were saved.")
    context = {key: value for key, value in stored.items() if isinstance(value, str)}
    context.update(environment)
    if not (context.get("AZURE_RESOURCE_GROUP") or "").strip():
        context["AZURE_RESOURCE_GROUP"] = stored.get("AZURE_RESOURCE_GROUP", "")
    if (context.get("AZURE_ENV_NAME") or env_name).strip() != env_name:
        raise ResourceGroupError("azd returned a different environment; no defaults were saved.")
    if bound is not None:
        return context
    candidate = dict(context)
    root = (context.get("AZURE_RESOURCE_GROUP") or "").strip() or f"rg-{env_name}"
    candidate["AZURE_RESOURCE_GROUP"] = _name(root, "AZURE_RESOURCE_GROUP")
    candidate["AZURE_APP_RESOURCE_GROUP"] = (
        (context.get("AZURE_APP_RESOURCE_GROUP") or "").strip()
        or _default_destination(root, "app")
    )
    candidate["AZURE_NETWORK_RESOURCE_GROUP"] = (
        (context.get("AZURE_NETWORK_RESOURCE_GROUP") or "").strip()
        or _default_destination(root, "network")
    )
    candidate.setdefault("CREATE_RESOURCE_GROUPS", "true")
    selection = resolve_resource_groups(candidate)
    env_file = env_file_path(azure_dir, env_name)
    if not env_file.is_file():
        raise ResourceGroupError("Selected azd environment has no .env file. Run `azd env select` first.")
    if _legacy_deployed(context, env_file, selection, env_name):
        return context
    validate_application_pe_subnet(candidate)
    if _exists(root, selection.subscription) and _legacy_deployed(
        context, env_file, selection, env_name, check_inventory=True,
    ):
        return context
    _check_legacy_root_scope(selection, context, env_file)
    for key in ("AZURE_RESOURCE_GROUP", "AZURE_APP_RESOURCE_GROUP",
                "AZURE_NETWORK_RESOURCE_GROUP", "CREATE_RESOURCE_GROUPS"):
        if stored.get(key) != candidate[key]:
            _run_azd(azure_dir, [
                "env", "set", key, candidate[key], "--environment", env_name, "--no-prompt",
            ])
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--azure-dir", type=Path, default=Path(".azure"))
    parser.add_argument("--env-name")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--bind-only", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--describe", action="store_true")
    args = parser.parse_args(argv)
    try:
        env_name = args.env_name or resolve_env_name(args.azure_dir)
        if args.describe:
            selection = read_binding(args.azure_dir, env_name)
            if selection is None:
                selection = resolve_resource_groups(os.environ, allow_pending_root=True)
        else:
            environment: Mapping[str, str] = os.environ
            if not (args.bind_only or args.check):
                environment = initialize_defaults(environment, args.azure_dir, env_name)
            selection = prepare_resource_groups(
                environment, args.azure_dir, env_name,
                bind_only=args.bind_only, check_only=args.check,
            )
        # Machine-readable stdout only; no environment dump or Azure diagnostics.
        sys.stdout.write(json.dumps(asdict(selection)) + "\n")
        return 0
    except (ResourceGroupError, EnvironmentNotFoundError, OSError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
