"""Current lifecycle, provenance and retained versioned-contract integrity."""

from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from config.appdefinition import load_definition, validate_definition

ROOT = Path(__file__).resolve().parents[1]


class IntegrationPinTests(unittest.TestCase):
    def test_manifest_contains_exact_integration_pins(self):
        validate_definition(load_definition(ROOT / "app-definition.json", repo_root=ROOT), ROOT)
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        components = {item["name"]: item for item in manifest["components"]}
        self.assertRegex(manifest["tag"], r"^v\d+\.\d+\.\d+$")
        self.assertNotIn("ailz_tag", manifest)
        self.assertNotIn("ailz_commit", manifest)
        self.assertEqual({
            "repo": "https://github.com/Azure/bicep-ptn-aiml-landing-zone.git",
            "tag": "v2.7.3", "commit": "97e2375b89dcda4900d75aac9e7ffb7b20cce165",
        }, manifest["infra"]["source"])
        self.assertEqual({
            "agent-app-mcp", "agent-app-orchestrator", "agent-app-ingestion", "agent-app-ui",
        }, set(components))
        for name, ref_key, ref, commit in (
            ("agent-app-mcp", "branch", "feature/nl2sql-mcp-cosmos",
             "a824bae8631e49066741ceedfd72e243c9e217d0"),
            ("agent-app-orchestrator", "branch", "feature/nl2sql-mcp-cosmos",
             "53b63422d1c2628ad02a0253651e8cf7068ed1e9"),
            ("agent-app-ingestion", "tag", "v3.1.3", "d7f34eb040cc308ce18d0d95ee9c9cb0f07028b1"),
            ("agent-app-ui", "tag", "v3.5.0", "3961224368685cd0e96966c18496adb8b6626987"),
        ):
            self.assertNotIn("tag" if ref_key == "branch" else "branch", components[name])
            self.assertEqual((ref, commit), (components[name][ref_key], components[name]["commit"]))
        fixture = json.loads((ROOT / "infra/tests/contracts/fixtures/incorporated-foundation-normalization.json").read_text())
        self.assertEqual(manifest["components"], fixture["projection"]["changes"]["variables"]["changes"]["$fxv#0"]["changes"]["components"]["after"])

    def test_infra_is_in_repository_source_without_submodule_pin(self):
        self.assertFalse((ROOT / ".gitmodules").exists())
        result = subprocess.run(["git", "ls-files", "--stage", "--", "infra/bicep/main.bicep", "infra"],
                                cwd=ROOT, check=True, capture_output=True, text=True)
        modes = {line.split()[0] for line in result.stdout.splitlines()}
        self.assertIn("100644", modes)
        self.assertNotIn("160000", modes)

    def test_previous_release_snapshot_is_historical_not_executable_configuration(self):
        self.assertFalse((ROOT / "config/deployment/rollback.json").exists())
        snapshot = json.loads((ROOT / "tests/fixtures/historical-runtime-rollback.json").read_text())
        self.assertEqual("v3.7.0", snapshot["umbrella"]["tag"])
        self.assertEqual("v2.3.0", snapshot["umbrella"]["ailz_tag"])
        self.assertEqual({
            "gpt-rag-ui": "v2.3.13", "gpt-rag-orchestrator": "v3.8.0",
            "gpt-rag-ingestion": "v2.5.0",
        }, snapshot["components"])


class LifecycleParityTests(unittest.TestCase):
    def test_preprovision_does_not_fetch_or_checkout_infrastructure(self):
        for name in ("preProvision.ps1", "preProvision.sh"):
            content = (ROOT / "scripts" / name).read_text(encoding="utf-8-sig")
            for retired in ("ailz_commit", "git submodule", "fetch --depth 1 origin", "checkout --detach", "config.deployment.infra_checkout"):
                self.assertNotIn(retired, content)
            self.assertIn("was not found. Restore the configured infrastructure entry point", content)

    def test_all_hooks_use_shared_current_product_resolution(self):
        for stem in ("preProvision", "preDeploy", "postProvision"):
            for extension in ("ps1", "sh"):
                content = (ROOT / "scripts" / f"{stem}.{extension}").read_text(encoding="utf-8-sig")
                if stem != "postProvision" or extension == "ps1":
                    self.assertIn("config.deployment.topology", content)
                for obsolete in (
                    "PRESERVE_CLASSIC_RUNTIME", "HOSTED_CUTOVER_COMPLETE",
                    "DEPLOYMENT_TOPOLOGY", "DEPLOY_ADMINISTRATIVE_PANEL",
                    "hosted-panel", "hosted-no-panel", "config.continuity.setup",
                ):
                    self.assertNotIn(obsolete, content)

    def test_native_publication_precedes_component_deploy_and_has_no_adapter_path(self):
        for extension in ("ps1", "sh"):
            content = (ROOT / "scripts" / f"preDeploy.{extension}").read_text(encoding="utf-8-sig")
            self.assertLess(content.index("config.deployment.native_deploy"), content.index("config.deployment.appconfig"))
            self.assertLess(content.index("config.deployment.appconfig"), content.index("git clone"))
            self.assertNotIn("azd deploy orchestrator-agent", content)
            self.assertNotIn("--protocol invocations", content)
            native_block = content[content.index("# BEGIN native application lifecycle"):content.index("# END native application lifecycle")]
            self.assertNotIn("--validate-smoke", native_block)
            self.assertIn("config.deployment.private_network", content)
            self.assertIn("config.deployment.egress", content)

    def test_definition_binding_precedes_resource_group_changes(self):
        for extension in ("ps1", "sh"):
            content = (ROOT / "scripts" / f"preProvision.{extension}").read_text(encoding="utf-8-sig")
            self.assertLess(content.index("config.appdefinition"), content.index("config.deployment.resource_groups"))
            self.assertLess(content.index("config.deployment.topology"), content.index("config.deployment.resource_groups"))
            self.assertIn("config.deployment.provider", content)
            self.assertIn("config.deployment.terraform_groups", content)
            self.assertIn("config.deployment.terraform_inputs", content)

    def test_postprovision_retains_role_output_and_metadata_owners(self):
        for extension in ("ps1", "sh"):
            content = (ROOT / "scripts" / f"postProvision.{extension}").read_text(encoding="utf-8-sig")
            for module in ("config.appdefinition", "config.deployment.outputs", "config.deployment.appconfig", "config.panel.setup"):
                self.assertIn(module, content)
            self.assertIn("--assign-roles", content)

    def test_windows_python_invocation_retains_jumpbox_interpreter_support(self):
        for stem in ("preProvision", "postProvision", "preDeploy"):
            content = (ROOT / "scripts" / f"{stem}.ps1").read_text(encoding="utf-8-sig")
            self.assertIn("Invoke-PythonModule", content)
            self.assertIn("AGENTLZ_REPO_ROOT", content)

    def test_preserved_image_and_provenance_guards_remain_shared(self):
        content = (ROOT / "config/deployment/hosted_prepare.py").read_text()
        self.assertIn("HOSTED_AGENT_IMAGE_SOURCE_COMMIT", content)
        self.assertIn("HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256", content)
        self.assertIn("deployment_handoff(environment)", content)
        self.assertNotIn("HOSTED_AGENT_PREPARED", content)
        self.assertIn("resolve_mode", content)
        for extension in ("ps1", "sh"):
            content = (ROOT / "scripts" / f"preDeploy.{extension}").read_text(encoding="utf-8-sig")
            self.assertIn("expected_commit" if extension == "sh" else "expectedCommit", content)


class AgentLandingZoneContractIntegrityTests(unittest.TestCase):
    SCHEMAS = ("app-definition-v1.schema.json", "platform-outputs-v1.schema.json")

    def test_schema_bytes_match_committed_sha256(self) -> None:
        for name in self.SCHEMAS:
            with self.subTest(schema=name):
                schema_path = ROOT / "contracts" / name
                digest_path = ROOT / "contracts" / f"{name}.sha256"
                data = schema_path.read_bytes()
                self.assertNotIn(b"\r\n", data, "schema must be LF-encoded")
                expected, file_name = digest_path.read_text(encoding="utf-8").split()
                self.assertEqual(name, file_name)
                self.assertEqual(expected, hashlib.sha256(data).hexdigest())

    def test_schemas_are_versioned_draft_2020_12_documents(self) -> None:
        for name in self.SCHEMAS:
            with self.subTest(schema=name):
                schema = json.loads((ROOT / "contracts" / name).read_text("utf-8"))
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
                self.assertTrue(schema["$id"].endswith("/" + name))
                self.assertEqual({"const": 1}, schema["properties"]["schemaVersion"])
                self.assertIn("schemaVersion", schema["required"])

    def test_contracts_readme_registers_new_schemas(self) -> None:
        readme = (ROOT / "contracts" / "README.md").read_text(encoding="utf-8")
        for name in self.SCHEMAS:
            self.assertIn(name, readme)
        self.assertIn("naming-map.md", readme)


class AuditEventV2ContractTests(unittest.TestCase):
    V1 = ("audit-event-v1.schema.json", "audit-event-v1.application-insights.schema.json")
    V2 = ("audit-event-v2.schema.json", "audit-event-v2.application-insights.schema.json")

    @staticmethod
    def _pins(name: str) -> dict:
        pins = {}
        for line in (ROOT / "contracts" / name).read_text("utf-8").splitlines():
            digest, file_name = line.split()
            pins[file_name] = digest
        return pins

    def test_v2_bytes_match_committed_sha256(self) -> None:
        pins = self._pins("audit-event-v2.sha256")
        self.assertEqual(set(self.V2), set(pins))
        for name in self.V2:
            with self.subTest(schema=name):
                data = (ROOT / "contracts" / name).read_bytes()
                self.assertNotIn(b"\r\n", data, "schema must be LF-encoded")
                self.assertEqual(pins[name], hashlib.sha256(data).hexdigest())

    def test_v1_is_retained_unchanged(self) -> None:
        pins = self._pins("audit-event-v1.sha256")
        self.assertEqual("825db8ef40a81e2c19e5d80d37c565b6b47fc9a6540e9881d35cc12b8fde5aab", pins[self.V1[0]])
        self.assertEqual("066c8f5408610ab839d5121d06ca5bc59e8797e551d5c47c875c5ba52f7e0588", pins[self.V1[1]])
        for name in self.V1:
            data = (ROOT / "contracts" / name).read_bytes()
            self.assertEqual(pins[name], hashlib.sha256(data).hexdigest())

    def test_v2_renames_prefix_and_keeps_fields_aligned(self) -> None:
        v1_logical, v1_wire = (json.loads((ROOT / "contracts" / n).read_text("utf-8")) for n in self.V1)
        logical, wire = (json.loads((ROOT / "contracts" / n).read_text("utf-8")) for n in self.V2)
        self.assertEqual({"const": 2}, logical["properties"]["schema_version"])
        for schema, name in zip((logical, wire), self.V2):
            self.assertTrue(schema["$id"].endswith("/" + name))
            self.assertNotIn("gpt", json.dumps(schema).lower())
        names = wire["properties"]["name"]["enum"]
        event_types = logical["properties"]["event_type"]["enum"]
        self.assertEqual(["agentlz.audit." + t for t in event_types], names)
        self.assertEqual([n.replace("gptrag.", "agentlz.", 1) for n in v1_wire["properties"]["name"]["enum"]], names)
        self.assertEqual(v1_logical["required"], logical["required"])
        self.assertEqual(set(v1_logical["properties"]), set(logical["properties"]))
        self.assertEqual(logical["required"], wire["properties"]["properties"]["required"])

    def test_readme_registers_v2_and_deprecates_v1(self) -> None:
        readme = (ROOT / "contracts" / "README.md").read_text(encoding="utf-8")
        pins = self._pins("audit-event-v2.sha256")
        for name in self.V2:
            self.assertIn(name, readme)
            self.assertEqual(pins[name], hashlib.sha256((ROOT / "contracts" / name).read_bytes()).hexdigest())
