"""Provisioned MCP bindings and ordered component deployment, shared by both hooks."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import requests

from config import find_repo_root
from config.appdefinition.roles import _ensure_rbac
from config.appdefinition.loader import load_selected_definition
from config.deployment import mcp_config
from config.deployment.appconfig import _container_app, _run_az, publish_settings
from config.deployment.context import bound_resource_id, registry_resource_group
from config.deployment.egress import selected_environment
from config.deployment.hosted_access import (
    Role,
    _config_value,
    _setting,
    discover_instance,
    run_az,
)
from config.deployment.native import resolve_application
from config.deployment.native_access import grant_secrets
from config.deployment.native_deploy import publication_environment
from config.deployment.resource_groups import resource_group_for
from config.deployment.setup_settings import load_setup_environment
from config.panel.setup import (
    COSMOS_DATA_READER_ROLE_GUID,
    container_scope_path,
    ensure_cosmos_sql_role_assignment,
)

LOGGER = logging.getLogger(__name__)
GRAPH = "https://graph.microsoft.com/v1.0"


def guid(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("MCP identity bindings must be GUID strings.")
    return str(UUID(value))


def command(arguments: list[str]) -> object:
    output = _run_az([*arguments, "--output", "json"], required=False)
    return json.loads(output) if output else {}


def graph(
    method: str, path: str, body: dict | None = None, *, subscription: str
) -> object:
    arguments = ["rest", "--method", method, "--url", GRAPH + path]
    arguments.extend(["--subscription", subscription])
    if body is not None:
        arguments.extend(
            ["--headers", "Content-Type=application/json", "--body", json.dumps(body)]
        )
    try:
        return command(arguments)
    except RuntimeError as error:
        raise RuntimeError(
            "MCP Entra API setup failed. The deployer needs permission to manage its "
            "API application and application-role assignments. No auth fallback was applied."
        ) from error


def stored(environment: Mapping[str, str], key: str) -> str:
    row = _setting(run_az, environment["APP_CONFIG_ENDPOINT"], key)
    return str(row["value"]) if row else ""


def persist(
    root: Path, environment: Mapping[str, str], values: Mapping[str, str]
) -> None:
    name = environment["AZURE_ENV_NAME"]
    for key, value in values.items():
        result = subprocess.run(
            ["azd", "env", "set", key, value, "--environment", name, "--no-prompt"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
        if result.returncode:
            raise RuntimeError("Cannot persist the selected MCP deployment bindings.")


def capture_capabilities(environment: Mapping[str, str]) -> list[str]:
    if not mcp_config.vector_required(environment):
        return mcp_config.account_capabilities(environment)
    resource_id = environment.get("COSMOS_DB_ACCOUNT_RESOURCE_ID", "")
    if not resource_id:
        return mcp_config.account_capabilities(environment)
    bound_resource_id(
        resource_id,
        environment,
        "Microsoft.DocumentDB/databaseAccounts",
        area="application",
    )
    account = command(["resource", "show", "--ids", resource_id])
    if (
        not isinstance(account, dict)
        or account.get("id", "").lower() != resource_id.lower()
    ):
        raise ValueError("Cosmos capability discovery returned a different account.")
    properties = account["properties"]
    capabilities = properties.get("capabilities", [])
    names = [item["name"] for item in capabilities]
    if mcp_config.vector_required(environment) and (
        account.get("kind") != "GlobalDocumentDB" or "EnableServerless" not in names
    ):
        raise ValueError(
            "The MCP catalog requires a compatible application NoSQL serverless account; no throughput conversion was performed."
        )
    return mcp_config.account_capabilities(
        {**environment, "COSMOS_ACCOUNT_CAPABILITIES": json.dumps(names)}
    )


def ensure_api(environment: Mapping[str, str]) -> dict[str, str]:
    tenant = guid(
        command(
            [
                "account",
                "show",
                "--subscription",
                environment["AZURE_SUBSCRIPTION_ID"],
                "--query",
                "tenantId",
            ]
        )
    )
    if (
        environment.get("AZURE_TENANT_ID")
        and guid(environment["AZURE_TENANT_ID"]) != tenant
    ):
        raise ValueError(
            "MCP API tenant conflicts with the selected deployment directory."
        )
    object_id = stored(environment, "MCP_AUTH_APP_OBJECT_ID")
    role_id = str(
        uuid5(NAMESPACE_URL, environment["APP_CONFIG_ENDPOINT"] + "|MCP.Invoke")
    )
    if object_id:
        application = graph(
            "GET",
            "/applications/" + guid(object_id),
            subscription=environment["AZURE_SUBSCRIPTION_ID"],
        )
    else:
        application = graph(
            "POST",
            "/applications",
            {
                "displayName": "Agent App MCP Server " + environment["RESOURCE_TOKEN"],
                "signInAudience": "AzureADMyOrg",
                "api": {"requestedAccessTokenVersion": 2},
                "appRoles": [
                    {
                        "id": role_id,
                        "allowedMemberTypes": ["Application"],
                        "displayName": "Invoke MCP tools",
                        "description": "Invoke approved Agent App MCP tools.",
                        "isEnabled": True,
                        "value": "MCP.Invoke",
                    }
                ],
            },
            subscription=environment["AZURE_SUBSCRIPTION_ID"],
        )
        if not isinstance(application, dict):
            raise ValueError("Entra application creation returned an invalid response.")
        # Save its immutable identity before later writes, so retry cannot create duplicates.
        publish_settings(
            environment["APP_CONFIG_ENDPOINT"],
            {
                "MCP_AUTH_APP_OBJECT_ID": guid(application["id"]),
            },
        )
    if not isinstance(application, dict):
        raise TypeError("MCP Entra application binding is invalid.")
    object_id, client_id = guid(application["id"]), guid(application["appId"])
    if application.get("signInAudience") != "AzureADMyOrg":
        raise ValueError("MCP API application must be single-tenant.")
    roles = application.get("appRoles", [])
    if not any(
        item.get("id") == role_id
        and item.get("value") == "MCP.Invoke"
        and item.get("isEnabled") is True
        and item.get("allowedMemberTypes") == ["Application"]
        for item in roles
    ):
        raise ValueError("MCP API application has an incompatible invocation role.")
    if application.get("api", {}).get("requestedAccessTokenVersion") != 2:
        raise ValueError("MCP API application must issue v2 access tokens.")
    uri = "api://" + client_id
    if application.get("identifierUris") != [uri]:
        if application.get("identifierUris"):
            raise ValueError("MCP API application has an unexpected resource URI.")
        graph(
            "PATCH",
            "/applications/" + object_id,
            {"identifierUris": [uri]},
            subscription=environment["AZURE_SUBSCRIPTION_ID"],
        )
    rows = graph(
        "GET",
        "/servicePrincipals?$filter=appId eq '" + client_id + "'",
        subscription=environment["AZURE_SUBSCRIPTION_ID"],
    )
    if not isinstance(rows, dict) or rows.get("@odata.nextLink"):
        raise ValueError(
            "MCP API service principal lookup must be a complete response."
        )
    principals = rows.get("value", [])
    if len(principals) > 1:
        raise ValueError("MCP API service principal binding is not unique.")
    principal = (
        principals[0]
        if principals
        else graph(
            "POST",
            "/servicePrincipals",
            {"appId": client_id},
            subscription=environment["AZURE_SUBSCRIPTION_ID"],
        )
    )
    if not isinstance(principal, dict) or guid(principal["appId"]) != client_id:
        raise ValueError(
            "MCP API service principal returned an unexpected application."
        )
    return {
        "MCP_AUTH_TENANT_ID": tenant,
        "MCP_AUTH_AUDIENCE": client_id,
        "MCP_AUTH_RESOURCE_SCOPE": uri + "/.default",
        "MCP_AUTH_APP_OBJECT_ID": object_id,
        "MCP_AUTH_SERVICE_PRINCIPAL_ID": guid(principal["id"]),
        "MCP_AUTH_ROLE_ID": role_id,
    }


def app_mapping(environment: Mapping[str, str], service: str) -> dict:
    rows = json.loads(environment.get("CONTAINER_APPS", "[]"))
    if not isinstance(rows, list):
        raise ValueError("Verified Container Apps mapping is required.")
    selected = [row for row in rows if isinstance(row, dict) and row.get("service_name") == service]
    if len(selected) != 1 or not selected[0].get("name") or not selected[0].get("identity", {}).get("principalId"):
        raise ValueError("Selected MCP operation requires an exact verified app and identity mapping.")
    return selected[0]


def server_binding(environment: Mapping[str, str]) -> dict[str, str]:
    group = resource_group_for(environment, "application")
    mapped = app_mapping(environment, "mcp")
    name = mapped["name"]
    server = _container_app(
        group,
        name,
        required=True,
        subscription=environment["AZURE_SUBSCRIPTION_ID"],
        require_identity_selection=True,
        identity_client_id=mapped["identity"].get("clientId") or "",
    )
    principal = server.get("uaiPrincipalId") or server.get("principalId")
    if not principal or not server["fqdn"]:
        raise ValueError(
            "MCP Container App requires its provisioned identity and HTTPS ingress."
        )
    if guid(principal) != guid(mapped["identity"]["principalId"]):
        raise ValueError("MCP app identity changed after verified discovery.")
    return {
        "MCP_APP_NAME": name,
        "MCP_APP_ENDPOINT": "https://" + server["fqdn"],
        "MCP_APP_PRINCIPAL_ID": guid(principal),
        "MCP_APP_CLIENT_ID": server.get("uaiClientId", ""),
    }


def grant_catalog(environment: Mapping[str, str], principal: str) -> None:
    account_id = environment.get("COSMOS_DB_ACCOUNT_RESOURCE_ID", "")
    context = bound_resource_id(
        account_id,
        environment,
        "Microsoft.DocumentDB/databaseAccounts",
        area="application",
    )
    database = environment.get("DATABASE_NAME", "")
    if not database:
        raise ValueError("MCP catalog requires its verified Cosmos database mapping.")
    values = mcp_config.settings(environment)
    for key in ("MCP_SOURCES_CONTAINER", "MCP_METADATA_CONTAINER"):
        ensure_cosmos_sql_role_assignment(
            context.name,
            context.resource_group,
            context.subscription,
            principal,
            COSMOS_DATA_READER_ROLE_GUID,
            container_scope_path(
                context.subscription,
                context.resource_group,
                context.name,
                database,
                values[key],
            ),
        )
    model_id = environment.get("AI_FOUNDRY_ACCOUNT_RESOURCE_ID", "")
    bound_resource_id(
        model_id, environment, "Microsoft.CognitiveServices/accounts", area="foundry"
    )
    _ensure_rbac(principal, Role.MODEL.value, model_id, _run_az)
    grant_secrets(
        environment, principal, tuple(json.loads(values["MCP_SQL_SECRET_NAMES"]))
    )


def reference_application(environment: Mapping[str, str]) -> bool:
    bundled = load_selected_definition(environment).bundled
    if not bundled and mcp_config.selected(environment):
        raise ValueError(
            "Reference MCP selection requires the bundled application. "
            "Custom definitions own their MCP service, toolsets and dependencies."
        )
    if bundled:
        mcp_config.validate_selection(environment)
    return bundled


def prepare(root: Path, environment: Mapping[str, str]) -> dict[str, str]:
    if not reference_application(environment):
        return {}
    settings = mcp_config.settings(environment)
    if not mcp_config.selected(environment):
        return {}
    binding = server_binding(environment)
    previous = stored(environment, "MCP_APP_ENDPOINT")
    mcp_config.consumer_settings(
        {**environment, "MCP_APP_ENDPOINT": previous}, binding["MCP_APP_ENDPOINT"], ""
    )
    registry_id = environment.get("AZURE_CONTAINER_REGISTRY_RESOURCE_ID", "")
    if not registry_id:
        raise ValueError(
            "MCP deployment requires the provisioned AZURE_CONTAINER_REGISTRY_RESOURCE_ID output."
        )
    registry_resource_group(environment)
    auth = ensure_api(environment)
    values = {
        **settings,
        **binding,
        **auth,
        "CONTAINER_REGISTRY_RESOURCE_ID": registry_id,
        "MCP_SERVER_URL": binding["MCP_APP_ENDPOINT"].rstrip("/") + "/mcp",
        "MCP_ALLOWED_CLIENT_IDS": stored(environment, "MCP_ALLOWED_CLIENT_IDS") or "[]",
        "MCP_ENABLED": "false",
    }
    if mcp_config.nl2sql_enabled(environment):
        values.update({
            "MCP_COSMOS_ENDPOINT": environment["COSMOS_DB_ENDPOINT"],
            "MCP_COSMOS_DATABASE": environment["DATABASE_NAME"],
        })
        vault = environment.get("KEY_VAULT_URI", "")
        if vault:
            values["KEY_VAULT_ENDPOINT"] = vault
        grant_catalog(environment, binding["MCP_APP_PRINCIPAL_ID"])
    publish_settings(environment["APP_CONFIG_ENDPOINT"], values)
    persist(root, environment, values)
    return values


def deploy(root: Path, environment: Mapping[str, str]) -> None:
    if not reference_application(environment):
        return
    mcp_config.toolsets(environment)
    if not mcp_config.selected(environment):
        return
    values = prepare(root, environment)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    components = [
        item
        for item in manifest["components"]
        if item["name"] == mcp_config.MCP_COMPONENT
    ]
    if len(components) != 1:
        raise ValueError("Manifest must bind exactly one Agent App MCP Server.")
    component = components[0]
    if component["repo"] != "https://github.com/Azure/agent-app-mcp.git":
        raise ValueError(
            "MCP manifest source is not the selected component repository."
        )
    commit = component["commit"]
    if len(commit) != 40 or any(
        character not in "0123456789abcdef" for character in commit
    ):
        raise ValueError("MCP component must be pinned to a complete immutable commit.")
    target = root.parent / mcp_config.MCP_COMPONENT
    if not target.exists():
        _process(
            [
                "git",
                "clone",
                "--no-checkout",
                "--filter=blob:none",
                component["repo"],
                str(target),
            ],
            root,
        )
        _process(["git", "-C", str(target), "fetch", "origin", commit], root)
        _process(["git", "-C", str(target), "checkout", "--detach", commit], root)
    actual = _process(
        ["git", "-C", str(target), "rev-parse", "HEAD"], root
    ).stdout.strip()
    if actual != commit:
        raise ValueError(
            "MCP sibling checkout does not match the manifest pin. Relocate the stale checkout explicitly."
        )
    source_env = root / ".azure" / environment["AZURE_ENV_NAME"]
    if not source_env.is_dir():
        raise ValueError("Selected azd environment is missing from the platform.")
    shutil.copytree(
        source_env,
        target / ".azure" / environment["AZURE_ENV_NAME"],
        dirs_exist_ok=True,
    )
    child_environment = {**os.environ, **environment, **values}
    if os.name == "nt":
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            raise ValueError("PowerShell is required for the MCP component deployment.")
        invocation = [
            shell,
            "-NoProfile",
            "-File",
            str(target / "scripts" / "deploy.ps1"),
        ]
    else:
        invocation = ["bash", str(target / "scripts" / "deploy.sh")]
    _process(invocation, target, child_environment)
    readiness(values)


def _process(
    arguments: list[str], root: Path, environment: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        arguments,
        cwd=root,
        env=dict(environment) if environment is not None else None,
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    if result.returncode:
        log_dir = root / ".logs"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / "mcp-lifecycle.log"
        log_path.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        raise RuntimeError(
            f"MCP component lifecycle command failed. Inspect local diagnostics securely: {log_path}."
        )
    return result


def readiness(values: Mapping[str, str]) -> None:
    endpoint = values["MCP_APP_ENDPOINT"].rstrip("/")
    response = requests.get(endpoint + "/healthz", timeout=15)
    response.raise_for_status()
    # Liveness is insufficient: the MCP endpoint must deny anonymous invocation.
    response = requests.post(
        endpoint + "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={"Accept": "application/json, text/event-stream"},
        timeout=15,
    )
    if response.status_code != 401:
        raise ValueError(
            "MCP readiness requires authenticated transport; anonymous discovery was not rejected."
        )


def restart_server(environment: Mapping[str, str], binding: Mapping[str, str]) -> None:
    group = resource_group_for(environment, "application")
    arguments = [
        "--name",
        binding["MCP_APP_NAME"],
        "--resource-group",
        group,
        "--subscription",
        environment["AZURE_SUBSCRIPTION_ID"],
    ]
    revisions = command(
        [
            "containerapp",
            "revision",
            "list",
            *arguments,
            "--query",
            "[?properties.active].name",
        ]
    )
    if (
        not isinstance(revisions, list)
        or not revisions
        or any(
            not isinstance(name, str)
            or not name.startswith(binding["MCP_APP_NAME"] + "--")
            for name in revisions
        )
    ):
        raise ValueError(
            "MCP allowlist activation requires its exact active serving revisions."
        )
    for revision in revisions:
        command(
            ["containerapp", "revision", "restart", *arguments, "--revision", revision]
        )


def caller_principals(environment: Mapping[str, str]) -> list[str]:
    app = resolve_application(environment)
    if app.host.value == "container_apps":
        return [guid(app_mapping(environment, "orchestrator")["identity"]["principalId"])]
    return [
        guid(discover_instance(publication_environment(environment, mode)).principal_id)
        for mode in app.publications
    ]


def authorize(
    environment: Mapping[str, str], auth: Mapping[str, str], principals: list[str]
) -> list[str]:
    clients = []
    for principal in dict.fromkeys(principals):
        row = command(["ad", "sp", "show", "--id", guid(principal)])
        if not isinstance(row, dict) or guid(row["id"]) != guid(principal):
            raise ValueError(
                "MCP caller service principal does not match its provisioned identity."
            )
        clients.append(guid(row["appId"]))
        path = "/servicePrincipals/" + principal + "/appRoleAssignments"
        assignments = graph(
            "GET", path, subscription=environment["AZURE_SUBSCRIPTION_ID"]
        )
        if not isinstance(assignments, dict) or assignments.get("@odata.nextLink"):
            raise ValueError("MCP caller role lookup must be complete.")
        expected = {
            "principalId": principal,
            "resourceId": auth["MCP_AUTH_SERVICE_PRINCIPAL_ID"],
            "appRoleId": auth["MCP_AUTH_ROLE_ID"],
        }
        if not any(
            all(item.get(key) == value for key, value in expected.items())
            for item in assignments.get("value", [])
        ):
            graph(
                "POST",
                path,
                expected,
                subscription=environment["AZURE_SUBSCRIPTION_ID"],
            )
    return clients


def activate(root: Path, environment: Mapping[str, str]) -> None:
    if not reference_application(environment):
        return
    toolsets = mcp_config.toolsets(environment)
    if not mcp_config.selected(environment):
        if environment.get("MCP_AUTH_APP_OBJECT_ID"):
            publish_settings(
                environment["APP_CONFIG_ENDPOINT"],
                {
                    "MCP_ENABLED": "false",
                    "DEPLOY_AGENT_APP_MCP": "false",
                    "MCP_TOOLSETS": "[]",
                    "MCP_ALLOWED_CLIENT_IDS": "[]",
                },
            )
            name = "ca-" + environment["RESOURCE_TOKEN"] + "-mcp"
            applications = command(
                [
                    "containerapp",
                    "list",
                    "--resource-group",
                    resource_group_for(environment, "application"),
                    "--subscription",
                    environment["AZURE_SUBSCRIPTION_ID"],
                    "--query",
                    "[].name",
                ]
            )
            if not isinstance(applications, list):
                raise TypeError(
                    "MCP deselection requires a complete Container App inventory."
                )
            # Bicep incremental deployment may retain the deselected compute.
            if name in applications:
                restart_server(environment, {"MCP_APP_NAME": name})
        return
    binding = server_binding(environment)
    auth = ensure_api(environment)
    clients = authorize(environment, auth, caller_principals(environment))
    publish_settings(
        environment["APP_CONFIG_ENDPOINT"],
        {
            **auth,
            "MCP_TOOLSETS": json.dumps(toolsets),
            "MCP_ALLOWED_CLIENT_IDS": json.dumps(clients),
            "MCP_ENABLED": "false",
        },
    )
    restart_server(environment, binding)
    readiness(binding)
    consumer = mcp_config.consumer_settings(
        environment, binding["MCP_APP_ENDPOINT"], auth["MCP_AUTH_RESOURCE_SCOPE"]
    )
    publish_settings(environment["APP_CONFIG_ENDPOINT"], consumer)
    persist(root, environment, {**auth, **consumer})


def capture(root: Path, environment: Mapping[str, str]) -> dict[str, str]:
    if not reference_application(environment):
        values = {
            "COSMOS_ACCOUNT_CAPABILITIES": json.dumps(
                capture_capabilities({**environment, "MCP_TOOLSETS": "[]"})
            )
        }
        persist(root, environment, values)
        return values
    mcp_config.settings(environment)
    previous_endpoint = environment.get("MCP_APP_ENDPOINT", "")
    previous_name = environment.get("MCP_APP_NAME", "")
    if mcp_config.selected(environment) and environment.get("APP_CONFIG_ENDPOINT"):
        previous_endpoint = stored(environment, "MCP_APP_ENDPOINT") or previous_endpoint
        previous_name = stored(environment, "MCP_APP_NAME") or previous_name
    if (
        mcp_config.selected(environment)
        and previous_endpoint
        and previous_name != "ca-" + environment["RESOURCE_TOKEN"] + "-mcp"
    ):
        raise ValueError(
            "Agent App MCP conflicts with an existing external MCP endpoint. Select one explicitly before provisioning."
        )
    if mcp_config.retained_catalog(environment) and environment.get(
        "APP_CONFIG_ENDPOINT"
    ):
        desired = mcp_config.settings(environment)
        for key in (
            "MCP_SOURCES_CONTAINER",
            "MCP_METADATA_CONTAINER",
            "MCP_EMBEDDING_DIMENSIONS",
        ):
            previous = stored(environment, key)
            if previous and previous != desired[key]:
                raise ValueError(
                    "Existing MCP catalog policy cannot be changed in place. Migrate and reindex the catalog explicitly before rebinding it."
                )
    values = {
        "COSMOS_ACCOUNT_CAPABILITIES": json.dumps(capture_capabilities(environment))
    }
    if previous_endpoint:
        values["MCP_APP_ENDPOINT"] = previous_endpoint
    if mcp_config.vector_required(environment):
        values.update(
            {
                "COSMOS_VECTOR_SEARCH_ENABLED": "true",
                **{
                    key: value
                    for key, value in mcp_config.settings(environment).items()
                    if key
                    in (
                        "MCP_SOURCES_CONTAINER",
                        "MCP_METADATA_CONTAINER",
                        "MCP_EMBEDDING_DIMENSIONS",
                    )
                },
            }
        )
    persist(root, environment, values)
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--capture-capabilities", action="store_true")
    actions.add_argument("--deploy", action="store_true")
    actions.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    try:
        root = find_repo_root()
        environment = (
            os.environ
            if args.capture_capabilities
            else load_setup_environment(os.environ, project_root=root)
        )
        if args.capture_capabilities:
            print(json.dumps(capture(root, environment)))
        elif args.deploy:
            deploy(root, environment)
        elif args.activate:
            activate(root, environment)
        else:
            parser.error("Select --capture-capabilities, --deploy or --activate.")
    except (
        TypeError,
        ValueError,
        KeyError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        requests.RequestException,
    ) as error:
        LOGGER.error("MCP deployment failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
