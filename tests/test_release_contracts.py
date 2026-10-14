from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from config.deployment.composition import (
    DeploymentMode,
    compose_parameters,
    materialized_settings,
    resolve_mode,
)


ROOT = Path(__file__).resolve().parents[1]


class IntegrationPinTests(unittest.TestCase):
    def test_manifest_contains_exact_integration_pins(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        components = {item["name"]: item for item in manifest["components"]}

        self.assertRegex(manifest["tag"], r"^v\d+\.\d+\.\d+$")
        self.assertNotIn("ailz_tag", manifest)
        self.assertNotIn("ailz_commit", manifest)
        self.assertEqual(
            {
                "repo": "https://github.com/Azure/bicep-ptn-aiml-landing-zone.git",
                "tag": "v2.7.3",
                "commit": "97e2375b89dcda4900d75aac9e7ffb7b20cce165",
            },
            manifest["infra"]["source"],
        )
        self.assertEqual(
            ("v5.2.1", "27f952fcf8d48a2ba6267c237ea6bea8361fedd2"),
            (
                components["agent-app-orchestrator"]["tag"],
                components["agent-app-orchestrator"]["commit"],
            ),
        )
        self.assertEqual(
            ("v3.1.1", "72efd8d7d51e10d38bf8b89f03b7eb42e1ed8ff2"),
            (
                components["agent-app-ingestion"]["tag"],
                components["agent-app-ingestion"]["commit"],
            ),
        )
        self.assertEqual(
            ("v3.2.2", "b8bd441d578e840de2bc5189afdb3693131cfd71"),
            (
                components["agent-app-ui"]["tag"],
                components["agent-app-ui"]["commit"],
            ),
        )

    def test_infra_is_in_repository_source_without_submodule_pin(self) -> None:
        self.assertFalse((ROOT / ".gitmodules").exists())
        completed = subprocess.run(
            ["git", "ls-files", "--stage", "--", "infra/main.bicep", "infra"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        modes = {line.split()[0] for line in completed.stdout.splitlines()}
        self.assertIn("100644", modes)
        self.assertNotIn("160000", modes)

    def test_preprovision_does_not_fetch_or_checkout_infrastructure(self) -> None:
        scripts = ROOT / "scripts"
        for name in ("preProvision.ps1", "preProvision.sh"):
            with self.subTest(script=name):
                content = (scripts / name).read_text(encoding="utf-8-sig")
                self.assertNotIn("ailz_commit", content)
                self.assertNotIn("git submodule", content)
                self.assertNotIn("fetch --depth 1 origin", content)
                self.assertNotIn("checkout --detach", content)
                self.assertNotIn("config.deployment.infra_checkout", content)
                self.assertIn("infra/main.bicep was not found", content)

    def test_preprovision_fails_when_topology_persistence_fails(self) -> None:
        scripts = ROOT / "scripts"
        ps1 = (scripts / "preProvision.ps1").read_text(encoding="utf-8-sig")
        sh = (scripts / "preProvision.sh").read_text(encoding="utf-8-sig")

        self.assertIn(
            "Failed to persist resolved topology setting $name",
            ps1,
        )
        self.assertIn(
            "if ($LASTEXITCODE -ne 0)",
            ps1,
        )
        self.assertIn(
            "Failed to persist the resolved deployment topology",
            sh,
        )
        self.assertIn('if ! azd env set "$TOPO_KEY" "$TOPO_VALUE"', sh)

    def test_rollback_restores_full_classic_release_contract(self) -> None:
        rollback = json.loads(
            (ROOT / "config" / "deployment" / "rollback.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual("v3.7.0", rollback["umbrella"]["tag"])
        self.assertEqual("v2.3.0", rollback["umbrella"]["ailz_tag"])
        self.assertEqual(
            {
                "gpt-rag-ui": "v2.3.13",
                "gpt-rag-orchestrator": "v3.8.0",
                "gpt-rag-ingestion": "v2.5.0",
            },
            rollback["components"],
        )
        self.assertEqual(
            "false", rollback["azd"]["DEPLOY_HOSTED_AGENT_ORCHESTRATION"]
        )
        self.assertEqual("classic", rollback["azd"]["DEPLOYMENT_TOPOLOGY"])
        self.assertEqual("orchestrator", rollback["azd"]["CHAT_BACKEND"])
        self.assertEqual("false", rollback["azd"]["PREPARE_HOSTED_AGENT"])
        self.assertEqual("false", rollback["azd"]["DEPLOY_HOSTED_AGENT"])
        self.assertEqual(
            "",
            rollback["azd"]["HOSTED_AGENT_IMAGE_STARTUP_COMMAND_SHA256"],
        )
        self.assertEqual(
            "false", rollback["azd"]["DEPLOY_ADMINISTRATIVE_PANEL"]
        )
        self.assertEqual("classic", rollback["azd"]["DEPLOYMENT_TOPOLOGY"])
        self.assertEqual("orchestrator", rollback["azd"]["CHAT_BACKEND"])
        self.assertEqual(
            "false", rollback["azd"]["PRESERVE_CLASSIC_RUNTIME"]
        )
        self.assertEqual(
            "false", rollback["azd"]["HOSTED_CUTOVER_COMPLETE"]
        )
        self.assertEqual(
            "orchestrator", rollback["appConfiguration"]["CHAT_BACKEND"]
        )
        self.assertEqual(
            {
                "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
                "PREPARE_HOSTED_AGENT": "false",
                "DEPLOY_HOSTED_AGENT": "false",
                "HOSTED_AGENT_PREPARED": "false",
                "DEPLOY_ADMINISTRATIVE_PANEL": "false",
                "CHAT_BACKEND": "orchestrator",
                "DEPLOYMENT_TOPOLOGY": "classic",
                "HOSTED_AGENT_BASE_URL": "",
                "HOSTED_AGENT_RESOURCE_SCOPE": "",
                "HOSTED_AGENT_IMAGE_VERSION": "",
                "HOSTED_AGENT_SSE_IDLE_TIMEOUT_SECONDS": "60",
            },
            {
                key: value
                for key, value in rollback["appConfiguration"].items()
                if key != "label"
            },
        )

    def test_rollback_overrides_materialized_hosted_state_before_composition(
        self,
    ) -> None:
        rollback = json.loads(
            (ROOT / "config" / "deployment" / "rollback.json").read_text(
                encoding="utf-8"
            )
        )
        environment = materialized_settings(
            DeploymentMode.HOSTED_NO_PANEL,
            hosted_cutover_complete=True,
        )
        environment.update(
            {
                "PREPARE_HOSTED_AGENT": "true",
                "DEPLOY_HOSTED_AGENT": "true",
                "HOSTED_AGENT_BASE_URL": (
                    "https://agent.example.test/protocols"
                ),
                "HOSTED_AGENT_IMAGE_VERSION": "sha256:" + ("a" * 64),
                "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
            }
        )

        environment.update(rollback["azd"])
        composed = compose_parameters(
            json.loads(
                (ROOT / "main.parameters.json").read_text(encoding="utf-8")
            ),
            environment,
        )
        parameters = composed["parameters"]

        self.assertEqual(DeploymentMode.CLASSIC, resolve_mode(environment))
        self.assertFalse(parameters["prepareHostedAgent"]["value"])
        self.assertFalse(parameters["deployHostedAgent"]["value"])
        self.assertIn(
            "orchestrator",
            [
                app["service_name"]
                for app in parameters["containerAppsList"]["value"]
            ],
        )


class LifecycleParityTests(unittest.TestCase):
    def test_canonical_hosted_agent_adr_is_retained_and_revised(self) -> None:
        adr = ROOT / "docs" / "adr" / "ADR-0001-hosted-agents.md"
        self.assertTrue(adr.is_file())
        content = adr.read_text(encoding="utf-8")
        self.assertIn("ADR-0001", content)
        self.assertIn("implementation boundary implemented by issue #595", content)
        self.assertIn("Implemented accelerator and landing-zone boundary", content)
        self.assertIn("AI Landing Zone remains accelerator-neutral", content)

    def test_powershell_and_shell_hooks_use_shared_mode_contracts(self) -> None:
        pairs = (
            ("preProvision.ps1", "preProvision.sh", "deployment.composition"),
            ("postProvision.ps1", "postProvision.sh", "deployment.appconfig"),
        )
        scripts = ROOT / "scripts"

        for powershell, shell, contract in pairs:
            with self.subTest(contract=contract):
                self.assertIn(
                    contract,
                    (scripts / powershell).read_text(encoding="utf-8-sig"),
                )
                self.assertIn(
                    contract,
                    (scripts / shell).read_text(encoding="utf-8-sig"),
                )

    def test_postprovision_hooks_invoke_panel_setup_module(self) -> None:
        # Issue #611 / ADR-0004: the container-scoped panel Cosmos RBAC
        # script must run from both the PowerShell and POSIX shell
        # postProvision hooks, with parity, exactly like every other
        # config.*.setup module.
        scripts = ROOT / "scripts"
        ps1 = (scripts / "postProvision.ps1").read_text(encoding="utf-8-sig")
        sh = (scripts / "postProvision.sh").read_text(encoding="utf-8-sig")

        self.assertIn("config.panel.setup", ps1)
        self.assertIn("config.panel.setup", sh)

    def test_preprovision_hooks_validate_and_bind_definition_before_topology(
        self,
    ) -> None:
        scripts = ROOT / "scripts"
        for name in ("preProvision.ps1", "preProvision.sh"):
            with self.subTest(script=name):
                content = (scripts / name).read_text(encoding="utf-8-sig")
                appdefinition = content.index("config.appdefinition")
                topology = content.index("config.deployment.topology")
                self.assertLess(appdefinition, topology)
                self.assertIn("--validate", content)
                self.assertIn("'--bind'" if name.endswith(".ps1") else "--bind", content)
                self.assertIn("--env-name", content)
                self.assertIn("binding failed", content)

    def test_postprovision_hooks_plan_placeholders_and_assign_profile_roles(
        self,
    ) -> None:
        scripts = ROOT / "scripts"
        for name in ("postProvision.ps1", "postProvision.sh"):
            with self.subTest(script=name):
                content = (scripts / name).read_text(encoding="utf-8-sig")
                placeholders = content.index("config.deployment.existing_images")
                roles = content.index("--assign-roles")
                outputs = content.index("config.deployment.outputs")
                self.assertLess(placeholders, roles)
                self.assertLess(roles, outputs)
                # Components come from config.appdefinition, not shell parsing.
                self.assertNotIn("--components", content)

    def test_bootstrap_hosted_access_uses_component_project_and_service(self) -> None:
        scripts = ROOT / "scripts"
        for name in ("bootstrapHostedAccess.ps1", "bootstrapHostedAccess.sh"):
            with self.subTest(script=name):
                content = (scripts / name).read_text(encoding="utf-8-sig")
                self.assertIn("AGENTLZ_HOSTED_PROJECT", content)
                self.assertIn("AGENTLZ_HOSTED_SERVICE", content)
                self.assertIn("orchestrator-agent", content)

    def test_postprovision_hooks_delegate_runtime_switch_to_shared_publisher(
        self,
    ) -> None:
        scripts = ROOT / "scripts"
        ps1 = (scripts / "postProvision.ps1").read_text(encoding="utf-8-sig")
        settings_block = ps1.split("$settings = [ordered]@{", 1)[1].split(
            "}", 1
        )[0]
        self.assertNotIn("CHAT_BACKEND", settings_block)
        self.assertIn("config.deployment.appconfig", ps1)
        self.assertIn("$topologyInfo.runtime_topology", ps1)
        self.assertIn(
            "config.deployment.appconfig",
            (scripts / "postProvision.sh").read_text(encoding="utf-8-sig"),
        )

    def test_postprovision_fails_closed_when_foundry_project_is_unresolved(
        self,
    ) -> None:
        content = (ROOT / "scripts" / "postProvision.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn(
            "Microsoft.CognitiveServices/accounts/projects",
            content,
        )

    def test_postprovision_disambiguates_resources_by_explicit_name_or_location(
        self,
    ) -> None:
        content = (ROOT / "scripts" / "postProvision.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn("$preferredMatches = @(", content)
        self.assertIn("-PreferredName (Get-OptionalEnvValue 'KEY_VAULT_NAME')", content)
        self.assertIn(
            "-PreferredName (Get-OptionalEnvValue 'AZURE_AI_SEARCH_NAME')",
            content,
        )
        self.assertIn("$foundryProjectResourceId -match '/accounts/([^/]+)/projects/'", content)
        self.assertIn("$locationMatches = @(", content)
        self.assertIn("[StringComparison]::OrdinalIgnoreCase", content)
        self.assertIn("return $locationMatches[0].name", content)
        self.assertIn("throw", content)

    def test_windows_lifecycle_python_modules_support_jumpbox_python(self) -> None:
        for relative_path in (
            "scripts/preProvision.ps1",
            "scripts/prepareHostedDeployment.ps1",
        ):
            content = (ROOT / relative_path).read_text(encoding="utf-8-sig")
            self.assertIn("sys.path.insert(0", content, relative_path)
            self.assertIn("runpy.run_module", content, relative_path)

    def test_hosted_smoke_uses_json_invocations_contract(self) -> None:
        for relative_path in (
            "scripts/preDeploy.ps1",
            "scripts/preDeploy.sh",
        ):
            content = (ROOT / relative_path).read_text(encoding="utf-8-sig")
            self.assertIn("--input-file", content, relative_path)
            self.assertIn(
                '{"messages":[{"role":"user","content":',
                content,
                relative_path,
            )
            self.assertIn('"content":"Hello!"', content, relative_path)
            self.assertIn("--protocol invocations --new-session", content, relative_path)
            self.assertIn("--validate-smoke", content, relative_path)
            self.assertNotIn("GPT-RAG hosted smoke OK.", content, relative_path)
        for relative_path in (
            "scripts/preDeploy.ps1",
            "scripts/preDeploy.sh",
        ):
            content = (ROOT / relative_path).read_text(encoding="utf-8-sig")
            self.assertIn("--target", content, relative_path)
            self.assertNotIn("-m venv", content, relative_path)

    def test_hosted_configuration_bootstrap_uses_foundation_vault_uri(self) -> None:
        import yaml

        foundation = (ROOT / "infra" / "main.bicep").read_text(encoding="utf-8")
        self.assertIn(
            "output KEY_VAULT_URI string = deployKeyVault ? keyVault!.properties.vaultUri : ''",
            foundation,
        )
        project = yaml.safe_load(
            (ROOT / "hosted-agent" / "azure.yaml").read_text(encoding="utf-8")
        )
        environment = project["services"]["orchestrator-agent"]["env"]
        self.assertEqual("${KEY_VAULT_URI}", environment["KEY_VAULT_URI"])
        self.assertEqual(
            "${APP_CONFIG_TLS_COMPATIBILITY=false}",
            environment["APP_CONFIG_TLS_COMPATIBILITY"],
        )

    def test_postprovision_preserves_search_user_assigned_identity(self) -> None:
        content = (ROOT / "scripts" / "postProvision.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn("Get-UserAssignedIdentityResourceId", content)
        self.assertIn(
            "SEARCH_SERVICE_UAI_RESOURCE_ID = $searchServiceUaiResourceId",
            content,
        )
        self.assertNotIn("SEARCH_SERVICE_UAI_RESOURCE_ID = ''", content)
        self.assertIn('Set-Item -Path "Env:$key" -Value $flatSettings[$key]', content)
        self.assertIn("$foundryProjects.Count -ne 1", content)
        self.assertIn("AI_FOUNDRY_PROJECT_NAME", content)
        self.assertNotIn("aifoundry-default-project", content)
        self.assertNotIn("cognitiveservices account list-projects", content)

    def test_predeploy_hooks_gate_cutover_on_success_marker(self) -> None:
        scripts = ROOT / "scripts"
        for name in ("preDeploy.ps1", "preDeploy.sh"):
            with self.subTest(script=name):
                content = (scripts / name).read_text(encoding="utf-8-sig")
                self.assertIn("HOSTED_CUTOVER_COMPLETE", content)
                if name == "preDeploy.ps1":
                    self.assertIn(
                        "Invoke-PythonModule -ModuleName "
                        "'config.deployment.appconfig' -Arguments "
                        "@('--require-hosted-endpoint')",
                        content,
                    )
                else:
                    self.assertIn(
                        "config.deployment.appconfig --require-hosted-endpoint",
                        content,
                    )

    def test_lifecycle_hooks_resolve_topology_through_shared_module(self) -> None:
        # ADR-0001 rev. 5: config.deployment.topology is the single source of
        # truth for the fresh-vs-existing/sticky/conflict decision.
        # preProvision resolves and materializes it (no --describe: it is the
        # one hook allowed to perform the Azure resource-group/App
        # Configuration lookups); preDeploy and postProvision.ps1 only ever
        # read the already-materialized decision back via --describe and
        # must never re-derive it independently.
        scripts = ROOT / "scripts"

        for name in ("preProvision.ps1", "preProvision.sh"):
            with self.subTest(script=name):
                content = (scripts / name).read_text(encoding="utf-8-sig")
                self.assertIn("config.deployment.topology", content)
                # preProvision resolves and materializes topology itself; it
                # must invoke the module without --describe at least once
                # (a comment may still mention --describe when explaining
                # that later hooks read the decision back).
                self.assertTrue(
                    "-m config.deployment.topology\n" in content
                    or "-m config.deployment.topology)" in content
                    or "-m config.deployment.topology\"" in content
                    or (
                        "Invoke-PythonModule -ModuleName "
                        "'config.deployment.topology'" in content
                    )
                )

        for name in (
            "preDeploy.ps1",
            "preDeploy.sh",
            "postProvision.ps1",
        ):
            with self.subTest(script=name):
                content = (scripts / name).read_text(encoding="utf-8-sig")
                self.assertIn("config.deployment.topology", content)
                self.assertTrue(
                    "--describe" in content
                    or "--validate-hosted-deploy" in content
                )

    def test_postprovision_sh_relies_on_materialized_azd_env_not_reresolution(
        self,
    ) -> None:
        # postProvision.sh intentionally does not call config.deployment.topology
        # directly: it mirrors the azd environment (already populated by
        # preProvision) into process env and delegates App Configuration
        # publishing to config.deployment.appconfig, whose resolve_mode() is
        # explicit-signal-only and therefore safe to call only because the
        # topology decision was already materialized upstream.
        content = (ROOT / "scripts" / "postProvision.sh").read_text(
            encoding="utf-8-sig"
        )
        self.assertNotIn("config.deployment.topology", content)
        self.assertIn("config.deployment.appconfig", content)
        self.assertIn("azd env get-values", content)

    def test_both_predeploy_hooks_select_components_and_hosted_agent(self) -> None:
        scripts = ROOT / "scripts"
        for name in ("preDeploy.ps1", "preDeploy.sh"):
            with self.subTest(script=name):
                content = (scripts / name).read_text(encoding="utf-8-sig")
                # ADR-0001 rev. 5: preDeploy no longer re-derives the hosted
                # flag, deployment mode, or component selection independently.
                # It reads the topology that preProvision already resolved
                # and materialized, via the shared
                # config.deployment.topology --describe contract, and filters
                # manifest.json's components against that read-back selection
                # (config.deployment.composition.selected_components) instead
                # of hardcoding component names per mode.
                self.assertIn("config.deployment.topology", content)
                self.assertIn("--validate-hosted-deploy", content)
                self.assertIn("deploy_hosted_agent_orchestration", content)
                self.assertIn("azd deploy orchestrator-agent", content)
                self.assertIn("AZD_AGENT_SKIP_ACR", content)
                self.assertIn("PYTHONPATH", content)
                if name == "preDeploy.ps1":
                    self.assertIn("runpy.run_module", content)
                self.assertIn(
                    "AGENT_ORCHESTRATOR_AGENT_INVOCATIONS_ENDPOINT", content
                )

    def test_both_predeploy_hooks_export_azd_values_for_final_cutover(
        self,
    ) -> None:
        scripts = ROOT / "scripts"
        ps1 = (scripts / "preDeploy.ps1").read_text(encoding="utf-8-sig")
        sh = (scripts / "preDeploy.sh").read_text(encoding="utf-8-sig")

        self.assertIn('Set-Item -Path "Env:$($prop.Name)"', ps1)
        self.assertIn("azd env get-values", sh)
        self.assertIn('export "$key=$value"', sh)
        for content in (ps1, sh):
            self.assertIn("config.deployment.appconfig", content)

    def test_both_predeploy_hooks_cut_over_after_components_and_persist_last(
        self,
    ) -> None:
        scripts = ROOT / "scripts"
        for name in ("preDeploy.ps1", "preDeploy.sh"):
            with self.subTest(script=name):
                content = (scripts / name).read_text(encoding="utf-8-sig")
                component_failure_gate = content.rindex(
                    "One or more components failed"
                )
                publisher = content.index(
                    "config.deployment.appconfig",
                    component_failure_gate,
                )
                endpoint_persistence = content.index(
                    "azd env set HOSTED_AGENT_BASE_URL",
                    publisher,
                )
                marker_persistence = content.index(
                    "azd env set HOSTED_CUTOVER_COMPLETE true",
                    publisher,
                )
                self.assertLess(component_failure_gate, publisher)
                self.assertLess(publisher, endpoint_persistence)
                self.assertLess(endpoint_persistence, marker_persistence)

    def test_both_predeploy_hooks_fail_closed_on_missing_hosted_prerequisites(
        self,
    ) -> None:
        # preDeploy accepts only the second, digest-backed handoff phase.
        scripts = ROOT / "scripts"

        ps1 = (scripts / "preDeploy.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("HOSTED_AGENT_RESOURCE_SCOPE", ps1)
        self.assertIn("AZURE_AI_PROJECT_ENDPOINT", ps1)
        self.assertIn("AZURE_AI_PROJECT_RESOURCE_ID", ps1)
        self.assertIn("FOUNDRY_PROJECT_ENDPOINT", ps1)
        self.assertIn("--validate-hosted-deploy", ps1)
        self.assertIn("HOSTED_AGENT_PREPARED", ps1)
        self.assertIn("DEPLOY_HOSTED_AGENT", ps1)

        sh = (scripts / "preDeploy.sh").read_text(encoding="utf-8-sig")
        self.assertIn("HOSTED_AGENT_RESOURCE_SCOPE", sh)
        self.assertIn("AZURE_AI_PROJECT_ENDPOINT", sh)
        self.assertIn("AZURE_AI_PROJECT_RESOURCE_ID", sh)
        self.assertIn("FOUNDRY_PROJECT_ENDPOINT", sh)
        self.assertIn("--validate-hosted-deploy", sh)
        self.assertIn("HOSTED_AGENT_PREPARED", sh)
        self.assertIn("DEPLOY_HOSTED_AGENT", sh)
        self.assertIn(
            'export HOSTED_AGENT_PREPARED="$hosted_prepared"',
            sh,
        )
        self.assertIn(
            'export DEPLOY_HOSTED_AGENT="$deploy_hosted"',
            sh,
        )
        self.assertIn(
            'export HOSTED_AGENT_STARTUP_COMMAND="$hosted_startup_command"',
            sh,
        )

    def test_hosted_image_preparation_is_pinned_parity_safe_and_classic_build_free(
        self,
    ) -> None:
        scripts = ROOT / "scripts"
        ps1 = (scripts / "prepareHostedDeployment.ps1").read_text(
            encoding="utf-8-sig"
        )
        sh = (scripts / "prepareHostedDeployment.sh").read_text(
            encoding="utf-8-sig"
        )

        for token in (
            "config.deployment.hosted_prepare",
            "manifest.json",
            "azd env get-values",
        ):
            with self.subTest(token=token):
                self.assertIn(token, ps1)
                self.assertIn(token, sh)

        for name in ("preDeploy.ps1", "preDeploy.sh"):
            content = (scripts / name).read_text(encoding="utf-8-sig")
            self.assertNotIn("config.deployment.hosted_image", content)
            self.assertNotIn("azd provision --environment", content)

    def test_exact_upstream_prepare_deploy_contract_is_mapped(self) -> None:
        parameters = json.loads(
            (ROOT / "main.parameters.json").read_text(encoding="utf-8")
        )["parameters"]
        self.assertEqual(
            "${PREPARE_HOSTED_AGENT=false}",
            parameters["prepareHostedAgent"]["value"],
        )
        self.assertEqual(
            "${DEPLOY_HOSTED_AGENT=false}",
            parameters["deployHostedAgent"]["value"],
        )

    def test_both_predeploy_hooks_filter_manifest_components_by_topology(
        self,
    ) -> None:
        # Component selection now flows from
        # config.deployment.composition.selected_components (exercised in
        # tests/test_deployment_modes.py) instead of being hardcoded per
        # script, so assert each hook filters manifest.json's components list
        # against the topology-provided selection rather than embedding a
        # duplicate ["agent-app-ui", "agent-app-orchestrator", "agent-app-ingestion"]
        # literal.
        scripts = ROOT / "scripts"
        ps1 = (scripts / "preDeploy.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$selectedComponents = @($topologyInfo.components)", ps1)
        self.assertIn("manifest.components", ps1)

        sh = (scripts / "preDeploy.sh").read_text(encoding="utf-8-sig")
        self.assertIn("selected_components", sh)
        self.assertIn('then join(" ")', sh)
        self.assertIn(".name", sh)

    def test_hosted_manifest_contains_no_secret_values(self) -> None:
        content = (ROOT / "hosted-agent" / "azure.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("host: azure.ai.agent", content)
        self.assertIn("language: docker", content)
        self.assertIn("remoteBuild: true", content)
        self.assertIn("protocol: responses", content)
        self.assertIn("protocol: invocations", content)
        self.assertNotIn("API_KEY", content)
        self.assertNotIn("PASSWORD", content)
        self.assertNotIn("InstrumentationKey=", content)
        self.assertNotIn("AccountKey=", content)

    def test_hosted_manifest_disables_azure_vm_resource_detector(self) -> None:
        # Live validation (see docs/adr history and issue #592) reproduced HTTP 500
        # on every hosted /responses and /invocations call: azure-monitor-opentelemetry
        # defaults OTEL_EXPERIMENTAL_RESOURCE_DETECTORS to "azure_app_service,azure_vm"
        # via environ.setdefault(...) whenever the variable is not already present.
        # The Foundry hosted-agent sandbox exposes neither IMDS (169.254.169.254) nor
        # the App Service resource detector's expected environment, so both detectors
        # fail; that failure was observed escaping the SDK's own configure_observability
        # guard and crashing live request handling. Pinning this env var explicitly
        # (to a value the SDK's environ.setdefault will not override) is the fix.
        content = (ROOT / "hosted-agent" / "azure.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("OTEL_EXPERIMENTAL_RESOURCE_DETECTORS:", content)

    def test_hosted_manifest_disables_statsbeat_imds_probe(self) -> None:
        # Live re-validation of the resource-detector fix above still
        # reproduced the same IMDS failure reaching request handling:
        # azure-monitor-opentelemetry-exporter's own "statsbeat" SDK
        # self-monitoring subsystem probes the same IMDS endpoint
        # independently of OTEL_EXPERIMENTAL_RESOURCE_DETECTORS. Disabling
        # statsbeat entirely removes that second IMDS call.
        content = (ROOT / "hosted-agent" / "azure.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL: "true"', content
        )


class AgentLandingZoneContractIntegrityTests(unittest.TestCase):
    SCHEMAS = ("app-definition-v1.schema.json", "platform-outputs-v1.schema.json")

    def test_schema_bytes_match_committed_sha256(self) -> None:
        for name in self.SCHEMAS:
            with self.subTest(schema=name):
                schema_path = ROOT / "contracts" / name
                digest_path = ROOT / "contracts" / f"{name}.sha256"
                data = schema_path.read_bytes()
                self.assertNotIn(b"\r\n", data, "schema must be LF-encoded")
                expected, file_name = digest_path.read_text(
                    encoding="utf-8"
                ).split()
                self.assertEqual(name, file_name)
                self.assertEqual(expected, hashlib.sha256(data).hexdigest())

    def test_schemas_are_versioned_draft_2020_12_documents(self) -> None:
        for name in self.SCHEMAS:
            with self.subTest(schema=name):
                schema = json.loads((ROOT / "contracts" / name).read_text("utf-8"))
                self.assertEqual(
                    "https://json-schema.org/draft/2020-12/schema", schema["$schema"]
                )
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
        self.assertEqual(
            "825db8ef40a81e2c19e5d80d37c565b6b47fc9a6540e9881d35cc12b8fde5aab",
            pins[self.V1[0]],
        )
        self.assertEqual(
            "066c8f5408610ab839d5121d06ca5bc59e8797e551d5c47c875c5ba52f7e0588",
            pins[self.V1[1]],
        )
        for name in self.V1:
            data = (ROOT / "contracts" / name).read_bytes()
            self.assertEqual(pins[name], hashlib.sha256(data).hexdigest())

    def test_v2_renames_prefix_and_keeps_fields_aligned(self) -> None:
        v1_logical, v1_wire = (
            json.loads((ROOT / "contracts" / n).read_text("utf-8")) for n in self.V1
        )
        logical, wire = (
            json.loads((ROOT / "contracts" / n).read_text("utf-8")) for n in self.V2
        )
        self.assertEqual({"const": 2}, logical["properties"]["schema_version"])
        for schema, name in zip((logical, wire), self.V2):
            self.assertTrue(schema["$id"].endswith("/" + name))
            self.assertNotIn("gpt", json.dumps(schema).lower())
        names = wire["properties"]["name"]["enum"]
        event_types = logical["properties"]["event_type"]["enum"]
        self.assertEqual(["agentlz.audit." + t for t in event_types], names)
        self.assertEqual(
            [n.replace("gptrag.", "agentlz.", 1) for n in v1_wire["properties"]["name"]["enum"]],
            names,
        )
        self.assertEqual(v1_logical["required"], logical["required"])
        self.assertEqual(set(v1_logical["properties"]), set(logical["properties"]))
        self.assertEqual(
            logical["required"], wire["properties"]["properties"]["required"]
        )

    def test_readme_registers_v2_and_deprecates_v1(self) -> None:
        readme = (ROOT / "contracts" / "README.md").read_text(encoding="utf-8")
        pins = self._pins("audit-event-v2.sha256")
        for name in self.V2:
            self.assertIn(name, readme)
            self.assertIn(pins[name], readme)
        self.assertIn("Audit event v1 (deprecated)", readme)
        naming = (ROOT / "contracts" / "naming-map.md").read_text(encoding="utf-8")
        self.assertIn("`agentlz.audit.*`", naming)


if __name__ == "__main__":
    unittest.main()
