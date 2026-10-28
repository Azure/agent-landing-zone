"""Resolve and materialize the Agent Landing Zone deployment topology (ADR-0001 rev. 5).

This is the single shared CLI/integration point used by both
``scripts/preProvision`` implementations (PowerShell and POSIX shell) so the
fresh-vs-existing default/sticky/conflict decision is made in exactly one
place -- see ``config.deployment.composition.resolve_topology`` for the pure
resolution logic. ``preProvision`` calls this module without ``--describe``
to resolve the topology (performing the Azure CLI lookups needed to detect a
fresh vs. existing environment) and materializes the result into the azd
environment. ``preDeploy`` and ``postProvision`` then call this module with
``--describe`` to read back the already-materialized topology, purely from
the environment, with no further Azure CLI lookups -- avoiding any
duplicated detection logic across hooks.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Mapping

from config.deployment.composition import (
    APP_CONFIG_LABEL,
    DEPLOY_INGESTION_CONTAINER_APP,
    DeploymentMode,
    DeploymentTopologyError,
    HOSTED_CUTOVER_COMPLETE,
    HOSTED_IMAGE_DIGEST_PATTERN,
    PRESERVE_CLASSIC_RUNTIME,
    describe_mode,
    hosted_cutover_ready,
    is_truthy,
    materialized_settings,
    resolve_explicit_topology,
    resolve_mode,
    resolve_cosmos_selection,
    resolve_ingestion_selection,
    resolve_runtime_mode,
    resolve_topology,
    validate_hosted_prerequisites,
    validate_ingestion_selection,
)
from util.azure_cli import resolve_az_command

_PERSISTED_KEYS = (
    DEPLOY_INGESTION_CONTAINER_APP,
    "DEPLOYMENT_TOPOLOGY",
    "DEPLOY_HOSTED_AGENT_ORCHESTRATION",
    "DEPLOY_ADMINISTRATIVE_PANEL",
    "CHAT_BACKEND",
)
_LOCAL_RUNTIME_MARKERS = (
    "CHAT_BACKEND",
    PRESERVE_CLASSIC_RUNTIME,
    HOSTED_CUTOVER_COMPLETE,
    "HOSTED_AGENT_BASE_URL",
    "HOSTED_AGENT_IMAGE_VERSION",
)


@dataclass(frozen=True)
class TopologyResolution:
    mode: DeploymentMode
    preserve_classic_runtime: bool = False
    deploy_ingestion: bool = True


def _local_migration_state(
    environment: Mapping[str, str],
    mode: DeploymentMode,
) -> bool | None:
    """Classify explicit hosted migration without private data-plane I/O."""
    raw_preserve = environment.get(PRESERVE_CLASSIC_RUNTIME)
    if raw_preserve is None:
        backend = (environment.get("CHAT_BACKEND") or "").strip().lower()
        legacy_hosted = bool(
            mode is DeploymentMode.HOSTED_NO_PANEL
            and is_truthy(
                environment.get("DEPLOY_HOSTED_AGENT_ORCHESTRATION")
            )
            and (environment.get("HOSTED_AGENT_BASE_URL") or "").strip()
            and HOSTED_IMAGE_DIGEST_PATTERN.fullmatch(
                (environment.get("HOSTED_AGENT_IMAGE_VERSION") or "").strip()
            )
        )
        if (
            backend == "hosted_agent"
            or hosted_cutover_ready(environment)
            or legacy_hosted
        ):
            return False
        if backend == "orchestrator":
            return mode is not DeploymentMode.CLASSIC
        # An explicit hosted selection without a durable runtime marker may
        # be either a classic migration or incomplete hosted state. Resolve
        # that ambiguity from persisted state and fail closed if it is
        # unavailable.
        return None
    normalized_preserve = raw_preserve.strip().lower()
    if normalized_preserve not in {"true", "false"}:
        raise DeploymentTopologyError(
            f"{PRESERVE_CLASSIC_RUNTIME} must be 'true' or 'false'."
        )
    if is_truthy(normalized_preserve):
        return resolve_runtime_mode(mode, environment) is DeploymentMode.CLASSIC

    backend = (environment.get("CHAT_BACKEND") or "").strip().lower()
    if backend == "orchestrator":
        return mode is not DeploymentMode.CLASSIC
    if backend == "hosted_agent":
        return False
    return None


def _run_az(arguments: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        [resolve_az_command(), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def resource_group_exists(
    name: str | None,
    subscription_id: str | None = None,
) -> bool:
    """Return ``True`` only when ``name`` is non-empty and Azure confirms it exists.

    A fresh azd environment may already have an empty resource group because
    azd creates it before running preprovision. Call
    ``resource_group_has_resources`` when that distinction matters.
    """
    name = (name or "").strip()
    if not name:
        return False
    arguments = ["group", "exists", "--name", name, "--output", "tsv"]
    if (subscription_id or "").strip():
        arguments.extend(["--subscription", subscription_id.strip()])
    returncode, stdout, stderr = _run_az(arguments)
    if returncode != 0:
        raise DeploymentTopologyError(
            "Unable to determine whether the Azure resource group exists; "
            f"topology selection cannot safely continue: {stderr or stdout}"
        )
    normalized = stdout.strip().lower()
    if normalized not in {"true", "false"}:
        raise DeploymentTopologyError(
            "Azure CLI returned an unexpected resource-group existence result: "
            f"{stdout!r}."
        )
    return normalized == "true"


def resource_group_has_resources(
    name: str | None,
    subscription_id: str | None = None,
) -> bool:
    """Return whether an existing resource group contains deployed resources."""
    name = (name or "").strip()
    if not name:
        return False
    arguments = [
        "resource",
        "list",
        "--resource-group",
        name,
        "--query",
        "[0].id",
        "--output",
        "tsv",
    ]
    if (subscription_id or "").strip():
        arguments.extend(["--subscription", subscription_id.strip()])
    returncode, stdout, stderr = _run_az(arguments)
    if returncode != 0:
        raise DeploymentTopologyError(
            "Unable to determine whether the Azure resource group contains "
            f"resources; topology selection cannot safely continue: "
            f"{stderr or stdout}"
        )
    return bool(stdout.strip())


def read_persisted_settings(endpoint: str | None) -> dict[str, str]:
    """Read persisted Agent Landing Zone topology markers, failing closed on access errors.

    A missing endpoint means the environment predates the App Configuration
    output and is handled as unmarked/classic. Once an endpoint is known,
    lookup or parse failures are fatal so an existing hosted environment is
    never mistaken for an unmarked classic environment.
    """
    endpoint = (endpoint or "").strip()
    settings: dict[str, str] = {}
    if not endpoint:
        return settings
    returncode, stdout, stderr = _run_az(
        [
            "appconfig",
            "kv",
            "list",
            "--endpoint",
            endpoint,
            "--label",
            APP_CONFIG_LABEL,
            "--fields",
            "key",
            "value",
            "--output",
            "json",
            "--auth-mode",
            "login",
        ]
    )
    if returncode != 0:
        raise DeploymentTopologyError(
            "Unable to read the existing deployment topology from App "
            "Configuration; topology/application selection cannot safely continue. "
            "Restore access, or set explicit DEPLOYMENT_TOPOLOGY and "
            f"{DEPLOY_INGESTION_CONTAINER_APP} after reviewing migration "
            f"requirements: {stderr or stdout}"
        )
    try:
        values = json.loads(stdout or "[]")
    except json.JSONDecodeError as exc:
        raise DeploymentTopologyError(
            "App Configuration returned invalid JSON while reading the existing "
            "deployment topology."
        ) from exc
    for item in values:
        key = item.get("key")
        value = item.get("value")
        if key in _PERSISTED_KEYS and value is not None:
            settings[key] = str(value)
    return settings


def resolve_environment_topology(
    environment: Mapping[str, str],
    *,
    resource_group_name: str | None = None,
    subscription_id: str | None = None,
    app_config_endpoint: str | None = None,
) -> DeploymentMode:
    # Compatibility API returns only topology. Lifecycle hooks use the full
    # plan so application selection cannot be discarded there.
    return _resolve_environment_plan(
        environment,
        resource_group_name=resource_group_name,
        subscription_id=subscription_id,
        app_config_endpoint=app_config_endpoint,
    ).mode


def resolve_environment_plan(
    environment: Mapping[str, str],
    *,
    resource_group_name: str | None = None,
    subscription_id: str | None = None,
    app_config_endpoint: str | None = None,
) -> TopologyResolution:
    """Resolve component selection with the shared topology detection path."""
    explicit_ingestion = (
        DEPLOY_INGESTION_CONTAINER_APP in environment
        or resolve_ingestion_selection(environment, existing=False)
    )
    # A materialized selection needs no new detection or data-plane lookups.
    if explicit_ingestion:
        enabled = resolve_ingestion_selection(environment)
        validate_ingestion_selection(environment, enabled)
        plan = _resolve_environment_plan(
            environment,
            resource_group_name=resource_group_name,
            subscription_id=subscription_id,
            app_config_endpoint=app_config_endpoint,
        )
    else:
        exists = resource_group_exists(resource_group_name, subscription_id)
        has_runtime_state = any(
            (environment.get(key) or "").strip() for key in _LOCAL_RUNTIME_MARKERS
        )
        # Durable local runtime state is conservative evidence of an existing
        # deployment even when the resource-group output has been lost.
        existing = exists or has_runtime_state
        if exists and not has_runtime_state:
            existing = resource_group_has_resources(resource_group_name, subscription_id)
        persisted = read_persisted_settings(app_config_endpoint) if existing else {}
        enabled = resolve_ingestion_selection(
            environment, existing=existing, persisted_settings=persisted
        )
        validate_ingestion_selection(environment, enabled)
        plan = _resolve_environment_plan(
            environment,
            resource_group_name=resource_group_name,
            subscription_id=subscription_id,
            app_config_endpoint=app_config_endpoint,
            detected_exists=existing,
            detected_has_resources=existing,
            persisted_settings=persisted,
        )
    return TopologyResolution(plan.mode, plan.preserve_classic_runtime, enabled)


def _resolve_environment_plan(
    environment: Mapping[str, str],
    *,
    resource_group_name: str | None = None,
    subscription_id: str | None = None,
    app_config_endpoint: str | None = None,
    detected_exists: bool | None = None,
    detected_has_resources: bool | None = None,
    persisted_settings: Mapping[str, str] | None = None,
) -> TopologyResolution:
    """I/O-aware wrapper around ``resolve_topology`` for use at preProvision time.

    Detects whether the environment is fresh (no resource group or an empty
    group pre-created by azd) or existing, reads any persisted topology markers
    for existing environments, and delegates the actual decision to the pure
    ``resolve_topology`` function. Explicit classic remains a direct rollback.
    Explicit hosted additionally classifies the current deployed runtime so a
    classic-to-hosted migration can retain classic during its prepare-only
    phase without changing the fresh-hosted fail-closed contract.
    """
    explicit = resolve_explicit_topology(environment)
    if explicit is DeploymentMode.CLASSIC:
        return TopologyResolution(explicit)

    rg_exists = (
        resource_group_exists(resource_group_name, subscription_id)
        if detected_exists is None else detected_exists
    )
    has_local_runtime_marker = any(
        (environment.get(key) or "").strip()
        for key in _LOCAL_RUNTIME_MARKERS
    )
    if (
        explicit is not None
        and rg_exists
        and not has_local_runtime_marker
        and not (
            resource_group_has_resources(resource_group_name, subscription_id)
            if detected_has_resources is None else detected_has_resources
        )
    ):
        # azd creates the target resource group before running preprovision.
        # An empty group is therefore still a fresh environment and must not
        # inherit an unrelated process-level App Configuration endpoint.
        return TopologyResolution(explicit)
    if explicit is None and rg_exists and not has_local_runtime_marker:
        # ADR-0001 defines an existing environment without any local topology
        # marker as pre-cutover classic. In particular, do not require a
        # workstation to reach a network-isolated App Configuration data
        # plane merely to preserve that safe state.
        return TopologyResolution(DeploymentMode.CLASSIC)

    materialized_preservation = (
        _local_migration_state(environment, explicit)
        if explicit is not None and rg_exists
        else None
    )
    if materialized_preservation is not None:
        return TopologyResolution(explicit, materialized_preservation)

    persisted = (
        persisted_settings if persisted_settings is not None
        else read_persisted_settings(app_config_endpoint) if rg_exists else {}
    )
    mode = resolve_topology(
        environment,
        resource_group_exists=rg_exists,
        persisted_settings=persisted,
    )
    preserve_classic_runtime = False
    if explicit is not None and rg_exists:
        current_mode = resolve_topology(
            {},
            resource_group_exists=True,
            persisted_settings=persisted,
        )
        preserve_classic_runtime = current_mode is DeploymentMode.CLASSIC
    return TopologyResolution(mode, preserve_classic_runtime)


def _print_materialized(resolution: TopologyResolution) -> None:
    runtime_environment = dict(os.environ)
    runtime_environment[PRESERVE_CLASSIC_RUNTIME] = str(
        resolution.preserve_classic_runtime
    ).lower()
    for key, value in materialized_settings(
        resolution.mode,
        preserve_classic_runtime=resolution.preserve_classic_runtime,
        runtime_mode=resolve_runtime_mode(
            resolution.mode,
            runtime_environment,
        ),
        hosted_cutover_complete=is_truthy(
            os.environ.get(HOSTED_CUTOVER_COMPLETE)
        )
        and not resolution.preserve_classic_runtime,
        deploy_ingestion=resolution.deploy_ingestion,
    ).items():
        print(f"{key}={value}")


def _print_description(mode: DeploymentMode) -> None:
    preserve_classic_runtime = (
        os.environ.get(PRESERVE_CLASSIC_RUNTIME, "").lower() == "true"
    )
    enabled = resolve_ingestion_selection(os.environ)
    validate_ingestion_selection(os.environ, enabled)
    description = describe_mode(
        mode,
        preserve_classic_runtime=preserve_classic_runtime,
        runtime_mode=resolve_runtime_mode(mode, os.environ),
        deploy_ingestion=enabled,
    )
    description["deploy_cosmos_db"] = resolve_cosmos_selection(os.environ)
    print(json.dumps(description))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve the Agent Landing Zone deployment topology (ADR-0001 revision 5)."
        )
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help=(
            "Do not perform any Azure CLI lookups; instead describe, as "
            "JSON, the topology already resolved into the current "
            "environment (DEPLOYMENT_TOPOLOGY / legacy flags). Intended for "
            "preDeploy/postProvision, which run after preProvision has "
            "already materialized the topology into the azd environment."
        ),
    )
    parser.add_argument(
        "--validate-hosted-deploy",
        action="store_true",
        help=(
            "Describe the already-materialized topology and, when hosted is "
            "selected, fail unless the immutable image, delegated scope, and "
            "provisioned Foundry project prerequisites are present."
        ),
    )
    parser.add_argument(
        "--validate-hosted-context",
        action="store_true",
        help=(
            "Describe the already-materialized topology and validate hosted "
            "scope and provisioned Foundry project settings without requiring "
            "an image digest. Used immediately before automatic image "
            "preparation."
        ),
    )
    parser.add_argument(
        "--resource-group-name",
        default=None,
        help=(
            "Resource group name to check for existence. Defaults to "
            "AZURE_RESOURCE_GROUP from the environment."
        ),
    )
    parser.add_argument(
        "--app-config-endpoint",
        default=None,
        help=(
            "App Configuration endpoint to read persisted settings from. "
            "Defaults to APP_CONFIG_ENDPOINT from the environment."
        ),
    )
    parser.add_argument(
        "--subscription-id",
        default=None,
        help=(
            "Subscription containing the resource group. Defaults to "
            "AZURE_SUBSCRIPTION_ID from the environment."
        ),
    )
    args = parser.parse_args()

    try:
        if (
            args.describe
            or args.validate_hosted_deploy
            or args.validate_hosted_context
        ):
            mode = resolve_mode(os.environ)
            if (
                args.validate_hosted_deploy or args.validate_hosted_context
            ) and mode is not DeploymentMode.CLASSIC:
                validate_hosted_prerequisites(
                    os.environ,
                    require_image_digest=not args.validate_hosted_context,
                    require_foundry_project=True,
                )
            _print_description(mode)
        else:
            resource_group_name = args.resource_group_name or os.environ.get(
                "AZURE_RESOURCE_GROUP"
            )
            app_config_endpoint = args.app_config_endpoint or os.environ.get(
                "APP_CONFIG_ENDPOINT"
            )
            subscription_id = args.subscription_id or os.environ.get(
                "AZURE_SUBSCRIPTION_ID"
            )
            resolution = resolve_environment_plan(
                os.environ,
                resource_group_name=resource_group_name,
                subscription_id=subscription_id,
                app_config_endpoint=app_config_endpoint,
            )
            _print_materialized(resolution)
    except DeploymentTopologyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
