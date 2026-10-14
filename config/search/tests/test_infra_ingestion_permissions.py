"""Exercise actual compiled infrastructure settings through the Search setup path."""

import json
import re
import unittest
from unittest.mock import Mock, patch

from config.search import setup
from config.search.tests.test_foundry_iq_templates import TEMPLATE_DIR
from config.search.tests.test_ingestion_permissions import BASE_CONTEXT, PERMISSION_KEY
from tests.test_firewall_dns_proxy import compile_template


def evaluate_setting(expression, template, parameters):
    """Interpret only the producer's pure ARM expressions, never Azure or eval."""
    if expression.startswith("'") and expression.endswith("'"):
        return expression[1:-1].replace("''", "'")
    match = re.fullmatch(r"(\w+)\((.*)\)", expression)
    if not match:
        raise AssertionError(f"Unsupported producer expression: {expression}")
    function, arguments = match.groups()
    parts = []
    start = depth = 0
    quoted = False
    for index, character in enumerate(arguments):
        if character == "'":
            quoted = not quoted
        if not quoted:
            depth += (character == "(") - (character == ")")
            if character == "," and depth == 0:
                parts.append(arguments[start:index].strip())
                start = index + 1
    parts.append(arguments[start:].strip())

    def evaluate(part):
        return evaluate_setting(part, template, parameters)

    if function == "parameters":
        return parameters[evaluate(parts[0])]
    if function == "variables":
        return evaluate(template["variables"][evaluate(parts[0])][1:-1])
    if function == "if":
        return evaluate(parts[1] if evaluate(parts[0]) else parts[2])
    values = [evaluate(part) for part in parts]
    if function == "and":
        return all(values)
    if function == "equals":
        return values[0] == values[1]
    if function == "not":
        return not values[0]
    if function == "empty":
        return not values[0]
    if function == "string":
        return values[0] if isinstance(values[0], str) else json.dumps(values[0])
    if function == "toLower":
        return values[0].lower()
    if function == "json":
        return json.loads(values[0])
    raise AssertionError(f"Unsupported producer function: {function}")


class InfraProducedPermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = compile_template("infra/main.bicep")

    def produced_context(self, overrides):
        parameters = {
            key: item.get("defaultValue") for key, item in self.template["parameters"].items()
        }
        parameters.update(overrides)
        producer = self.template["resources"]["appConfigPopulate"]["properties"]["parameters"]["keyValues"]["value"]
        names = {
            "RETRIEVAL_BACKEND", "FOUNDRY_IQ_PATTERN", "FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND",
            "FOUNDRY_IQ_IS_ADLS_GEN2", PERMISSION_KEY, "FOUNDRY_IQ_FILTER_ADD_ON_ENABLED",
            "FOUNDRY_IQ_SECURITY_FIELD_NAME", "FOUNDRY_IQ_SEARCH_INDEX_NAME",
        }
        context = dict(BASE_CONTEXT)
        found = set()
        for match in re.finditer(r"createObject\('name', '([^']+)', 'value', (.*?), 'label',", producer):
            name, expression = match.groups()
            if name in names:
                context[name] = evaluate_setting(expression, self.template, parameters)
                found.add(name)
        self.assertEqual(found, names)
        return context

    def render_setup(self, context, client):
        # Exercise the real App Configuration loader (including JSON parsing),
        # settings template, normalization, persistence and final payload render.
        client.list_configuration_settings.return_value = [
            Mock(key=key, value=value) for key, value in context.items()
        ]
        with (
            patch.dict(setup.os.environ, {"APP_CONFIG_ENDPOINT": "https://config.azconfig.io"}),
            patch.object(setup, "ChainedTokenCredential"),
            patch.object(setup, "AzureCliCredential"),
            patch.object(setup, "ManagedIdentityCredential"),
            patch.object(setup, "AzureAppConfigurationClient", return_value=client),
        ):
            return setup.prepare_context_and_render(setup.TEMPLATE_NAME, str(TEMPLATE_DIR))

    def test_infra_inactive_empty_permissions_reach_rendering_without_widening(self):
        for backend, pattern in (
            ("ai_search", "azureBlob"), ("ai_search", "searchIndex"),
            ("foundry_iq", "searchIndex"),
        ):
            for adls in (False, True):
                with self.subTest(backend=backend, pattern=pattern, adls=adls):
                    context = self.produced_context({
                        "retrievalBackend": backend, "foundryIqPattern": pattern,
                        "foundryIqIsAdlsGen2": adls, "foundryIqSearchIndexName": "external-index",
                    })
                    self.assertEqual(context[PERMISSION_KEY], "[]")
                    # An operator-selected existing index must retain its binding.
                    context["SEARCH_RAG_INDEX_NAME"] = "external-index"
                    definitions, result = self.render_setup(context, Mock())
                    self.assertIsNotNone(definitions)
                    self.assertEqual(result[PERMISSION_KEY], [])
                    protected, _ = self.render_setup({**context, PERMISSION_KEY: '["rbacScope"]'}, Mock())
                    self.assertEqual(definitions, protected)
                    if backend == "ai_search":
                        self.assertEqual(definitions["knowledgeSources"], [])
                    else:
                        source = definitions["knowledgeSources"][0]
                        self.assertEqual(source["kind"], "searchIndex")
                        self.assertEqual(source["searchIndexParameters"]["searchIndexName"], "external-index")
                        self.assertNotIn("azureBlobParameters", source)
                        self.assertEqual(result["FOUNDRY_IQ_FILTER_ADD_ON_ENABLED"], "true")

    def test_infra_native_blob_default_and_shared_options_including_managed_alias(self):
        for pattern in ("azureBlob", "managed"):
            for override, expected in (("", ["rbacScope"]), ("[]", [])):
                with self.subTest(pattern=pattern, override=override):
                    context = self.produced_context({
                        "foundryIqPattern": pattern,
                        "foundryIqIngestionPermissionOptionsJson": override,
                    })
                    definitions, _ = self.render_setup(context, Mock())
                    self.assertEqual(
                        definitions["knowledgeSources"][0]["azureBlobParameters"]["ingestionParameters"]["ingestionPermissionOptions"],
                        expected,
                    )

    def test_infra_active_adls_empty_and_invalid_blob_permissions_fail_before_writes(self):
        for overrides in (
            {"foundryIqIsAdlsGen2": True, "foundryIqIngestionPermissionOptionsJson": "[]"},
            {
                "foundryIqPattern": "managed", "foundryIqIsAdlsGen2": True,
                "foundryIqIngestionPermissionOptionsJson": "[]",
            },
            {
                "foundryIqKnowledgeSourceKind": "searchIndex",
                "foundryIqIngestionPermissionOptionsJson": "[]",
            },
            {"foundryIqIngestionPermissionOptionsJson": '["unknown"]'},
            {"foundryIqIngestionPermissionOptionsJson": '["rbacScope", "unknown"]'},
            {"foundryIqIngestionPermissionOptionsJson": '{"rbacScope": true}'},
        ):
            with self.subTest(overrides=overrides):
                client = Mock()
                with self.assertRaisesRegex(ValueError, PERMISSION_KEY):
                    self.render_setup(self.produced_context(overrides), client)
                client.set_configuration_setting.assert_not_called()


if __name__ == "__main__":
    unittest.main()
