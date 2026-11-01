"""Public hosted-panel settings shared by deployment publishers.

Mirrors ``config.continuity.settings``: every key here is safe to publish
unconditionally (App Configuration label ``agent-lz``) because it is inert
unless ``DEPLOY_ADMINISTRATIVE_PANEL`` and ``PANEL_HISTORY_ENABLED`` are both
``true`` (see ADR-0004 and the merged ``agent-app-ui`` ``panel_config.py``,
which this module's key names and defaults match exactly -- no duplicate or
invented keys).

``PANEL_HISTORY_OWNER_BINDING_VALIDATED`` is forced to ``false`` here the
same way ``HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED`` is forced to
``false`` in ``config.continuity.settings``: it is this ADR's own
environment-evidence gate for the panel's list/read call path, and no live
verification procedure for that gate ships in this change (only the
platform contract -- containers, RBAC, App Configuration keys, and the
versioned schema). Flipping it to ``true`` is out of scope until a
dedicated verification procedure exists; until then the panel safely stays
on its ``owner_index`` pre-gate/fallback mechanism, which is fully
functional and never itself returns an error for the unmet gate.

``PANEL_OPERATOR_SURFACES_ENABLED``, ``PANEL_OPERATOR_APP_ROLE``, and
``PANEL_OPERATOR_GROUP_ID`` mirror the exact key names and safe defaults the
merged ``agent-app-ingestion`` operator-facing overview/corpus-curation
surfaces consume (PR #274, merge ``5569dd6af3ecb317e1037108cb21859f1b2185a1``
-- see ``api/panel_operator.py``'s ``_require_gate_enabled`` and
``dependencies.operator_role_or_group_configured``/
``_operator_role_or_group_config``): those endpoints fail closed (503)
unless ``DEPLOY_ADMINISTRATIVE_PANEL=true``,
``PANEL_OPERATOR_SURFACES_ENABLED=true``, and an explicit operator app role
or group is configured. ``PANEL_OPERATOR_SURFACES_ENABLED`` is forced to
``false`` here the same way ``PANEL_HISTORY_OWNER_BINDING_VALIDATED`` is:
no dedicated evidence-gate verification procedure for the operator surfaces
ships in this change, so the safe default stays force-published regardless
of what an operator may set locally, even though the ingestion component
work itself has landed. ``PANEL_OPERATOR_APP_ROLE``/``PANEL_OPERATOR_GROUP_ID``
are plain operator inputs (like ``PANEL_CONVERSATIONS_TOKEN_AUDIENCE``/
``PANEL_CONVERSATIONS_TENANT_ID`` above) -- published empty and safely
overridable once an operator is ready to name a real app role or group.
``PANEL_CURSOR_TTL_SECONDS`` and ``PANEL_OVERVIEW_MIN_CARDINALITY`` (below)
are shared verbatim with ingestion's own cursor/suppression defaults --
no separate ingestion-only copy is published.
"""

from __future__ import annotations

from collections.abc import Mapping


LABEL = "agent-lz"

# Canonical panel Cosmos container names. Both are partitioned by
# ``/principal_id`` (matching the classic ``conversations`` container
# convention) and carry metadata only -- never message content, citations,
# or document content. Distinct from the classic chat-content container so
# switching topologies never mixes content and metadata in one container.
OWNER_INDEX_CONTAINER_NAME = "panel-conversation-owner-index"
FEEDBACK_CONTAINER_NAME = "panel-feedback"

# App Configuration keys that receive the container names above (published
# by the generic AILZ database-container-list mechanism via each entry's
# ``canonical_name``; see ``config.deployment.composition.panel_database_containers``).
OWNER_INDEX_CONTAINER_CONFIG_KEY = "PANEL_OWNER_INDEX_DATABASE_CONTAINER"
FEEDBACK_CONTAINER_CONFIG_KEY = "PANEL_FEEDBACK_DATABASE_CONTAINER"

DEFAULT_CURSOR_TTL_SECONDS = "600"
DEFAULT_OVERVIEW_MIN_CARDINALITY = "5"

DEFAULT_SETTINGS: Mapping[str, str] = {
    "PANEL_HISTORY_ENABLED": "false",
    "PANEL_HISTORY_OWNER_BINDING_VALIDATED": "false",
    "PANEL_CONVERSATION_ENUMERATION_MODE": "owner_index",
    "PANEL_CONVERSATIONS_TOKEN_AUDIENCE": "",
    "PANEL_CONVERSATIONS_TENANT_ID": "",
    OWNER_INDEX_CONTAINER_CONFIG_KEY: OWNER_INDEX_CONTAINER_NAME,
    FEEDBACK_CONTAINER_CONFIG_KEY: FEEDBACK_CONTAINER_NAME,
    "PANEL_CURSOR_TTL_SECONDS": DEFAULT_CURSOR_TTL_SECONDS,
    "PANEL_OVERVIEW_MIN_CARDINALITY": DEFAULT_OVERVIEW_MIN_CARDINALITY,
    "PANEL_OPERATOR_SURFACES_ENABLED": "false",
    "PANEL_OPERATOR_APP_ROLE": "",
    "PANEL_OPERATOR_GROUP_ID": "",
}


def public_settings(environment: Mapping[str, str]) -> dict[str, str]:
    """Return the panel settings to publish, keeping every evidence-gated
    flag fail closed regardless of what an operator may have set locally.

    While ``DEPLOY_ADMINISTRATIVE_PANEL``/``PANEL_HISTORY_ENABLED`` are
    ``false`` (the safe defaults), every value here stays inert and no panel
    Cosmos container or RBAC assignment is provisioned (see
    ``config.deployment.composition.panel_database_containers`` and
    ``config.panel.setup``).
    """
    settings = {
        key: str(environment.get(key, default))
        for key, default in DEFAULT_SETTINGS.items()
    }
    settings["PANEL_HISTORY_OWNER_BINDING_VALIDATED"] = "false"
    settings["PANEL_OPERATOR_SURFACES_ENABLED"] = "false"
    return settings
