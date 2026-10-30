"""Cross-repo drift guard: the exact App Configuration keys the merged
``gpt-rag-ingestion`` operator-facing panel surfaces (PR #274, merge
``5569dd6af3ecb317e1037108cb21859f1b2185a1``) and the merged ``gpt-rag-ui``
user-facing panel surfaces (PR #99, merge
``ee3b53b29019e675c1e9ff19ee607cea361e5a8e``) actually consume.

This umbrella repository does not vendor either component's source, so this
fixture is an explicit, reviewed snapshot of every ``config.get(...)``/
``environ.get(...)`` key name each consumer reads, captured directly from
those two merge commits (see the docstring of each key group below for the
exact source reference). If either consumer adds, renames, or removes a
config key, this test (and the umbrella's own ``config.panel.settings``)
must be updated together -- silent drift between the umbrella's published
defaults and what a consumer actually reads is exactly the failure mode this
guards against.

Keys intentionally excluded here because they are *not* panel-specific and
are already published unconditionally by other mechanisms (never duplicated
by ``config.panel.settings``):

- ``DEPLOY_ADMINISTRATIVE_PANEL`` -- published by
  ``config.deployment.composition.compose_parameters`` directly (reflects
  resolved topology; see ``tests/test_deployment_modes.py``).
- ``DATABASE_ACCOUNT_NAME`` / ``DATABASE_NAME`` / ``STORAGE_ACCOUNT_NAME`` --
  published unconditionally by the AI Landing Zone submodule for every
  topology (``infra/bicep/main.bicep``), regardless of the panel.
- ``DATA_INGEST_APP_APIKEY`` -- the reserved per-app ``<APP>_APIKEY`` Key
  Vault reference the AI Landing Zone submodule publishes automatically for
  every ``containerAppsList`` entry; republishing it here would create a
  duplicate key-value and fail deployment (see ``infra/bicep/main.bicep``'s
  ``additionalAppConfigurationSettings`` description).
- ``JOBS_LOG_CONTAINER`` -- ingestion's existing per-file-log blob control
  store container name (defaults to ``"jobs"`` in ``tools/admin.py`` /
  ``tools/corpus_curation_store.py`` even when unset); reused verbatim by
  corpus curation, never a new blob container or secret.
- ``OAUTH_AZURE_AD_TENANT_ID`` / ``OAUTH_AZURE_AD_CLIENT_ID`` -- ingestion's
  existing admin-dashboard bearer/audience configuration, reused as-is by
  ``validate_delegated_operator_bearer`` (no new auth config key).
"""

from __future__ import annotations

import unittest

from config.panel import settings


# Every App Configuration key `api/panel_operator.py` (and its
# `dependencies.py` auth helpers) reads directly, captured from
# gpt-rag-ingestion PR #274, merge 5569dd6af3ecb317e1037108cb21859f1b2185a1.
EXPECTED_INGESTION_OPERATOR_KEYS = frozenset(
    {
        "DEPLOY_ADMINISTRATIVE_PANEL",
        "PANEL_OPERATOR_SURFACES_ENABLED",
        "PANEL_OPERATOR_APP_ROLE",
        "PANEL_OPERATOR_GROUP_ID",
        "PANEL_OVERVIEW_MIN_CARDINALITY",
        "PANEL_CURSOR_TTL_SECONDS",
        "PANEL_OWNER_INDEX_DATABASE_CONTAINER",
        "PANEL_FEEDBACK_DATABASE_CONTAINER",
    }
)

# Every App Configuration key `panel_config.py`'s `load_panel_settings`
# reads directly, captured from gpt-rag-ui PR #99, merge
# ee3b53b29019e675c1e9ff19ee607cea361e5a8e.
EXPECTED_UI_PANEL_KEYS = frozenset(
    {
        "DEPLOY_ADMINISTRATIVE_PANEL",
        "PANEL_HISTORY_ENABLED",
        "PANEL_HISTORY_OWNER_BINDING_VALIDATED",
        "PANEL_CONVERSATION_ENUMERATION_MODE",
        "PANEL_CONVERSATIONS_TOKEN_AUDIENCE",
        "PANEL_CONVERSATIONS_TENANT_ID",
        "PANEL_OWNER_INDEX_DATABASE_CONTAINER",
        "PANEL_FEEDBACK_DATABASE_CONTAINER",
        "PANEL_CURSOR_TTL_SECONDS",
        # PANEL_CONVERSATIONS_TENANT_ID has a fallback, not a hard read:
        "OAUTH_AZURE_AD_TENANT_ID",
        # Cosmos identifiers, published unconditionally (see module docstring).
        "DATABASE_ACCOUNT_NAME",
        "DATABASE_NAME",
    }
)


class OperatorContractDriftTests(unittest.TestCase):
    def test_umbrella_publishes_every_key_ingestion_consumes(self) -> None:
        published = settings.public_settings({})
        panel_specific = EXPECTED_INGESTION_OPERATOR_KEYS - {
            # Published elsewhere; see module docstring exclusions.
            "DEPLOY_ADMINISTRATIVE_PANEL",
        }
        missing = panel_specific - set(published)
        self.assertEqual(
            missing,
            set(),
            "config.panel.settings no longer publishes a key "
            "gpt-rag-ingestion's operator surfaces (PR #274) consume; "
            "either this fixture is stale or a real drift was introduced.",
        )

    def test_umbrella_publishes_every_key_ui_consumes(self) -> None:
        published = settings.public_settings({})
        panel_specific = EXPECTED_UI_PANEL_KEYS - {
            "DEPLOY_ADMINISTRATIVE_PANEL",
            "OAUTH_AZURE_AD_TENANT_ID",
            "DATABASE_ACCOUNT_NAME",
            "DATABASE_NAME",
        }
        missing = panel_specific - set(published)
        self.assertEqual(
            missing,
            set(),
            "config.panel.settings no longer publishes a key gpt-rag-ui's "
            "user-facing panel surfaces (PR #99) consume; either this "
            "fixture is stale or a real drift was introduced.",
        )

    def test_no_invented_operator_keys_beyond_the_reviewed_set(self) -> None:
        # The inverse guard: config.panel.settings must never publish an
        # operator-surface-shaped key (PANEL_OPERATOR_*) that ingestion does
        # not actually consume -- that would be an invented key.
        published = settings.public_settings({})
        operator_shaped = {
            key for key in published if key.startswith("PANEL_OPERATOR_")
        }
        self.assertEqual(
            operator_shaped,
            {"PANEL_OPERATOR_SURFACES_ENABLED", "PANEL_OPERATOR_APP_ROLE", "PANEL_OPERATOR_GROUP_ID"},
        )
        self.assertTrue(operator_shaped.issubset(EXPECTED_INGESTION_OPERATOR_KEYS))

    def test_operator_defaults_never_enable_the_feature(self) -> None:
        published = settings.public_settings({})
        self.assertEqual(
            published["PANEL_OPERATOR_SURFACES_ENABLED"], "false"
        )
        self.assertEqual(published["PANEL_OPERATOR_APP_ROLE"], "")
        self.assertEqual(published["PANEL_OPERATOR_GROUP_ID"], "")


if __name__ == "__main__":
    unittest.main()
