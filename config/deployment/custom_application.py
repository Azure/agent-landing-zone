"""Deploy one custom service with an immutable image and private ACR builds."""

from __future__ import annotations

import argparse
import copy
import logging
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping
from uuid import uuid4

import yaml

from config.appdefinition import AppDefinitionError, load_definition, validate_definition
from config.appdefinition.loader import KIND_CONTAINER_APP, KIND_HOSTED_AGENT, component_service_name
from config.appdefinition.roles import assign_hosted_roles
from config.containerapps.registry import configure_service_registry
from config.deployment.composition import is_truthy
from config.deployment.hosted_image import (
    build_source_image,
    validate_acr_agent_pool,
    validate_digest,
)
from config.deployment.private_network import check_stage
from config.deployment.hosted_access import discover_instance
from config.deployment.context import registry_resource_group
from util.azure_cli import resolve_az_command

LOGGER = logging.getLogger("config.deployment.custom_application")


def _expand(value: str, environment: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match[1]
        result = (environment.get(name) or "").strip()
        if not result:
            raise ValueError(f"Image requires environment variable {name}.")
        return result

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", replace, value)


def prepare_image(
    component: Mapping[str, Any],
    service: Mapping[str, Any],
    folder: Path,
    environment: Mapping[str, str],
) -> str | None:
    """Keep normal azd builds, except pins and isolated Docker source builds."""
    source = component["source"]
    pin = source.get("imageDigest")
    isolated = is_truthy(environment.get("NETWORK_ISOLATION"))
    if pin:
        digest = validate_digest(pin, name="source.imageDigest")
        image = _expand(str(service.get("image") or ""), environment)
        if not re.fullmatch(
            r"[a-z0-9.-]+(?::[0-9]+)?/[a-z0-9._/-]+(?::[A-Za-z0-9_.-]+|@sha256:[0-9a-f]{64})?",
            image,
        ):
            raise ValueError("source.imageDigest requires a qualified service image in azure.yaml.")
        repository = image.split("@", 1)[0]
        last_slash = repository.rfind("/")
        if ":" in repository[last_slash:]:
            repository = repository[:repository.rfind(":")]
        return f"{repository}@{digest}"
    source_dir = (folder / component["path"]).resolve()
    actual = subprocess.run(
        ["git", "-C", str(source_dir), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if actual.lower() != source["commit"].lower():
        raise ValueError("Custom source HEAD does not match source.commit.")
    if not isolated:
        return None
    if service.get("language") != "docker":
        raise ValueError(
            "Isolated custom source builds require language: docker or source.imageDigest."
        )
    docker = service.get("docker") or {}
    unsupported = set(docker) - {"remoteBuild", "path", "context"}
    if unsupported:
        raise ValueError(
            "Isolated custom builds cannot preserve these docker options: "
            + ", ".join(sorted(unsupported))
            + ". Supply a prebuilt source.imageDigest instead."
        )
    project_dir = (folder / str(service.get("project") or ".")).resolve()
    if source_dir != project_dir:
        raise ValueError("The service project must match the pinned component path.")
    if docker.get("path", "Dockerfile") != "Dockerfile" or docker.get("context", ".") != ".":
        raise ValueError(
            "Isolated custom builds require Dockerfile and context '.' in the component path; "
            "supply a prebuilt source.imageDigest for another layout."
        )
    registry_endpoint = (
        environment.get("AZURE_CONTAINER_REGISTRY_ENDPOINT")
        or environment.get("CONTAINER_REGISTRY_LOGIN_SERVER") or ""
    ).strip()
    pool = (environment.get("ACR_TASK_AGENT_POOL") or "").strip()
    group = registry_resource_group(environment)
    if not registry_endpoint or not pool or not group:
        raise ValueError(
            "Isolated custom builds require the registry endpoint, "
            "ACR_TASK_AGENT_POOL and AZURE_RESOURCE_GROUP."
        )
    registry = registry_endpoint.split(".", 1)[0]
    azure_cli = resolve_az_command()
    check_stage(environment, "hosted-build")
    validate_acr_agent_pool(
        registry=registry, resource_group=group, agent_pool=pool, azure_cli=azure_cli,
    )
    image_name = f"agent-landing-zone/custom/{component['name']}"
    digest = build_source_image(
        registry=registry, source_dir=source_dir, image_name=image_name,
        image_tag=f"{actual[:12]}-{uuid4().hex[:12]}",
        agent_pool=pool, azure_cli=azure_cli,
    )
    return f"{registry_endpoint}/{image_name}@{digest}"


def deploy_service(definition_path: str, name: str, environment: Mapping[str, str]) -> str | None:
    definition = validate_definition(load_definition(definition_path))
    if definition.bundled:
        raise ValueError("Custom deployment cannot deploy a bundled component.")
    components = [item for item in definition.document["components"] if item["name"] == name]
    if len(components) != 1:
        raise ValueError(f"No unique custom component named {name}.")
    env_name = (environment.get("AZURE_ENV_NAME") or "").strip()
    if not env_name:
        raise ValueError("AZURE_ENV_NAME is required for custom deployment.")
    path = definition.folder / "azure.yaml"
    original = path.read_bytes()
    project = yaml.safe_load(original.decode("utf-8-sig"))
    service = project["services"][name]
    agent_name = service.get("name")
    if components[0]["kind"] == KIND_HOSTED_AGENT and (
        not isinstance(agent_name, str) or not agent_name.strip()
    ):
        raise ValueError("Custom hosted service requires an explicit agent name.")
    image = prepare_image(components[0], service, definition.folder, environment)
    if components[0]["kind"] == KIND_CONTAINER_APP:
        configure_service_registry(component_service_name(definition, components[0]), image, environment)
    try:
        if image:
            rendered = copy.deepcopy(project)
            rendered_service = rendered["services"][name]
            rendered_service["image"] = image
            rendered_service["docker"] = {"imagePassthrough": True}
            path.write_text(yaml.safe_dump(rendered, sort_keys=False), encoding="utf-8")
            LOGGER.info("Deploying custom service %s with immutable image %s", name, image)
        subprocess.run(
            ["azd", "deploy", name, "--environment", env_name, "--no-prompt"],
            cwd=definition.folder, env={**os.environ, **environment}, check=True,
        )
    finally:
        if image:
            path.write_bytes(original)
    if components[0]["kind"] == KIND_HOSTED_AGENT:
        instance = discover_instance(environment, name=agent_name)
        assign_hosted_roles(components[0], instance.principal_id, environment)
        LOGGER.info(
            "Verified capability-profile assignments for hosted service %s version %s.",
            name, instance.agent_version,
        )
    return image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--environment", required=True)
    args = parser.parse_args(argv)
    try:
        deploy_service(args.definition, args.service, {**os.environ, "AZURE_ENV_NAME": args.environment})
    except (AppDefinitionError, ValueError, RuntimeError, OSError, subprocess.CalledProcessError,
            yaml.YAMLError) as error:
        LOGGER.error("Custom service deployment failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
