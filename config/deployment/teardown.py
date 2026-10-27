"""Prevent azd teardown from deleting resources across shared RG boundaries."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import Mapping, Sequence

from config.appdefinition.binding import resolve_env_name
from config.appdefinition.errors import EnvironmentNotFoundError
from config.deployment.resource_groups import (
    ResourceGroupError,
    read_binding,
    resource_group_for,
)

LOGGER = logging.getLogger(__name__)
RESOURCE_GROUP_KEYS = (
    "AZURE_RESOURCE_GROUP",
    "AZURE_FOUNDRY_RESOURCE_GROUP",
    "AZURE_NETWORK_RESOURCE_GROUP",
)


class TeardownError(ValueError):
    """The selected environment cannot safely use automatic teardown."""


def require_single_resource_group(environment: Mapping[str, str]) -> None:
    root = (environment.get("AZURE_RESOURCE_GROUP") or "").strip()
    overrides = [
        (environment.get(key) or "").strip() for key in RESOURCE_GROUP_KEYS[1:]
    ]
    if not root:
        if any(overrides):
            raise TeardownError(
                "Cannot determine the application's resource group. "
                "Automatic teardown is blocked; inspect the selected azd environment."
            )
        return
    groups = {root.casefold(): root}
    for group in overrides:
        if group:
            groups.setdefault(group.casefold(), group)
    if len(groups) > 1:
        raise TeardownError(
            "azd down is blocked for a deployment spanning multiple resource groups "
            f"({', '.join(groups.values())}). Inventory the deployed resource IDs "
            "and their owners, then obtain explicit approval for manual cleanup. "
            "Do not delete shared resource groups or unrelated resources."
        )


def read_environment(environment_name: str | None = None) -> dict[str, str]:
    azd = shutil.which("azd")
    if not azd:
        raise TeardownError("Azure Developer CLI is required to inspect teardown scope.")
    command = [azd, "env", "get-values", "--output", "json"]
    if environment_name:
        command.extend(["--environment", environment_name])
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        raise TeardownError(
            "Unable to read the selected azd environment; automatic teardown is blocked."
        )
    try:
        values = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise TeardownError("azd returned an invalid environment document.") from exc
    if not isinstance(values, dict):
        raise TeardownError("azd environment values must be an object.")
    environment: dict[str, str] = {}
    for key in (*RESOURCE_GROUP_KEYS, "AZURE_ENV_NAME", "AZURE_SUBSCRIPTION_ID"):
        value = values.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            raise TeardownError(f"azd environment setting {key} must be a string.")
        environment[key] = value
    return environment


def require_safe_teardown(
    environment: Mapping[str, str], azure_dir: Path, environment_name: str | None
) -> None:
    context = dict(environment)
    if environment_name:
        selected = (context.get("AZURE_ENV_NAME") or "").strip()
        if selected and selected != environment_name:
            raise TeardownError("The selected azd environment does not match its values.")
        context["AZURE_ENV_NAME"] = environment_name
    name = resolve_env_name(azure_dir, context)
    bound = read_binding(azure_dir, name)
    if bound is not None and bound.split:
        raise TeardownError(
            "azd down is blocked by this environment's recorded multi-resource-group "
            "binding. Inventory the deployed resource IDs and obtain owner approval "
            "for manual cleanup; changing environment overrides does not authorize deletion."
        )
    if (
        bound is not None and bound.subscription
        and (context.get("AZURE_SUBSCRIPTION_ID") or "").strip().casefold()
        != bound.subscription.casefold()
    ):
        raise TeardownError("The selected subscription differs from the recorded binding.")
    require_single_resource_group(context)
    if bound is not None and bound.application is not None:
        for area in ("application", "foundry", "network"):
            target = getattr(bound, area)
            if target is None or resource_group_for(context, area).casefold() != target.casefold():
                raise TeardownError(
                    "Resource-group settings differ from the recorded deployment binding. "
                    "Restore the environment context before reviewing teardown."
                )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-name", default=os.environ.get("AZURE_ENV_NAME"))
    parser.add_argument("--azure-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        environment = read_environment(args.env_name)
        require_safe_teardown(environment, args.azure_dir, args.env_name)
    except (
        TeardownError, ResourceGroupError, EnvironmentNotFoundError,
        OSError, json.JSONDecodeError,
    ) as exc:
        LOGGER.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
