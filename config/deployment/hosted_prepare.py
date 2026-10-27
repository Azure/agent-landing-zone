"""Prepare and materialize the immutable hosted-agent image contract."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from config.deployment.composition import (
    HOSTED_AGENT_NAME_DEFAULT,
    DeploymentMode,
    hosted_startup_command,
    hosted_startup_command_sha256,
    is_truthy,
    resolve_mode,
    validate_hosted_prerequisites,
)
from config.deployment.hosted_image import prepare_hosted_image
from config.deployment.private_network import check_stage
from config.deployment.context import registry_resource_group
from util.azure_cli import resolve_az_command


def _required(environment: Mapping[str, str], name: str) -> str:
    value = (environment.get(name) or "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable {name}.")
    return value


# Matched by suffix so the pin survives the component repository renames (T059).
ORCHESTRATOR_SUFFIX = "-orchestrator"


def _orchestrator_component(manifest: Mapping[str, object]) -> dict[str, str]:
    components = manifest.get("components")
    if not isinstance(components, list):
        raise ValueError("manifest.json must contain a components array.")
    for component in components:
        if (
            isinstance(component, dict)
            and str(component.get("name") or "").endswith(ORCHESTRATOR_SUFFIX)
        ):
            repo = str(component.get("repo") or "").strip()
            source_ref = str(
                component.get("tag") or component.get("branch") or ""
            ).strip()
            commit = str(component.get("commit") or "").strip()
            if not repo or not source_ref or not commit:
                break
            return {
                "repo": repo,
                "source_ref": source_ref,
                "commit": commit,
            }
    raise ValueError(
        "manifest.json must pin the *-orchestrator component with a repository, "
        "tag or branch, and full commit."
    )


def prepare_environment(
    environment: Mapping[str, str],
    manifest: Mapping[str, object],
    *,
    image_version_override: str | None = None,
) -> tuple[str | None, str | None]:
    """Return ``(digest, generated_source_commit)`` for the selected topology."""
    if resolve_mode(environment) is DeploymentMode.CLASSIC:
        return None, None

    if not is_truthy(environment.get("HOSTED_AGENT_PREPARED")):
        raise ValueError(
            "Hosted prerequisites are not provisioned. Run azd provision before "
            "preparing the hosted image."
        )
    validate_hosted_prerequisites(
        environment,
        require_image_digest=False,
        require_foundry_project=True,
    )

    component = _orchestrator_component(manifest)
    source_commit = component["commit"]
    if image_version_override:
        digest = prepare_hosted_image(
            image_version=image_version_override,
            registry="",
            registry_endpoint="",
            image_name=(
                environment.get("HOSTED_AGENT_IMAGE")
                or HOSTED_AGENT_NAME_DEFAULT
            ),
            source_repo="",
            source_ref="",
            source_commit="",
        )
        return digest, None

    current_digest = (
        environment.get("HOSTED_AGENT_IMAGE_VERSION") or ""
    ).strip()
    generated_commit = (
        environment.get("HOSTED_AGENT_IMAGE_SOURCE_COMMIT") or ""
    ).strip()
    generated_startup_command_sha256 = (
        environment.get("HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256") or ""
    ).strip()

    if current_digest and not generated_commit:
        digest = prepare_hosted_image(
            image_version=current_digest,
            registry="",
            registry_endpoint="",
            image_name=(
                environment.get("HOSTED_AGENT_IMAGE")
                or HOSTED_AGENT_NAME_DEFAULT
            ),
            source_repo="",
            source_ref="",
            source_commit="",
        )
        return digest, None

    if (
        current_digest
        and generated_commit.lower() == source_commit.lower()
        and generated_startup_command_sha256
        == hosted_startup_command_sha256(environment)
    ):
        digest = prepare_hosted_image(
            image_version=current_digest,
            registry="",
            registry_endpoint="",
            image_name=(
                environment.get("HOSTED_AGENT_IMAGE")
                or HOSTED_AGENT_NAME_DEFAULT
            ),
            source_repo="",
            source_ref="",
            source_commit="",
        )
        return digest, source_commit

    registry_endpoint = _required(
        environment, "AZURE_CONTAINER_REGISTRY_ENDPOINT"
    )
    registry = registry_endpoint.split(".", maxsplit=1)[0]
    if not registry:
        raise ValueError(
            "AZURE_CONTAINER_REGISTRY_ENDPOINT does not contain a registry name."
        )

    network_isolation = is_truthy(environment.get("NETWORK_ISOLATION"))
    agent_pool = (environment.get("ACR_TASK_AGENT_POOL") or "").strip()
    if network_isolation and not agent_pool:
        raise ValueError(
            "Automatic hosted image preparation with NETWORK_ISOLATION=true "
            "requires the dedicated ACR_TASK_AGENT_POOL provisioned by the "
            "landing zone."
        )

    check_stage(environment, "hosted-build")
    digest = prepare_hosted_image(
        image_version=None,
        registry=registry,
        registry_endpoint=registry_endpoint,
        image_name=(
            environment.get("HOSTED_AGENT_IMAGE")
            or HOSTED_AGENT_NAME_DEFAULT
        ),
        source_repo=component["repo"],
        source_ref=component["source_ref"],
        source_commit=source_commit,
        startup_command=hosted_startup_command(environment),
        agent_pool=agent_pool or None,
        resource_group=registry_resource_group(environment),
        azure_cli=resolve_az_command(),
    )
    return digest, source_commit


def persist_digest(
    environment: Mapping[str, str],
    digest: str,
    generated_source_commit: str | None,
) -> None:
    environment_name = _required(environment, "AZURE_ENV_NAME")
    azd = shutil.which("azd") or "azd"
    # Clear the digest first and write it last. Any interrupted sequence then
    # remains fail-closed instead of accepting a generated digest without its
    # manifest source provenance.
    values = (
        ("HOSTED_AGENT_IMAGE_VERSION", ""),
        (
            "HOSTED_AGENT_IMAGE_SOURCE_COMMIT",
            generated_source_commit or "",
        ),
        (
            "HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256",
            (
                hosted_startup_command_sha256(environment)
                if generated_source_commit
                else ""
            ),
        ),
        ("HOSTED_AGENT_IMAGE_VERSION", digest),
    )
    for name, value in values:
        subprocess.run(
            [
                azd,
                "env",
                "set",
                name,
                value,
                "--environment",
                environment_name,
                "--no-prompt",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("manifest.json"),
    )
    parser.add_argument(
        "--image-version",
        default=None,
        help=(
            "Optional canonical immutable digest override. This skips image "
            "builds and clears generated-image provenance."
        ),
    )
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        digest, generated_source_commit = prepare_environment(
            os.environ,
            manifest,
            image_version_override=args.image_version,
        )
        if digest is None:
            print("Classic topology selected; hosted image preparation skipped.")
            return 0
        persist_digest(os.environ, digest, generated_source_commit)
        print(digest)
        print(
            "Hosted image digest materialized. Run azd provision again to "
            "materialize the deploy handoff, then run azd deploy.",
            file=sys.stderr,
        )
        return 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"Hosted image preparation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
