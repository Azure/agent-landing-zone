"""Offline contract of the connection consumed by the managed Foundry KB Toolbox."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NativeKnowledgeConnectionTests(unittest.TestCase):
    def test_compiled_connection_targets_kb_mcp_with_project_managed_identity(self):
        executable = shutil.which("bicep")
        if not executable:
            self.skipTest("Bicep compiler not installed")
        result = subprocess.run([
            executable, "build",
            str(ROOT / "infra/bicep/modules/ai-foundry/connection-knowledge-base.bicep"),
            "--no-restore", "--stdout",
        ], capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        template = json.loads(result.stdout)
        resources = template["resources"]
        connection = resources["connection"] if isinstance(resources, dict) else next(
            item for item in resources if item["type"].endswith("/connections")
        )
        self.assertEqual("Microsoft.CognitiveServices/accounts/projects/connections", connection["type"])
        self.assertEqual("RemoteTool", connection["properties"]["category"])
        self.assertEqual("ProjectManagedIdentity", connection["properties"]["authType"])
        self.assertEqual("https://search.azure.com/", connection["properties"]["audience"])
        self.assertIn("knowledgeBaseName", connection["properties"]["target"])
        self.assertIn("/mcp?api-version=", connection["properties"]["target"])

    def test_bicep_and_terraform_provision_project_remote_tool_with_managed_auth(self):
        bicep = (ROOT / "infra/bicep/modules/ai-foundry/connection-knowledge-base.bicep").read_text()
        terraform = (ROOT / "infra/terraform/main.foundry.tf").read_text()
        for source in (bicep, terraform):
            self.assertIn("Microsoft.CognitiveServices/accounts/projects/connections@2025-10-01-preview", source)
            self.assertIn("RemoteTool", source)
            self.assertIn("ProjectManagedIdentity", source)
            self.assertIn("https://search.azure.com/", source)
            self.assertIn("/knowledgebases/", source)
            self.assertIn("/mcp?api-version=", source)
        main = (ROOT / "infra/bicep/main.bicep").read_text()
        self.assertIn("'modules/ai-foundry/connection-knowledge-base.bicep'", main)
        self.assertIn("aiFoundryKnowledgeBaseSearchConnection.outputs.connectionId", main)
        # Direct Search tool connections remain CognitiveSearch, not MCP.
        direct = (ROOT / "infra/bicep/modules/ai-foundry/connection-ai-search.bicep").read_text()
        self.assertIn("category: 'CognitiveSearch'", direct)

    def test_caller_consumer_role_is_project_scoped_and_uses_shared_catalog(self):
        roles = json.loads((ROOT / "infra/shared/roles.json").read_text())
        self.assertEqual("eed3b665-ab3a-47b6-8f48-c9382fb1dad6", roles["FoundryAgentConsumer"]["guid"])
        for seed in ("main.parameters.json", "infra/bicep/main.parameters.json"):
            parameters = json.loads((ROOT / seed).read_text())["parameters"]
            apps = parameters["containerAppsList"]["value"]
            frontend = next(app for app in apps if app["canonical_name"] == "FRONTEND_APP")
            self.assertIn("FoundryAgentConsumer", frontend["roles"])
            self.assertNotIn("AzureAIUser", frontend["roles"])
        terraform = (ROOT / "infra/terraform/main.identity.tf").read_text()
        self.assertIn('FoundryAgentConsumer        = ["agent_project"]', terraform)
        self.assertIn("id = local.foundry_context.project_id", terraform)
