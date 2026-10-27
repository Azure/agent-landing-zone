"""ADR-0022 composition and hook behavior, with offline Azure boundaries."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from config.deployment import appconfig, composition, topology
from config.deployment.existing_images import definition_placeholder_plan
from config.appdefinition import load_definition, effective_components
from config.appdefinition.roles import assign_roles, discover_component_identities
from config.panel import setup as panel
from tests.test_app_definition_roles import FakeAz, RG

ROOT = Path(__file__).resolve().parents[1]
FLAG = composition.DEPLOY_INGESTION_CONTAINER_APP


def source():
    return json.loads((ROOT / "main.parameters.json").read_text(encoding="utf-8"))


class OptionalIngestionTests(unittest.TestCase):
    def test_omitted_component_has_no_placeholder_role_or_identity_discovery(self):
        definition = load_definition(ROOT / "app-definition.json", repo_root=ROOT)
        for hosted in (False, True):
            env = {
                FLAG: "false", "AZURE_RESOURCE_GROUP": RG, "AZURE_SUBSCRIPTION_ID": "0000",
                "DEPLOYMENT_TOPOLOGY": "hosted-no-panel" if hosted else "classic",
            }
            with self.subTest(hosted=hosted):
                fake = FakeAz()
                assignments = assign_roles(definition, env, hosted_orchestration=hosted, run_az=fake)
                self.assertNotIn("ingestion", {item.component for item in assignments})
                self.assertNotIn("ingestion", definition_placeholder_plan(env, images={
                    "frontend": "frontend@sha256:retained", "dataingest": "ingestion@sha256:retained",
                }))
                with patch("config.appdefinition.roles._resolve_identity",
                           return_value=("principal", "client", "")) as lookup:
                    identities = discover_component_identities(definition, env, hosted_orchestration=hosted)
                self.assertNotIn("ingestion", identities)
                self.assertNotIn("dataingest", [call.args[0] for call in lookup.call_args_list])

    def test_resolution_matrix(self):
        for existing in (False, True):
            for mode in composition.DeploymentMode:
                for explicit in (None, "true", "false"):
                    for persisted in (None, "true", "false"):
                        with self.subTest(existing=existing, mode=mode, explicit=explicit, persisted=persisted):
                            env = {"DEPLOYMENT_TOPOLOGY": mode.value}
                            if explicit is not None:
                                env[FLAG] = explicit
                            saved = {FLAG: persisted} if persisted is not None else {}
                            expected = (
                                explicit == "true" if explicit is not None
                                else persisted == "true" if existing and persisted is not None
                                else existing
                            )
                            self.assertEqual(expected, composition.resolve_ingestion_selection(
                                env, existing=existing, persisted_settings=saved
                            ))

    def test_invalid_booleans_fail_actionably(self):
        for value in ("", "off", "yes", "0", "maybe"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, FLAG):
                composition.resolve_ingestion_selection({FLAG: value})

    def test_parameter_and_hook_selection_agree_for_all_modes(self):
        for mode in composition.DeploymentMode:
            for enabled in (False, True):
                for preserve in (False, True):
                    with self.subTest(mode=mode, enabled=enabled, preserve=preserve):
                        env = {
                            "DEPLOYMENT_TOPOLOGY": mode.value,
                            FLAG: str(enabled).lower(),
                            "PRESERVE_CLASSIC_RUNTIME": str(preserve).lower(),
                            "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
                        }
                        before = source()
                        composed = composition.compose_parameters(before, env)
                        self.assertEqual(source(), before)
                        params = composed["parameters"]
                        apps = params["containerAppsList"]["value"]
                        self.assertEqual(enabled, any(a["service_name"] == "dataingest" for a in apps))
                        self.assertEqual(enabled, "agent-app-ingestion" in composition.describe_mode(
                            mode, deploy_ingestion=enabled
                        )["components"])
                        settings = {s["name"]: s["value"] for s in params["additionalAppConfigurationSettings"]["value"]}
                        self.assertEqual(str(enabled).lower(), settings[FLAG])
                        # Selection does not switch retrieval, indexes, or source.
                        for name in ("retrievalBackend", "foundryIqPattern", "foundryIqKnowledgeSourceKind"):
                            self.assertEqual(before["parameters"][name], params[name])
                        if preserve or mode is composition.DeploymentMode.CLASSIC:
                            self.assertIn("orchestrator", [a["service_name"] for a in apps])
                        self.assertIn("frontend", [a["service_name"] for a in apps])

    def test_custom_definitions_preserve_existing_additive_component_intent(self):
        for selected in ("samples/custom-app/containerapp", "samples/custom-app/hosted"):
            for explicit in (None, "false", "true"):
                with self.subTest(selected=selected, explicit=explicit):
                    env = {"AGENTLZ_APP_DEFINITION": selected, "DEPLOYMENT_TOPOLOGY": "classic"}
                    if explicit is not None:
                        env[FLAG] = explicit
                    self.assertTrue(composition.resolve_ingestion_selection(env, existing=False))
                    apps = composition.compose_parameters(source(), env)["parameters"]["containerAppsList"]["value"]
                    self.assertIn("dataingest", [a["service_name"] for a in apps])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "app-definition.json"
            definition = json.loads((ROOT / "app-definition.json").read_text())
            path.write_text(json.dumps(definition))
            # An explicit copy with ingestion listed is custom, not bundled.
            self.assertTrue(composition.resolve_ingestion_selection(
                {"AGENTLZ_APP_DEFINITION": str(path), FLAG: "false"}, existing=False
            ))
            custom = load_definition(path, repo_root=ROOT)
            self.assertIn("ingestion", [c["name"] for c in effective_components(
                custom, hosted_orchestration=False, deploy_ingestion=False
            )])
        self.assertFalse(composition.resolve_ingestion_selection(
            {"AGENTLZ_APP_DEFINITION": "app-definition.json"}, existing=False
        ))

    def test_app_dependent_sources_fail_before_endpoint_discovery(self):
        for settings in (
            {"RETRIEVAL_BACKEND": "ai_search"},
            {"FOUNDRY_IQ_PATTERN": "searchIndex"},
            {"FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND": "sharePoint"},
            {"FOUNDRY_IQ_CONVERSATION_UPLOAD_ENABLED": "true"},
            {"RETRIEVAL_BACKEND": "unknown", "SEARCH_RAG_INDEX_NAME": "existing"},
        ):
            env = {FLAG: "false", "DEPLOYMENT_TOPOLOGY": "classic", **settings}
            with self.subTest(settings=settings), patch.object(appconfig, "_container_app") as lookup:
                with self.assertRaisesRegex(ValueError, "retrieval/source/index"):
                    appconfig.build_settings(env)
                lookup.assert_not_called()
                with self.assertRaisesRegex(ValueError, FLAG):
                    composition.compose_parameters(source(), env)

    def test_custom_ui_and_ingestion_publish_actual_selection_everywhere(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "app-definition.json"
            declaration = json.loads((ROOT / "app-definition.json").read_text())
            declaration["components"] = [
                component for component in declaration["components"]
                if component["name"] in {"ui", "ingestion"}
            ]
            path.write_text(json.dumps(declaration), encoding="utf-8")
            definition = load_definition(path, repo_root=ROOT)
            for mode in composition.DeploymentMode:
                for existing in (False, True):
                    for explicit in (None, "false", "true"):
                        with self.subTest(mode=mode, existing=existing, explicit=explicit):
                            env = {
                                "AGENTLZ_APP_DEFINITION": str(path),
                                "DEPLOYMENT_TOPOLOGY": mode.value,
                                "AZURE_RESOURCE_GROUP": "test-group",
                                "RESOURCE_TOKEN": "token",
                                "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
                            }
                            if explicit is not None:
                                env[FLAG] = explicit
                            persisted = {
                                FLAG: "false",
                                "DEPLOYMENT_TOPOLOGY": mode.value,
                                "CHAT_BACKEND": (
                                    "orchestrator" if mode is composition.DeploymentMode.CLASSIC
                                    else "hosted_agent"
                                ),
                            }
                            with (
                                patch.object(topology, "resource_group_exists", return_value=existing),
                                patch.object(topology, "resource_group_has_resources", return_value=existing),
                                patch.object(topology, "read_persisted_settings", return_value=persisted),
                                patch.object(topology, "_run_az", side_effect=AssertionError("live Azure forbidden")),
                            ):
                                plan = topology.resolve_environment_plan(env)
                            self.assertTrue(plan.deploy_ingestion)
                            selected = effective_components(
                                definition, hosted_orchestration=mode is not composition.DeploymentMode.CLASSIC,
                                deploy_ingestion=plan.deploy_ingestion,
                            )
                            self.assertEqual({"ui", "ingestion"}, {c["name"] for c in selected})
                            # Execute the actual CLI emission used by both
                            # preProvision hooks, not just the pure resolver.
                            with (
                                patch.dict(os.environ, env, clear=True),
                                patch("builtins.print") as output,
                            ):
                                topology._print_materialized(plan)
                            materialized = dict(call.args[0].split("=", 1)
                                                for call in output.call_args_list)
                            self.assertEqual("true", materialized[FLAG])
                            hook_environment = {**env, **materialized}
                            document = composition.compose_parameters(source(), hook_environment)
                            parameters = document["parameters"]
                            self.assertIn("dataingest", [
                                app["service_name"] for app in parameters["containerAppsList"]["value"]
                            ])
                            settings = {item["name"]: item["value"] for item in
                                        parameters["additionalAppConfigurationSettings"]["value"]}
                            self.assertEqual("true", settings[FLAG])
                            with patch.object(appconfig, "_container_app", side_effect=lambda group, name, **kwargs: {
                                "fqdn": name + ".example.test", "principalId": name,
                            }):
                                published = appconfig.build_settings(hook_environment)
                            self.assertEqual("true", published[FLAG])
                            self.assertTrue(published["INGESTION_BASE_URL"])
                            self.assertIn("dataingest", [
                                app["serviceName"] for app in json.loads(published["CONTAINER_APPS"])
                            ])
                            self.assertEqual("true", str(composition.describe_mode(
                                plan.mode, deploy_ingestion=plan.deploy_ingestion
                            )["deploy_ingestion_container_app"]).lower())

    def test_explicit_alternative_index_is_preserved_and_not_inferred(self):
        for backend, pattern in (("ai_search", "azureBlob"), ("foundry_iq", "searchIndex")):
            env = {
                FLAG: "false", "DEPLOYMENT_TOPOLOGY": "classic",
                "RETRIEVAL_BACKEND": backend, "FOUNDRY_IQ_PATTERN": pattern,
                "FOUNDRY_IQ_KNOWLEDGE_SOURCE_KIND": pattern,
                "SEARCH_RAG_INDEX_NAME": "externally-populated",
            }
            document = composition.compose_parameters(source(), env)
            settings = {s["name"]: s["value"] for s in document["parameters"]["additionalAppConfigurationSettings"]["value"]}
            self.assertEqual("externally-populated", settings["SEARCH_RAG_INDEX_NAME"])
            self.assertNotIn("dataingest", [a["service_name"] for a in document["parameters"]["containerAppsList"]["value"]])

    def test_disabled_endpoint_reconciliation_never_looks_up_ingestion(self):
        def lookup(group, name, *, required, subscription=""):
            self.assertNotIn("dataingest", name)
            return {"fqdn": name + ".example.test", "principalId": name}

        for mode in composition.DeploymentMode:
            env = {
                FLAG: "false", "DEPLOYMENT_TOPOLOGY": mode.value,
                "AZURE_RESOURCE_GROUP": "test-group", "RESOURCE_TOKEN": "token",
                "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            }
            with self.subTest(mode=mode), patch.object(appconfig, "_container_app", side_effect=lookup):
                settings = appconfig.build_settings(env)
            for key in ("DATA_INGEST_APP_ENDPOINT", "DATA_INGEST_APP_NAME", "INGESTION_BASE_URL"):
                self.assertEqual("", settings[key])
            self.assertEqual("false", settings[FLAG])
            self.assertNotIn("dataingest", [a["serviceName"] for a in json.loads(settings["CONTAINER_APPS"])])

    def test_panel_omission_retains_only_frontend_grants(self):
        env = {
            FLAG: "false", "DEPLOY_ADMINISTRATIVE_PANEL": "true",
            "AZURE_RESOURCE_GROUP": "test-group", "RESOURCE_TOKEN": "token",
            "AZURE_SUBSCRIPTION_ID": "test-subscription",
            "DATABASE_ACCOUNT_NAME": "account", "DATABASE_NAME": "database",
        }
        with (
            patch.object(panel, "resolve_container_app_principal_id", return_value="frontend") as principal,
            patch.object(panel, "ensure_cosmos_sql_role_assignment", return_value=True) as assign,
        ):
            self.assertEqual(2, panel.configure_panel_rbac(env))
        principal.assert_called_once_with("test-group", "ca-token-frontend")
        self.assertEqual(2, assign.call_count)
        for call in assign.call_args_list:
            self.assertEqual(panel.COSMOS_DATA_CONTRIBUTOR_ROLE_GUID, call.args[4])

    def test_empty_precreated_group_is_fresh_and_legacy_existing_stays_enabled(self):
        for mode in composition.DeploymentMode:
            for has_resources in (False, True):
                with (
                    self.subTest(mode=mode, has_resources=has_resources),
                    patch.object(topology, "resource_group_exists", return_value=True),
                    patch.object(topology, "resource_group_has_resources", return_value=has_resources),
                    patch.object(topology, "read_persisted_settings", return_value={}),
                ):
                    plan = topology.resolve_environment_plan({"DEPLOYMENT_TOPOLOGY": mode.value})
                self.assertEqual(has_resources, plan.deploy_ingestion)

    def test_empty_group_without_topology_has_both_fresh_defaults(self):
        with (
            patch.object(topology, "resource_group_exists", return_value=True),
            patch.object(topology, "resource_group_has_resources", return_value=False),
            patch.object(topology, "read_persisted_settings") as persisted,
        ):
            plan = topology.resolve_environment_plan({})
        self.assertFalse(plan.deploy_ingestion)
        self.assertEqual(composition.DeploymentMode.HOSTED_NO_PANEL, plan.mode)
        persisted.assert_not_called()

    def test_lost_resource_group_output_does_not_reset_existing_runtime_selection(self):
        with (
            patch.object(topology, "resource_group_exists", return_value=False),
            patch.object(topology, "read_persisted_settings", return_value={}),
        ):
            plan = topology.resolve_environment_plan({"CHAT_BACKEND": "orchestrator"})
        self.assertTrue(plan.deploy_ingestion)
        self.assertEqual(composition.DeploymentMode.CLASSIC, plan.mode)

    def test_persisted_false_and_explicit_rollback(self):
        with (
            patch.object(topology, "resource_group_exists", return_value=True),
            patch.object(topology, "read_persisted_settings", return_value={FLAG: "false"}),
        ):
            env = {"DEPLOYMENT_TOPOLOGY": "classic", "CHAT_BACKEND": "orchestrator"}
            self.assertFalse(topology.resolve_environment_plan(env).deploy_ingestion)
            self.assertTrue(topology.resolve_environment_plan({**env, FLAG: "true"}).deploy_ingestion)

    def test_invalid_persisted_state_and_unavailable_state_fail_closed(self):
        with (
            patch.object(topology, "resource_group_exists", return_value=True),
            patch.object(topology, "read_persisted_settings", return_value={FLAG: "invalid"}),
        ):
            with self.assertRaisesRegex(ValueError, FLAG):
                topology.resolve_environment_plan({"CHAT_BACKEND": "orchestrator"})
        with (
            patch.object(topology, "resource_group_exists", return_value=True),
            patch.object(topology, "read_persisted_settings", side_effect=composition.DeploymentTopologyError(
                "Cannot read existing selection; set DEPLOY_INGESTION_CONTAINER_APP explicitly"
            )),
        ):
            with self.assertRaisesRegex(ValueError, FLAG):
                topology.resolve_environment_plan({"CHAT_BACKEND": "orchestrator"})

    def test_persisted_selection_is_read_under_shared_label(self):
        with patch.object(topology, "_run_az", return_value=(0, json.dumps([
            {"key": FLAG, "value": "false"}, {"key": "unrelated", "value": "ignored"}
        ]), "")) as azure:
            self.assertEqual({FLAG: "false"}, topology.read_persisted_settings("https://config.example.test"))
        self.assertIn("agent-lz", azure.call_args.args[0])

    def test_materialized_selection_has_no_azure_reads_for_description(self):
        for enabled in (False, True):
            with (
                patch.dict(os.environ, {"DEPLOYMENT_TOPOLOGY": "classic", FLAG: str(enabled).lower()}, clear=True),
                patch("sys.argv", ["topology", "--describe"]),
                patch.object(topology, "_run_az", side_effect=AssertionError("live Azure forbidden")),
                patch("builtins.print") as output,
            ):
                self.assertEqual(0, topology.main())
                description = json.loads(output.call_args.args[0])
                self.assertEqual(enabled, description["deploy_ingestion_container_app"])
                self.assertEqual(enabled, "agent-app-ingestion" in description["components"])
            self.assertEqual(str(enabled).lower(), composition.materialized_settings(
                composition.DeploymentMode.CLASSIC, deploy_ingestion=enabled
            )[FLAG])


class OptionalIngestionHookTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell required")
    def test_powershell_postprovision_skips_ingestion_endpoint_and_identity_reads(self):
        source_text = (ROOT / "scripts/postProvision.ps1").read_text(encoding="utf-8-sig")
        start = source_text.index("    $frontendFqdn = Invoke-AzTsv")
        end = source_text.index("    $modelDeployments = @(", start)
        for hosted in (False, True):
            for enabled in (False, True):
                script = f"""
$ErrorActionPreference = 'Stop'
$deployIngestion = ${str(enabled).lower()}
$hostedMode = ${str(hosted).lower()}
$frontendAppName = 'frontend'
$orchestratorAppName = 'orchestrator'
$dataIngestAppName = 'dataingest'
$resourceGroup = 'test-group'
$script:calls = @()
function Invoke-AzTsv {{
    param($Arguments, $Description, [switch]$Required)
    $script:calls += ($Arguments -join ' ')
    return 'mock-value'
}}
""" + source_text[start:end] + """
[ordered]@{ apps = @($containerApps.serviceName); calls = $script:calls } | ConvertTo-Json -Compress
"""
                with self.subTest(hosted=hosted, enabled=enabled), tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "hook.ps1"
                    path.write_text(script, encoding="utf-8")
                    result = subprocess.run([shutil.which("pwsh"), "-NoProfile", "-File", str(path)],
                                            capture_output=True, text=True, timeout=30)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(enabled, "dataingest" in payload["apps"])
                self.assertEqual(enabled, any("dataingest" in call for call in payload["calls"]))

    def test_both_predeploy_loops_skip_before_checkout_or_build(self):
        # Execute the actual loop selection guards with a fail-fast canary in
        # place of all operations after selection. No git/az/azd is invoked.
        for shell, suffix in (("pwsh", "ps1"), ("bash", "sh")):
            if not shutil.which(shell):
                continue
            text = (ROOT / "scripts" / f"preDeploy.{suffix}").read_text(encoding="utf-8-sig")
            if shell == "pwsh":
                start = text.index("foreach ($c in $manifest.components) {")
                end = text.index("  $repo = $c.repo", start)
                script = """
$manifest = @{ components = @(@{ name = 'agent-app-ingestion' }) }
$selectedComponents = @('agent-app-ui')
$definitionManifestNames = @('agent-app-ingestion')
$deploymentMode = 'classic'
""" + text[start:end] + "\nthrow 'unselected component was checked out'\n}\n"
                args = ["-NoProfile", "-File"]
            else:
                start = text.index("while IFS= read -r comp; do", text.index("# ---------- Iterate components"))
                end = text.index('  repo="$(printf', start)
                script = """
set -e
selected_components='agent-app-ui'
definition_manifest_names=' agent-app-ingestion '
deployment_mode=classic
yellow() { printf '%s\\n' "$*"; }
jq() { printf '%s\\n' agent-app-ingestion; }
""" + text[start:end] + """
echo 'unselected component was checked out'
exit 99
done <<< '{}'
"""
                args = []
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / f"hook.{suffix}"
                path.write_text(script, encoding="utf-8", newline="\n")
                result = subprocess.run([shutil.which(shell), *args, str(path)],
                                        capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("not deployed", result.stdout)
