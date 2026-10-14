"""Offline runtime bootstrap contracts; every Azure boundary is a fixture."""

from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
import subprocess
import unittest
from unittest.mock import Mock, patch

from config.deployment import hosted_access as access


SUB = "11111111-1111-4111-8111-111111111111"
PRINCIPAL = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
PREFIX = f"/subscriptions/{SUB}/resourceGroups/test-group/providers/"
ACCOUNT = PREFIX + "Microsoft.CognitiveServices/accounts/test-foundry"
MODEL = PREFIX + "Microsoft.CognitiveServices/accounts/test-model"
PROJECT = ACCOUNT + "/projects/test-project"
ENDPOINT = "https://test-foundry.services.ai.azure.com/api/projects/test-project"
STORE = PREFIX + "Microsoft.AppConfiguration/configurationStores/test-store"
VAULT = PREFIX + "Microsoft.KeyVault/vaults/test-vault"
SECRET = VAULT + "/secrets/AUDIT-HMAC-KEY"
ENV = {
    "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
    "AZURE_SUBSCRIPTION_ID": SUB, "AZURE_RESOURCE_GROUP": "test-group",
    "AZURE_AI_PROJECT_RESOURCE_ID": PROJECT, "AZURE_AI_PROJECT_ENDPOINT": ENDPOINT,
    "APP_CONFIG_ENDPOINT": "https://test-store.azconfig.io",
}


class AzureFixture:
    def __init__(self):
        self.calls = []
        self.writes = []
        self.assignments = []
        self.live = {
            "name": "agent-app-orchestrator",
            "instance_identity": {"principal_id": PRINCIPAL},
            "agent_endpoint": {
                "protocol_configuration": {"responses": {}, "unexpected-extension": {}},
                "version_selector": {"version_selection_rules": [
                    {"type": "fixedratio", "traffic_percentage": 100, "agent_version": "7"}
                ]},
            },
        }
        self.version = {"name": "agent-app-orchestrator", "version": "7", "definition": {"kind": "hosted", "protocol_versions": [{"protocol": "unexpected-extension"}]}}
        self.settings = {
            key: {"key": key, "label": "agent-lz", "value": value, "contentType": "text/plain"}
            for key, value in {
                "SUBSCRIPTION_ID": SUB, "AZURE_RESOURCE_GROUP": "test-group",
                "AI_FOUNDRY_ACCOUNT_NAME": "test-model",
                "KEY_VAULT_URI": "https://test-vault.vault.azure.net/",
            }.items()
        }
        self.settings["AUDIT_HMAC_KEY"] = {
            "key": "AUDIT_HMAC_KEY", "label": "agent-lz",
            "contentType": access.KV_REFERENCE + ";charset=utf-8",
            "value": json.dumps({"uri": "https://test-vault.vault.azure.net/secrets/AUDIT-HMAC-KEY/abc123"}),
        }
        self.resources = {
            PROJECT: {"id": PROJECT},
            ACCOUNT: {
                "id": ACCOUNT, "name": "test-foundry", "type": "Microsoft.CognitiveServices/accounts",
                "kind": "AIServices", "properties": {
                    "customSubDomainName": "test-foundry",
                    "futureServiceMetadata": [{"newList": ["ignored"]}],
                },
            },
            MODEL: {
                "id": MODEL, "name": "test-model", "type": "Microsoft.CognitiveServices/accounts",
                "kind": "AIServices", "properties": {"futureServiceMetadata": ["ignored"]},
            },
            STORE: {"id": STORE, "endpoint": ENV["APP_CONFIG_ENDPOINT"]},
            VAULT: {"id": VAULT, "properties": {"vaultUri": "https://test-vault.vault.azure.net/", "enableRbacAuthorization": True}},
        }
        self.fail_role = None
        self.create_errors = []

    def assignment(self, scope=STORE, role=access.Role.CONFIG, **overrides):
        return dict({
            "scope": scope, "principalId": PRINCIPAL, "principalType": "ServicePrincipal",
            "roleDefinitionId": f"/subscriptions/{SUB}/providers/Microsoft.Authorization/roleDefinitions/{role.value}",
            "condition": None, "conditionVersion": None,
        }, **overrides)

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["resource", "show"]:
            return self.resources[args[args.index("--ids") + 1]]
        for command, resource_type in (
            (["appconfig", "show"], "Microsoft.AppConfiguration/configurationStores"),
            (["keyvault", "show"], "Microsoft.KeyVault/vaults"),
        ):
            if args[:len(command)] == command:
                assert "--ids" not in args, "These fixtures require explicit name/group/subscription."
                name = args[args.index("--name") + 1]
                group = args[args.index("--resource-group") + 1]
                sub = args[args.index("--subscription") + 1]
                return self.resources[f"/subscriptions/{sub}/resourceGroups/{group}/providers/{resource_type}/{name}"]
        if args[0] == "rest":
            url = args[args.index("--url") + 1]
            if url.startswith(access.ARM_ENDPOINT + "/"):
                scope, query = url.removeprefix(access.ARM_ENDPOINT).split("?", 1)
                assert query == "api-version=2025-06-01"
                assert args == ["rest", "--method", "get", "--url", url]
                return self.resources[scope]
            return self.version if "/versions/" in url else self.live
        if args[:3] == ["appconfig", "kv", "list"]:
            key = args[args.index("--key") + 1]
            return [self.settings[key]] if key in self.settings else []
        if args[:3] == ["role", "assignment", "list"]:
            return self.assignments
        if args[:3] == ["role", "assignment", "create"]:
            self.writes.append(args)
            role = access.Role(args[args.index("--role") + 1])
            if self.fail_role == role:
                raise access.AzureCommandError()
            if self.create_errors:
                raise access.AzureCommandError(self.create_errors.pop(0))
            self.assignments.append(self.assignment(args[args.index("--scope") + 1], role))
            return self.assignments[-1]
        raise AssertionError(f"Unexpected Azure fixture call: {args}")


class HostedAccessTests(unittest.TestCase):
    def setUp(self):
        self.azure = AzureFixture()
        self.sleep = Mock()

    def discover(self, env=None):
        return access.discover(ENV if env is None else env, run=self.azure)

    def apply(self, plan=None):
        return access.apply(plan or self.discover(), run=self.azure, sleep=self.sleep)

    def fails_discovery(self, env=None):
        with self.assertRaises(access.AccessError):
            self.discover(env)
        self.assertEqual([], self.azure.writes)

    def test_classic_noop_no_azure_even_apply(self):
        plan = self.discover({"DEPLOYMENT_TOPOLOGY": "classic"})
        self.assertTrue(plan.classic)
        self.assertEqual((), self.apply(plan))
        self.assertEqual([], self.azure.calls)

    def test_classic_legacy_flag_and_canonical_override(self):
        for env in (
            {"DEPLOY_HOSTED_AGENT_ORCHESTRATION": "false"},
            {"DEPLOYMENT_TOPOLOGY": "classic", "DEPLOY_HOSTED_AGENT_ORCHESTRATION": "true"},
        ):
            with self.subTest(environment=env), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0, access.main(["--plan"], environment=env, run=self.azure))
                result = json.loads(output.getvalue())
                self.assertTrue(result["classic"])
                self.assertEqual([], result["grants"])
        self.assertEqual([], self.azure.calls)

    def test_exact_three_roles_and_actual_instance(self):
        plan = self.discover()
        self.assertEqual(PRINCIPAL, plan.principal_id)
        self.assertEqual("7", plan.agent_version)
        self.assertEqual("configured", plan.audit)
        self.assertEqual([
            (access.Role.CONFIG, STORE),
            (access.Role.MODEL, PREFIX + "Microsoft.CognitiveServices/accounts/test-model"),
            (access.Role.SECRET, SECRET),
        ], [(grant.role, grant.scope) for grant in plan.grants])

    def test_custom_instance_discovery_is_read_only_and_validates_actual_name(self):
        self.azure.live["name"] = self.azure.version["name"] = "sample-hosted-agent"
        instance = access.discover_instance(
            {**ENV, "DEPLOYMENT_TOPOLOGY": "classic"}, name="sample-hosted-agent", run=self.azure,
        )
        self.assertEqual(PRINCIPAL, instance.principal_id)
        self.assertEqual("7", instance.agent_version)
        self.assertFalse(any(call[:2] == ["appconfig", "kv"] for call in self.azure.calls))
        self.assertEqual([], self.azure.writes)
        with self.assertRaisesRegex(access.AccessError, "name does not match"):
            access.discover_instance(ENV, name="wrong-agent", run=self.azure)
        self.assertEqual([], self.azure.writes)
        self.assertTrue(all("secret" not in call[:2] for call in self.azure.calls))

    def test_assignment_inventory_does_not_require_microsoft_graph(self):
        plan = self.discover()
        access.inspect_assignments(plan, run=self.azure)
        reads = [args for args in self.azure.calls if args[:3] == ["role", "assignment", "list"]]
        self.assertEqual(3, len(reads))
        for args in reads:
            self.assertNotIn("--assignee", args)
            self.assertEqual(PRINCIPAL, args[args.index("--assignee-object-id") + 1])
            self.assertEqual("false", args[args.index("--fill-principal-name") + 1])

    def test_latest_routing_resolves_and_verifies_concrete_hosted_version(self):
        self.azure.live["agent_endpoint"]["version_selector"]["version_selection_rules"][0].update(
            type="FixedRatio", agent_version="@latest"
        )
        self.azure.live["versions"] = {"latest": self.azure.version.copy()}
        plan = self.discover()
        self.assertEqual("7", plan.agent_version)
        self.assertEqual(PRINCIPAL, plan.principal_id)
        self.assertEqual(3, len(plan.grants))
        version_reads = [
            args[args.index("--url") + 1] for args in self.azure.calls
            if args[0] == "rest" and "/versions/" in args[args.index("--url") + 1]
        ]
        self.assertEqual([f"{ENDPOINT}/agents/agent-app-orchestrator/versions/7?api-version=v1"], version_reads)
        self.assertEqual([], self.azure.writes)

    def test_latest_routing_requires_complete_bound_metadata(self):
        invalid_latest = [
            None, [], {},
            dict(self.azure.version, name="other-agent"),
            dict(self.azure.version, definition={"kind": "prompt"}),
            dict(self.azure.version, definition=None),
        ]
        invalid_latest.extend(
            dict(self.azure.version, version=value)
            for value in (None, 7, True, "", "0", "@latest", "../7", "7?other=1")
        )
        for latest in invalid_latest:
            with self.subTest(latest=latest):
                self.azure = AzureFixture()
                self.azure.live["agent_endpoint"]["version_selector"]["version_selection_rules"][0]["agent_version"] = "@latest"
                self.azure.live["versions"] = {"latest": latest}
                self.fails_discovery()
                self.assertFalse(any("/versions/" in str(args) for args in self.azure.calls))

    def test_latest_routing_requires_versions_container(self):
        for versions in (None, [], {}, {"other": self.azure.version}):
            with self.subTest(versions=versions):
                self.azure = AzureFixture()
                self.azure.live["agent_endpoint"]["version_selector"]["version_selection_rules"][0]["agent_version"] = "@latest"
                self.azure.live["versions"] = versions
                self.fails_discovery()

    def test_latest_routing_still_checks_concrete_response(self):
        for key, value in (
            ("name", "other-agent"), ("version", "8"), ("definition", {"kind": "prompt"}),
        ):
            with self.subTest(key=key):
                self.azure = AzureFixture()
                self.azure.live["agent_endpoint"]["version_selector"]["version_selection_rules"][0]["agent_version"] = "@latest"
                self.azure.live["versions"] = {"latest": self.azure.version.copy()}
                self.azure.version[key] = value
                self.fails_discovery()

    def test_unknown_version_aliases_never_fall_back_to_latest(self):
        for alias in ("latest", "@Latest", "@previous", "0", "../7", "7?other=1"):
            with self.subTest(alias=alias):
                self.azure = AzureFixture()
                self.azure.live["agent_endpoint"]["version_selector"]["version_selection_rules"][0]["agent_version"] = alias
                self.azure.live["versions"] = {"latest": self.azure.version.copy()}
                self.fails_discovery()

    def test_numeric_route_does_not_use_latest_metadata(self):
        self.azure.live["versions"] = {"latest": dict(self.azure.version, version="8")}
        self.assertEqual("7", self.discover().agent_version)

    def test_role_allowlist_excludes_search_blob_conversation_elevated(self):
        self.assertEqual({
            "516239f1-63e1-4d78-a4de-a74fb236a071",
            "4633458b-17de-408a-b874-0445c86b69e6",
            "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",
        }, {grant.role.value for grant in self.discover().grants})
        for role, scope in [("Owner", STORE), (access.Role.CONFIG, PREFIX), (access.Role.SECRET, VAULT), (access.Role.MODEL, PROJECT)]:
            with self.subTest(role=role), self.assertRaises(access.AccessError):
                access.Grant(role, scope)

    def test_absent_audit_never_reads_vault_or_creates_secret(self):
        del self.azure.settings["AUDIT_HMAC_KEY"]
        plan = self.discover()
        self.assertEqual("not-configured", plan.audit)
        self.assertEqual(2, len(plan.grants))
        self.assertFalse(any("keyvault" in call for call in self.azure.calls))

    def test_missing_inputs_fail_before_writes(self):
        for key in ("AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "APP_CONFIG_ENDPOINT", "AZURE_AI_PROJECT_RESOURCE_ID", "AZURE_AI_PROJECT_ENDPOINT"):
            with self.subTest(key=key):
                self.fails_discovery({k: v for k, v in ENV.items() if k != key})

    def test_no_identity_fallbacks(self):
        for identity in (None, {}, {"principal_id": OTHER.replace("-", "")}, {"principal_id": "not-guid"}, {"principal_id": "00000000-0000-0000-0000-000000000000"}):
            with self.subTest(identity=identity):
                self.azure.live["instance_identity"] = identity
                self.azure.live["identity"] = {"principalId": PRINCIPAL}
                self.fails_discovery()

    def test_wrong_name_kind_version_and_routing_fail(self):
        for target, key, value in [
            ("live", "name", "other-agent"), ("version", "name", "other-agent"),
            ("version", "version", "8"), ("version", "definition", {"kind": "prompt"}),
            ("live", "agent_endpoint", {"version_selector": {"version_selection_rules": []}}),
        ]:
            with self.subTest(target=target, key=key):
                self.azure = AzureFixture()
                getattr(self.azure, target)[key] = value
                self.fails_discovery()

    def test_unknown_protocol_fields_do_not_bypass_identity_validation(self):
        self.assertEqual(PRINCIPAL, self.discover().principal_id)
        self.azure.live["instance_identity"]["principal_id"] = "bad"
        self.fails_discovery()

    def test_project_endpoint_allowlist_and_arm_mapping(self):
        for endpoint in (
            ENDPOINT.replace("https:", "http:"), ENDPOINT.replace("test-foundry.", "evil."),
            ENDPOINT.replace("azure.com", "azure.com.evil.invalid"),
            ENDPOINT + "?", ENDPOINT + "#", ENDPOINT + "/../other",
            ENDPOINT.replace("https://", "https://user@"), ENDPOINT.replace(".com/", ".com:444/"),
            ENDPOINT.replace("test-project", "other-project"),
        ):
            with self.subTest(endpoint=endpoint):
                self.fails_discovery(dict(ENV, AZURE_AI_PROJECT_ENDPOINT=endpoint))

    def test_project_scope_and_alias_mismatch(self):
        for env in (
            dict(ENV, AZURE_AI_PROJECT_RESOURCE_ID=PROJECT.replace(SUB, OTHER)),
            dict(ENV, AZURE_AI_PROJECT_RESOURCE_ID=PROJECT.replace("test-group", "other-group")),
            dict(ENV, FOUNDRY_PROJECT_ENDPOINT=ENDPOINT.replace("test-foundry", "other")),
            dict(ENV, AZURE_AI_PROJECT_ID=PROJECT + "/agents/other"),
        ):
            with self.subTest(env=env):
                self.fails_discovery(env)

    def test_handoff_agent_name_and_project_bindings(self):
        handoff = {"agent": {"name": "custom-agent"}, "foundry": {"projectEndpoint": ENDPOINT, "projectResourceId": PROJECT}}
        self.azure.live["name"] = self.azure.version["name"] = "custom-agent"
        env = dict(ENV, HOSTED_AGENT_DEPLOYMENT=json.dumps(handoff))
        self.assertEqual("custom-agent", self.discover(env).agent_name)
        self.fails_discovery(dict(env, HOSTED_AGENT_NAME="conflicting"))
        handoff["foundry"]["projectResourceId"] = PROJECT.replace(SUB, OTHER)
        self.fails_discovery(dict(ENV, HOSTED_AGENT_DEPLOYMENT=json.dumps(handoff)))

    def test_null_prerequisite_handoff_uses_default_agent(self):
        self.assertEqual("agent-app-orchestrator", self.discover(dict(ENV, HOSTED_AGENT_DEPLOYMENT='{"agent":null,"foundry":null}')).agent_name)

    def test_malformed_handoff_json(self):
        for value in ("{", "[]", '{"agent":"wrong-type"}'):
            with self.subTest(value=value):
                self.fails_discovery(dict(ENV, HOSTED_AGENT_DEPLOYMENT=value))

    def test_target_resource_metadata_scope_mismatch(self):
        for resource in (PROJECT, ACCOUNT, STORE, PREFIX + "Microsoft.CognitiveServices/accounts/test-model", VAULT):
            with self.subTest(resource=resource):
                self.azure = AzureFixture()
                self.azure.resources[resource]["id"] = resource.replace(SUB, OTHER)
                self.fails_discovery()

    def test_account_raw_arm_argv_and_named_store_vault_reads(self):
        self.discover()
        expected = [
            ["rest", "--method", "get", "--url", f"https://management.azure.com{scope}?api-version=2025-06-01"]
            for scope in (ACCOUNT, MODEL)
        ] + [
            ["appconfig", "show", "--name", "test-store", "--resource-group", "test-group", "--subscription", SUB],
            ["keyvault", "show", "--name", "test-vault", "--resource-group", "test-group", "--subscription", SUB],
        ]
        for command in expected:
            self.assertIn(command, self.azure.calls)
        self.assertFalse(any(command[0] == "cognitiveservices" for command in self.azure.calls))
        self.assertEqual(
            [["resource", "show", "--ids", PROJECT]],
            [command for command in self.azure.calls if "--ids" in command],
        )

    def test_account_raw_arm_rejects_unbound_scope_before_cli(self):
        run = Mock()
        for scope in (ACCOUNT.replace(SUB, OTHER), ACCOUNT.replace("test-group", "other-group"), PROJECT):
            with self.subTest(scope=scope), self.assertRaises(access.AccessError):
                access._account_metadata(run, scope, SUB, "test-group")
        run.assert_not_called()

    def test_raw_account_new_list_properties_do_not_disable_security_validation(self):
        self.assertEqual(PRINCIPAL, self.discover().principal_id)
        for scope in (ACCOUNT, MODEL):
            for key, value in (
                ("id", scope.replace(SUB, OTHER)),
                ("id", scope.replace("test-group", "other-group")),
                ("name", "wrong-account"),
                ("type", "Microsoft.Storage/storageAccounts"),
                ("kind", "SpeechServices"),
                ("properties", []),
                ("properties", None),
            ):
                with self.subTest(scope=scope, key=key, value=value):
                    self.azure = AzureFixture()
                    self.azure.resources[scope][key] = value
                    self.fails_discovery()

    def test_raw_account_missing_required_metadata_fails_closed(self):
        for scope in (ACCOUNT, MODEL):
            for key in ("id", "name", "type", "kind", "properties"):
                with self.subTest(scope=scope, key=key):
                    self.azure = AzureFixture()
                    del self.azure.resources[scope][key]
                    self.fails_discovery()

    def test_raw_foundry_subdomain_must_still_bind_project_endpoint(self):
        for value in ("wrong-account", ["test-foundry"], None):
            with self.subTest(value=value):
                self.azure = AzureFixture()
                self.azure.resources[ACCOUNT]["properties"]["customSubDomainName"] = value
                self.fails_discovery()

    def test_raw_account_failure_has_no_typed_command_or_alternate_api_fallback(self):
        run = Mock(side_effect=access.AzureCommandError(stage=access.Operation.ACCOUNT_READ))
        with self.assertRaises(access.AzureCommandError):
            access._account_metadata(run, ACCOUNT, SUB, "test-group")
        run.assert_called_once_with([
            "rest", "--method", "get", "--url",
            f"https://management.azure.com{ACCOUNT}?api-version=2025-06-01",
        ])

    def test_configured_deployment_scope_mismatch(self):
        for key in ("SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP"):
            with self.subTest(key=key):
                self.azure = AzureFixture()
                self.azure.settings[key]["value"] = OTHER
                self.fails_discovery()

    def test_wrong_appconfig_key_or_label(self):
        for key in ("key", "label"):
            with self.subTest(key=key):
                self.azure = AzureFixture()
                self.azure.settings["AUDIT_HMAC_KEY"][key] = "wrong"
                self.fails_discovery()

    def test_plaintext_or_wrong_content_type_rejected_without_value(self):
        for content_type in ("text/plain", access.KV_REFERENCE + ".evil", None):
            self.azure.settings["AUDIT_HMAC_KEY"].update(contentType=content_type, value="PRIVATE-MARKER")
            with self.assertRaises(access.AccessError) as caught:
                self.discover()
            self.assertNotIn("PRIVATE-MARKER", str(caught.exception))

    def test_malformed_reference_json_and_type(self):
        for value in ("{PRIVATE-MARKER", "[]", "null", '{"uri":2}', '{"not_uri":"PRIVATE-MARKER"}'):
            self.azure.settings["AUDIT_HMAC_KEY"]["value"] = value
            with self.assertRaises(access.AccessError) as caught:
                self.discover()
            self.assertNotIn("PRIVATE-MARKER", str(caught.exception))

    def test_secret_uri_rejections(self):
        base = "https://test-vault.vault.azure.net/secrets/AUDIT-HMAC-KEY"
        for uri in (
            base.replace("https:", "http:"), base.replace("test-vault", "other-vault"),
            base.replace("azure.net", "azure.net.evil.invalid"), base + "?x=PRIVATE-MARKER",
            base + "#fragment", base + "?", base + "#", base.replace("https://", "https://user:pass@"),
            base + "/../other", base + "/%2e%2e", base + "/version/more",
            base.replace("AUDIT-HMAC-KEY", "_invalid"), base.replace("/secrets/", "/keys/"),
            base.replace("/secrets/", "/secrets//"), base + "\\other",
        ):
            with self.subTest(uri=uri):
                self.azure.settings["AUDIT_HMAC_KEY"]["value"] = json.dumps({"uri": uri})
                self.fails_discovery()

    def test_versioned_and_unversioned_wellformed_secret_names(self):
        for suffix in ("Rotated-Audit-42", "Rotated-Audit-42/a1b2"):
            self.azure.settings["AUDIT_HMAC_KEY"]["value"] = json.dumps({"uri": "https://test-vault.vault.azure.net/secrets/" + suffix})
            self.assertEqual(VAULT + "/secrets/Rotated-Audit-42", self.discover().grants[-1].scope)

    def test_vault_requires_endpoint_mapping_and_rbac(self):
        for key, value in (("vaultUri", "https://other.vault.azure.net"), ("enableRbacAuthorization", False)):
            with self.subTest(key=key):
                self.azure = AzureFixture()
                self.azure.resources[VAULT]["properties"][key] = value
                self.fails_discovery()

    def test_exact_existing_grants_and_idempotent_rerun(self):
        plan = self.discover()
        self.assertEqual(("CONFIG", "MODEL", "SECRET"), self.apply(plan))
        self.assertEqual(3, len(self.azure.writes))
        self.apply(self.discover())
        self.assertEqual(3, len(self.azure.writes))
        self.sleep.assert_not_called()

    def test_all_resource_and_assignment_discovery_precedes_first_write(self):
        self.apply()
        first_write = next(i for i, call in enumerate(self.azure.calls) if call[:3] == ["role", "assignment", "create"])
        reads = self.azure.calls[:first_write]
        self.assertIn("keyvault", {call[0] for call in reads})
        self.assertEqual(3, sum(call[:3] == ["role", "assignment", "list"] for call in reads))
        self.assertTrue(all(call[0] == "role" for call in self.azure.calls[first_write:]))

    def test_broad_different_or_other_principal_grants_not_reused(self):
        self.azure.assignments = [
            self.azure.assignment(scope=PREFIX),
            self.azure.assignment(principalId=OTHER),
            self.azure.assignment(roleDefinitionId=f"/subscriptions/{SUB}/providers/Microsoft.Authorization/roleDefinitions/{OTHER}"),
        ]
        self.apply()
        self.assertEqual(3, len(self.azure.writes))
        self.assertEqual(6, len(self.azure.assignments))  # No deletion/replacement.

    def test_conditional_assignment_preflight_blocks_all_writes(self):
        for overrides in ({"condition": "@condition"}, {"conditionVersion": "2.0"}, {"principalType": "Group"}):
            self.azure.assignments = [self.azure.assignment(SECRET, access.Role.SECRET, **overrides)]
            with self.assertRaisesRegex(access.AccessError, "Conflicting"):
                self.apply()
            self.assertEqual([], self.azure.writes)

    def test_writes_bind_principal_scope_role_and_stable_name(self):
        plan = self.discover()
        self.apply(plan)
        for grant, command in zip(plan.grants, self.azure.writes):
            for flag, expected in (
                ("--assignee-object-id", PRINCIPAL), ("--assignee-principal-type", "ServicePrincipal"),
                ("--scope", grant.scope), ("--role", grant.role.value),
                ("--name", grant.assignment_name(PRINCIPAL)),
            ):
                self.assertEqual(expected, command[command.index(flag) + 1])
            self.assertNotEqual(grant.assignment_name(PRINCIPAL), grant.assignment_name(OTHER))

    def test_tampered_plan_scope_principal_or_role_rejected(self):
        plan = self.discover()
        for changed in (
            replace(plan, subscription=OTHER), replace(plan, resource_group="other-group"),
            replace(plan, principal_id="guess"), replace(plan, grants=plan.grants + (plan.grants[0],)),
            replace(plan, classic=True),
        ):
            with self.subTest(plan=changed), self.assertRaises(access.AccessError):
                self.apply(changed)
        self.assertEqual([], self.azure.writes)

    def test_partial_write_failure_reports_retention_and_recovery(self):
        self.azure.fail_role = access.Role.MODEL
        with self.assertRaisesRegex(access.AccessError, "1/3 grants verified.*MODEL.*retained.*No cutover"):
            self.apply()
        self.assertEqual(1, len(self.azure.assignments))
        self.azure.fail_role = None
        self.apply()
        self.assertEqual(3, len(self.azure.assignments))
        self.sleep.assert_not_called()

    def test_principal_replication_retry_is_bounded(self):
        self.azure.create_errors = ["PrincipalNotFound", "PrincipalNotFound"]
        self.apply()
        self.assertEqual([unittest.mock.call(2), unittest.mock.call(4)], self.sleep.call_args_list)
        self.azure = AzureFixture()
        self.azure.create_errors = ["PrincipalNotFound"] * 4
        with self.assertRaises(access.AccessError):
            self.apply()
        self.assertEqual(3, len(self.azure.writes))

    def test_race_requires_exact_assignment_visibility(self):
        original = self.azure
        def race(args):
            if args[:3] == ["role", "assignment", "create"]:
                original(args)
                raise access.AzureCommandError("RoleAssignmentExists")
            return original(args)
        self.assertEqual(3, len(access.apply(self.discover(), run=race, sleep=self.sleep)))
        self.sleep.assert_not_called()
        self.azure = AzureFixture()
        self.azure.create_errors = ["RoleAssignmentExists"]
        with self.assertRaisesRegex(access.AccessError, "not yet exactly visible"):
            self.apply()
        self.assertEqual(2, self.sleep.call_count)

    def test_arm_visibility_retry_is_bounded_and_not_a_readiness_claim(self):
        original = self.azure
        hidden_reads = 2
        def delayed(args):
            nonlocal hidden_reads
            result = original(args)
            if args[:3] == ["role", "assignment", "list"] and original.writes and hidden_reads:
                hidden_reads -= 1
                return []
            return result
        access.apply(self.discover(), run=delayed, sleep=self.sleep)
        self.assertEqual([unittest.mock.call(2), unittest.mock.call(4)], self.sleep.call_args_list)
        self.assertEqual(3, len(self.azure.writes))
        self.assertFalse(any("invoke" in call or "restart" in call for call in self.azure.calls))

    def test_unknown_write_failure_not_retried(self):
        self.azure.create_errors = ["AuthorizationFailed"]
        with self.assertRaises(access.AccessError):
            self.apply()
        self.assertEqual(1, len(self.azure.writes))
        self.sleep.assert_not_called()

    def test_cli_default_and_plan_never_write(self):
        for args in ([], ["--plan"]):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0, access.main(args, environment=ENV, run=self.azure))
            result = json.loads(output.getvalue())
            self.assertEqual(PRINCIPAL, result["principal_id"])
            self.assertTrue(all(not grant["exact_unconditional_assignment"] for grant in result["grants"]))
            self.assertEqual("not-tested", result["data_plane_readiness"])
        self.assertEqual([], self.azure.writes)

    def test_readonly_plan_proves_existing_roles_without_secret_value_reads(self):
        plan = self.discover()
        self.azure.assignments = [self.azure.assignment(grant.scope, grant.role) for grant in plan.grants]
        self.azure.calls.clear()
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, access.main(["--plan"], environment=ENV, run=self.azure))
        result = json.loads(output.getvalue())
        self.assertEqual(3, len(result["grants"]))
        self.assertTrue(all(grant["exact_unconditional_assignment"] for grant in result["grants"]))
        self.assertEqual("not-tested", result["data_plane_readiness"])
        self.assertEqual([], self.azure.writes)
        # Vault management metadata only, never Key Vault secret show/list/get,
        # App Configuration's reference resolver, or the Conversation HMAC key.
        self.assertEqual([["keyvault", "show", "--name", "test-vault", "--resource-group", "test-group", "--subscription", SUB]],
                         [call for call in self.azure.calls if call[0] == "keyvault"])
        self.assertFalse(any("--resolve-keyvault" in call or "HOSTED_CONVERSATION_CAPABILITY_KEY" in call for call in self.azure.calls))
        self.assertEqual(3, sum(call[:3] == ["role", "assignment", "list"] for call in self.azure.calls))

    def test_readonly_plan_does_not_accept_broad_or_conditional_proof(self):
        self.azure.assignments = [self.azure.assignment(scope=PREFIX), self.azure.assignment(principalId=OTHER)]
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, access.main(["--plan"], environment=ENV, run=self.azure))
        self.assertTrue(all(not grant["exact_unconditional_assignment"] for grant in json.loads(output.getvalue())["grants"]))
        self.azure.assignments = [self.azure.assignment(condition="@condition")]
        with self.assertLogs(level="ERROR"), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(1, access.main(["--plan"], environment=ENV, run=self.azure))
        self.assertEqual("", output.getvalue())
        self.assertEqual([], self.azure.writes)

    def test_cli_apply_warns_not_data_plane_ready(self):
        with self.assertLogs(level="WARNING") as logs, redirect_stdout(io.StringIO()):
            self.assertEqual(0, access.main(["--apply"], environment=ENV, run=self.azure))
        self.assertIn("NOT data-plane readiness", " ".join(logs.output))
        self.assertEqual(3, len(self.azure.writes))

    def test_cli_failure_nonzero_without_raw_value(self):
        self.azure.settings["AUDIT_HMAC_KEY"]["value"] = "PRIVATE-MARKER"
        with self.assertLogs(level="ERROR") as logs, redirect_stdout(io.StringIO()):
            self.assertEqual(1, access.main(["--apply"], environment=ENV, run=self.azure))
        self.assertNotIn("PRIVATE-MARKER", " ".join(logs.output))
        self.assertEqual([], self.azure.writes)

    def test_native_cli_resolution_and_sanitized_errors(self):
        result = subprocess.CompletedProcess([], 1, "PRIVATE-MARKER", "ERROR: (PrincipalNotFound) PRIVATE-MARKER")
        with patch.object(access, "resolve_az_command", return_value="native-az.cmd"), patch.object(access.subprocess, "run", return_value=result) as run:
            with self.assertRaises(access.AzureCommandError) as caught:
                access.run_az(["role", "assignment", "create"])
        self.assertEqual("native-az.cmd", run.call_args.args[0][0])
        self.assertEqual("PrincipalNotFound", caught.exception.code)
        self.assertEqual(access.Operation.ASSIGNMENT_CREATE, caught.exception.stage)
        self.assertNotIn("PRIVATE-MARKER", str(caught.exception))

    def test_cli_usage_failure_has_safe_stage_not_permission_diagnosis(self):
        for code, stderr in (
            (2, "PRIVATE-MARKER"),
            (1, "ERROR: the following arguments are required: --resource-group/-g, --name/-n PRIVATE-MARKER"),
            (1, "ERROR: unrecognized arguments: --ids PRIVATE-MARKER"),
        ):
            result = subprocess.CompletedProcess([], code, "PRIVATE-MARKER", stderr)
            with patch.object(access.subprocess, "run", return_value=result) as run:
                with self.assertRaises(access.AzureCommandError) as caught:
                    access.run_az(["cognitiveservices", "account", "show", "--ids", "PRIVATE-MARKER"])
            self.assertEqual("CliUsageError", caught.exception.code)
            self.assertEqual(access.Operation.ACCOUNT_READ, caught.exception.stage)
            self.assertIn("before changing Azure permissions", str(caught.exception))
            self.assertNotIn("PRIVATE-MARKER", str(caught.exception))
            run.assert_called_once()

    def test_unknown_failure_stage_and_code_cannot_echo_external_values(self):
        error = access.AzureCommandError("PRIVATE-MARKER", stage="PRIVATE-MARKER")
        self.assertEqual("CommandFailed", error.code)
        self.assertEqual(access.Operation.UNKNOWN, error.stage)
        self.assertNotIn("PRIVATE-MARKER", str(error))
        with patch.object(access.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "PRIVATE-MARKER")):
            with self.assertRaises(access.AzureCommandError) as caught:
                access.run_az(["keyvault", "show", "--name", "PRIVATE-MARKER"])
        self.assertEqual(access.Operation.VAULT_READ, caught.exception.stage)
        self.assertNotIn("PRIVATE-MARKER", str(caught.exception))
    def test_cli_malformed_json_and_timeout_redacted(self):
        for result in (subprocess.CompletedProcess([], 0, "PRIVATE-MARKER", ""),):
            with patch.object(access.subprocess, "run", return_value=result), self.assertRaises(access.AccessError) as caught:
                access.run_az(["resource", "show"])
            self.assertNotIn("PRIVATE-MARKER", str(caught.exception))
        with patch.object(access.subprocess, "run", side_effect=subprocess.TimeoutExpired("PRIVATE-MARKER", 90)), self.assertRaises(access.AccessError) as caught:
            access.run_az(["resource", "show"])
        self.assertNotIn("PRIVATE-MARKER", str(caught.exception))

    def test_raw_arm_and_foundry_rest_failures_have_distinct_safe_stages(self):
        for url, stage in (
            (f"https://management.azure.com{ACCOUNT}?api-version=2025-06-01", access.Operation.ACCOUNT_READ),
            (ENDPOINT + "/agents/test-agent?api-version=v1", access.Operation.AGENT_READ),
        ):
            with self.subTest(stage=stage), patch.object(
                access.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 1, "", "PRIVATE-MARKER"),
            ):
                with self.assertRaises(access.AzureCommandError) as caught:
                    access.run_az(["rest", "--method", "get", "--url", url])
            self.assertEqual(stage, caught.exception.stage)
            self.assertNotIn("PRIVATE-MARKER", str(caught.exception))
            self.assertNotIn(url, str(caught.exception))

    def test_selected_child_environment_loaded_as_json_not_evaluated(self):
        env = dict(ENV, AZURE_ENV_NAME="offline-child", HOSTED_AGENT_DEPLOYMENT='{"agent":null}', UNUSED='$(do-not-execute); "quoted"')
        result = subprocess.CompletedProcess([], 0, json.dumps(env), "")
        with patch.object(access.subprocess, "run", return_value=result) as run:
            self.assertEqual(env, access.load_azd_environment({"AZURE_ENV_NAME": "offline-child", "HOSTED_AGENT_NAME": "stale-parent"}))
        command = run.call_args.args[0]
        self.assertEqual("offline-child", command[command.index("--environment") + 1])
        self.assertIn("--no-prompt", command)

    def test_bad_azd_environment_stops_before_discovery(self):
        for status, value in ((1, "PRIVATE-MARKER"), (0, "["), (0, '{"bad-key": "x"}'), (0, '{"AZURE_ENV_NAME":"wrong"}')):
            result = subprocess.CompletedProcess([], status, value, "PRIVATE-MARKER")
            with patch.object(access.subprocess, "run", return_value=result), self.assertLogs(level="ERROR"), redirect_stdout(io.StringIO()):
                self.assertEqual(1, access.main(["--azd-env", "--apply"], environment={"AZURE_ENV_NAME": "offline-child"}, run=self.azure))
            self.assertEqual([], self.azure.calls)


if __name__ == "__main__":
    unittest.main()
