from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.deployment import appconfig
from config.deployment.composition import compose_parameters


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "samples/custom-app/containerapp"
CLASSIC = {
    "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false",
    "DEPLOY_ADMINISTRATIVE_PANEL": "false",
}


def source_parameters() -> dict[str, object]:
    return json.loads((ROOT / "main.parameters.json").read_text(encoding="utf-8"))


def apps_for(environment: dict[str, str]) -> list[dict[str, object]]:
    composed = compose_parameters(source_parameters(), environment)
    return composed["parameters"]["containerAppsList"]["value"]


class CustomAppCompositionTests(unittest.TestCase):
    def test_trio_composition_unchanged_without_custom_definition(self) -> None:
        expected = source_parameters()["parameters"]["containerAppsList"]["value"]
        self.assertEqual(expected, apps_for(dict(CLASSIC)))
        self.assertEqual(
            expected,
            apps_for({**CLASSIC, "AGENTLZ_APP_DEFINITION": "app-definition.json"}),
        )

    def test_sample_containerapp_composes_into_container_apps_list(self) -> None:
        apps = apps_for({**CLASSIC, "AGENTLZ_APP_DEFINITION": SAMPLE})
        trio = source_parameters()["parameters"]["containerAppsList"]["value"]
        self.assertEqual(trio, apps[: len(trio)])
        custom = apps[len(trio):]
        self.assertEqual(1, len(custom))
        web = custom[0]
        self.assertEqual("web", web["service_name"])
        self.assertTrue(web["external"])
        self.assertEqual("0.5", web["cpu"])
        self.assertEqual("1.0Gi", web["memory"])
        self.assertEqual("WEB_APP", web["canonical_name"])
        self.assertIsNone(web["name"])
        self.assertNotIn("image", web)
        self.assertIn("AcrPull", web["roles"])
        self.assertEqual(set(trio[2]), set(web))

    def test_sample_folder_or_file_selection_is_equivalent(self) -> None:
        by_folder = apps_for({**CLASSIC, "AGENTLZ_APP_DEFINITION": SAMPLE})
        by_file = apps_for(
            {**CLASSIC, "AGENTLZ_APP_DEFINITION": f"{SAMPLE}/app-definition.json"}
        )
        self.assertEqual(by_folder, by_file)

    def test_hosted_sample_adds_no_container_app(self) -> None:
        expected = source_parameters()["parameters"]["containerAppsList"]["value"]
        apps = apps_for(
            {**CLASSIC, "AGENTLZ_APP_DEFINITION": "samples/custom-app/hosted"}
        )
        self.assertEqual(expected, apps)

    def test_custom_hosted_prepares_foundation_without_bundled_deployment(self) -> None:
        baseline = compose_parameters(source_parameters(), {**CLASSIC, "NETWORK_ISOLATION": "true"})
        for selection in (
            "samples/custom-app/hosted",
            "samples/custom-app/hosted/app-definition.json",
        ):
            with self.subTest(selection=selection):
                environment = {
                    **CLASSIC,
                    "AGENTLZ_APP_DEFINITION": selection,
                    # A leftover bundled digest must not enable its agent.
                    "HOSTED_AGENT_IMAGE_VERSION": "sha256:" + "a" * 64,
                    "NETWORK_ISOLATION": "true",
                }
                composed = compose_parameters(source_parameters(), environment)
                parameters = composed["parameters"]
                self.assertTrue(parameters["prepareHostedAgent"]["value"])
                self.assertFalse(parameters["grantHostedAgentProjectManager"]["value"])
                self.assertFalse(parameters["deployHostedAgent"]["value"])
                self.assertEqual(
                    composed, compose_parameters(source_parameters(), environment)
                )
                # Only prerequisite selection and its two public metadata
                # values change: not models, capacity, services or topology.
                parameters["prepareHostedAgent"] = baseline["parameters"]["prepareHostedAgent"]
                parameters["grantHostedAgentProjectManager"] = baseline["parameters"]["grantHostedAgentProjectManager"]
                settings = parameters["additionalAppConfigurationSettings"]["value"]
                for setting in settings:
                    if setting["name"] in {"PREPARE_HOSTED_AGENT", "HOSTED_AGENT_PREPARED"}:
                        self.assertEqual("true", setting["value"])
                        setting["value"] = "false"
                    elif setting["name"] == "HOSTED_AGENT_IMAGE_VERSION":
                        setting["value"] = ""
                self.assertEqual(baseline, composed)

    def test_container_only_and_bundled_classic_do_not_prepare_hosted_foundation(self) -> None:
        for selection in ("", "app-definition.json", SAMPLE):
            with self.subTest(selection=selection):
                composed = compose_parameters(
                    source_parameters(), {**CLASSIC, "AGENTLZ_APP_DEFINITION": selection}
                )
                self.assertFalse(composed["parameters"]["prepareHostedAgent"]["value"])
                self.assertFalse(composed["parameters"]["deployHostedAgent"]["value"])
                self.assertEqual(
                    source_parameters()["parameters"]["grantHostedAgentProjectManager"],
                    composed["parameters"]["grantHostedAgentProjectManager"],
                )

    def test_mixed_components_prepare_but_infra_only_definition_does_not(self) -> None:
        container = json.loads(
            (ROOT / SAMPLE / "app-definition.json").read_text(encoding="utf-8")
        )["components"][0]
        agent = json.loads(
            (ROOT / "samples/custom-app/hosted/app-definition.json").read_text(encoding="utf-8")
        )["components"][0]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "app-definition.json"
            for components, expected in (([], False), ([container], False), ([container, agent], True)):
                with self.subTest(components=[item["name"] for item in components]):
                    path.write_text(json.dumps({"components": components}), encoding="utf-8")
                    composed = compose_parameters(
                        source_parameters(), {**CLASSIC, "AGENTLZ_APP_DEFINITION": str(path)}
                    )
                    self.assertEqual(expected, composed["parameters"]["prepareHostedAgent"]["value"])
                    self.assertFalse(composed["parameters"]["deployHostedAgent"]["value"])
                    if expected:
                        self.assertFalse(composed["parameters"]["grantHostedAgentProjectManager"]["value"])
                    apps = composed["parameters"]["containerAppsList"]["value"]
                    self.assertEqual(3 + (container in components), len(apps))

    def test_custom_hosted_postprovision_preserves_preparation_and_classic_runtime(self) -> None:
        environment = {
            **CLASSIC,
            "AGENTLZ_APP_DEFINITION": "samples/custom-app/hosted",
            "AZURE_RESOURCE_GROUP": "rg-test",
            "RESOURCE_TOKEN": "test",
        }
        with patch.object(
            appconfig, "_container_app",
            return_value={"fqdn": "app.example.test", "principalId": "runtime-principal"},
        ):
            settings = appconfig.build_settings(environment)
        self.assertEqual("true", settings["PREPARE_HOSTED_AGENT"])
        self.assertEqual("true", settings["HOSTED_AGENT_PREPARED"])
        self.assertEqual("false", settings["DEPLOY_HOSTED_AGENT"])
        self.assertEqual("false", settings["DEPLOY_HOSTED_AGENT_ORCHESTRATION"])
        self.assertEqual("classic", settings["DEPLOYMENT_TOPOLOGY"])
        self.assertEqual("orchestrator", settings["CHAT_BACKEND"])
        self.assertEqual("", settings["HOSTED_AGENT_BASE_URL"])
        self.assertEqual(3, len(json.loads(settings["CONTAINER_APPS"])))

    def test_bundled_hosted_keeps_operator_grant_default(self) -> None:
        for topology in ("hosted-panel", "hosted-no-panel"):
            with self.subTest(topology=topology):
                composed = compose_parameters(source_parameters(), {
                    "DEPLOYMENT_TOPOLOGY": topology,
                    "HOSTED_AGENT_RESOURCE_SCOPE": "api://agent/.default",
                })
                self.assertTrue(composed["parameters"]["prepareHostedAgent"]["value"])
                self.assertEqual(
                    source_parameters()["parameters"]["grantHostedAgentProjectManager"],
                    composed["parameters"]["grantHostedAgentProjectManager"],
                )


if __name__ == "__main__":
    unittest.main()
