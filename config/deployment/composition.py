"""Compose Agent Landing Zone infrastructure parameters for classic and hosted modes."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Mapping

from config.continuity.settings import public_settings as continuity_public_settings
from config.deployment.existing_images import (
    apply_existing_images,
    discover_existing_images,
)
from config.panel.settings import (
    FEEDBACK_CONTAINER_CONFIG_KEY,
    FEEDBACK_CONTAINER_NAME,
    OWNER_INDEX_CONTAINER_CONFIG_KEY,
    OWNER_INDEX_CONTAINER_NAME,
    public_settings as panel_public_settings,
)


APP_CONFIG_LABEL = "agent-lz"
# Default hosted agent name and image repository (new deployments only, ADR-0018).
HOSTED_AGENT_NAME_DEFAULT = "agent-app-orchestrator"
PRESERVE_CLASSIC_RUNTIME = "PRESERVE_CLASSIC_RUNTIME"
HOSTED_CUTOVER_COMPLETE = "HOSTED_CUTOVER_COMPLETE"
HOSTED_IMAGE_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
HOSTED_STARTUP_COMMAND_DEFAULT = (
    "uvicorn src.api.hosted_entrypoint:app --host 0.0.0.0 --port 8088"
)
HOSTED_RESOURCE_SCOPE_PATTERN = re.compile(
    r"^[^\s/](?:[^\s]*[^\s/])?/\.default$"
)


class DeploymentMode(str, Enum):
    CLASSIC = "classic"
    HOSTED_NO_PANEL = "hosted-no-panel"
    HOSTED_PANEL = "hosted-panel"


_KNOWN_TOPOLOGY_VALUES = {mode.value for mode in DeploymentMode}


class DeploymentTopologyError(ValueError):
    """Base class for Agent Landing Zone deployment-topology resolution failures.

    Raised instead of silently falling back so operators get explicit,
    actionable guidance (see ADR-0001 revision 5) rather than an unexpected
    topology being provisioned or deployed.
    """


class ConflictingTopologySignalsError(DeploymentTopologyError):
    """Raised when explicit or persisted topology signals disagree.

    This is a fail-closed guard: Agent Landing Zone never guesses which of two
    disagreeing signals "wins". The operator must resolve the conflict (in
    the azd environment and/or in App Configuration) and re-run
    provisioning.
    """


def is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "t", "yes", "y"}


def hosted_startup_command(environment: Mapping[str, str]) -> str:
    return (
        environment.get("HOSTED_AGENT_STARTUP_COMMAND")
        or HOSTED_STARTUP_COMMAND_DEFAULT
    )


def hosted_startup_command_sha256(environment: Mapping[str, str]) -> str:
    return hashlib.sha256(
        hosted_startup_command(environment).encode("utf-8")
    ).hexdigest()


def validate_hosted_prerequisites(
    environment: Mapping[str, str],
    *,
    require_image_digest: bool = True,
    require_foundry_project: bool = False,
) -> None:
    """Validate the fail-closed hosted deployment contract."""
    configured_startup_command = (
        environment.get("HOSTED_AGENT_STARTUP_COMMAND") or ""
    ).strip()
    if (
        configured_startup_command
        and configured_startup_command != HOSTED_STARTUP_COMMAND_DEFAULT
    ):
        raise DeploymentTopologyError(
            "Custom HOSTED_AGENT_STARTUP_COMMAND values are not supported by "
            "the azure.ai.agent deployment manifest; use the default hosted "
            "entrypoint."
        )

    scope = (environment.get("HOSTED_AGENT_RESOURCE_SCOPE") or "").strip()
    if not HOSTED_RESOURCE_SCOPE_PATTERN.fullmatch(scope):
        raise DeploymentTopologyError(
            "Hosted mode requires HOSTED_AGENT_RESOURCE_SCOPE as an explicit "
            "delegated-user data-plane scope with a non-empty resource "
            "identifier followed by '/.default'."
        )

    digest = (environment.get("HOSTED_AGENT_IMAGE_VERSION") or "").strip()
    if require_image_digest or digest:
        if not HOSTED_IMAGE_DIGEST_PATTERN.fullmatch(digest):
            raise DeploymentTopologyError(
                "Hosted mode requires HOSTED_AGENT_IMAGE_VERSION as an immutable "
                "OCI digest in sha256:<64 hex characters> form."
            )

    if require_foundry_project:
        missing = [
            name
            for name in (
                "AZURE_AI_PROJECT_ENDPOINT",
                "AZURE_AI_PROJECT_RESOURCE_ID",
            )
            if not (environment.get(name) or "").strip()
        ]
        if missing:
            raise DeploymentTopologyError(
                "Hosted mode requires provisioned Foundry project configuration: "
                + ", ".join(missing)
                + "."
            )


def hosted_cutover_ready(environment: Mapping[str, str]) -> bool:
    """Return whether the successful hosted cutover contract is materialized."""
    endpoint = (environment.get("HOSTED_AGENT_BASE_URL") or "").strip()
    digest = (environment.get("HOSTED_AGENT_IMAGE_VERSION") or "").strip()
    return bool(
        endpoint
        and HOSTED_IMAGE_DIGEST_PATTERN.fullmatch(digest)
        and is_truthy(environment.get(HOSTED_CUTOVER_COMPLETE))
    )


def resolve_runtime_mode(
    mode: DeploymentMode,
    environment: Mapping[str, str],
) -> DeploymentMode:
    """Keep a migrating classic runtime until hosted cutover inputs exist."""
    if mode is DeploymentMode.CLASSIC or not is_truthy(
        environment.get(PRESERVE_CLASSIC_RUNTIME)
    ):
        return mode
    if hosted_cutover_ready(environment):
        return mode
    return DeploymentMode.CLASSIC


def _explicit_flag_topology(
    environment: Mapping[str, str],
) -> DeploymentMode | None:
    """Interpret the legacy hosted/panel boolean-flag pair, if present.

    Returns ``None`` when neither ``DEPLOY_HOSTED_AGENT_ORCHESTRATION`` nor
    ``DEPLOY_ADMINISTRATIVE_PANEL`` is present in ``environment`` -- i.e.
    there is nothing explicit to interpret from this signal. This preserves
    the legacy explicit ``DEPLOY_HOSTED_AGENT_ORCHESTRATION=false`` flag as a
    compatible way to select the classic Container Apps topology.

    A panel flag selects hosted-panel only when hosted orchestration is also
    enabled. A stray panel flag alongside ``hosted=false`` is ignored and the
    result stays classic, matching pre-ADR-0001 behavior.
    """
    hosted_raw = environment.get("DEPLOY_HOSTED_AGENT_ORCHESTRATION")
    panel_raw = environment.get("DEPLOY_ADMINISTRATIVE_PANEL")
    if hosted_raw is None and panel_raw is None:
        return None
    hosted = is_truthy(hosted_raw)
    panel = is_truthy(panel_raw)
    if not hosted:
        return DeploymentMode.CLASSIC
    if panel:
        return DeploymentMode.HOSTED_PANEL
    return DeploymentMode.HOSTED_NO_PANEL


def _explicit_topology_value(
    environment: Mapping[str, str],
) -> DeploymentMode | None:
    """Interpret the canonical ``DEPLOYMENT_TOPOLOGY`` variable, if present."""
    raw = (environment.get("DEPLOYMENT_TOPOLOGY") or "").strip().lower()
    if not raw:
        return None
    if raw not in _KNOWN_TOPOLOGY_VALUES:
        raise DeploymentTopologyError(
            f"Unknown DEPLOYMENT_TOPOLOGY={raw!r}; expected one of: "
            + ", ".join(sorted(_KNOWN_TOPOLOGY_VALUES))
        )
    return DeploymentMode(raw)


def resolve_explicit_topology(
    environment: Mapping[str, str],
    *,
    strict_conflicts: bool = False,
) -> DeploymentMode | None:
    """Resolve any explicit topology signal in ``environment``.

    Returns ``None`` when neither the canonical ``DEPLOYMENT_TOPOLOGY``
    variable nor the legacy ``DEPLOY_HOSTED_AGENT_ORCHESTRATION``/
    ``DEPLOY_ADMINISTRATIVE_PANEL`` pair is present. When both signals are
    present, the canonical ``DEPLOYMENT_TOPOLOGY`` value is the operator
    override and takes precedence over previously materialized compatibility
    flags. Pass ``strict_conflicts=True`` when interpreting persisted App
    Configuration, where disagreement represents ambiguous deployed state
    and must fail closed.
    """
    topology_value = _explicit_topology_value(environment)
    if topology_value is not None and not strict_conflicts:
        return topology_value
    flag_value = _explicit_flag_topology(environment)
    if (
        topology_value is not None
        and flag_value is not None
        and topology_value is not flag_value
        and strict_conflicts
    ):
        raise ConflictingTopologySignalsError(
            "Conflicting deployment-topology signals: DEPLOYMENT_TOPOLOGY="
            f"{topology_value.value!r} does not match the "
            "DEPLOY_HOSTED_AGENT_ORCHESTRATION/DEPLOY_ADMINISTRATIVE_PANEL "
            f"pair, which resolves to {flag_value.value!r}. Set only one of "
            "these signals (or align them) before retrying. See ADR-0001 "
            "for the supported migration procedure between classic and "
            "hosted topologies."
        )
    return topology_value if topology_value is not None else flag_value


def resolve_mode(environment: Mapping[str, str]) -> DeploymentMode:
    """Resolve the deployment mode from explicit signals in ``environment``.

    Kept as a simple, backward-compatible entry point for
    ``compose_parameters``/``appconfig.build_settings``, which run after
    ``preProvision`` has already materialized the resolved topology into the
    environment. When nothing explicit is set, defaults to hosted-no-panel
    (ADR-0001 revision 5's fresh-deployment default); callers that need the
    full fresh-vs-existing/sticky/conflict contract should use
    ``resolve_topology`` instead.
    """
    explicit = resolve_explicit_topology(environment)
    if explicit is not None:
        return explicit
    return DeploymentMode.HOSTED_NO_PANEL


def resolve_topology(
    environment: Mapping[str, str],
    *,
    resource_group_exists: bool | None,
    persisted_settings: Mapping[str, str] | None = None,
) -> DeploymentMode:
    """Resolve the deployment topology per ADR-0001 revision 5.

    This is the single source of truth for the fresh-vs-existing
    default/sticky/conflict contract, intended to be called once, at
    ``preProvision`` time, before any later hook or Bicep composition runs:

    - An explicit signal in ``environment`` (``DEPLOYMENT_TOPOLOGY``, or the
      legacy ``DEPLOY_HOSTED_AGENT_ORCHESTRATION``/
      ``DEPLOY_ADMINISTRATIVE_PANEL`` pair) always wins. This honors a
      deliberate operator request, including an explicit migration between
      topologies -- there is no silent request-time fallback.
    - Otherwise, a genuinely fresh environment (``resource_group_exists`` is
      falsy, i.e. no resource group has been provisioned yet) defaults to
      hosted-no-panel.
    - Otherwise (an existing environment with no explicit signal in the
      current environment), the already-persisted App Configuration
      settings decide: a topology marker recorded there is sticky and is
      honored as-is (including a persisted hosted topology); the absence of
      any marker means a pre-cutover environment, which stays classic;
      internally conflicting persisted signals fail closed with migration
      guidance rather than guessing.
    """
    explicit = resolve_explicit_topology(environment)
    if explicit is not None:
        return explicit

    if not resource_group_exists:
        return DeploymentMode.HOSTED_NO_PANEL

    persisted_signals = persisted_settings or {}
    try:
        persisted = resolve_explicit_topology(
            persisted_signals, strict_conflicts=True
        )
    except ConflictingTopologySignalsError as exc:
        raise ConflictingTopologySignalsError(
            "The existing deployment has conflicting persisted "
            f"deployment-topology settings in App Configuration ({exc}). "
            "Resolve the conflict directly in App Configuration, or set an "
            "explicit DEPLOYMENT_TOPOLOGY in the azd environment, before "
            "re-running provisioning. See ADR-0001 for the supported "
            "migration procedure."
        ) from exc
    backend_raw = (persisted_signals.get("CHAT_BACKEND") or "").strip().lower()
    backend_mode: DeploymentMode | None = None
    if backend_raw:
        if backend_raw == "orchestrator":
            backend_mode = DeploymentMode.CLASSIC
        elif backend_raw == "hosted_agent":
            backend_mode = DeploymentMode.HOSTED_NO_PANEL
        else:
            raise DeploymentTopologyError(
                f"The existing deployment has unknown persisted CHAT_BACKEND="
                f"{backend_raw!r}. Set an explicit DEPLOYMENT_TOPOLOGY after "
                "reviewing the ADR-0001 migration procedure."
            )
    persisted_backend = (
        "orchestrator"
        if persisted is DeploymentMode.CLASSIC
        else "hosted_agent"
        if persisted is not None
        else None
    )
    if (
        persisted_backend is not None
        and backend_mode is not None
        and persisted_backend
        != ("orchestrator" if backend_mode is DeploymentMode.CLASSIC else "hosted_agent")
    ):
        raise ConflictingTopologySignalsError(
            "The existing deployment has conflicting persisted topology and "
            "CHAT_BACKEND settings in App Configuration. Resolve the conflict "
            "or set an explicit DEPLOYMENT_TOPOLOGY after following the "
            "ADR-0001 migration procedure."
        )
    if persisted is not None:
        return persisted
    if backend_mode is not None:
        return backend_mode
    # No persisted topology marker: a pre-cutover, unmarked existing
    # environment stays classic rather than silently adopting the new
    # hosted-by-default template behavior.
    return DeploymentMode.CLASSIC


def describe_mode(
    mode: DeploymentMode,
    *,
    preserve_classic_runtime: bool = False,
    runtime_mode: DeploymentMode | None = None,
) -> dict[str, object]:
    """Describe a resolved mode as the paired settings/flags that agree with it."""
    hosted = mode is not DeploymentMode.CLASSIC
    panel = mode is DeploymentMode.HOSTED_PANEL
    effective_runtime = runtime_mode or mode
    return {
        "topology": mode.value,
        "chat_backend": "hosted_agent" if hosted else "orchestrator",
        "components": list(selected_components(mode)),
        "deploy_hosted_agent_orchestration": hosted,
        "deploy_administrative_panel": panel,
        "preserve_classic_runtime": preserve_classic_runtime,
        "runtime_topology": effective_runtime.value,
        "runtime_chat_backend": (
            "hosted_agent"
            if effective_runtime is not DeploymentMode.CLASSIC
            else "orchestrator"
        ),
    }


def materialized_settings(
    mode: DeploymentMode,
    *,
    preserve_classic_runtime: bool = False,
    runtime_mode: DeploymentMode | None = None,
    hosted_cutover_complete: bool = False,
) -> dict[str, str]:
    """Return the paired settings to materialize into the azd environment.

    Used by ``preProvision`` immediately after resolving the topology, so
    every later hook (``preDeploy``, ``postProvision``) and the App
    Configuration `agent-lz` label agree on the same values -- there is a
    single resolution, materialized once, not re-derived independently by
    each consumer.
    """
    effective_runtime = runtime_mode or (
        DeploymentMode.CLASSIC if preserve_classic_runtime else mode
    )
    description = describe_mode(
        mode,
        preserve_classic_runtime=preserve_classic_runtime,
        runtime_mode=effective_runtime,
    )
    return {
        "DEPLOYMENT_TOPOLOGY": str(description["topology"]),
        "DEPLOY_HOSTED_AGENT_ORCHESTRATION": str(
            effective_runtime is not DeploymentMode.CLASSIC
        ).lower(),
        "DEPLOY_ADMINISTRATIVE_PANEL": str(
            effective_runtime is DeploymentMode.HOSTED_PANEL
        ).lower(),
        "CHAT_BACKEND": str(description["runtime_chat_backend"]),
        PRESERVE_CLASSIC_RUNTIME: str(preserve_classic_runtime).lower(),
        HOSTED_CUTOVER_COMPLETE: str(
            mode is not DeploymentMode.CLASSIC and hosted_cutover_complete
        ).lower(),
    }


def resolve_database_containers(
    mode: DeploymentMode,
    existing_containers: list[dict[str, object]],
    *,
    preserving_classic_runtime: bool = False,
) -> list[dict[str, object]]:
    """Return the exact ``databaseContainersList`` value for ``mode``.

    A small, directly-testable pure function (mirrors ``describe_mode``/
    ``materialized_settings`` in this module, which also take ``mode`` as a
    plain argument) so the panel/no-panel container-list contract can be unit
    tested directly.

    - Classic (or a migrating hosted deployment still preserving the classic
      runtime): the static classic list is unchanged.
    - Hosted/no-panel: no Cosmos containers at all (ADR-0001/0004).
    - Hosted/panel: *only* the two panel metadata containers (owner index,
      feedback) -- never the classic ``conversations``/``datasources``/
      ``prompts``/``mcp`` list -- so panel Cosmos never mixes protected chat
      content with metadata in the shared account/database.
    """
    if preserving_classic_runtime or mode is DeploymentMode.CLASSIC:
        return existing_containers
    if mode is DeploymentMode.HOSTED_PANEL:
        return panel_database_containers()
    return []


def selected_components(mode: DeploymentMode) -> tuple[str, ...]:
    if mode is DeploymentMode.CLASSIC:
        return (
            "agent-app-ui",
            "agent-app-orchestrator",
            "agent-app-ingestion",
        )
    return ("agent-app-ui", "agent-app-ingestion")


def panel_database_containers() -> list[dict[str, object]]:
    """Return the exact, reversible Cosmos containers for hosted/panel mode.

    Used only when ``mode is DeploymentMode.HOSTED_PANEL`` -- see
    ``compose_parameters``. Both containers are partitioned by
    ``/principal_id`` (matching the classic ``conversations`` container
    convention) and carry metadata only: the owner index (conversation
    id/title/timestamps) and feedback (rating/category/comment/message
    reference) -- never message content, citations, or document content
    (ADR-0004). Deliberately distinct from the classic ``conversations``
    chat-content container, and hosted/panel provisions *only* these two
    containers -- not the classic mode's ``conversations``/``datasources``/
    ``prompts``/``mcp`` list -- so switching topologies never mixes protected
    chat content with panel metadata in one container. Each entry's
    ``canonical_name`` is published verbatim to App Configuration (label
    ``agent-lz``) by the generic AILZ database-container-list mechanism,
    matching the exact keys ``agent-app-ui``'s merged panel configuration
    already consumes (``PANEL_OWNER_INDEX_DATABASE_CONTAINER``,
    ``PANEL_FEEDBACK_DATABASE_CONTAINER``). Container-scoped Cosmos RBAC for
    these containers is assigned separately by ``config.panel.setup`` (never
    through the generic account-scope ``containerAppsList`` role loop).
    """
    return [
        {
            "name": OWNER_INDEX_CONTAINER_NAME,
            "canonical_name": OWNER_INDEX_CONTAINER_CONFIG_KEY,
            "partitionKey": "/principal_id",
        },
        {
            "name": FEEDBACK_CONTAINER_NAME,
            "canonical_name": FEEDBACK_CONTAINER_CONFIG_KEY,
            "partitionKey": "/principal_id",
        },
    ]


def _setting(name: str, value: str) -> dict[str, str]:
    return {
        "name": name,
        "value": value,
        "label": APP_CONFIG_LABEL,
        "contentType": "text/plain",
    }


#: Infrastructure roles every custom Container App needs. Data-plane roles
#: come from the component's profiles via ``config.appdefinition --assign-roles``.
CUSTOM_CONTAINER_APP_ROLES = ["AcrPull"]


def requires_hosted_foundation(
    environment: Mapping[str, str], *, hosted_orchestration: bool
) -> bool:
    """Select shared Hosted prerequisites independently of bundled routing.

    Custom Hosted components need the foundation's project-identity registry
    pull grant before deployment. Their per-instance runtime profiles remain
    reconciled by custom deployment; this never selects the bundled agent.
    """
    from config.appdefinition.loader import (
        DEFINITION_ENV,
        KIND_HOSTED_AGENT,
        effective_components,
        load_selected_definition,
    )

    if hosted_orchestration:
        return True
    if not (environment.get(DEFINITION_ENV) or "").strip():
        return False
    definition = load_selected_definition(environment)
    return not definition.bundled and any(
        component.get("kind") == KIND_HOSTED_AGENT
        for component in effective_components(
            definition, hosted_orchestration=hosted_orchestration
        )
    )


def custom_container_apps(
    environment: Mapping[str, str],
    existing_apps: list[object],
    *,
    hosted_orchestration: bool,
) -> list[dict[str, object]]:
    """Return ``containerAppsList`` entries for the selected custom definition.

    The bundled definition is already represented by the static trio in
    ``main.parameters.json``; only a custom definition (``AGENTLZ_APP_DEFINITION``)
    contributes entries. Each entry mirrors the trio's shape so infra creates
    the Container App, its managed identity, and the ``azd-service-name`` tag,
    with the placeholder image until ``azd deploy`` publishes the real one.
    """
    from config.appdefinition.loader import (
        DEFINITION_ENV,
        KIND_CONTAINER_APP,
        component_service_name,
        effective_components,
        load_selected_definition,
    )

    if not (environment.get(DEFINITION_ENV) or "").strip():
        return []
    definition = load_selected_definition(environment)
    if definition.bundled:
        return []
    taken = {
        app.get("service_name") for app in existing_apps if isinstance(app, dict)
    }
    entries: list[dict[str, object]] = []
    for component in effective_components(
        definition, hosted_orchestration=hosted_orchestration
    ):
        if component.get("kind") != KIND_CONTAINER_APP:
            continue
        service = component_service_name(definition, component)
        if not service or service in taken:
            continue
        taken.add(service)
        resources = component.get("resources") or {}
        entries.append(
            {
                "name": None,
                "external": component.get("ingress", "internal") == "external",
                "service_name": service,
                "profile_name": "main",
                "min_replicas": 1,
                "max_replicas": 1,
                "cpu": str(float(resources.get("cpu", 0.5))),
                "memory": str(resources.get("memory", "1.0Gi")),
                "canonical_name": re.sub(r"[^A-Z0-9]", "_", service.upper())
                + "_APP",
                "dapr": {"enabled": False},
                "roles": list(CUSTOM_CONTAINER_APP_ROLES),
            }
        )
    return entries


def compose_parameters(
    source: Mapping[str, object],
    environment: Mapping[str, str],
    *,
    expected_hosted_source_commit: str | None = None,
) -> dict[str, object]:
    result = copy.deepcopy(source)
    parameters = result.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("Parameter document must contain a 'parameters' object.")

    mode = resolve_mode(environment)
    hosted = mode is not DeploymentMode.CLASSIC
    prepare_hosted = requires_hosted_foundation(
        environment, hosted_orchestration=hosted
    )
    panel = mode is DeploymentMode.HOSTED_PANEL
    preserve_classic_runtime = hosted and is_truthy(
        environment.get(PRESERVE_CLASSIC_RUNTIME)
    )

    digest = (environment.get("HOSTED_AGENT_IMAGE_VERSION") or "").strip()
    generated_source_commit = (
        environment.get("HOSTED_AGENT_IMAGE_SOURCE_COMMIT") or ""
    ).strip()
    generated_startup_command_sha256 = (
        environment.get("HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256") or ""
    ).strip()
    deploy_hosted = hosted and bool(digest)
    runtime_mode = resolve_runtime_mode(mode, environment)
    preserving_classic_runtime = (
        preserve_classic_runtime
        and runtime_mode is DeploymentMode.CLASSIC
    )
    runtime_hosted = runtime_mode is not DeploymentMode.CLASSIC

    if deploy_hosted:
        validate_hosted_prerequisites(environment)
        if (
            generated_source_commit
            and expected_hosted_source_commit
            and generated_source_commit.lower()
            != expected_hosted_source_commit.lower()
        ):
            raise DeploymentTopologyError(
                "The generated HOSTED_AGENT_IMAGE_VERSION was built from "
                f"{generated_source_commit}, but manifest.json now pins "
                f"{expected_hosted_source_commit}. Run the hosted image "
                "preparation command again before provisioning the deploy "
                "handoff."
            )
        if (
            generated_source_commit
            and generated_startup_command_sha256
            and generated_startup_command_sha256
            != hosted_startup_command_sha256(environment)
        ):
            raise DeploymentTopologyError(
                "The generated HOSTED_AGENT_IMAGE_VERSION does not match "
                "the configured HOSTED_AGENT_STARTUP_COMMAND. Run the hosted "
                "image preparation command again before provisioning the "
                "deploy handoff."
            )
    elif hosted:
        validate_hosted_prerequisites(
            environment,
            require_image_digest=False,
        )

    parameters["prepareHostedAgent"] = {"value": prepare_hosted}
    if prepare_hosted and not hosted:
        # Custom Hosted preparation requires foundation pull, not additional
        # operator privilege. Bundled/foundation callers retain their default.
        parameters["grantHostedAgentProjectManager"] = {"value": False}
    parameters["deployHostedAgent"] = {"value": deploy_hosted}
    parameters["deployCosmosDb"] = {
        "value": mode is DeploymentMode.CLASSIC
        or panel
        or preserving_classic_runtime
    }
    if hosted and is_truthy(environment.get("NETWORK_ISOLATION")):
        parameters["deployAcrTaskAgentPool"] = {"value": True}

    if hosted:
        parameters["hostedAgent"] = {
            "value": {
                "name": (
                    environment.get("HOSTED_AGENT_NAME")
                    or HOSTED_AGENT_NAME_DEFAULT
                ),
                "image": (
                    environment.get("HOSTED_AGENT_IMAGE")
                    or HOSTED_AGENT_NAME_DEFAULT
                ),
                "version": digest,
                "startupCommand": (
                    hosted_startup_command(environment)
                ),
                "runtime": {
                    "cpu": environment.get("HOSTED_AGENT_CONTAINER_CPU") or "2",
                    "memory": (
                        environment.get("HOSTED_AGENT_CONTAINER_MEMORY") or "4Gi"
                    ),
                },
                "protocols": [
                    {
                        "protocol": "responses",
                        "version": (
                            environment.get(
                                "HOSTED_AGENT_RESPONSES_PROTOCOL_VERSION"
                            )
                            or "2.0.0"
                        ),
                    },
                    {
                        "protocol": "invocations",
                        "version": (
                            environment.get(
                                "HOSTED_AGENT_INVOCATIONS_PROTOCOL_VERSION"
                            )
                            or "1.0.0"
                        ),
                    },
                ],
            }
        }

    apps_parameter = parameters.get("containerAppsList")
    if not isinstance(apps_parameter, dict) or not isinstance(
        apps_parameter.get("value"), list
    ):
        raise ValueError("containerAppsList must contain an array value.")

    apps = apps_parameter["value"]
    if hosted and not preserving_classic_runtime:
        apps = [
            app
            for app in apps
            if isinstance(app, dict) and app.get("service_name") != "orchestrator"
        ]
    if hosted and not preserving_classic_runtime:
        # Neither hosted topology grants Cosmos RBAC to dataingest through
        # the generic account-scope role loop. Hosted/no-panel has no Cosmos
        # at all; hosted/panel assigns dataingest a narrow, container-scoped
        # Data Reader role (aggregate overview counts only) exclusively via
        # config.panel.setup, never the account-wide Data Contributor role
        # this static list otherwise grants in classic mode.
        for app in apps:
            if app.get("service_name") == "dataingest":
                app["roles"] = [
                    role
                    for role in app.get("roles", [])
                    if role != "CosmosDBBuiltInDataContributor"
                ]
    apps.extend(custom_container_apps(environment, apps, hosted_orchestration=hosted))
    parameters["containerAppsList"] = {"value": apps}
    if hosted and not preserving_classic_runtime:
        # The orchestrator API key only protects classic UI-to-orchestrator
        # calls. Hosted mode authenticates with Entra tokens, so no key is
        # created in Key Vault or referenced from App Configuration.
        parameters["useCAppAPIKey"] = {"value": False}

    databases_parameter = parameters.get("databaseContainersList")
    existing_containers = (
        databases_parameter.get("value")
        if isinstance(databases_parameter, dict)
        else None
    )
    parameters["databaseContainersList"] = {
        "value": resolve_database_containers(
            mode,
            existing_containers if isinstance(existing_containers, list) else [],
            preserving_classic_runtime=preserving_classic_runtime,
        )
    }

    parameters["additionalAppConfigurationSettings"] = {
        "value": [
            _setting(
                "DEPLOY_HOSTED_AGENT_ORCHESTRATION",
                str(runtime_hosted).lower(),
            ),
            _setting("PREPARE_HOSTED_AGENT", str(prepare_hosted).lower()),
            _setting("DEPLOY_HOSTED_AGENT", str(deploy_hosted).lower()),
            _setting("HOSTED_AGENT_PREPARED", str(prepare_hosted).lower()),
            _setting(
                "DEPLOY_ADMINISTRATIVE_PANEL",
                str(runtime_mode is DeploymentMode.HOSTED_PANEL).lower(),
            ),
            _setting("DEPLOYMENT_TOPOLOGY", runtime_mode.value),
            _setting(
                "HOSTED_AGENT_BASE_URL",
                environment.get("HOSTED_AGENT_BASE_URL", ""),
            ),
            _setting(
                "HOSTED_AGENT_RESOURCE_SCOPE",
                environment.get("HOSTED_AGENT_RESOURCE_SCOPE", ""),
            ),
            _setting(
                "HOSTED_AGENT_IMAGE_VERSION",
                environment.get("HOSTED_AGENT_IMAGE_VERSION", ""),
            ),
            _setting(
                "HOSTED_AGENT_SSE_IDLE_TIMEOUT_SECONDS",
                environment.get(
                    "HOSTED_AGENT_SSE_IDLE_TIMEOUT_SECONDS", "60"
                ),
            ),
            *[
                _setting(name, value)
                for name, value in continuity_public_settings(environment).items()
            ],
            *[
                _setting(name, value)
                for name, value in panel_public_settings(environment).items()
            ],
            # The routing selector is intentionally last so endpoint and
            # immutable-image prerequisites materialize before cutover.
            _setting(
                "CHAT_BACKEND",
                "hosted_agent" if runtime_hosted else "orchestrator",
            ),
        ]
    }
    return result


def compose_file(
    input_path: Path,
    output_path: Path,
    environment: Mapping[str, str],
    *,
    expected_hosted_source_commit: str | None = None,
    existing_images: Mapping[str, str] | None = None,
) -> DeploymentMode:
    source = json.loads(input_path.read_text(encoding="utf-8-sig"))
    composed = compose_parameters(
        source,
        environment,
        expected_hosted_source_commit=expected_hosted_source_commit,
    )
    if existing_images:
        apps = composed["parameters"]["containerAppsList"]["value"]
        for service in apply_existing_images(apps, existing_images):
            print(f"Preserving deployed image for {service}.", file=sys.stderr)
    output_path.write_text(
        json.dumps(composed, indent=2) + "\n",
        encoding="utf-8",
    )
    return resolve_mode(environment)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hosted-source-commit", default=None)
    parser.add_argument(
        "--no-preserve-images",
        action="store_true",
        help="Do not keep currently deployed Container Apps images (#708).",
    )
    args = parser.parse_args()

    existing_images: dict[str, str] = {}
    if not args.no_preserve_images and not is_truthy(
        os.environ.get("RESET_CONTAINER_APP_IMAGES")
    ):
        existing_images = discover_existing_images(
            os.environ.get("AZURE_RESOURCE_GROUP", ""),
            os.environ.get("AZURE_SUBSCRIPTION_ID") or None,
            os.environ.get("AZURE_ENV_NAME") or None,
        )

    mode = compose_file(
        args.input,
        args.output,
        os.environ,
        expected_hosted_source_commit=args.hosted_source_commit,
        existing_images=existing_images,
    )
    print(mode.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
