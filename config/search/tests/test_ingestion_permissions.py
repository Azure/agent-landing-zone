"""Offline regressions for the source-scoped native Blob permission opt-in."""

import copy
import json
import unittest
from unittest.mock import Mock, patch

from config.search import setup
from config.search.tests.test_foundry_iq_templates import (
    TEMPLATE_DIR,
    render_json_template,
)

PERMISSION_KEY = "FOUNDRY_IQ_INGESTION_PERMISSION_OPTIONS"
BASE_CONTEXT = {
    "RESOURCE_TOKEN": "abc123",
    "SEARCH_SERVICE_QUERY_ENDPOINT": "https://search.search.windows.net",
    "AI_FOUNDRY_ACCOUNT_NAME": "aif-abc123",
    "RETRIEVAL_BACKEND": "foundry_iq",
    "STORAGE_ACCOUNT_RESOURCE_ID": (
        "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st"
    ),
    "NETWORK_ISOLATION": "true",
    "ALLOW_ANONYMOUS": "false",
}


def normalized_settings(overrides=None):
    context = {**BASE_CONTEXT, **(overrides or {})}
    settings = render_json_template("search.settings.j2", context)
    return setup.normalize_foundry_iq_settings(
        setup.normalize_json_like_settings(settings)
    )


class IngestionPermissionTests(unittest.TestCase):
    def test_omitted_and_null_retain_protected_default(self):
        for overrides in ({}, {PERMISSION_KEY: None}):
            with self.subTest(overrides=overrides):
                self.assertEqual(normalized_settings(overrides)[PERMISSION_KEY], ["rbacScope"])
        settings = normalized_settings()
        del settings[PERMISSION_KEY]
        self.assertEqual(
            setup.normalize_foundry_iq_settings(settings)[PERMISSION_KEY], ["rbacScope"]
        )

    def test_explicit_empty_native_and_json_lists_are_preserved(self):
        for value in ([], "[]", " [] ", r'[\"rbacScope\"]'):
            with self.subTest(value=value):
                expected = ["rbacScope"] if "rbacScope" in str(value) else []
                self.assertEqual(normalized_settings({PERMISSION_KEY: value})[PERMISSION_KEY], expected)

    def test_valid_native_blob_options_are_preserved_exactly(self):
        for options in (["rbacScope"], ["sensitivityLabels"], ["sensitivityLabels", "rbacScope"]):
            with self.subTest(options=options):
                self.assertEqual(normalized_settings({PERMISSION_KEY: options})[PERMISSION_KEY], options)

    def test_empty_permissions_require_a_recognized_non_adls_selection(self):
        for value in ("false", "0", "f", "no", "n", False, 0):
            with self.subTest(value=value):
                self.assertEqual(normalized_settings({
                    PERMISSION_KEY: [], "FOUNDRY_IQ_IS_ADLS_GEN2": value,
                })[PERMISSION_KEY], [])

    def test_invalid_values_fail_closed_instead_of_filtering_to_empty(self):
        for value in (
            "", "null", "rbacScope", "false", False, 0, {},
            "[", '["rbacScope",]', {"rbacScope": True},
            [None], [False], [0], [{}], [[]], [""], [" "],
            ["unknown"], ["rbacScope", "unknown"], ["userIds"], ["groupIds"],
        ):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, PERMISSION_KEY):
                normalized_settings({PERMISSION_KEY: value})

    def test_empty_permissions_reject_unsupported_source_modes(self):
        for overrides in (
            {"FOUNDRY_IQ_IS_ADLS_GEN2": "true"},
            {"FOUNDRY_IQ_IS_ADLS_GEN2": "yes"},
            {"FOUNDRY_IQ_IS_ADLS_GEN2": "invalid"},
            {"FOUNDRY_IQ_IS_ADLS_GEN2": None},
            {"FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND": "searchIndex"},
            {"FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND": "indexedSharePoint"},
            {"RETRIEVAL_BACKEND": "unsupported"},
            {"FOUNDRY_IQ_PATTERN": "unsupported"},
        ):
            for value in ([], "[]"):
                with self.subTest(overrides=overrides, value=value), self.assertRaisesRegex(
                    ValueError, "only.*native azureBlob non-ADLS"
                ):
                    normalized_settings({**overrides, PERMISSION_KEY: value})

    def test_inactive_permission_metadata_keeps_legacy_retrieval_modes(self):
        for overrides in (
            {"RETRIEVAL_BACKEND": "ai_search"},
            {"FOUNDRY_IQ_PATTERN": "searchIndex"},
        ):
            for value in ([], "[]"):
                with self.subTest(overrides=overrides, value=value):
                    self.assertEqual(
                        normalized_settings({**overrides, PERMISSION_KEY: value})[PERMISSION_KEY], []
                    )

    def test_existing_protected_modes_keep_defaults_and_adls_permissions(self):
        for overrides in (
            {"FOUNDRY_IQ_IS_ADLS_GEN2": "true"},
            {"FOUNDRY_IQ_PATTERN": "searchIndex"},
            {"RETRIEVAL_BACKEND": "ai_search"},
        ):
            with self.subTest(overrides=overrides):
                self.assertEqual(normalized_settings(overrides)[PERMISSION_KEY], ["rbacScope"])
        options = ["userIds", "groupIds", "rbacScope"]
        self.assertEqual(
            normalized_settings({
                "FOUNDRY_IQ_IS_ADLS_GEN2": "true", PERMISSION_KEY: options,
            })[PERMISSION_KEY],
            options,
        )

    def test_rendered_change_is_only_the_native_source_permission_list(self):
        context = {
            **BASE_CONTEXT,
            "FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED": "true",
            "WORK_IQ_ENABLED": "true",
            "WORK_IQ_KNOWLEDGE_SOURCE_NAME": "work-ks",
            "FOUNDRY_IQ_FILTER_ADD_ON_ENABLED": "false",
        }
        protected_settings = normalized_settings(context)
        shared_settings = normalized_settings({**context, PERMISSION_KEY: []})
        expected_settings = {**protected_settings, PERMISSION_KEY: []}
        self.assertEqual(shared_settings, expected_settings)
        definitions = []
        for settings in (protected_settings, shared_settings):
            definitions.append(render_json_template("search.j2", {
                **context, **settings, "EMBEDDING_MODEL_INFO": {}, "GPT_MODEL_INFO": {},
            }))
        expected = copy.deepcopy(definitions[0])
        ingestion = expected["knowledgeSources"][0]["azureBlobParameters"]["ingestionParameters"]
        self.assertEqual(ingestion["ingestionPermissionOptions"], ["rbacScope"])
        ingestion["ingestionPermissionOptions"] = []
        self.assertEqual(definitions[1], expected)
        self.assertEqual(len(definitions[1]["knowledgeSources"]), 3)
        # A separate protected source configuration is not mutated by the opt-in.
        self.assertEqual(normalized_settings()[PERMISSION_KEY], ["rbacScope"])

    def test_mocked_appconfig_persists_empty_and_rejects_invalid_before_writes(self):
        for value in ("[]", '["unknown"]', "not-json"):
            with self.subTest(value=value):
                client = Mock()
                context = {**BASE_CONTEXT, PERMISSION_KEY: value}
                with patch.dict(setup.os.environ, {"APP_CONFIG_ENDPOINT": "https://config.azconfig.io"}), \
                     patch.object(setup, "ChainedTokenCredential"), \
                     patch.object(setup, "AzureCliCredential"), \
                     patch.object(setup, "ManagedIdentityCredential"), \
                     patch.object(setup, "AzureAppConfigurationClient", return_value=client), \
                     patch.object(setup, "load_appconfig_settings", return_value=context):
                    if value != "[]":
                        with self.assertRaisesRegex(ValueError, PERMISSION_KEY):
                            setup.prepare_context_and_render(setup.TEMPLATE_NAME, str(TEMPLATE_DIR))
                        client.set_configuration_setting.assert_not_called()
                        continue
                    definitions, result = setup.prepare_context_and_render(setup.TEMPLATE_NAME, str(TEMPLATE_DIR))
                self.assertEqual(result[PERMISSION_KEY], [])
                ingestion = definitions["knowledgeSources"][0]["azureBlobParameters"]["ingestionParameters"]
                self.assertEqual(ingestion["ingestionPermissionOptions"], [])
                stored = [
                    call.args[0] for call in client.set_configuration_setting.call_args_list
                    if call.args[0].key == PERMISSION_KEY
                ]
                self.assertEqual(len(stored), 1)
                self.assertEqual(stored[0].label, "agent-lz")
                self.assertEqual(stored[0].value, json.dumps([]))


if __name__ == "__main__":
    unittest.main()
