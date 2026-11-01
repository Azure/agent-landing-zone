"""Read native azd infrastructure selection; no provider environment overrides."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import TypedDict

import yaml

LOGGER = logging.getLogger(__name__)


class ProviderSelection(TypedDict):
    provider: str
    path: str
    module: str
    entrypoint: str


def resolve_provider(project_root: Path) -> ProviderSelection:
    """Validate the selected native entrypoint, preserving azd's Bicep defaults."""
    root = project_root.resolve()
    try:
        project = yaml.safe_load((root / "azure.yaml").read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError("Cannot read root azure.yaml as YAML.") from exc
    if not isinstance(project, dict):
        raise ValueError("Root azure.yaml must be a mapping.")
    infra = project.get("infra", {})
    if not isinstance(infra, dict):
        raise ValueError("azure.yaml infra must be a mapping.")
    provider = infra.get("provider", "bicep")
    if provider not in ("bicep", "terraform"):
        raise ValueError("azure.yaml infra.provider must be bicep or terraform.")
    path = infra.get("path", "infra")
    module = infra.get("module", "main")
    if (
        not isinstance(path, str) or not path.strip() or "${" in path
        or not isinstance(module, str) or not module.strip()
        or any(char in module for char in ("/", "\\", "$", ":"))
        or module in (".", "..")
    ):
        raise ValueError("azure.yaml infra.path/module must be literal directory/module names.")
    directory = (root / path).resolve()
    if not directory.is_relative_to(root):
        raise ValueError("azure.yaml infra.path must stay inside the project root.")
    entrypoint = directory / f"{module}.{ 'bicep' if provider == 'bicep' else 'tf'}"
    if not entrypoint.is_file() or not entrypoint.resolve().is_relative_to(root):
        raise ValueError("The configured infrastructure entrypoint is missing or outside the project root.")
    return {
        "provider": provider, "path": path, "module": module,
        "entrypoint": str(entrypoint.resolve()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", "--project-root", dest="project_root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        sys.stdout.write(json.dumps(resolve_provider(args.project_root)) + "\n")
        return 0
    except ValueError as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
