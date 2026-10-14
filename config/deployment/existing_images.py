"""Preserve deployed Container Apps images across ``azd provision`` (#708).

The landing zone creates every Container App with a placeholder image. Without
this step, re-running ``azd provision`` on an existing environment replaces the
real images published by ``azd deploy`` and takes the apps down until each
component is redeployed. Pre-provision discovers the images currently running
(by ``azd-service-name`` tag) and passes them to the template as
``containerAppsList[].image``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from typing import Iterable, Mapping, MutableMapping, Sequence

LOGGER = logging.getLogger("config.deployment.existing_images")

PLACEHOLDER_IMAGE_PREFIX = "mcr.microsoft.com/dotnet/samples:"
# Must match ``_containerDummyImageName`` in infra/main.bicep.
PLACEHOLDER_IMAGE = f"{PLACEHOLDER_IMAGE_PREFIX}aspnetapp-9.0"
CONTAINERAPP_KIND = "containerapp"
COMPONENT_KINDS = (CONTAINERAPP_KIND, "azure.ai.agent")


def parse_container_app_images(
    payload: object, environment_name: str | None = None
) -> dict[str, str]:
    """Return ``{service_name: image}`` from ``az containerapp list`` JSON."""
    images: dict[str, str] = {}
    if not isinstance(payload, list):
        return images
    for app in payload:
        if not isinstance(app, dict):
            continue
        tags = app.get("tags") or {}
        if not isinstance(tags, dict):
            continue
        service = tags.get("azd-service-name")
        if not service:
            continue
        if environment_name and tags.get("azd-env-name") not in (
            None,
            environment_name,
        ):
            continue
        image = app.get("image")
        if not isinstance(image, str) or not image.strip():
            continue
        image = image.strip()
        if image.startswith(PLACEHOLDER_IMAGE_PREFIX):
            continue
        images[str(service)] = image
    return images


def discover_existing_images(
    resource_group: str,
    subscription: str | None = None,
    environment_name: str | None = None,
) -> dict[str, str]:
    """Query Azure for images already deployed. Missing apps or errors yield ``{}``."""
    az = shutil.which("az")
    if not az or not resource_group:
        return {}
    command: list[str] = [
        az,
        "containerapp",
        "list",
        "-g",
        resource_group,
        "--query",
        "[].{tags:tags,image:properties.template.containers[0].image}",
        "-o",
        "json",
        "--only-show-errors",
    ]
    if subscription:
        command += ["--subscription", subscription]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=180, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if completed.returncode != 0:
        return {}
    try:
        payload = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError:
        return {}
    return parse_container_app_images(payload, environment_name)


def apply_existing_images(
    apps: Sequence[object],
    images: Mapping[str, str],
    selected: Iterable[str] | None = None,
) -> list[str]:
    """Set ``image`` on matching apps; returns the service names updated.

    When ``selected`` is given, only those services are touched.
    """
    allowed = None if selected is None else {str(name) for name in selected}
    updated: list[str] = []
    for app in apps:
        if not isinstance(app, MutableMapping):
            continue
        service = app.get("service_name")
        if allowed is not None and str(service) not in allowed:
            continue
        image = images.get(str(service)) if service else None
        if image and not app.get("image"):
            app["image"] = image
            updated.append(str(service))
    return updated


def placeholder_plan(
    components: Sequence[Mapping[str, object]],
    images: Mapping[str, str],
) -> dict[str, str]:
    """Return ``{component: image}`` for the Container Apps provision creates.

    Only components passed in with ``kind == "containerapp"`` are included;
    ``azure.ai.agent`` components get no Container App (they are created at
    deploy time). A component that already runs a published image keeps it,
    so re-provisioning never resets a deployed image; new ones get
    ``PLACEHOLDER_IMAGE``. Discovered images for components not passed in are
    ignored.
    """
    plan: dict[str, str] = {}
    for component in components:
        kind = component.get("kind")
        name = component.get("name")
        if kind not in COMPONENT_KINDS:
            raise ValueError(
                f"Component {name!r} has unsupported kind {kind!r}; "
                f"expected one of {', '.join(COMPONENT_KINDS)}."
            )
        if kind != CONTAINERAPP_KIND:
            continue
        if not isinstance(name, str) or not name:
            raise ValueError("Every containerapp component needs a name.")
        if name in plan:
            raise ValueError(f"Duplicate containerapp component {name!r}.")
        plan[name] = images.get(name) or PLACEHOLDER_IMAGE
    return plan


def definition_placeholder_plan(
    environment: Mapping[str, str],
    images: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return the placeholder plan for the selected application definition.

    Components come from :func:`config.appdefinition.effective_components` for
    the materialized deployment mode, so a hosted orchestrator is never given a
    Container App. ``images`` maps azd service names to running images; when
    omitted they are discovered from ``AZURE_RESOURCE_GROUP``.
    """
    # Imported lazily: composition imports this module.
    from config.appdefinition import (
        component_service_name,
        effective_components,
        load_selected_definition,
        validate_definition,
    )
    from config.deployment.composition import DeploymentMode, resolve_mode, resolve_ingestion_selection

    definition = load_selected_definition(environment)
    validate_definition(definition)
    hosted = resolve_mode(environment) is not DeploymentMode.CLASSIC
    components = effective_components(
        definition, hosted_orchestration=hosted,
        deploy_ingestion=resolve_ingestion_selection(environment),
    )
    if images is None:
        images = discover_existing_images(
            (environment.get("AZURE_RESOURCE_GROUP") or "").strip(),
            (environment.get("AZURE_SUBSCRIPTION_ID") or "").strip() or None,
            (environment.get("AZURE_ENV_NAME") or "").strip() or None,
        )
    by_component = {
        str(component.get("name")): images[service]
        for component in components
        if (service := component_service_name(definition, component)) in images
    }
    return placeholder_plan(components, by_component)


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m config.deployment.existing_images``: report the placeholder plan.

    Exit codes: 0 success, 1 invalid definition, deployment mode, or component.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    parser = argparse.ArgumentParser(
        prog="python -m config.deployment.existing_images",
        description=(
            "List the Container Apps that provision keeps for the selected "
            "application definition (containerapp components only)."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print the plan as JSON on stdout.")
    args = parser.parse_args(argv)

    from config.appdefinition import AppDefinitionError
    from config.deployment.composition import DeploymentTopologyError

    try:
        plan = definition_placeholder_plan(os.environ)
    except (AppDefinitionError, DeploymentTopologyError, FileNotFoundError, ValueError) as error:
        LOGGER.error("%s", error)
        return 1
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    if not plan:
        LOGGER.info("No containerapp components; no placeholder Container Apps are needed.")
    for name, image in plan.items():
        state = "placeholder (not deployed yet)" if image == PLACEHOLDER_IMAGE else f"keeps {image}"
        LOGGER.info("Container App %s: %s", name, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
