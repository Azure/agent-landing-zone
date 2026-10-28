"""Offline backend safety and native azd template contracts; no Azure access."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
from string import Template
import subprocess
import unittest
from unittest.mock import patch

from util.terraform_backend import TerraformBackendError, main, resolve_backend

ROOT = Path(__file__).resolve().parents[1]
TF_ROOT = ROOT / "infra" / "terraform"
SUBSCRIPTION = "11111111-2222-3333-4444-555555555555"
OTHER_SUBSCRIPTION = "66666666-7777-8888-9999-aaaaaaaaaaaa"


def environment(**overrides: str) -> dict[str, str]:
    return {
        "AZURE_ENV_NAME": "test-one",
        "ARM_ENVIRONMENT": "public",
        "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION,
        "AZURE_RESOURCE_GROUP": "rg-foundation",
        "AZURE_APP_RESOURCE_GROUP": "rg-app",
        "AZURE_NETWORK_RESOURCE_GROUP": "rg-network",
        "TF_STATE_RESOURCE_GROUP": "rg-independent-state",
        "TF_STATE_STORAGE_ACCOUNT": "examplestate001",
        "TF_STATE_CONTAINER": "tfstate",
        **overrides,
    }


class BackendPrerequisiteTests(unittest.TestCase):
    def test_existing_backend_requires_no_io_and_defaults_only_subscription(self) -> None:
        values = environment()
        original = dict(values)
        with patch("subprocess.run", side_effect=AssertionError("No subprocess allowed")):
            backend = resolve_backend(values)
        self.assertEqual(values, original)
        self.assertEqual(backend.subscription_id, SUBSCRIPTION)
        self.assertEqual(backend.azd_environment(), {
            "TF_STATE_RESOURCE_GROUP": "rg-independent-state",
            "TF_STATE_STORAGE_ACCOUNT": "examplestate001",
            "TF_STATE_CONTAINER": "tfstate",
            "TF_STATE_SUBSCRIPTION_ID": SUBSCRIPTION,
            "ARM_ENVIRONMENT": "public",
        })

    def test_explicit_backend_subscription_is_preserved(self) -> None:
        backend = resolve_backend(environment(TF_STATE_SUBSCRIPTION_ID=OTHER_SUBSCRIPTION))
        self.assertEqual(backend.subscription_id, OTHER_SUBSCRIPTION)

    def test_case_insensitive_workload_group_overlap_is_rejected(self) -> None:
        for group in ("RG-FOUNDATION", "RG-APP", "RG-NETWORK"):
            with self.subTest(group=group), self.assertRaisesRegex(TerraformBackendError, "azd down"):
                resolve_backend(environment(TF_STATE_RESOURCE_GROUP=group))

    def test_group_name_can_match_in_a_distinct_backend_subscription(self) -> None:
        backend = resolve_backend(environment(
            TF_STATE_RESOURCE_GROUP="rg-foundation",
            TF_STATE_SUBSCRIPTION_ID=OTHER_SUBSCRIPTION,
        ))
        self.assertEqual(backend.subscription_id, OTHER_SUBSCRIPTION)

    def test_collapsed_workload_destinations_still_cannot_hold_state(self) -> None:
        with self.assertRaisesRegex(TerraformBackendError, "azd down"):
            resolve_backend(environment(
                TF_STATE_RESOURCE_GROUP="rg-foundation",
                AZURE_APP_RESOURCE_GROUP="",
                AZURE_NETWORK_RESOURCE_GROUP="",
            ))

    def test_bad_optional_workload_destination_types_fail_closed(self) -> None:
        for key in ("AZURE_APP_RESOURCE_GROUP", "AZURE_NETWORK_RESOURCE_GROUP",
                    "AZURE_FOUNDRY_RESOURCE_GROUP"):
            with self.subTest(key=key), self.assertRaises(TerraformBackendError):
                resolve_backend(environment(**{key: 42}))

    def test_missing_prerequisites_never_choose_local_state(self) -> None:
        for key in (
            "AZURE_ENV_NAME", "ARM_ENVIRONMENT", "AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP",
            "TF_STATE_RESOURCE_GROUP", "TF_STATE_STORAGE_ACCOUNT", "TF_STATE_CONTAINER",
        ):
            for value in ("", " ", None, 42):
                with self.subTest(key=key, value=value), self.assertRaises(TerraformBackendError):
                    resolve_backend(environment(**{key: value}))

    def test_invalid_settings_fail_without_echoing_input(self) -> None:
        invalid = {
            "TF_STATE_STORAGE_ACCOUNT": (
                "UPPERCASE", "ab", "a" * 25, "account/name", "${ACCOUNT}", 'secret"value',
            ),
            "TF_STATE_CONTAINER": (
                "ab", "a" * 64, "-state", "state-", "two--hyphens", "UPPER", "state/path",
            ),
            "TF_STATE_RESOURCE_GROUP": ("resource/group", "trailing.", 'secret"value'),
            "TF_STATE_SUBSCRIPTION_ID": ("not-a-uuid", f" {SUBSCRIPTION}", "${SUBSCRIPTION}"),
            "AZURE_SUBSCRIPTION_ID": ("not-a-uuid", "${SUBSCRIPTION}"),
            "AZURE_ENV_NAME": (
                "../other", "two/parts", r"two\parts", "${ENV}", 'secret"value', "a" * 1024,
            ),
        }
        for key, values in invalid.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    with self.assertRaises(TerraformBackendError) as raised:
                        resolve_backend(environment(**{key: value}))
                    self.assertNotIn(value, str(raised.exception))

    def test_shared_key_or_sas_overrides_are_rejected_without_logging_secrets(self) -> None:
        for key in ("ARM_ACCESS_KEY", "ARM_SAS_TOKEN"):
            with self.subTest(key=key), self.assertRaises(TerraformBackendError) as raised:
                resolve_backend(environment(**{key: "sensitive-sentinel"}))
            self.assertNotIn("sensitive-sentinel", str(raised.exception))

    def test_native_arm_credentials_do_not_enter_backend_configuration(self) -> None:
        backend = resolve_backend(environment(
            ARM_CLIENT_ID="client",
            ARM_CLIENT_SECRET="sensitive-sentinel",
            ARM_TENANT_ID="tenant",
            ARM_USE_OIDC="true",
        ))
        self.assertNotIn("sensitive-sentinel", json.dumps(backend.terraform_config()))
        self.assertEqual(
            {key for key in backend.azd_environment() if key.startswith("ARM_")},
            {"ARM_ENVIRONMENT"},
        )

    def test_cloud_context_requires_canonical_adapter_normalization(self) -> None:
        for value in ("AzureCloud", "AzureUSGovernment", "AzureChinaCloud",
                      "PUBLIC", " public", "custom", "german", "${CLOUD}"):
            with self.subTest(value=value), self.assertRaises(TerraformBackendError):
                resolve_backend(environment(ARM_ENVIRONMENT=value))

    def test_cloud_context_is_never_inferred_from_acr_dns_suffix(self) -> None:
        values = environment(ARM_ENVIRONMENT="usgovernment", ACR_DNS_SUFFIX="azurecr.cn")
        self.assertEqual(resolve_backend(values).azure_environment, "usgovernment")
        del values["ARM_ENVIRONMENT"]
        with self.assertRaisesRegex(TerraformBackendError, "ARM_ENVIRONMENT"):
            resolve_backend(values)

    def test_check_does_not_silently_materialize_subscription_default(self) -> None:
        with patch.dict(os.environ, environment(), clear=True), self.assertLogs(level="ERROR"):
            self.assertEqual(main(), 1)

    def test_check_succeeds_without_external_commands_and_reports_evidence_limits(self) -> None:
        with (
            patch.dict(os.environ, environment(TF_STATE_SUBSCRIPTION_ID=SUBSCRIPTION), clear=True),
            patch("subprocess.run", side_effect=AssertionError("No subprocess allowed")),
            self.assertLogs(level="INFO") as logs,
        ):
            self.assertEqual(main(), 0)
        self.assertIn("independent verification", "\n".join(logs.output))
        self.assertIn("disable state locking", "\n".join(logs.output))


class NativeBackendTemplateTests(unittest.TestCase):
    def test_native_azd_simple_substitution_preserves_json_types(self) -> None:
        # Installed azd 1.37.1 (6bd1275...) createInputParametersFile does raw
        # drone/envsubst replacement from t.env.Getenv, without type conversion.
        # Only simple ${NAME} tokens are used here; this is not a general-purpose
        # reimplementation of azd/envsubst or an assertion of live Azure access.
        template = (TF_ROOT / "provider.conf.json").read_text(encoding="utf-8")
        for env_name in ("test-one", "test_two", "test.Three"):
            values = environment(AZURE_ENV_NAME=env_name)
            backend = resolve_backend(values)
            stored = {**values, **backend.azd_environment()}
            rendered = json.loads(Template(template).substitute(stored))
            self.assertEqual(rendered, backend.terraform_config())
            self.assertIs(rendered["use_azuread_auth"], True)
            self.assertIs(rendered["use_cli"], True)
            self.assertIs(rendered["lookup_blob_endpoint"], True)
            self.assertTrue(all(isinstance(value, str) for key, value in rendered.items()
                                if key not in ("use_azuread_auth", "use_cli", "lookup_blob_endpoint")))

    def test_environments_never_share_blob_keys(self) -> None:
        first = resolve_backend(environment(AZURE_ENV_NAME="test-one")).terraform_config()
        second = resolve_backend(environment(AZURE_ENV_NAME="test-two")).terraform_config()
        self.assertNotEqual(first["key"], second["key"])
        self.assertEqual(first["storage_account_name"], second["storage_account_name"])
        self.assertEqual(first["container_name"], second["container_name"])

    def test_native_backend_cloud_context_transport(self) -> None:
        template = (TF_ROOT / "provider.conf.json").read_text(encoding="utf-8")
        for cloud in ("public", "usgovernment", "china"):
            with self.subTest(cloud=cloud):
                values = environment(ARM_ENVIRONMENT=cloud)
                backend = resolve_backend(values)
                stored = {**values, **backend.azd_environment()}
                rendered = json.loads(Template(template).substitute(stored))
                self.assertEqual(rendered, backend.terraform_config())
                self.assertEqual(rendered["environment"], cloud)
                self.assertEqual(backend.azd_environment()["ARM_ENVIRONMENT"], cloud)

    def test_backend_and_native_provider_auth_are_explicit(self) -> None:
        providers = (TF_ROOT / "providers.tf").read_text(encoding="utf-8")
        # The literal declaration is also necessary for native azd's remote
        # backend detection, which scans *.tf files for this text.
        self.assertRegex(providers, r'backend "azurerm"\s*\{\}')
        self.assertEqual(len(re.findall(r"\buse_cli\s*=\s*true", providers)), 2)
        self.assertEqual(len(re.findall(r"\bsubscription_id\s*=\s*var.subscriptionId", providers)), 2)
        self.assertEqual(len(re.findall(r"\btenant_id\s*=\s*var.tenantId", providers)), 2)
        self.assertEqual(len(re.findall(
            r"\benvironment\s*=\s*var.azureCloud.environment", providers,
        )), 2)
        self.assertNotRegex(providers, r"\b(client_secret|client_certificate_password|access_key|sas_token)\s*=")

    def test_every_declared_provider_has_an_exact_constraint(self) -> None:
        versions = (TF_ROOT / "versions.tf").read_text(encoding="utf-8")
        sources = re.findall(r'\bsource\s*=\s*"([^"]+)"', versions)
        pins = re.findall(r'\bversion\s*=\s*"= \d+\.\d+\.\d+"', versions)
        self.assertGreaterEqual(len(sources), 2)
        self.assertEqual(len(sources), len(pins))
        self.assertIn("hashicorp/azurerm", sources)
        self.assertIn("Azure/azapi", sources)

    def test_root_lock_matches_all_exact_pins_with_multiplatform_hashes(self) -> None:
        versions = (TF_ROOT / "versions.tf").read_text(encoding="utf-8")
        pins = {
            source.lower(): version for source, version in re.findall(
                r'source\s*=\s*"([^"]+)"\s*version\s*=\s*"= (\d+\.\d+\.\d+)"',
                versions,
            )
        }
        lock = (TF_ROOT / ".terraform.lock.hcl").read_text(encoding="utf-8")
        blocks = dict(re.findall(
            r'provider "registry\.terraform\.io/([^"]+)" \{(.*?)\n\}', lock, re.DOTALL,
        ))
        self.assertEqual(set(blocks), set(pins))
        for source, block in blocks.items():
            with self.subTest(source=source):
                selected = re.search(r'\bversion\s*=\s*"([^"]+)"', block)
                self.assertIsNotNone(selected)
                self.assertEqual(selected.group(1), pins[source])
                # The real providers lock command fetches linux_amd64 and
                # windows_amd64; each contributes an unpacked-package h1 hash.
                self.assertGreaterEqual(len(re.findall(r'"h1:[^"]+"', block)), 2)

    @unittest.skipUnless(shutil.which("git"), "git is needed to exercise exclusions")
    def test_generated_inputs_are_ignored_but_backend_template_and_lock_are_not(self) -> None:
        ignored = (
            ".azure/test/infra/terraform/main.tfvars.json",
            "infra/terraform/main.tfvars.json",
            "infra/terraform/.terraform/providers/plugin",
            "infra/terraform/.terraform-plugin-cache/plugin",
            "infra/terraform/terraform.tfstate",
            "infra/terraform/terraform.tfstate.backup",
            "infra/terraform/.terraform.tfstate.lock.info",
            "infra/terraform/test.tfplan",
            "infra/terraform/test.tfplan.json",
            "infra/terraform/test.plan",
            "infra/terraform/test.plan.json",
            "infra/terraform/private.tfvars",
            "infra/terraform/private.tfvars.json",
            "infra/terraform/private.tfbackend",
            "infra/terraform/private.backend.conf",
            "infra/terraform/private.backend.conf.json",
            "infra/terraform/crash.log",
        )
        tracked = (
            "infra/terraform/provider.conf.json",
            "infra/terraform/providers.tf",
            "infra/terraform/versions.tf",
            "infra/terraform/.terraform.lock.hcl",
        )
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin", "-z"],
            cwd=ROOT, input=("\0".join((*ignored, *tracked)) + "\0").encode(),
            capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.stdout.decode().rstrip("\0").split("\0")), set(ignored))


if __name__ == "__main__":
    unittest.main()
