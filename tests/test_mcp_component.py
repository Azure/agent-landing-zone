"""Focused MCP composition and lifecycle contracts, with Azure boundaries mocked."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import NAMESPACE_URL, uuid5

import pytest

from config.deployment import appconfig, mcp, mcp_config
from config.deployment.composition import compose_parameters
from config.deployment.app_settings import substitute_values
from config.deployment.resolution import resolve_parameters

ROOT = Path(__file__).resolve().parents[1]
SUB = "11111111-1111-4111-8111-111111111111"
TENANT = "22222222-2222-4222-8222-222222222222"
OBJECT = "33333333-3333-4333-8333-333333333333"
CLIENT = "44444444-4444-4444-8444-444444444444"
PRINCIPAL = "55555555-5555-4555-8555-555555555555"
ACCOUNT = f"/subscriptions/{SUB}/resourceGroups/rg-test/providers/Microsoft.DocumentDB/databaseAccounts/test"


def environment(**values):
    return {
        "ORCHESTRATION_HOST": "container_apps",
        "APPLICATION_MODE": "conversational",
        "AZURE_ENV_NAME": "test",
        "AZURE_SUBSCRIPTION_ID": SUB,
        "AZURE_RESOURCE_GROUP": "rg-test",
        "AZURE_APP_RESOURCE_GROUP": "rg-test",
        "RESOURCE_TOKEN": "test",
        "APP_CONFIG_ENDPOINT": "https://test.azconfig.io",
        "HOSTED_AGENT_RESOURCE_SCOPE": "https://ai.azure.com/.default",
        "AGENTLZ_APP_DEFINITION": str(ROOT / "app-definition.json"),
        "DEPLOY_AGENT_APP_MCP": "true",
        "MCP_TOOLSETS": '["nl2sql"]',
        **values,
    }


def composition(values):
    source = json.loads((ROOT / "main.parameters.json").read_text(encoding="utf-8"))
    return {
        key: item["value"]
        for key, item in compose_parameters(source, values)["parameters"].items()
    }


@pytest.mark.parametrize("host", ["container_apps", "hosted"])
def test_mcp_is_optional_and_requires_only_application_cosmos(host):
    enabled = composition(environment(ORCHESTRATION_HOST=host))
    server = next(
        app for app in enabled["containerAppsList"] if app["service_name"] == "mcp"
    )
    assert enabled["deployCosmosDb"] is True
    assert enabled["enableCosmosVectorSearch"] is True
    assert server["external"] is True
    assert all(
        "Search" not in role and "Cosmos" not in role for role in server["roles"]
    )
    disabled = composition(
        environment(ORCHESTRATION_HOST=host, DEPLOY_AGENT_APP_MCP="false", MCP_TOOLSETS="[]")
    )
    assert disabled["deployCosmosDb"] is False
    assert disabled["enableCosmosVectorSearch"] is False
    assert not any(
        app["service_name"] == "mcp" for app in disabled["containerAppsList"]
    )
    assert disabled["deploySearchService"] == enabled["deploySearchService"]


def test_explicit_cosmos_opt_out_conflicts_with_selected_mcp():
    with pytest.raises(ValueError, match="Unset DEPLOY_COSMOS_DB"):
        composition(environment(DEPLOY_COSMOS_DB="false"))


def test_deselection_retains_vector_catalog_without_server():
    values = composition(
        environment(DEPLOY_AGENT_APP_MCP="false", MCP_TOOLSETS="[]", COSMOS_VECTOR_SEARCH_ENABLED="true")
    )
    assert values["deployCosmosDb"] and values["enableCosmosVectorSearch"]
    assert [item["name"] for item in values["databaseContainersList"]] == [
        "mcp-sources",
        "mcp-nl2sql-metadata",
    ]
    assert not any(app["service_name"] == "mcp" for app in values["containerAppsList"])


def test_vector_policy_and_filter_partition_have_identical_provider_inputs():
    containers = mcp_config.cosmos_containers(environment())
    assert (
        containers[0]["partitionKey"] == containers[1]["partitionKey"] == "/source_id"
    )
    vector = containers[1]
    assert vector["vectorEmbeddingPolicy"]["vectorEmbeddings"] == [
        {
            "path": "/embedding",
            "dataType": "float32",
            "distanceFunction": "cosine",
            "dimensions": 3072,
        }
    ]
    assert vector["indexingPolicy"]["vectorIndexes"] == [
        {"path": "/embedding", "type": "quantizedFlat"}
    ]
    for relative in (
        ROOT / "infra" / "bicep" / "main.bicep",
        ROOT / "infra" / "terraform" / "main.data.tf",
    ):
        source = relative.read_text(encoding="utf-8")
        assert "EnableNoSQLVectorSearch" in source
        assert "vectorEmbeddingPolicy" in source


@pytest.mark.parametrize(
    "setting,value",
    [
        ("DEPLOY_AGENT_APP_MCP", "maybe"),
        ("MCP_TOOLSETS", "{}"),
        ("MCP_TOOLSETS", '"nl2sql"'),
        ("MCP_TOOLSETS", '["unknown"]'),
        ("MCP_TOOLSETS", '["nl2sql", "nl2sql"]'),
        ("MCP_TOOLSETS", "[{}]"),
        ("MCP_QUERY_TIMEOUT_SECONDS", "76"),
        ("MCP_METADATA_CONTAINER", "mcp-sources"),
        ("MCP_EMBEDDING_DIMENSIONS", "4097"),
        ("MCP_METADATA_TOP_K", "0"),
        ("MCP_SQL_SECRET_NAMES", '["/secrets/password"]'),
        ("MCP_SQL_SECRET_NAMES", "{}"),
    ],
)
def test_invalid_mcp_inputs_fail_before_azure(setting, value):
    with pytest.raises(ValueError):
        mcp_config.settings(environment(**{setting: value}))


def test_client_deadline_is_longer_than_whole_query():
    values = mcp_config.consumer_settings(
        environment(), "https://mcp.example", "api://id/.default"
    )
    assert values["MCP_CLIENT_TIMEOUT"] == "90"
    assert json.loads(values["MCP_TRUSTED_HOSTS"]) == ["mcp.example"]
    with pytest.raises(ValueError, match="exceed"):
        mcp_config.consumer_settings(
            environment(MCP_CLIENT_TIMEOUT="75"), "https://mcp.example", "scope"
        )


def test_external_mcp_endpoint_cannot_be_overwritten():
    with pytest.raises(ValueError, match="external MCP"):
        mcp_config.consumer_settings(
            environment(MCP_APP_ENDPOINT="https://external.example"),
            "https://mcp.example",
            "scope",
        )


def test_capabilities_are_read_from_the_exact_account_and_preserved():
    env = environment(COSMOS_DB_ACCOUNT_RESOURCE_ID=ACCOUNT)
    with patch.object(
        mcp,
        "command",
        return_value={
            "id": ACCOUNT,
            "kind": "GlobalDocumentDB",
            "properties": {
                "capabilities": [
                    {"name": "EnableServerless"},
                    {"name": "EnablePerPartitionFailover"},
                ]
            },
        },
    ) as command:
        assert mcp.capture_capabilities(env) == [
            "EnableServerless",
            "EnablePerPartitionFailover",
            "EnableNoSQLVectorSearch",
        ]
    command.assert_called_once_with(["resource", "show", "--ids", ACCOUNT])


def test_account_binding_can_come_from_existing_foundation_appconfig():
    with (
        patch.object(mcp, "stored", return_value=ACCOUNT),
        patch.object(
            mcp,
            "command",
            return_value={
                "id": ACCOUNT,
                "kind": "GlobalDocumentDB",
                "properties": {"capabilities": [{"name": "EnableServerless"}]},
            },
        ) as command,
    ):
        assert "EnableNoSQLVectorSearch" in mcp.capture_capabilities(environment())
    command.assert_called_once_with(["resource", "show", "--ids", ACCOUNT])


@pytest.mark.parametrize(
    "account",
    [
        {"id": ACCOUNT.replace("rg-test", "rg-other")},
        {"id": ACCOUNT, "kind": "MongoDB", "properties": {"capabilities": []}},
        {"id": ACCOUNT, "kind": "GlobalDocumentDB", "properties": {"capabilities": []}},
    ],
)
def test_existing_incompatible_account_is_not_converted(account):
    with patch.object(mcp, "command", return_value=account), pytest.raises(ValueError):
        mcp.capture_capabilities(environment(COSMOS_DB_ACCOUNT_RESOURCE_ID=ACCOUNT))


def test_catalog_owner_marker_is_persisted_before_provider_composition():
    with (
        patch.object(
            mcp,
            "capture_capabilities",
            return_value=["EnableServerless", "EnableNoSQLVectorSearch"],
        ),
        patch.object(mcp, "persist") as persist,
        patch.object(mcp, "stored", return_value=""),
    ):
        values = mcp.capture(ROOT, environment())
    assert values["COSMOS_VECTOR_SEARCH_ENABLED"] == "true"
    assert values["MCP_EMBEDDING_DIMENSIONS"] == "3072"
    persist.assert_called_once_with(ROOT, environment(), values)


def test_existing_vector_policy_changes_require_explicit_migration():
    with (
        patch.object(
            mcp,
            "stored",
            side_effect=["", "", "mcp-sources", "mcp-nl2sql-metadata", "3072"],
        ),
        patch.object(mcp, "persist") as persist,
        pytest.raises(ValueError, match="reindex"),
    ):
        mcp.capture(
            ROOT,
            environment(
                COSMOS_VECTOR_SEARCH_ENABLED="true", MCP_EMBEDDING_DIMENSIONS="1536"
            ),
        )
    persist.assert_not_called()


def test_existing_external_mcp_is_rejected_before_provisioning():
    with (
        patch.object(mcp, "stored", side_effect=["https://external.example", ""]),
        patch.object(mcp, "capture_capabilities") as capabilities,
        pytest.raises(ValueError, match="external MCP"),
    ):
        mcp.capture(ROOT, environment())
    capabilities.assert_not_called()


def test_fresh_api_setup_has_v2_tokens_and_application_only_role():
    env = environment()
    role = str(uuid5(NAMESPACE_URL, env["APP_CONFIG_ENDPOINT"] + "|MCP.Invoke"))
    application = {
        "id": OBJECT,
        "appId": CLIENT,
        "signInAudience": "AzureADMyOrg",
        "api": {"requestedAccessTokenVersion": 2},
        "appRoles": [
            {
                "id": role,
                "value": "MCP.Invoke",
                "isEnabled": True,
                "allowedMemberTypes": ["Application"],
            }
        ],
    }
    with (
        patch.object(mcp, "command", return_value=TENANT),
        patch.object(mcp, "stored", return_value=""),
        patch.object(mcp, "publish_settings") as publish,
        patch.object(
            mcp,
            "graph",
            side_effect=[
                application,
                {},
                {"value": []},
                {"id": PRINCIPAL, "appId": CLIENT},
            ],
        ) as graph,
    ):
        values = mcp.ensure_api(env)
    assert graph.call_args_list[0].args[:2] == ("POST", "/applications")
    assert graph.call_args_list[0].args[2]["api"]["requestedAccessTokenVersion"] == 2
    assert values["MCP_AUTH_AUDIENCE"] == CLIENT
    assert values["MCP_AUTH_RESOURCE_SCOPE"] == f"api://{CLIENT}/.default"
    publish.assert_called_once_with(
        env["APP_CONFIG_ENDPOINT"], {"MCP_AUTH_APP_OBJECT_ID": OBJECT}
    )


def test_existing_api_is_resolved_by_exact_object_not_display_name():
    env = environment()
    role = str(uuid5(NAMESPACE_URL, env["APP_CONFIG_ENDPOINT"] + "|MCP.Invoke"))
    application = {
        "id": OBJECT,
        "appId": CLIENT,
        "signInAudience": "AzureADMyOrg",
        "identifierUris": [f"api://{CLIENT}"],
        "api": {"requestedAccessTokenVersion": 2},
        "appRoles": [
            {
                "id": role,
                "value": "MCP.Invoke",
                "isEnabled": True,
                "allowedMemberTypes": ["Application"],
            }
        ],
    }
    with (
        patch.object(mcp, "command", return_value=TENANT),
        patch.object(mcp, "stored", return_value=OBJECT),
        patch.object(
            mcp,
            "graph",
            side_effect=[application, {"value": [{"id": PRINCIPAL, "appId": CLIENT}]}],
        ) as graph,
    ):
        mcp.ensure_api(env)
    assert graph.call_args_list[0].args == ("GET", "/applications/" + OBJECT)
    assert not any(call.args[0] == "POST" for call in graph.call_args_list)


def test_server_gets_only_two_reader_containers_models_and_declared_secrets():
    env = environment(MCP_SQL_SECRET_NAMES='["approved-sql-password"]')
    model = f"/subscriptions/{SUB}/resourceGroups/rg-test/providers/Microsoft.CognitiveServices/accounts/test"
    with (
        patch.object(mcp, "_config_value", side_effect=[ACCOUNT, "catalog", model]),
        patch.object(mcp, "ensure_cosmos_sql_role_assignment") as grant,
        patch.object(mcp, "_ensure_rbac") as rbac,
        patch.object(mcp, "grant_secrets") as secrets,
    ):
        mcp.grant_catalog(env, PRINCIPAL)
    assert grant.call_count == 2
    assert {call.args[-1].split("/")[-1] for call in grant.call_args_list} == {
        "mcp-sources",
        "mcp-nl2sql-metadata",
    }
    assert all(
        call.args[4] == mcp.COSMOS_DATA_READER_ROLE_GUID
        for call in grant.call_args_list
    )
    assert all(call.args[2] == model for call in rbac.call_args_list)
    secrets.assert_called_once_with(env, PRINCIPAL, ("approved-sql-password",))


def test_both_hosted_publications_use_actual_distinct_principals():
    with (
        patch.object(
            mcp,
            "publication_environment",
            side_effect=lambda env, mode: {**env, "mode": mode},
        ),
        patch.object(
            mcp,
            "discover_instance",
            side_effect=[
                SimpleNamespace(principal_id=PRINCIPAL),
                SimpleNamespace(principal_id=OBJECT),
            ],
        ),
    ):
        assert mcp.caller_principals(
            environment(ORCHESTRATION_HOST="hosted", APPLICATION_MODE="both")
        ) == [PRINCIPAL, OBJECT]


def test_role_assignment_uses_caller_application_id_and_is_idempotent():
    auth = {"MCP_AUTH_SERVICE_PRINCIPAL_ID": OBJECT, "MCP_AUTH_ROLE_ID": TENANT}
    assignment = {"principalId": PRINCIPAL, "resourceId": OBJECT, "appRoleId": TENANT}
    with (
        patch.object(mcp, "command", return_value={"id": PRINCIPAL, "appId": CLIENT}),
        patch.object(mcp, "graph", return_value={"value": [assignment]}) as graph,
    ):
        assert mcp.authorize(environment(), auth, [PRINCIPAL, PRINCIPAL]) == [CLIENT]
    graph.assert_called_once_with(
        "GET",
        "/servicePrincipals/" + PRINCIPAL + "/appRoleAssignments",
        subscription=SUB,
    )


def test_health_alone_does_not_authorize_mcp_readiness():
    with (
        patch.object(mcp.requests, "get", return_value=Mock()),
        patch.object(
            mcp.requests, "post", return_value=SimpleNamespace(status_code=200)
        ),
        pytest.raises(ValueError, match="anonymous"),
    ):
        mcp.readiness({"MCP_APP_ENDPOINT": "https://mcp.example"})


def test_ready_server_denies_anonymous_tool_discovery():
    with (
        patch.object(mcp.requests, "get", return_value=Mock()),
        patch.object(
            mcp.requests, "post", return_value=SimpleNamespace(status_code=401)
        ) as post,
    ):
        mcp.readiness({"MCP_APP_ENDPOINT": "https://mcp.example"})
    assert post.call_args.args == ("https://mcp.example/mcp",)


def test_disabled_component_does_not_make_azure_calls():
    env = environment(DEPLOY_AGENT_APP_MCP="false", MCP_TOOLSETS="[]")
    with patch.object(mcp, "command") as command, patch.object(mcp, "stored") as stored:
        assert mcp.prepare(ROOT, env) == {}
        mcp.deploy(ROOT, env)
        mcp.activate(ROOT, env)
        assert mcp.capture_capabilities(env) == ["EnableServerless"]
    command.assert_not_called()
    stored.assert_not_called()


@pytest.mark.parametrize("applications", [[], ["ca-test-mcp"]])
def test_deselection_revokes_callers_and_refreshes_only_remaining_compute(applications):
    env = environment(DEPLOY_AGENT_APP_MCP="false", MCP_TOOLSETS="[]", MCP_AUTH_APP_OBJECT_ID=OBJECT)
    with (
        patch.object(mcp, "command", return_value=applications),
        patch.object(mcp, "publish_settings") as publish,
        patch.object(mcp, "restart_server") as restart,
    ):
        mcp.activate(ROOT, env)
    assert publish.call_args.args[1]["MCP_ALLOWED_CLIENT_IDS"] == "[]"
    assert publish.call_args.args[1]["MCP_TOOLSETS"] == "[]"
    if applications:
        restart.assert_called_once_with(env, {"MCP_APP_NAME": "ca-test-mcp"})
    else:
        restart.assert_not_called()


def test_allowlist_refresh_restarts_every_active_server_revision():
    env = environment()
    binding = {"MCP_APP_NAME": "ca-test-mcp"}
    with patch.object(
        mcp, "command", side_effect=[["ca-test-mcp--a", "ca-test-mcp--b"], {}, {}]
    ) as command:
        mcp.restart_server(env, binding)
    assert command.call_count == 3
    assert command.call_args_list[1].args[0][-1] == "ca-test-mcp--a"
    assert command.call_args_list[2].args[0][-1] == "ca-test-mcp--b"


def test_allowlist_is_published_and_server_restarted_before_consumer_activation():
    env = environment()
    binding = {"MCP_APP_NAME": "ca-test-mcp", "MCP_APP_ENDPOINT": "https://mcp.example"}
    auth = {"MCP_AUTH_RESOURCE_SCOPE": "api://id/.default"}
    events = []
    with (
        patch.object(mcp, "server_binding", return_value=binding),
        patch.object(mcp, "ensure_api", return_value=auth),
        patch.object(mcp, "caller_principals", return_value=[PRINCIPAL]),
        patch.object(mcp, "authorize", return_value=[CLIENT]),
        patch.object(mcp, "persist"),
        patch.object(
            mcp,
            "publish_settings",
            side_effect=lambda endpoint, values: events.append(values),
        ),
        patch.object(
            mcp, "restart_server", side_effect=lambda *args: events.append("restart")
        ),
        patch.object(
            mcp, "readiness", side_effect=lambda *args: events.append("ready")
        ),
    ):
        mcp.activate(ROOT, env)
    assert events[0]["MCP_ENABLED"] == "false"
    assert json.loads(events[0]["MCP_ALLOWED_CLIENT_IDS"]) == [CLIENT]
    assert events[1:3] == ["restart", "ready"]
    assert events[3]["MCP_ENABLED"] == "true"


def test_hooks_share_capture_deploy_activate_and_order_mcp_before_consumer():
    for suffix in ("ps1", "sh"):
        provision = (ROOT / "scripts" / f"preProvision.{suffix}").read_text(
            encoding="utf-8"
        )
        deploy = (ROOT / "scripts" / f"preDeploy.{suffix}").read_text(encoding="utf-8")
        assert (
            "config.deployment.mcp" in provision
            and "--capture-capabilities" in provision
        )
        assert deploy.index("config.deployment.mcp") < deploy.index(
            "config.deployment.native_deploy"
        )
        assert "--activate" in deploy


def test_regular_appconfig_publication_preserves_server_bootstrap_endpoints():
    env = environment(
        MCP_COSMOS_ENDPOINT="https://cosmos.documents.azure.com",
        MCP_COSMOS_DATABASE="catalog",
        KEY_VAULT_ENDPOINT="https://vault.vault.azure.net",
    )
    with (
        patch.object(
            appconfig,
            "_container_app",
            return_value={"fqdn": "mcp.example", "principalId": PRINCIPAL},
        ),
        patch.object(appconfig, "scheduler_settings", return_value={}),
    ):
        values = appconfig.build_settings(env)
    assert values["MCP_COSMOS_ENDPOINT"] == env["MCP_COSMOS_ENDPOINT"]
    assert values["MCP_COSMOS_DATABASE"] == "catalog"
    assert values["KEY_VAULT_ENDPOINT"] == env["KEY_VAULT_ENDPOINT"]


def test_mcp_uai_selection_is_exact_and_ambiguous_identity_fails():
    response = {
        "fqdn": "mcp.example",
        "userAssigned": {
            "a": {"clientId": CLIENT, "principalId": PRINCIPAL},
            "b": {"clientId": TENANT, "principalId": OBJECT},
        },
    }
    with patch.object(appconfig, "_run_az", return_value=json.dumps(response)):
        with pytest.raises(ValueError, match="multiple"):
            appconfig._container_app(
                "rg-test", "mcp", required=True, require_identity_selection=True
            )
        result = appconfig._container_app(
            "rg-test",
            "mcp",
            required=True,
            require_identity_selection=True,
            identity_client_id=CLIENT,
        )
    assert result["uaiClientId"] == CLIENT and result["uaiPrincipalId"] == PRINCIPAL


def test_activation_cli_reads_fresh_selected_publication_bindings(monkeypatch):
    env = environment(HOSTED_AGENT_IMAGE_VERSION="new-publication")
    monkeypatch.setenv("AZURE_ENV_NAME", "test")
    monkeypatch.setattr("sys.argv", ["mcp", "--activate"])
    with (
        patch.object(mcp, "find_repo_root", return_value=ROOT),
        patch.object(mcp, "selected_environment", return_value=env) as selected,
        patch.object(mcp, "activate") as activate,
    ):
        assert mcp.main() == 0
    selected.assert_called_once_with(ROOT, "test")
    activate.assert_called_once_with(ROOT, env)


@pytest.mark.parametrize("host", ["container_apps", "hosted"])
@pytest.mark.parametrize("selection", ["[]", '["nl2sql"]'])
def test_toolset_requirements_match_both_provider_projections(host, selection):
    env = environment(ORCHESTRATION_HOST=host, MCP_TOOLSETS=selection)
    source = json.loads((ROOT / "main.parameters.json").read_text(encoding="utf-8"))
    plain = substitute_values(
        {key: value["value"] for key, value in source["parameters"].items()}, env
    )
    terraform = resolve_parameters(plain, env)
    bicep = composition(env)
    for key in (
        "containerAppsList", "databaseContainersList", "deployCosmosDb",
        "enableCosmosVectorSearch", "cosmosAccountCapabilities",
        "additionalAppConfigurationSettings",
    ):
        assert terraform[key] == bicep[key]
    enabled = selection != "[]"
    assert bicep["deployCosmosDb"] is enabled
    assert bicep["enableCosmosVectorSearch"] is enabled
    assert bool(bicep["databaseContainersList"]) is enabled
    published = {item["name"]: item for item in bicep["additionalAppConfigurationSettings"]}
    assert json.loads(published["MCP_TOOLSETS"]["value"]) == json.loads(selection)
    assert published["MCP_TOOLSETS"]["label"] == "agent-lz"


def test_empty_server_ignores_sql_settings_and_has_no_static_model_grant():
    env = environment(
        MCP_TOOLSETS="[]", MCP_SQL_SECRET_NAMES="invalid", MCP_QUERY_TIMEOUT_SECONDS="invalid"
    )
    assert mcp_config.settings(env) == {
        "DEPLOY_AGENT_APP_MCP": "true", "MCP_TOOLSETS": "[]"
    }
    definition = json.loads((ROOT / "app-definition.json").read_text(encoding="utf-8"))
    server = next(item for item in definition["components"] if item["name"] == "mcp")
    assert server["profiles"] == []
    assert composition(env)["deployCosmosDb"] is False


def test_toolsets_cannot_be_selected_without_the_server():
    with pytest.raises(ValueError, match="requires DEPLOY_AGENT_APP_MCP"):
        composition(environment(DEPLOY_AGENT_APP_MCP="false"))


def test_empty_server_preparation_never_discovers_or_grants_sql_dependencies():
    env = environment(
        MCP_TOOLSETS="[]",
        AZURE_CONTAINER_REGISTRY_RESOURCE_ID=(
            f"/subscriptions/{SUB}/resourceGroups/rg-test/providers/"
            "Microsoft.ContainerRegistry/registries/test"
        ),
    )
    binding = {
        "MCP_APP_ENDPOINT": "https://mcp.example",
        "MCP_APP_PRINCIPAL_ID": PRINCIPAL,
    }
    with (
        patch.object(mcp, "server_binding", return_value=binding),
        patch.object(mcp, "stored", return_value=""),
        patch.object(mcp, "registry_resource_group"),
        patch.object(mcp, "ensure_api", return_value={}),
        patch.object(mcp, "_config_value") as discover,
        patch.object(mcp, "grant_catalog") as grant,
        patch.object(mcp, "publish_settings"),
        patch.object(mcp, "persist"),
    ):
        values = mcp.prepare(ROOT, env)
    assert values["MCP_TOOLSETS"] == "[]"
    assert "MCP_COSMOS_ENDPOINT" not in values
    assert "MCP_COSMOS_DATABASE" not in values
    assert "MCP_SQL_SECRET_NAMES" not in values
    discover.assert_not_called()
    grant.assert_not_called()


def test_custom_vector_application_never_inherits_reference_mcp_catalog():
    env = environment(
        AGENTLZ_APP_DEFINITION="samples/custom-app/containerapp",
        DEPLOY_AGENT_APP_MCP="false", MCP_TOOLSETS="[]",
        COSMOS_VECTOR_SEARCH_ENABLED="true",
    )
    values = composition(env)
    source = json.loads((ROOT / "main.parameters.json").read_text(encoding="utf-8"))
    plain = substitute_values(
        {key: value["value"] for key, value in source["parameters"].items()}, env
    )
    terraform = resolve_parameters(plain, env)
    for key in (
        "containerAppsList", "databaseContainersList", "deployCosmosDb",
        "enableCosmosVectorSearch", "cosmosAccountCapabilities",
    ):
        assert terraform[key] == values[key]
    assert [app["service_name"] for app in values["containerAppsList"]] == ["web"]
    assert values["deployCosmosDb"] is True
    assert values["enableCosmosVectorSearch"] is True
    assert values["databaseContainersList"] == []
    assert {
        item["name"]: item["value"]
        for item in values["additionalAppConfigurationSettings"]
        if item["name"].startswith("MCP_")
    } == {"MCP_TOOLSETS": "[]"}
    with (
        patch.object(mcp, "command") as command,
        patch.object(mcp, "stored", return_value="") as stored,
        patch.object(mcp, "persist") as persist,
    ):
        assert mcp.prepare(ROOT, env) == {}
        mcp.deploy(ROOT, env)
        mcp.activate(ROOT, env)
        captured = mcp.capture(ROOT, env)
    assert set(captured) == {"COSMOS_ACCOUNT_CAPABILITIES"}
    assert "EnableNoSQLVectorSearch" in json.loads(captured["COSMOS_ACCOUNT_CAPABILITIES"])
    command.assert_not_called()
    stored.assert_called_once_with(env, "COSMOS_DB_ACCOUNT_RESOURCE_ID")
    persist.assert_called_once()


def test_custom_definition_rejects_reference_controls_before_azure_calls():
    env = environment(AGENTLZ_APP_DEFINITION="samples/custom-app/containerapp")
    with (
        patch.object(mcp, "command") as command,
        patch.object(mcp, "stored") as stored,
    ):
        for action in (mcp.prepare, mcp.deploy, mcp.activate, mcp.capture):
            with pytest.raises(ValueError, match="Custom definitions own"):
                action(ROOT, env)
    command.assert_not_called()
    stored.assert_not_called()


def test_custom_application_owns_toolsets_without_selecting_reference_resources():
    env = environment(
        AGENTLZ_APP_DEFINITION="samples/custom-app/containerapp",
        DEPLOY_AGENT_APP_MCP="false",
    )
    values = composition(env)
    assert values["deployCosmosDb"] is False
    assert values["enableCosmosVectorSearch"] is False
    assert values["databaseContainersList"] == []
    assert [app["service_name"] for app in values["containerAppsList"]] == ["web"]
    published = {item["name"]: item["value"] for item in values["additionalAppConfigurationSettings"]}
    assert json.loads(published["MCP_TOOLSETS"]) == ["nl2sql"]
    with (
        patch.object(mcp, "command") as command,
        patch.object(mcp, "stored") as stored,
        patch.object(mcp, "persist"),
    ):
        assert mcp.prepare(ROOT, env) == {}
        mcp.deploy(ROOT, env)
        mcp.activate(ROOT, env)
        mcp.capture(ROOT, env)
    command.assert_not_called()
    stored.assert_not_called()
    with patch.object(
        appconfig, "_container_app",
        return_value={"fqdn": "web.example", "principalId": PRINCIPAL},
    ) as discover:
        runtime = appconfig.build_settings(env)
    assert json.loads(runtime["MCP_TOOLSETS"]) == ["nl2sql"]
    assert [call.args[1] for call in discover.call_args_list] == ["ca-test-web"]
