"""Application definition schema, semantic rules, and capability profiles.

Covers T065 (schema and semantic validation with JSON pointers), T067
(profile -> role mapping), and T099 (profile parity with the trio's current
``containerAppsList`` role assignments).
"""

from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from config.appdefinition import (
    PROFILES,
    AppDefinition,
    AppDefinitionValidationError,
    collect_issues,
    effective_components,
    expand_profiles,
    load_definition,
    role_names,
    validate_definition,
)
from config.appdefinition.__main__ import main as cli_main

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64


def custom_document() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "id": "my-app",
        "components": [
            {"name": "web", "kind": "containerapp", "path": "web", "source": {"commit": COMMIT}, "profiles": ["model-user"]},
            {"name": "agent", "kind": "azure.ai.agent", "path": "agent", "source": {"imageDigest": DIGEST}, "profiles": []},
        ],
        "settings": [{"key": "GREETING", "value": "hi"}],
    }


AZURE_YAML = """name: my-app
services:
  web:
    host: containerapp
    project: ./web
  agent:
    host: azure.ai.agent
    project: ./agent
"""


class CustomFolderCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="agentlz-appdef-")
        self.folder = Path(self._tmp.name)
        (self.folder / "web").mkdir()
        (self.folder / "agent").mkdir()
        (self.folder / "azure.yaml").write_text(AZURE_YAML, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def definition(self, document: dict[str, object]) -> AppDefinition:
        path = self.folder / "app-definition.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return load_definition(path, repo_root=ROOT)

    def issues(self, document: dict[str, object]) -> dict[str, str]:
        return {issue.pointer: issue.message for issue in collect_issues(self.definition(document), ROOT)}


class SchemaValidationTests(CustomFolderCase):
    def test_valid_custom_definition_with_mixed_components(self) -> None:
        validate_definition(self.definition(custom_document()), ROOT)

    def test_commit_and_digest_are_the_only_pinned_sources(self) -> None:
        for source in ({"commit": "main"}, {"commit": "abc123"}, {"tag": "v1.0.0"}, {"imageDigest": "sha256:short"}, {"commit": COMMIT, "imageDigest": DIGEST}):
            with self.subTest(source=source):
                document = custom_document()
                document["components"][0]["source"] = source
                issues = self.issues(document)
                self.assertIn("/components/0/source", issues)
                self.assertIn("40-character commit or a sha256 image digest", issues["/components/0/source"])

    def test_reserved_agentlz_prefix_is_rejected(self) -> None:
        document = custom_document()
        document["settings"] = [{"key": "AGENTLZ_FOO", "value": "x"}]
        document["components"][1]["settings"] = [{"key": "AGENTLZ_BAR"}]
        issues = self.issues(document)
        self.assertIn("reserved", issues["/settings/0/key"])
        self.assertIn("reserved", issues["/components/1/settings/0/key"])

    def test_zero_components_is_invalid(self) -> None:
        document = custom_document()
        document["components"] = []
        self.assertIn("at least one component", self.issues(document)["/components"])

    def test_hooks_are_forbidden_in_definition(self) -> None:
        for location in ((), ("components", 0)):
            with self.subTest(location=location):
                document = custom_document()
                target = document if not location else document["components"][0]
                target["hooks"] = {"postdeploy": {"run": "evil.sh"}}
                where = "".join(f"/{part}" for part in location) + "/hooks"
                self.assertIn("not allowed", self.issues(document)[where])

    def test_hooks_are_forbidden_in_custom_azure_yaml(self) -> None:
        (self.folder / "azure.yaml").write_text(AZURE_YAML + "hooks:\n  preprovision:\n    run: x.sh\n", encoding="utf-8")
        messages = [issue.message for issue in collect_issues(self.definition(custom_document()), ROOT)]
        self.assertTrue(any("azure.yaml#/hooks" in message for message in messages), messages)

    def test_azure_yaml_is_required_in_the_app_folder(self) -> None:
        (self.folder / "azure.yaml").unlink()
        issues = collect_issues(self.definition(custom_document()), ROOT)
        self.assertTrue(any("must contain its own azure.yaml" in issue.message for issue in issues))

    def test_azure_yaml_services_must_match_components_and_hosts(self) -> None:
        (self.folder / "azure.yaml").write_text(AZURE_YAML.replace("host: azure.ai.agent", "host: containerapp").replace("  web:", "  site:"), encoding="utf-8")
        issues = self.issues(custom_document())
        self.assertIn("no service named `web`", issues["/components/0/name"])
        self.assertIn("host: azure.ai.agent", issues["/components/1/kind"])

    def test_paths_must_be_local_and_exist(self) -> None:
        for path in ("../outside", "/abs", "C:/abs", "missing"):
            with self.subTest(path=path):
                document = custom_document()
                document["components"][0]["path"] = path
                self.assertIn("/components/0/path", self.issues(document))

    def test_remote_urls_are_rejected(self) -> None:
        document = custom_document()
        document["settings"] = [{"key": "UPSTREAM", "value": "https://example.test/repo.git"}]
        self.assertIn("remote URLs", self.issues(document)["/settings/0/value"])

    def test_unknown_or_explicit_base_profile_is_rejected(self) -> None:
        for profile in ("owner", "base"):
            with self.subTest(profile=profile):
                document = custom_document()
                document["components"][0]["profiles"] = [profile]
                self.assertIn("is not supported", self.issues(document)["/components/0/profiles/0"])

    def test_free_form_roles_are_rejected(self) -> None:
        document = custom_document()
        document["components"][0]["roles"] = ["Owner"]
        self.assertIn("/components/0/roles", self.issues(document))

    def test_hosted_component_cannot_declare_container_app_fields(self) -> None:
        document = custom_document()
        document["components"][1]["ingress"] = "external"
        self.assertIn("/components/1/ingress", self.issues(document))

    def test_duplicate_component_names_and_setting_keys(self) -> None:
        document = custom_document()
        document["components"][1]["name"] = "web"
        document["components"][0]["settings"] = [{"key": "GREETING"}]
        issues = self.issues(document)
        self.assertIn("/components/1/name", issues)
        self.assertIn("/components/0/settings/0/key", issues)

    def test_every_issue_carries_a_json_pointer(self) -> None:
        document = custom_document()
        document["id"] = "X"
        document["components"][0]["source"] = {"commit": "main"}
        document["components"][1]["profiles"] = ["owner"]
        document["extra"] = True
        with self.assertRaises(AppDefinitionValidationError) as raised:
            validate_definition(self.definition(document), ROOT)
        pointers = {issue.pointer for issue in raised.exception.issues}
        self.assertEqual({"/id", "/components/0/source", "/components/1/profiles/0", "/extra"}, pointers)
        for issue in raised.exception.issues:
            self.assertTrue(issue.pointer.startswith("/"))
            self.assertIn(issue.pointer, str(raised.exception))

    def test_cli_validate_exit_codes(self) -> None:
        with redirect_stderr(io.StringIO()):
            self.definition(custom_document())
            self.assertEqual(0, cli_main(["--validate", str(self.folder)]))
            broken = custom_document()
            broken["components"] = []
            self.definition(broken)
            self.assertNotEqual(0, cli_main(["--validate", str(self.folder)]))
            self.assertNotEqual(0, cli_main(["--validate", str(self.folder / "absent.json")]))


TRIO_CANONICAL = {"ui": "FRONTEND_APP", "orchestrator": "ORCHESTRATOR_APP", "ingestion": "DATA_INGEST_APP"}


class CapabilityProfileTests(unittest.TestCase):
    EXPECTED = {
        "base": {"AppConfigurationDataReader", "AcrPull", "KeyVaultSecretsUser"},
        "model-user": {"CognitiveServicesUser", "CognitiveServicesOpenAIUser"},
        "retrieval-reader": {"SearchIndexDataReader", "StorageBlobDataReader"},
        "conversation-store": {"CosmosDBBuiltInDataContributor"},
        "blob-delegator": {"StorageBlobDataReader", "StorageBlobDelegator"},
        "ingestion-writer": {"SearchIndexDataContributor", "StorageBlobDataContributor"},
    }

    def test_catalog_is_fixed(self) -> None:
        self.assertEqual(list(self.EXPECTED), list(PROFILES))

    def test_profile_role_mapping(self) -> None:
        for name, roles in self.EXPECTED.items():
            with self.subTest(profile=name):
                self.assertEqual(roles, {r.role for r in PROFILES[name].roles})
                self.assertEqual(self.EXPECTED["base"] | roles, set(role_names([name])))

    def test_base_is_implicit_and_assignments_are_deduplicated(self) -> None:
        assignments = expand_profiles(["retrieval-reader", "blob-delegator"])
        self.assertEqual(len(assignments), len(set(assignments)))
        self.assertTrue(self.EXPECTED["base"] <= {a.role for a in assignments})

    def test_unknown_profile_fails(self) -> None:
        with self.assertRaises(ValueError):
            expand_profiles(["owner"])

    def test_bundled_ui_can_check_native_download_permissions_without_search_write(self) -> None:
        definition = load_definition(ROOT / "app-definition.json", repo_root=ROOT)
        ui = next(component for component in definition.document["components"] if component["name"] == "ui")
        roles = set(role_names(ui["profiles"]))
        self.assertIn("SearchIndexDataReader", roles)
        self.assertNotIn("SearchIndexDataContributor", roles)
        self.assertNotIn("SearchServiceContributor", roles)

    def test_trio_profiles_reproduce_current_role_assignments(self) -> None:
        """T099 parity checklist: profiles == containerAppsList roles per app."""
        parameters = json.loads((ROOT / "main.parameters.json").read_text(encoding="utf-8"))
        current = {
            app["canonical_name"]: set(app["roles"])
            for app in parameters["parameters"]["containerAppsList"]["value"]
        }
        trio = load_definition(ROOT / "app-definition.json", repo_root=ROOT)
        self.assertTrue(trio.bundled)
        for component in trio.document["components"]:
            canonical = TRIO_CANONICAL[component["name"]]
            with self.subTest(component=component["name"], app=canonical):
                self.assertEqual(current[canonical], set(role_names(component["profiles"])))
        self.assertEqual(set(TRIO_CANONICAL.values()), set(current))


class BundledDefinitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trio = load_definition(ROOT / "app-definition.json", repo_root=ROOT)

    def test_bundled_trio_is_valid_and_pinned_to_manifest(self) -> None:
        validate_definition(self.trio, ROOT)
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        pins = {c["name"].rsplit("-", 1)[-1]: c["commit"] for c in manifest["components"]}
        for component in self.trio.document["components"]:
            self.assertEqual(pins[component["name"]], component["source"]["commit"])

    def test_bundled_source_drift_from_manifest_fails(self) -> None:
        document = copy.deepcopy(self.trio.document)
        document["components"][0]["source"]["commit"] = "c" * 40
        drifted = AppDefinition(self.trio.path, document, bundled=True)
        self.assertIn("/components/0/source/commit", {i.pointer for i in collect_issues(drifted, ROOT)})

    def test_hosted_mode_turns_orchestrator_into_hosted_agent(self) -> None:
        classic = {c["name"]: c for c in effective_components(self.trio, hosted_orchestration=False)}
        hosted = {c["name"]: c for c in effective_components(self.trio, hosted_orchestration=True)}
        self.assertTrue(all(c["kind"] == "containerapp" for c in classic.values()))
        self.assertEqual("azure.ai.agent", hosted["orchestrator"]["kind"])
        self.assertEqual("hosted-agent", hosted["orchestrator"]["path"])
        self.assertEqual("orchestrator-agent", hosted["orchestrator"]["service"])
        self.assertNotIn("ingress", hosted["orchestrator"])
        self.assertEqual("containerapp", hosted["ui"]["kind"])
        self.assertEqual("containerapp", hosted["ingestion"]["kind"])
        self.assertTrue((ROOT / "hosted-agent" / "azure.yaml").is_file())
        # The source document is never mutated.
        self.assertEqual("containerapp", self.trio.document["components"][1]["kind"])


if __name__ == "__main__":
    unittest.main()
