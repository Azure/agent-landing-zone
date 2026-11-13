"""Command line: ``python -m config.appdefinition``.

    --validate [PATH]   Validate PATH (file or folder), or the selected
                        definition (AGENTLZ_APP_DEFINITION or the bundled trio).
    --bind              Validate, then bind the azd environment to the
                        definition id (AGENTLZ_APP_ID). Fails on a different id.
    --check-binding     Validate, then fail on a different bound id without writing.
    --assign-roles      Validate, then assign capability-profile roles to every
                        containerapp component identity (postProvision; idempotent).

Exit codes: 0 success, 1 invalid or missing definition, 2 binding error,
3 role assignment error.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

from config import find_repo_root

from .binding import bind, check_binding, env_file_path, resolve_env_name
from .errors import AppDefinitionError, BindingMismatchError, EnvironmentNotFoundError
from .loader import AppDefinition, load_definition, resolve_definition_path
from .validator import validate_definition

LOGGER = logging.getLogger("config.appdefinition")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m config.appdefinition", description="Validate and bind an Agent Landing Zone application definition.")
    parser.add_argument("--validate", nargs="?", const="", metavar="PATH", help="Definition file or folder. Defaults to the selected definition.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--bind", action="store_true", help="Bind the azd environment to the definition id.")
    mode.add_argument("--check-binding", action="store_true", help="Fail when the environment is bound to a different id.")
    parser.add_argument("--assign-roles", action="store_true", help="Assign capability-profile roles to containerapp component identities.")
    parser.add_argument("--env-name", help="azd environment name. Defaults to AZURE_ENV_NAME or the azd default environment.")
    parser.add_argument("--azure-dir", type=Path, help="The .azure folder. Defaults to <repo root>/.azure.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    args = _parser().parse_args(argv)
    if args.validate is None and not (args.bind or args.check_binding or args.assign_roles):
        _parser().error("one of --validate, --bind, --check-binding, or --assign-roles is required")

    try:
        repo_root = find_repo_root()
        path = Path(args.validate) if args.validate else resolve_definition_path(os.environ, repo_root)
        definition = validate_definition(load_definition(path, repo_root=repo_root), repo_root)
        LOGGER.info("Application definition %s (id %s) is valid.", definition.path, definition.id)
    except AppDefinitionError as error:
        LOGGER.error("%s", error)
        return 1
    except FileNotFoundError as error:
        LOGGER.error("%s", error)
        return 1

    if args.bind or args.check_binding:
        code = _binding(args, repo_root, definition.id)
        if code:
            return code
    if args.assign_roles:
        return _assign_roles(definition)
    return 0


def _assign_roles(definition: AppDefinition) -> int:
    from config.deployment.composition import DeploymentTopologyError, resolve_mode
    from config.deployment.metadata import MetadataError
    from config.deployment.setup_settings import load_setup_environment

    from .roles import RoleAssignmentError, assign_roles

    try:
        environment = load_setup_environment(os.environ)
        if definition.id != environment["AGENTLZ_APP_ID"]:
            raise RoleAssignmentError("Application definition differs from the verified foundation application.")
        hosted = resolve_mode(environment).value == "hosted"
        created = assign_roles(definition, environment, hosted_orchestration=hosted)
    except (DeploymentTopologyError, RoleAssignmentError, MetadataError, RuntimeError) as error:
        LOGGER.error("Capability-profile role assignment failed: %s", error)
        return 3
    LOGGER.info("Capability-profile roles are in place (%d created).", len(created))
    return 0


def _binding(args: argparse.Namespace, repo_root: Path, app_id: str) -> int:
    try:
        azure_dir = args.azure_dir or repo_root / ".azure"
        env_name = args.env_name or resolve_env_name(azure_dir)
        env_file = env_file_path(azure_dir, env_name)
        if args.check_binding:
            check_binding(env_file, app_id)
            LOGGER.info("Environment %s matches application %s.", env_name, app_id)
        else:
            result = bind(env_file, app_id)
            verb = "bound to" if result.newly_bound else "already bound to"
            LOGGER.info("Environment %s is %s application %s.", env_name, verb, app_id)
    except (BindingMismatchError, EnvironmentNotFoundError) as error:
        LOGGER.error("%s", error)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
