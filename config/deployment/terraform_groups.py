"""Classify and bind native Terraform groups without imperative Azure creation.

The lifecycle must call this instead of Bicep's default prepare path. Common
defaults, validation, legacy evidence, binding and Azure read errors are reused.
Ownership is persisted once and never re-inferred after provision. Down must
consume Terraform state plus the common binding/cleanup guards; it must not
delete BYO destinations. No provider switching/adoption is supported.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import logging
from pathlib import Path
import re
import sys
from typing import Mapping

from config.appdefinition.binding import env_file_path, resolve_env_name
from config.appdefinition.errors import EnvironmentNotFoundError
from config.deployment import resource_groups as groups

LOGGER = logging.getLogger(__name__)
OWNERSHIP_FILENAME = "terraform-resource-groups.json"


def read_group_ownership(
    path: Path, selection: groups.ResourceGroupSelection,
    bound: groups.ResourceGroupSelection | None,
) -> tuple[str, ...] | None:
    if not path.exists():
        return None
    try:
        ownership = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(ownership, dict) or set(ownership) != {"managedResourceGroupNames"}:
            raise ValueError
        names = ownership["managedResourceGroupNames"]
        if (
            not isinstance(names, list) or not all(isinstance(name, str) for name in names)
            or len({name.casefold() for name in names}) != len(names)
            or any(name.casefold() not in {group.casefold() for group in selection.unique_groups} for name in names)
            or bound is None or bound.application is None
        ):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError):
        raise groups.ResourceGroupError(
            "Terraform resource-group ownership is invalid or has no matching "
            "binding. Restore both local records; do not reclassify deployed groups."
        ) from None
    return tuple(names)


def prepare_groups(
    environment: Mapping[str, str], azure_dir: Path, env_name: str,
) -> dict[str, object]:
    """Perform local azd defaults/binding writes and read-only Azure checks."""
    context = groups.initialize_defaults(environment, azure_dir, env_name)
    groups.validate_application_pe_subnet(context)
    selection = groups.resolve_resource_groups(context)
    bound = groups.read_binding(azure_dir, env_name)
    groups.check_binding(selection, bound)
    env_file = env_file_path(azure_dir, env_name)
    if not env_file.is_file():
        raise groups.ResourceGroupError("Selected azd environment has no .env file.")
    ownership_file = env_file.parent / OWNERSHIP_FILENAME
    names = read_group_ownership(ownership_file, selection, bound)
    if names is not None:
        # A missing BYO destination is an error, never a request to adopt/create it.
        managed = {name.casefold() for name in names}
        if any(not groups._exists(name, selection.subscription) for name in selection.unique_groups if name.casefold() not in managed):
            raise groups.ResourceGroupError("A bound BYO resource-group destination is missing; restore it before provisioning.")
        return {**asdict(selection), "ownershipFile": str(ownership_file.resolve())}
    if bound is not None and bound.application is not None:
        raise groups.ResourceGroupError(
            "A resource-group binding exists without Terraform ownership. Restore "
            "the original ownership record, or use a new environment; provider "
            "switching and automatic adoption are not supported."
        )
    groups._check_legacy_root_scope(selection, context, env_file)
    existence = {
        name: groups._exists(name, selection.subscription)
        for name in selection.unique_groups
    }
    if groups._legacy_deployed(
        context, env_file, selection, env_name,
        check_inventory=existence[selection.foundry],
    ):
        raise groups.ResourceGroupError(
            "This environment already has deployment evidence without Terraform "
            "ownership. Use a new environment; no automatic adoption is performed."
        )
    missing = [name for name, exists in existence.items() if not exists]
    if missing and not selection.create_resource_groups:
        raise groups.ResourceGroupError(
            "Requested groups do not exist. Explicit CREATE_RESOURCE_GROUPS=true "
            "authorization is required for Terraform to own new groups."
        )
    if missing and not re.fullmatch(r"[A-Za-z0-9-]+", context.get("AZURE_LOCATION", "")):
        raise groups.ResourceGroupError("AZURE_LOCATION must be selected before Terraform can create groups.")
    ownership = {"managedResourceGroupNames": missing}
    staging = ownership_file.with_suffix(".json.pending")
    try:
        with staging.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(ownership, indent=2) + "\n")
        # Shared binding verifies immutable destinations again before saving.
        groups._save_binding(azure_dir, env_name, selection)
        staging.replace(ownership_file)
    except FileExistsError:
        raise groups.ResourceGroupError(
            "A Terraform group-ownership write is pending. Finish that local "
            "operation before retrying; no Azure group was created."
        ) from None
    return {**asdict(selection), "ownershipFile": str(ownership_file.resolve())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, help="azd env get-values JSON file, or - for stdin.")
    parser.add_argument("--azure-dir", type=Path, default=Path(".azure"))
    parser.add_argument("--env-name")
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.read() if args.environment == "-" else Path(args.environment).read_text(encoding="utf-8-sig")
        try:
            environment = json.loads(raw.lstrip("\ufeff"))
        except ValueError:
            raise groups.ResourceGroupError("Invalid azd environment JSON snapshot.") from None
        if not isinstance(environment, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in environment.items()
        ):
            raise groups.ResourceGroupError("The azd environment snapshot must contain string values.")
        env_name = args.env_name or resolve_env_name(args.azure_dir)
        sys.stdout.write(json.dumps(prepare_groups(environment, args.azure_dir, env_name)) + "\n")
        return 0
    except (ValueError, EnvironmentNotFoundError, OSError) as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
