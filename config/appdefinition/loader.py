"""Locate and load an application definition (FR-015a, FR-015b).

Selection order:

1. ``AGENTLZ_APP_DEFINITION`` (a file, or a folder containing
   ``app-definition.json``), relative paths resolved from the repository root.
2. The bundled trio definition, ``app-definition.json`` at the repository root.

Loading never contacts Azure. Validation lives in :mod:`validator`.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from config import find_repo_root

from .errors import AppDefinitionError, DefinitionNotFoundError

DEFINITION_ENV = "AGENTLZ_APP_DEFINITION"
DEFINITION_FILENAME = "app-definition.json"

KIND_CONTAINER_APP = "containerapp"
KIND_HOSTED_AGENT = "azure.ai.agent"

#: Bundled orchestrator overrides applied in hosted-agent deployment modes.
#: Schema v1 has no per-component hosting switch, so the bundled file declares
#: the orchestrator once and the deployment mode selects its hosting.
BUNDLED_HOSTED_COMPONENT = "orchestrator"
BUNDLED_HOSTED_PATH = "hosted-agent"
BUNDLED_HOSTED_SERVICE = "orchestrator-agent"
#: ``azd-service-name`` tags of the bundled trio's Container Apps
#: (``containerAppsList[].service_name`` in ``main.parameters.json``).
BUNDLED_SERVICE_NAMES = {
    "ui": "frontend",
    "orchestrator": "orchestrator",
    "ingestion": "dataingest",
}


@dataclass(frozen=True)
class AppDefinition:
    """A loaded, not yet validated, application definition."""

    path: Path
    document: dict[str, Any] = field(repr=False)
    bundled: bool

    @property
    def folder(self) -> Path:
        return self.path.parent

    @property
    def id(self) -> str:
        value = self.document.get("id")
        return value if isinstance(value, str) else ""


def resolve_definition_path(
    environment: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Return the selected definition file path; fail when it does not exist."""
    env = os.environ if environment is None else environment
    root = repo_root if repo_root is not None else find_repo_root(environment=env)
    selected = (env.get(DEFINITION_ENV) or "").strip()
    if not selected:
        candidate = root / DEFINITION_FILENAME
        if not candidate.is_file():
            raise DefinitionNotFoundError(
                f"The bundled application definition {candidate} does not exist."
            )
        return candidate.resolve()

    candidate = Path(selected).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    if candidate.is_dir():
        candidate = candidate / DEFINITION_FILENAME
    if not candidate.is_file():
        raise DefinitionNotFoundError(
            f"`{DEFINITION_ENV}` points to `{selected}`, which does not exist "
            f"(expected a file or a folder containing {DEFINITION_FILENAME})."
        )
    return candidate.resolve()


def load_definition(path: Path | str, repo_root: Path | None = None) -> AppDefinition:
    """Read ``path`` as JSON. ``bundled`` is true for the repository-root file."""
    file_path = Path(path)
    if file_path.is_dir():
        file_path = file_path / DEFINITION_FILENAME
    if not file_path.is_file():
        raise DefinitionNotFoundError(
            f"Application definition `{path}` does not exist."
        )
    file_path = file_path.resolve()
    try:
        document = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise AppDefinitionError(
            f"Application definition {file_path} is not valid JSON: "
            f"line {error.lineno}, column {error.colno}: {error.msg}."
        ) from error
    if not isinstance(document, dict):
        raise AppDefinitionError(
            f"Application definition {file_path} must be a JSON object."
        )
    root = repo_root
    if root is None:
        try:
            root = find_repo_root()
        except FileNotFoundError:
            root = None
    bundled = root is not None and file_path == (root / DEFINITION_FILENAME).resolve()
    return AppDefinition(path=file_path, document=document, bundled=bundled)


def load_selected_definition(
    environment: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
) -> AppDefinition:
    env = os.environ if environment is None else environment
    root = repo_root if repo_root is not None else find_repo_root(environment=env)
    return load_definition(resolve_definition_path(env, root), repo_root=root)


def component_service_name(definition: AppDefinition, component: Mapping[str, Any]) -> str:
    """Return the azd service name (``azd-service-name`` tag) of ``component``.

    An explicit ``service`` wins; the bundled trio maps to its historical
    service names; custom components use their ``name``.
    """
    explicit = component.get("service")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    name = str(component.get("name") or "")
    if definition.bundled:
        return BUNDLED_SERVICE_NAMES.get(name, name)
    return name


def effective_components(
    definition: AppDefinition, *, hosted_orchestration: bool,
    deploy_ingestion: bool = True,
) -> list[dict[str, Any]]:
    """Return the components to deploy for the selected deployment mode.

    Custom definitions are returned unchanged, including ingestion when the
    bundled-only switch is false. For the bundled application, an omitted
    ingestion app is excluded before hosting overrides. In a
    hosted-agent mode, the orchestrator becomes an ``azure.ai.agent``
    component served by the ``hosted-agent`` child project; Container App
    only fields (``ingress``, ``resources``) are dropped.
    """
    components = copy.deepcopy(list(definition.document.get("components") or []))
    if definition.bundled and not deploy_ingestion:
        components = [component for component in components if component.get("name") != "ingestion"]
    if not (definition.bundled and hosted_orchestration):
        return components
    for component in components:
        if component.get("name") == BUNDLED_HOSTED_COMPONENT:
            component["kind"] = KIND_HOSTED_AGENT
            component["path"] = BUNDLED_HOSTED_PATH
            component["service"] = BUNDLED_HOSTED_SERVICE
            component.pop("ingress", None)
            component.pop("resources", None)
    return components
