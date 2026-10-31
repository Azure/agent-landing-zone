"""Native application selection at the platform boundary (ADR-0034).

No Azure I/O, migration detection, checkpoint replay, or runtime protocol adapter.
The foundation handoff contains provider-returned scheduler metadata, not secrets.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Mapping
from urllib.parse import urlsplit


def selected(environment: Mapping[str, str]) -> bool:
    """Legacy library callers remain compatible; lifecycle explicitly selects native."""
    return "APPLICATION_MODE" in environment or "ORCHESTRATION_HOST" in environment


def boolean(environment: Mapping[str, str], key: str, default: bool = False) -> bool:
    value = environment.get(key, str(default)).strip().lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{key} must be 'true' or 'false'.")
    return value == "true"


@dataclass(frozen=True)
class NativeApplication:
    mode: str
    host: str
    topology: str
    ingestion: bool
    metadata: bool

    @property
    def publications(self) -> tuple[str, ...]:
        return ("conversational", "workflow") if self.mode == "both" else (self.mode,)

    def settings(self) -> dict[str, str]:
        return {"APPLICATION_MODE": self.mode, "ORCHESTRATION_HOST": self.host}


def resolve_application(environment: Mapping[str, str]) -> NativeApplication:
    mode = environment.get("APPLICATION_MODE", "conversational").strip().lower()
    host = environment.get("ORCHESTRATION_HOST", "").strip().lower()
    topology = environment.get("DEPLOYMENT_TOPOLOGY", "").strip().lower()
    if mode not in {"conversational", "workflow", "both"}:
        raise ValueError("APPLICATION_MODE must be conversational, workflow, or both.")
    if host and host not in {"hosted", "container_apps"}:
        raise ValueError("ORCHESTRATION_HOST must be hosted or container_apps.")
    mapped = {"classic": "container_apps", "hosted-no-panel": "hosted", "hosted-panel": "hosted"}
    if topology and topology not in mapped:
        raise ValueError("Unknown DEPLOYMENT_TOPOLOGY.")
    signals = [value for value in (host, mapped.get(topology)) if value]
    if "DEPLOY_HOSTED_AGENT_ORCHESTRATION" in environment:
        signals.append("hosted" if boolean(environment, "DEPLOY_HOSTED_AGENT_ORCHESTRATION") else "container_apps")
    if len(set(signals)) > 1:
        raise ValueError("Contradictory ORCHESTRATION_HOST and deployment topology settings; align them before provisioning.")
    host = signals[0] if signals else "hosted"
    panel = boolean(environment, "DEPLOY_ADMINISTRATIVE_PANEL", topology == "hosted-panel")
    if topology and panel != (topology == "hosted-panel"):
        raise ValueError("DEPLOY_ADMINISTRATIVE_PANEL contradicts DEPLOYMENT_TOPOLOGY.")
    if panel and host != "hosted":
        raise ValueError("The administrative panel topology requires Hosted.")
    if boolean(environment, "PRESERVE_CLASSIC_RUNTIME"):
        raise ValueError("Native applications do not support PRESERVE_CLASSIC_RUNTIME; use an explicit deployment, not legacy migration.")
    if environment.get("CHAT_BACKEND", "").strip():
        raise ValueError("Native selection cannot be combined with legacy CHAT_BACKEND. Use a separate native environment; do not migrate or delete the previous deployment's state.")
    history = boolean(environment, "ENABLE_CHAT_HISTORY", panel)
    feedback = boolean(environment, "ENABLE_USER_FEEDBACK")
    metadata = mode in {"workflow", "both"} or history or feedback
    if boolean(environment, "ENABLE_PRIVATE_ATTACHMENTS"):
        raise ValueError("ENABLE_PRIVATE_ATTACHMENTS is not supported by the current native input contract.")
    # Legacy panel is mapped to product history at this boundary, not enabled
    # as a second native runtime. Materialized native topology has no panel.
    topology = "classic" if host == "container_apps" else "hosted-no-panel"
    return NativeApplication(
        mode, host, topology,
        boolean(environment, "DEPLOY_INGESTION_CONTAINER_APP"),
        metadata,
    )


def nl2sql_selected(environment: Mapping[str, str]) -> bool:
    enabled = boolean(environment, "NL2SQL_ENABLED")
    if enabled and environment.get("NL2SQL_SOURCE_REGISTRY", "").strip() != "cosmos":
        raise ValueError("NL2SQL_ENABLED requires the explicit existing NL2SQL_SOURCE_REGISTRY=cosmos catalog.")
    return enabled


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
            f"Endpoint={endpoint.rstrip('/')};TaskHub={hub};Authentication=DefaultAzure"
        ),
        "DURABLE_TASK_HUB_NAME": hub,
        "DURABLE_TASK_SCHEDULER_RESOURCE_ID": resource_id,
    }
