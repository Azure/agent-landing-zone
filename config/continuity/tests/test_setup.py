from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from azure.core.exceptions import ResourceNotFoundError

from config.continuity import setup


REPO_ROOT = Path(__file__).resolve().parents[3]


class ContinuitySetupTests(TestCase):
    @patch.object(setup, "get_configuration_setting_or_none", return_value=None)
    @patch.object(setup, "_run_az", return_value="")
    def test_disabled_continuity_allows_fresh_frontend_without_identity(
        self,
        run_az,
        get_setting,
    ):
        setup.reconcile_disabled_continuity(
            Mock(),
            {
                "AZURE_RESOURCE_GROUP": "rg",
                "FRONTEND_APP_NAME": "frontend",
            },
        )

        run_az.assert_called_once()
        self.assertFalse(run_az.call_args.kwargs["required"])
        self.assertEqual(
            ["AZURE_APP_RESOURCE_GROUP", "HOSTED_CONVERSATION_CAPABILITY_KEY"],
            [call.args[1] for call in get_setting.call_args_list],
        )

    @patch.object(
        setup,
        "get_configuration_setting_or_none",
        side_effect=lambda client, key: (
            SimpleNamespace(value="reference")
            if key == "HOSTED_CONVERSATION_CAPABILITY_KEY" else None
        ),
    )
    @patch.object(setup, "_run_az", return_value="")
    def test_disabled_continuity_fails_closed_without_identity_when_capability_exists(
        self,
        run_az,
        get_setting,
    ):
        with self.assertRaisesRegex(
            RuntimeError,
            "capability reference still exists",
        ):
            setup.reconcile_disabled_continuity(
                Mock(),
                {
                    "AZURE_RESOURCE_GROUP": "rg",
                    "FRONTEND_APP_NAME": "frontend",
                },
            )

        run_az.assert_called_once()
        self.assertEqual(
            ["AZURE_APP_RESOURCE_GROUP", "HOSTED_CONVERSATION_CAPABILITY_KEY"],
            [call.args[1] for call in get_setting.call_args_list],
        )

    def test_application_destination_prefers_explicit_environment_then_configuration(self):
        client = Mock()
        for configured, explicit, expected in (
            (None, "", "rg-ai"),
            (SimpleNamespace(value="rg-app"), "", "rg-app"),
            (SimpleNamespace(value="rg-other"), "rg-explicit", "rg-explicit"),
        ):
            environment = {"AZURE_RESOURCE_GROUP": "rg-ai", "AZURE_APP_RESOURCE_GROUP": explicit}
            with self.subTest(expected=expected), patch.object(
                setup, "get_configuration_setting_or_none", return_value=configured,
            ):
                self.assertEqual(expected, setup._application_resource_group(client, environment))

    def test_safe_defaults_disable_continuity_and_prefer_delegation(self):
        values = dict(setup.DEFAULT_SETTINGS)

        settings = setup.validate_continuity_settings(values)

        self.assertFalse(settings.enabled)
        self.assertEqual(settings.owner_binding, "delegated")
        self.assertFalse(settings.owner_binding_validated)
        self.assertEqual(
            settings.delegated_identity_header,
            "x-ms-user-identity",
        )
        self.assertEqual(
            settings.delegated_identity_source,
            "authenticated_ui_bff_principal",
        )
        self.assertEqual(settings.responses_protocol_version, "2.0.0")
        self.assertEqual(settings.unavailable_status_code, 503)
        self.assertEqual(
            settings.token_audience,
            "https://ai.azure.com",
        )
        self.assertEqual(settings.history_truncation, "drop_oldest")

    def test_activation_request_can_start_with_validation_false(self):
        values = {
            **setup.DEFAULT_SETTINGS,
            "HOSTED_CONTINUITY_ENABLED": "true",
        }

        settings = setup.validate_continuity_settings(
            values,
            deployment_topology="hosted-no-panel",
            chat_backend="hosted_agent",
            deploy_key_vault=False,
        )
        self.assertTrue(settings.enabled)
        self.assertFalse(settings.owner_binding_validated)

    def test_raw_caller_identity_binding_is_rejected_even_while_disabled(self):
        values = {
            **setup.DEFAULT_SETTINGS,
            "HOSTED_CONVERSATION_OWNER_BINDING": "oid",
        }

        with self.assertRaisesRegex(ValueError, "'delegated' or 'capability'"):
            setup.validate_continuity_settings(values)

    def test_enabled_continuity_requires_hosted_no_panel_contract(self):
        values = {
            **setup.DEFAULT_SETTINGS,
            "HOSTED_CONTINUITY_ENABLED": "true",
            "HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED": "true",
        }

        with self.assertRaisesRegex(ValueError, "hosted deployment topology"):
            setup.validate_continuity_settings(
                values,
                deployment_topology="classic",
                chat_backend="orchestrator",
            )

    @patch.object(setup, "create_credential")
    @patch.object(setup, "AzureAppConfigurationClient")
    def test_invalid_environment_is_forced_disabled_before_any_publication(
        self,
        app_config_client_type,
        create_credential,
    ):
        app_config_client = app_config_client_type.return_value
        environment = {
            **setup.DEFAULT_SETTINGS,
            "APP_CONFIG_ENDPOINT": "https://appcs.example.azconfig.io",
            "HOSTED_CONTINUITY_ENABLED": "true",
            "HOSTED_CONVERSATION_OWNER_BINDING": "oid",
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "CHAT_BACKEND": "hosted_agent",
        }

        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ValueError, "'delegated' or 'capability'"):
                setup.main()

        create_credential.assert_called_once()
        published = [
            call.args[0]
            for call in app_config_client.set_configuration_setting.call_args_list
        ]
        self.assertEqual(len(published), 2)
        self.assertEqual(published[0].key, "HOSTED_CONTINUITY_ENABLED")
        self.assertEqual(published[0].value, "false")
        self.assertEqual(
            published[1].key,
            "HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED",
        )
        self.assertEqual(published[1].value, "false")

    def test_capability_fallback_requires_key_vault_only_when_enabled(self):
        values = {
            **setup.DEFAULT_SETTINGS,
            "HOSTED_CONTINUITY_ENABLED": "true",
            "HOSTED_CONVERSATION_OWNER_BINDING": "capability",
        }
        with self.assertRaisesRegex(ValueError, "Capability fallback"):
            setup.validate_continuity_settings(
                values,
                deployment_topology="hosted-no-panel",
                chat_backend="hosted_agent",
                deploy_key_vault=False,
            )

    @patch.object(setup, "SecretClient")
    @patch.object(setup, "reconcile_delegated_binding")
    @patch.object(setup, "configure_frontend_roles")
    @patch.object(setup, "seed_continuity_settings")
    @patch.object(setup, "effective_continuity_values")
    @patch.object(setup, "create_credential")
    @patch.object(setup, "AzureAppConfigurationClient")
    def test_delegated_activation_never_provisions_capability_material(
        self,
        app_config_client_type,
        create_credential,
        effective_values,
        seed_settings,
        configure_roles,
        reconcile_delegated,
        secret_client_type,
    ):
        effective_values.return_value = {
            **setup.DEFAULT_SETTINGS,
            "HOSTED_CONTINUITY_ENABLED": "true",
        }
        access = setup.ContinuityAccess(
            frontend_principal_id="frontend-principal",
            hosted_agent_principal_id="hosted-principal",
            agent_scope=(
                "/subscriptions/sub/resourceGroups/rg/providers/"
                "Microsoft.CognitiveServices/accounts/aif/projects/project/"
                "agents/agent-app-orchestrator"
            ),
            routed_version="7",
            role_actions={
                setup.FOUNDRY_AGENT_CONSUMER_ROLE_ID: "created",
                setup.USER_IDENTITY_IMPERSONATION_ROLE_ID: "created",
            },
        )
        configure_roles.return_value = access
        environment = {
            "APP_CONFIG_ENDPOINT": "https://appcs.example.azconfig.io",
            "DEPLOYMENT_TOPOLOGY": "hosted-no-panel",
            "CHAT_BACKEND": "hosted_agent",
            "DEPLOY_KEY_VAULT": "false",
        }

        with patch.dict(os.environ, environment, clear=True):
            setup.main(activate=True)

        secret_client_type.assert_not_called()
        reconcile_delegated.assert_called_once_with(
            app_config_client_type.return_value,
            access,
        )
        app_config_client = app_config_client_type.return_value
        published = [
            call.args[0]
            for call in app_config_client.set_configuration_setting.call_args_list
        ]
        self.assertEqual(
            [(item.key, item.value) for item in published],
            [
                ("HOSTED_CONTINUITY_ENABLED", "false"),
                ("HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED", "false"),
                ("HOSTED_CONVERSATION_OWNER_BINDING_VALIDATED", "true"),
                ("HOSTED_CONTINUITY_ENABLED", "true"),
            ],
        )
        seed_settings.assert_called_once()
        create_credential.assert_called_once()

    def test_secret_creation_and_rotation_are_idempotent_by_key_id(self):
        missing = Mock()
        missing.get_secret.side_effect = ResourceNotFoundError("missing")
        with patch.object(
            setup.secrets,
            "token_bytes",
            return_value=b"x" * 32,
        ):
            self.assertEqual(
                setup.ensure_capability_secret(missing, "v1"),
                "created",
            )
        secret_value = missing.set_secret.call_args.args[1]
        self.assertEqual(
            base64.urlsafe_b64decode(secret_value + "="),
            b"x" * 32,
        )
        self.assertNotIn(secret_value, str(missing.set_secret.call_args.kwargs))

        current = SimpleNamespace(
            value=secret_value,
            properties=SimpleNamespace(tags={"key_id": "v1"}),
        )
        reused = Mock()
        reused.get_secret.return_value = current
        self.assertEqual(
            setup.ensure_capability_secret(reused, "v1"),
            "reused",
        )
        reused.set_secret.assert_not_called()

        rotated = Mock()
        rotated.get_secret.return_value = current
        with patch.object(
            setup.secrets,
            "token_bytes",
            return_value=b"y" * 32,
        ):
            self.assertEqual(
                setup.ensure_capability_secret(rotated, "v2"),
                "rotated",
            )
        self.assertEqual(
            rotated.set_secret.call_args.kwargs["tags"]["key_id"],
            "v2",
        )

        untagged = Mock()
        untagged.get_secret.return_value = SimpleNamespace(
            value=secret_value,
            properties=SimpleNamespace(tags={}),
        )
        with patch.object(
            setup.secrets,
            "token_bytes",
            return_value=b"w" * 32,
        ):
            self.assertEqual(
                setup.ensure_capability_secret(untagged, "v1"),
                "rotated",
            )
        self.assertEqual(
            untagged.set_secret.call_args.kwargs["tags"]["key_id"],
            "v1",
        )

    def test_app_configuration_publishes_only_key_vault_reference(self):
        app_config_client = Mock()
        app_config_client.get_configuration_setting.return_value = None
        secret_client = Mock()
        secret_client.get_secret.side_effect = ResourceNotFoundError("missing")

        with patch.object(
            setup.secrets,
            "token_bytes",
            return_value=b"z" * 32,
        ):
            action = setup.apply_capability_key_reference(
                app_config_client,
                secret_client,
                "https://kv-ui.vault.azure.net/",
                "v1",
            )

        self.assertEqual(action, "created")
        setting = app_config_client.set_configuration_setting.call_args.args[0]
        self.assertEqual(setting.key, setup.CAPABILITY_CONFIG_KEY)
        self.assertEqual(
            setting.value,
            '{"uri":"https://kv-ui.vault.azure.net/secrets/'
            'HOSTED-CONVERSATION-CAPABILITY-KEY"}',
        )
        self.assertEqual(
            setting.content_type,
            setup.KEY_VAULT_REFERENCE_CONTENT_TYPE,
        )
        self.assertNotIn(
            secret_client.set_secret.call_args.args[1],
            setting.value,
        )

    def test_plaintext_capability_key_is_rejected(self):
        app_config_client = Mock()
        app_config_client.get_configuration_setting.return_value = SimpleNamespace(
            value="not-allowed",
            content_type="text/plain",
        )

        with self.assertRaisesRegex(ValueError, "plaintext"):
            setup.apply_capability_key_reference(
                app_config_client,
                Mock(),
                "https://kv-ui.vault.azure.net/",
                "v1",
            )

    def test_key_vault_reference_hostname_comparison_is_case_insensitive(self):
        self.assertTrue(
            setup._same_key_vault_reference(
                (
                    '{"uri":"https://KV-UI.vault.azure.net/secrets/'
                    'HOSTED-CONVERSATION-CAPABILITY-KEY"}'
                ),
                (
                    '{"uri":"https://kv-ui.vault.azure.net/secrets/'
                    'HOSTED-CONVERSATION-CAPABILITY-KEY"}'
                ),
            )
        )
        self.assertFalse(
            setup._same_key_vault_reference(
                (
                    '{"uri":"https://kv-ui.vault.azure.net:444/secrets/'
                    'HOSTED-CONVERSATION-CAPABILITY-KEY"}'
                ),
                (
                    '{"uri":"https://kv-ui.vault.azure.net/secrets/'
                    'HOSTED-CONVERSATION-CAPABILITY-KEY"}'
                ),
            )
        )

    def test_capability_vault_must_be_dedicated_to_the_ui_bff(self):
        with self.assertRaisesRegex(ValueError, "dedicated UI BFF Key Vault"):
            setup.resolve_capability_vault_uri(
                {
                    "KEY_VAULT_URI": "https://kv-shared.vault.azure.net/",
                    "HOSTED_CONTINUITY_KEY_VAULT_URI": (
                        "https://kv-shared.vault.azure.net/"
                    ),
                }
            )

        with self.assertRaisesRegex(ValueError, "dedicated UI BFF Key Vault"):
            setup.resolve_capability_vault_uri(
                {
                    "KEY_VAULT_URI": "https://kv-shared.vault.azure.net/",
                    "HOSTED_CONTINUITY_KEY_VAULT_URI": (
                        "https://KV-SHARED.vault.azure.net/"
                    ),
                }
            )

        self.assertEqual(
            setup.resolve_capability_vault_uri(
                {
                    "KEY_VAULT_URI": "https://kv-shared.vault.azure.net/",
                    "HOSTED_CONTINUITY_KEY_VAULT_NAME": "kv-ui",
                }
            ),
            "https://kv-ui.vault.azure.net/",
        )

    @patch.object(setup, "_run_az")
    def test_role_assignment_list_uses_valid_inherited_switch(self, run_az):
        run_az.return_value = "[]"

        setup._role_assignments(
            "principal",
            "/subscriptions/sub",
            include_inherited=True,
        )

        arguments = run_az.call_args.args[0]
        self.assertIn("--include-inherited", arguments)
        self.assertIn("--include-groups", arguments)
        self.assertNotIn("false", arguments)

    @patch.object(setup, "_role_assignments")
    @patch.object(setup, "_run_az")
    def test_capability_secret_access_is_frontend_only_and_secret_scoped(
        self,
        run_az,
        role_assignments,
    ):
        secret_scope = (
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.KeyVault/vaults/kv-ui/secrets/"
            "HOSTED-CONVERSATION-CAPABILITY-KEY"
        )
        role_assignments.side_effect = [
            [],
            [
                {
                    "roleDefinitionId": (
                        "/subscriptions/sub/providers/Microsoft.Authorization/"
                        "roleDefinitions/"
                        f"{setup.KEY_VAULT_SECRETS_USER_ROLE_ID}"
                    ),
                    "scope": secret_scope,
                    "principalId": "frontend-principal",
                    "principalType": "ServicePrincipal",
                }
            ],
        ]
        run_az.return_value = ""

        self.assertTrue(
            setup.ensure_frontend_capability_secret_access(
                "frontend-principal",
                secret_scope,
            )
        )

        arguments = run_az.call_args.args[0]
        self.assertIn("frontend-principal", arguments)
        self.assertEqual(arguments[arguments.index("--scope") + 1], secret_scope)

    @patch.object(setup, "_role_assignments")
    def test_group_derived_secret_access_is_rejected(self, role_assignments):
        secret_scope = (
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.KeyVault/vaults/kv-ui/secrets/"
            "HOSTED-CONVERSATION-CAPABILITY-KEY"
        )
        role_assignments.return_value = [
            {
                "roleDefinitionId": (
                    "/subscriptions/sub/providers/Microsoft.Authorization/"
                    "roleDefinitions/"
                    f"{setup.KEY_VAULT_SECRETS_USER_ROLE_ID}"
                ),
                "scope": secret_scope,
                "principalId": "group-principal",
                "principalType": "Group",
            }
        ]

        with self.assertRaisesRegex(RuntimeError, "UI BFF capability secret"):
            setup.ensure_frontend_capability_secret_access(
                "frontend-principal",
                secret_scope,
            )

    def test_live_role_definition_must_match_reviewed_single_data_action(self):
        role = {
            "name": setup.FOUNDRY_AGENT_CONSUMER_ROLE_ID,
            "roleName": setup.FOUNDRY_AGENT_CONSUMER_ROLE_NAME,
            "roleType": "BuiltInRole",
            "permissions": [
                {
                    "actions": [],
                    "notActions": [],
                    "dataActions": [setup.FOUNDRY_AGENT_INTERACT_DATA_ACTION],
                    "notDataActions": [],
                }
            ],
        }

        setup.validate_foundry_agent_consumer_role(role)

        role["permissions"][0]["dataActions"].append(
            "Microsoft.CognitiveServices/accounts/AIServices/*"
        )
        with self.assertRaisesRegex(RuntimeError, "least-privilege"):
            setup.validate_foundry_agent_consumer_role(role)

    def test_custom_role_has_exactly_one_data_action_and_no_actions(self):
        assignable_scope = "/subscriptions/sub/resourceGroups/rg"
        role = {
            "name": setup.USER_IDENTITY_IMPERSONATION_ROLE_ID,
            "roleName": setup.USER_IDENTITY_IMPERSONATION_ROLE_NAME,
            "roleType": "CustomRole",
            "assignableScopes": [assignable_scope],
            "permissions": [
                {
                    "actions": [],
                    "notActions": [],
                    "dataActions": [
                        setup.USER_IDENTITY_IMPERSONATION_DATA_ACTION
                    ],
                    "notDataActions": [],
                }
            ],
        }
        setup.validate_user_identity_impersonation_role(
            role,
            assignable_scope,
        )
        role["permissions"][0]["actions"] = ["Microsoft.Resources/*/read"]
        with self.assertRaisesRegex(RuntimeError, "no Actions"):
            setup.validate_user_identity_impersonation_role(
                role,
                assignable_scope,
            )

    @patch.object(setup, "_run_az")
    def test_custom_role_creation_is_resource_group_assignable(self, run_az):
        project_scope = (
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.CognitiveServices/accounts/aif/projects/project"
        )
        assignable_scope = "/subscriptions/sub/resourceGroups/rg"
        created_role = {
            "name": setup.USER_IDENTITY_IMPERSONATION_ROLE_ID,
            "roleName": setup.USER_IDENTITY_IMPERSONATION_ROLE_NAME,
            "roleType": "CustomRole",
            "assignableScopes": [assignable_scope],
            "permissions": [
                {
                    "actions": [],
                    "notActions": [],
                    "dataActions": [
                        setup.USER_IDENTITY_IMPERSONATION_DATA_ACTION
                    ],
                    "notDataActions": [],
                }
            ],
        }
        run_az.side_effect = ["[]", "", json.dumps([created_role])]

        self.assertTrue(
            setup.ensure_user_identity_impersonation_role(project_scope)
        )

        create_arguments = run_az.call_args_list[1].args[0]
        definition = json.loads(
            create_arguments[
                create_arguments.index("--role-definition") + 1
            ]
        )
        self.assertEqual(definition["Actions"], [])
        self.assertEqual(definition["NotActions"], [])
        self.assertEqual(
            definition["DataActions"],
            [setup.USER_IDENTITY_IMPERSONATION_DATA_ACTION],
        )
        self.assertEqual(definition["NotDataActions"], [])
        self.assertEqual(definition["AssignableScopes"], [assignable_scope])

    @patch.object(setup, "_run_az")
    def test_legacy_custom_role_is_renamed_in_place(self, run_az):
        project_scope = (
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.CognitiveServices/accounts/aif/projects/project"
        )
        assignable_scope = "/subscriptions/sub/resourceGroups/rg"

        def role(name):
            return {
                "name": setup.USER_IDENTITY_IMPERSONATION_ROLE_ID,
                "roleName": name,
                "roleType": "CustomRole",
                "assignableScopes": [assignable_scope],
                "permissions": [
                    {
                        "actions": [],
                        "notActions": [],
                        "dataActions": [
                            setup.USER_IDENTITY_IMPERSONATION_DATA_ACTION
                        ],
                        "notDataActions": [],
                    }
                ],
            }

        legacy_name = setup.LEGACY_USER_IDENTITY_IMPERSONATION_ROLE_NAMES[0]
        run_az.side_effect = [
            json.dumps([role(legacy_name)]),
            "",
            json.dumps([role(setup.USER_IDENTITY_IMPERSONATION_ROLE_NAME)]),
        ]

        self.assertTrue(
            setup.ensure_user_identity_impersonation_role(project_scope)
        )

        update_arguments = run_az.call_args_list[1].args[0]
        self.assertIn("update", update_arguments)
        definition = json.loads(
            update_arguments[update_arguments.index("--role-definition") + 1]
        )
        self.assertEqual(
            definition["Name"], setup.USER_IDENTITY_IMPERSONATION_ROLE_NAME
        )
        self.assertEqual(
            definition["Id"], setup.USER_IDENTITY_IMPERSONATION_ROLE_ID
        )

    @patch.object(setup, "_run_az")
    def test_live_protocol_verifies_routed_responses_2_0_0(self, run_az):
        run_az.side_effect = [
            json.dumps(
                {
                    "instance_identity": {"principal_id": "hosted-principal"},
                    "agent_endpoint": {
                        "protocol_configuration": {"responses": {}},
                        "version_selector": {
                            "version_selection_rules": [
                                {
                                    "type": "FixedRatio",
                                    "agent_version": "7",
                                    "traffic_percentage": 100,
                                }
                            ]
                        },
                    },
                }
            ),
            json.dumps(
                {
                    "definition": {
                        "protocol_versions": [
                            {"protocol": "responses", "version": "2.0.0"},
                            {"protocol": "invocations", "version": "1.0.0"},
                        ]
                    }
                }
            ),
        ]
        contract = setup.verify_live_hosted_agent_contract(
            "https://account.services.ai.azure.com/api/projects/project",
            "agent-app-orchestrator",
        )
        self.assertEqual(contract.principal_id, "hosted-principal")
        self.assertEqual(contract.routed_version, "7")
        for call in run_az.call_args_list:
            self.assertIn("https://ai.azure.com", call.args[0])

    @patch.object(setup, "_run_az")
    def test_live_protocol_rejects_non_2_0_0_version(self, run_az):
        run_az.side_effect = [
            json.dumps(
                {
                    "instance_identity": {"principal_id": "hosted-principal"},
                    "agent_endpoint": {
                        "protocol_configuration": {"responses": {}},
                        "version_selector": {
                            "version_selection_rules": [
                                {
                                    "type": "FixedRatio",
                                    "agent_version": "1",
                                    "traffic_percentage": 100,
                                }
                            ]
                        },
                    },
                }
            ),
            json.dumps(
                {
                    "definition": {
                        "protocol_versions": [
                            {"protocol": "responses", "version": "1.0.0"}
                        ]
                    }
                }
            ),
        ]
        with self.assertRaisesRegex(RuntimeError, "2.0.0 exactly"):
            setup.verify_live_hosted_agent_contract(
                "https://account.services.ai.azure.com/api/projects/project",
                "agent-app-orchestrator",
            )

    @patch.object(setup, "_run_az")
    @patch.object(setup, "_role_assignments")
    @patch.object(setup, "ensure_user_identity_impersonation_role")
    @patch.object(setup, "verify_live_foundry_agent_consumer_role")
    def test_role_assignments_target_only_frontend_at_agent_scope(
        self,
        verify_consumer,
        ensure_impersonation,
        role_assignments,
        run_az,
    ):
        scope = (
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.CognitiveServices/accounts/aif/projects/project/"
            "agents/agent-app-orchestrator"
        )
        project_scope = scope.rsplit("/agents/", 1)[0]
        assignments = [
            {
                "roleDefinitionId": (
                    "/subscriptions/sub/providers/Microsoft.Authorization/"
                    f"roleDefinitions/{role_id}"
                ),
                "scope": scope,
                "principalId": "frontend-principal",
                "principalType": "ServicePrincipal",
            }
            for role_id in (
                setup.FOUNDRY_AGENT_CONSUMER_ROLE_ID,
                setup.USER_IDENTITY_IMPERSONATION_ROLE_ID,
            )
        ]
        role_assignments.side_effect = [[], [], [], assignments]
        ensure_impersonation.return_value = True
        run_az.return_value = ""

        actions = setup.ensure_frontend_continuity_assignments(
            "frontend-principal",
            scope,
            project_scope,
            hosted_agent_principal_id="hosted-principal",
        )

        self.assertEqual(
            set(actions),
            {
                setup.FOUNDRY_AGENT_CONSUMER_ROLE_ID,
                setup.USER_IDENTITY_IMPERSONATION_ROLE_ID,
            },
        )
        self.assertEqual(len(run_az.call_args_list), 2)
        for call in run_az.call_args_list:
            arguments = call.args[0]
            self.assertIn("frontend-principal", arguments)
            self.assertNotIn("hosted-principal", arguments)
            self.assertEqual(arguments[arguments.index("--scope") + 1], scope)
        self.assertEqual(
            {
                call.args[0][call.args[0].index("--role") + 1]
                for call in run_az.call_args_list
            },
            set(actions),
        )
        verify_consumer.assert_called_once()
        ensure_impersonation.assert_called_once_with(project_scope)

    @patch.object(setup, "_role_assignments")
    @patch.object(setup, "ensure_user_identity_impersonation_role")
    @patch.object(setup, "verify_live_foundry_agent_consumer_role")
    def test_hosted_container_with_conversation_role_fails_closed(
        self,
        verify_role,
        ensure_impersonation,
        role_assignments,
    ):
        role_assignments.return_value = [
            {
                "roleDefinitionId": (
                    "/subscriptions/sub/providers/Microsoft.Authorization/"
                    "roleDefinitions/"
                    f"{setup.FOUNDRY_AGENT_CONSUMER_ROLE_ID}"
                )
            }
        ]

        with self.assertRaisesRegex(RuntimeError, "hosted container identity"):
            setup.ensure_frontend_continuity_assignments(
                "frontend-principal",
                (
                    "/subscriptions/sub/resourceGroups/rg/providers/"
                    "Microsoft.CognitiveServices/accounts/aif/projects/project/"
                    "agents/agent-app-orchestrator"
                ),
                (
                    "/subscriptions/sub/resourceGroups/rg/providers/"
                    "Microsoft.CognitiveServices/accounts/aif/projects/project"
                ),
                hosted_agent_principal_id="hosted-principal",
            )

        verify_role.assert_called_once()
        ensure_impersonation.assert_called_once()

    @patch.object(setup, "_role_assignments")
    @patch.object(setup, "ensure_user_identity_impersonation_role")
    @patch.object(setup, "verify_live_foundry_agent_consumer_role")
    def test_group_derived_ui_impersonation_role_fails_closed(
        self,
        verify_role,
        ensure_impersonation,
        role_assignments,
    ):
        scope = (
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.CognitiveServices/accounts/aif/projects/project/"
            "agents/agent-app-orchestrator"
        )
        role_assignments.side_effect = [
            [],
            [],
            [
                {
                    "roleDefinitionId": (
                        "/subscriptions/sub/providers/Microsoft.Authorization/"
                        "roleDefinitions/"
                        f"{setup.USER_IDENTITY_IMPERSONATION_ROLE_ID}"
                    ),
                    "scope": scope,
                    "principalId": "group-principal",
                    "principalType": "Group",
                }
            ],
        ]

        with self.assertRaisesRegex(RuntimeError, "group-derived"):
            setup.ensure_frontend_continuity_assignments(
                "frontend-principal",
                scope,
                scope.rsplit("/agents/", 1)[0],
                hosted_agent_principal_id="hosted-principal",
            )

        verify_role.assert_called_once()
        ensure_impersonation.assert_called_once()

    @patch.object(setup, "ensure_user_identity_impersonation_role")
    @patch.object(setup, "verify_live_foundry_agent_consumer_role")
    def test_ui_and_hosted_container_cannot_share_identity_case_insensitively(
        self,
        verify_role,
        ensure_impersonation,
    ):
        scope = (
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.CognitiveServices/accounts/aif/projects/project/"
            "agents/agent-app-orchestrator"
        )
        with self.assertRaisesRegex(RuntimeError, "must not share an identity"):
            setup.ensure_frontend_continuity_assignments(
                "A0B1C2D3",
                scope,
                scope.rsplit("/agents/", 1)[0],
                hosted_agent_principal_id="a0b1c2d3",
            )
        verify_role.assert_called_once()
        ensure_impersonation.assert_called_once()

    @patch.object(setup, "_role_assignments")
    @patch.object(setup, "ensure_user_identity_impersonation_role")
    @patch.object(setup, "verify_live_foundry_agent_consumer_role")
    def test_foundry_user_role_is_never_an_approved_substitute(
        self,
        verify_role,
        ensure_impersonation,
        role_assignments,
    ):
        scope = (
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.CognitiveServices/accounts/aif/projects/project/"
            "agents/agent-app-orchestrator"
        )
        role_assignments.side_effect = [
            [],
            [],
            [{"roleDefinitionName": "Foundry User"}],
        ]
        with self.assertRaisesRegex(RuntimeError, "broad Foundry User"):
            setup.ensure_frontend_continuity_assignments(
                "frontend-principal",
                scope,
                scope.rsplit("/agents/", 1)[0],
                hosted_agent_principal_id="hosted-principal",
            )
        verify_role.assert_called_once()
        ensure_impersonation.assert_called_once()

    def test_no_panel_composition_has_no_cosmos_or_hosted_container_rbac(self):
        parameters = json.loads(
            (REPO_ROOT / "main.parameters.json").read_text(encoding="utf-8")
        )["parameters"]
        hosted_agent = parameters["hostedAgent"]["value"]
        self.assertNotIn("roles", hosted_agent)
        self.assertNotIn("principalId", hosted_agent)

        post_provision = (
            REPO_ROOT / "scripts" / "postProvision.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("config.continuity.setup", post_provision)
        self.assertNotIn(
            "HOSTED_CONVERSATION_CAPABILITY_KEY=",
            post_provision,
        )

    def test_capability_contract_checksum_and_canonical_framing(self):
        schema_path = (
            REPO_ROOT
            / "contracts"
            / "hosted-conversation-capability-v1.schema.json"
        )
        checksum_path = (
            REPO_ROOT
            / "contracts"
            / "hosted-conversation-capability-v1.sha256"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        checksum = checksum_path.read_text(encoding="utf-8").split()[0]

        self.assertEqual(
            hashlib.sha256(
                schema_path.read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest(),
            checksum,
        )
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(
            schema["x-canonical-framing"]["field_order"],
            [
                "schema_version",
                "oid",
                "conversation_resource_id",
                "issued_at",
                "expiry",
                "key_id",
            ],
        )
        self.assertNotIn("secret", schema["required"])
        self.assertNotIn("key", schema["required"])
        self.assertIn("Disabled fallback", schema["description"])

    def test_hooks_keep_powershell_and_shell_continuity_parity(self):
        powershell_script = (REPO_ROOT / "scripts" / "postProvision.ps1").read_text(
            encoding="utf-8"
        )
        shell_script = (REPO_ROOT / "scripts" / "postProvision.sh").read_text(
            encoding="utf-8"
        )

        self.assertEqual(
            powershell_script.count(
                "Invoke-PythonModule -ModuleName 'config.continuity.setup'"
            ),
            1,
        )
        self.assertEqual(shell_script.count("python -m config.continuity.setup"), 1)

        powershell_predeploy = (
            REPO_ROOT / "scripts" / "preDeploy.ps1"
        ).read_text(encoding="utf-8")
        shell_predeploy = (REPO_ROOT / "scripts" / "preDeploy.sh").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            powershell_predeploy.count(
                "sys.argv = ['config.continuity.setup', '--activate']"
            ),
            1,
        )
        self.assertEqual(
            shell_predeploy.count(
                "-m config.continuity.setup --activate"
            ),
            1,
        )
