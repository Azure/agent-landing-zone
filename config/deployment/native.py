"""Native application selection at the platform boundary (ADR-0034).

No Azure I/O, migration detection, checkpoint replay, or runtime protocol adapter.
The foundation handoff contains provider-returned scheduler metadata, not secrets.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import re
from typing import Mapping
from urllib.parse import urlsplit


def selected(environment: Mapping[str, str]) -> bool:
    """The shipped application lifecycle is native, including unset defaults."""
    return True


class OrchestrationHost(str, Enum):
    HOSTED = "hosted"
    CONTAINER_APPS = "container_apps"


OBSOLETE_SELECTION_KEYS = frozenset({
    "DEPLOYMENT_TOPOLOGY", "DEPLOY_ADMINISTRATIVE_PANEL",
    "DEPLOY_HOSTED_AGENT_ORCHESTRATION", "PRESERVE_CLASSIC_RUNTIME",
    "HOSTED_CUTOVER_COMPLETE", "CHAT_BACKEND",
    "USE_FOUNDRY_HOSTED_AGENTS", "PREPARE_HOSTED_AGENT",
    "DEPLOY_HOSTED_AGENT", "DEPLOY_DURABLE_TASK_SCHEDULER", "HOSTED_AGENT_PREPARED",
})


def boolean(environment: Mapping[str, str], key: str, default: bool = False) -> bool:
    value = environment.get(key, str(default)).strip().lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{key} must be 'true' or 'false'.")
    return value == "true"


@dataclass(frozen=True)
class NativeApplication:
    mode: str
    host: OrchestrationHost
    ingestion: bool
    metadata: bool
    history: bool
    feedback: bool
    private_attachments: bool

    @property
    def publications(self) -> tuple[str, ...]:
        return ("conversational", "workflow") if self.mode == "both" else (self.mode,)

    def settings(self) -> dict[str, str]:
        return {
            "APPLICATION_MODE": self.mode, "ORCHESTRATION_HOST": self.host.value,
            "ENABLE_CHAT_HISTORY": str(self.history).lower(),
            "ENABLE_USER_FEEDBACK": str(self.feedback).lower(),
            "ENABLE_PRIVATE_ATTACHMENTS": str(self.private_attachments).lower(),
        }


def resolve_application(environment: Mapping[str, str]) -> NativeApplication:
    mode = environment.get("APPLICATION_MODE", "conversational").strip().lower()
    host = environment.get("ORCHESTRATION_HOST", "hosted").strip().lower()
    obsolete = sorted(OBSOLETE_SELECTION_KEYS.intersection(environment))
    if obsolete:
        raise ValueError(
            "Obsolete native deployment settings: " + ", ".join(obsolete)
            + ". Remove these settings and select ORCHESTRATION_HOST=hosted|container_apps "
            "and APPLICATION_MODE=conversational|workflow|both. Features are explicit."
        )
    if mode not in {"conversational", "workflow", "both"}:
        raise ValueError("APPLICATION_MODE must be conversational, workflow, or both.")
    if host not in {"hosted", "container_apps"}:
        raise ValueError("ORCHESTRATION_HOST must be hosted or container_apps.")
    history = boolean(environment, "ENABLE_CHAT_HISTORY")
    feedback = boolean(environment, "ENABLE_USER_FEEDBACK")
    private_attachments = boolean(environment, "ENABLE_PRIVATE_ATTACHMENTS")
    if private_attachments and mode == "workflow":
        raise ValueError("ENABLE_PRIVATE_ATTACHMENTS requires conversational or both mode; workflow starts do not accept private attachments.")
    metadata = mode in {"workflow", "both"} or history or feedback or private_attachments
    return NativeApplication(
        mode, OrchestrationHost(host),
        boolean(environment, "DEPLOY_INGESTION_CONTAINER_APP"),
        metadata, history, feedback, private_attachments,
    )


def nl2sql_selected(environment: Mapping[str, str]) -> bool:
    if boolean(environment, "NL2SQL_ENABLED"):
        raise ValueError('Direct NL2SQL is retired. Select DEPLOY_AGENT_APP_MCP=true and MCP_TOOLSETS=["nl2sql"] instead of NL2SQL_ENABLED.')
    return False


def scheduler_settings(environment: Mapping[str, str]) -> dict[str, str]:
    try:
        handoff = json.loads(environment.get("HOSTED_AGENT_DEPLOYMENT", "{}"))
        backend = handoff["durableTask"]
        endpoint = backend["endpoint"]
        hub = backend["taskHubName"]
        resource_id = backend["resourceId"]
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https" or not parsed.hostname
            or not parsed.hostname.endswith(".durabletask.io")
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or parsed.port not in {None, 443}
            or not re.fullmatch(r"[A-Za-z0-9-]{3,64}", hub)
            or not isinstance(resource_id, str)
            or "/providers/microsoft.durabletask/schedulers/" not in resource_id.lower()
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError("Missing or invalid provisioned Durable Task backend; run azd provision. Scheduler endpoints must come from resource outputs.") from None
    return {
        "DURABLE_TASK_SCHEDULER_CONNECTION_STRING": (
            f"Endpoint={endpoint.rstrip('/')};TaskHub={hub};Authentication=ManagedIdentity"
        ),
        "DURABLE_TASK_HUB_NAME": hub,
        "DURABLE_TASK_SCHEDULER_RESOURCE_ID": resource_id,
    }
