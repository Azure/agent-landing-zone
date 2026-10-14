"""Plan (default) or apply the hosted instance's minimum runtime RBAC.

Only configuration metadata, Foundry agent metadata and ARM are read. No secret
values, inference requests, continuity activation or document grants are used.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from enum import Enum
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Callable, Mapping
from urllib.parse import urlsplit
from uuid import UUID, uuid5, NAMESPACE_URL

from config.continuity.settings import FOUNDRY_TOKEN_AUDIENCE
from config.deployment.composition import HOSTED_AGENT_NAME_DEFAULT, DeploymentMode, resolve_mode
from util.azure_cli import resolve_az_command


class AccessError(RuntimeError):
    """A sanitized, operator-actionable bootstrap failure."""


class Operation(str, Enum):
    RESOURCE_READ = "arm-resource-read"
    ACCOUNT_READ = "cognitive-account-read"
    STORE_READ = "appconfig-store-read"
    SETTINGS_READ = "appconfig-settings-read"
    VAULT_READ = "keyvault-metadata-read"
    AGENT_READ = "foundry-agent-read"
    ASSIGNMENT_READ = "role-assignment-read"
    ASSIGNMENT_CREATE = "role-assignment-create"
    UNKNOWN = "azure-cli-operation"


class AzureCommandError(AccessError):
    def __init__(self, code: str = "CommandFailed", *, stage: Operation = Operation.UNKNOWN):
        self.code = code if code in {
            "CommandFailed", "CliUsageError", "CliUnavailable", "CliTimeout",
            "InvalidJson", "PrincipalNotFound", "RoleAssignmentExists",
        } else "CommandFailed"
        self.stage = stage if isinstance(stage, Operation) else Operation.UNKNOWN
        guidance = (
            "Local Azure CLI rejected the arguments; check CLI compatibility and "
            "bootstrap command construction before changing Azure permissions."
            if self.code == "CliUsageError" else
            "Check CLI availability/compatibility, operator access and connectivity "
            "as appropriate; the failure alone does not identify a permission issue."
        )
        super().__init__(
            f"Bootstrap stage {self.stage.value} failed ({self.code}). {guidance} "
            "Rerun read-only --plan after correcting the cause. "
            "Arguments and provider output are intentionally omitted."
        )


class Role(str, Enum):
    # Verified against infra/constants/roles.json; never resolve a role by name.
    CONFIG = "516239f1-63e1-4d78-a4de-a74fb236a071"
    SECRET = "4633458b-17de-408a-b874-0445c86b69e6"
    MODEL = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"


GUID = r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"
NAME = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
ARM_PREFIX = rf"/subscriptions/({GUID})/resourceGroups/({NAME})/providers/"
RESOURCE_PATHS = {
    Role.CONFIG: rf"Microsoft\.AppConfiguration/configurationStores/{NAME}",
    Role.MODEL: rf"Microsoft\.CognitiveServices/accounts/{NAME}",
    Role.SECRET: r"Microsoft\.KeyVault/vaults/[A-Za-z0-9-]+/secrets/[A-Za-z0-9-]{1,127}",
}
PROJECT_PATH = rf"Microsoft\.CognitiveServices/accounts/({NAME})/projects/({NAME})"
KV_REFERENCE = "application/vnd.microsoft.appconfig.keyvaultref+json"
ARM_ENDPOINT = "https://management.azure.com"
# Operator-verified raw account API. Avoid the installed CLI's typed Cognitive
# Services SDK, which cannot deserialize newer unrelated list-shaped fields.
COGNITIVE_ACCOUNT_API_VERSION = "2025-06-01"
PROPAGATION = (
    "ARM assignments verified, NOT data-plane readiness. Azure RBAC may still "
    "propagate. If root smoke fails, cutover must remain blocked: wait, rerun "
    "this bootstrap --apply (idempotent), then retry the existing root azd deploy "
    "smoke/cutover with the same immutable image. No inference or session restart "
    "is performed by this module."
)
RunAzure = Callable[[list[str]], object]


def _object(value: object) -> dict:
    if not isinstance(value, dict):
        raise AccessError("Expected an object in deployment metadata.")
    return value


def _json(value: str) -> object:
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        raise AccessError("Invalid JSON in deployment metadata; values omitted.") from None


def _string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccessError("Required deployment metadata is missing or has the wrong type.")
    return value.strip()


def _guid(value: object) -> str:
    text = _string(value)
    if not re.fullmatch(GUID, text) or UUID(text).int == 0:
        raise AccessError("The deployed instance principal/subscription must be a nonzero GUID.")
    return text.lower()


def _same(left: object, right: str) -> bool:
    return isinstance(left, str) and left.lower() == right.lower()


def _endpoint(value: object, suffix: str, path: str = r"/?") -> str:
    text = _string(value)
    try:
        parsed = urlsplit(text)
        if (
            any(ord(c) <= 32 for c in text)
            or "\\" in text or "?" in text or "#" in text
            or parsed.scheme != "https" or parsed.port not in (None, 443)
            or parsed.username is not None or parsed.password is not None
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?" + re.escape(suffix), parsed.hostname or "")
            or not re.fullmatch(path, parsed.path)
        ):
            raise ValueError
    except ValueError:
        raise AccessError("Invalid public-Azure HTTPS endpoint or resource path; value omitted.") from None
    return f"https://{parsed.hostname}{parsed.path}".rstrip("/")


def _bound_scope(scope: str, path: str, subscription: str, group: str) -> None:
    match = re.fullmatch(ARM_PREFIX + path, scope, re.IGNORECASE)
    if not match or not _same(match[1], subscription) or not _same(match[2], group):
        raise AccessError("Resource scope is not an exact resource in the declared subscription/resource group.")


@dataclass(frozen=True)
class Grant:
    role: Role
    scope: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, Role) or not re.fullmatch(
            ARM_PREFIX + RESOURCE_PATHS[self.role], self.scope, re.IGNORECASE
        ):
            raise AccessError("Grant is outside the closed runtime role/scope allowlist.")

    def assignment_name(self, principal: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"{self.scope.lower()}|{principal.lower()}|{self.role.value}"))


@dataclass(frozen=True)
class AccessPlan:
    subscription: str = ""
    resource_group: str = ""
    principal_id: str = ""
    agent_name: str = ""
    agent_version: str = ""
    grants: tuple[Grant, ...] = ()
    audit: str = "not-configured"
    classic: bool = False

    def validate(self) -> None:
        if self.classic:
            if self.grants or self.principal_id:
                raise AccessError("Classic bootstrap cannot contain grants.")
            return
        _guid(self.subscription)
        _guid(self.principal_id)
        roles = [grant.role for grant in self.grants]
        expected = {Role.CONFIG, Role.MODEL}
        if self.audit == "configured":
            expected.add(Role.SECRET)
        elif self.audit != "not-configured":
            raise AccessError("Unknown audit configuration status.")
        if len(set(roles)) != len(roles) or set(roles) != expected:
            raise AccessError("Incomplete or duplicate runtime role plan.")
        for grant in self.grants:
            _bound_scope(grant.scope, RESOURCE_PATHS[grant.role], self.subscription, self.resource_group)


def run_az(arguments: list[str]) -> object:
    """Use native CLI resolution; never include arguments/provider bodies in errors."""
    stages = {
        ("resource", "show"): Operation.RESOURCE_READ,
        ("cognitiveservices", "account", "show"): Operation.ACCOUNT_READ,
        ("appconfig", "show"): Operation.STORE_READ,
        ("appconfig", "kv", "list"): Operation.SETTINGS_READ,
        ("keyvault", "show"): Operation.VAULT_READ,
        ("rest",): Operation.AGENT_READ,
        ("role", "assignment", "list"): Operation.ASSIGNMENT_READ,
        ("role", "assignment", "create"): Operation.ASSIGNMENT_CREATE,
    }
    stage = next(
        (value for prefix, value in stages.items() if tuple(arguments[:len(prefix)]) == prefix),
        Operation.UNKNOWN,
    )
    if arguments[:1] == ["rest"] and "--url" in arguments:
        index = arguments.index("--url") + 1
        if index < len(arguments) and arguments[index].startswith(f"{ARM_ENDPOINT}/subscriptions/"):
            stage = Operation.ACCOUNT_READ
    try:
        result = subprocess.run(
            [resolve_az_command(), *arguments, "--output", "json", "--only-show-errors"],
            capture_output=True, text=True, check=False, timeout=90,
        )
    except OSError:
        raise AzureCommandError("CliUnavailable", stage=stage) from None
    except subprocess.TimeoutExpired:
        raise AzureCommandError("CliTimeout", stage=stage) from None
    if result.returncode:
        if result.returncode == 2 or any(marker in result.stderr.lower() for marker in (
            "the following arguments are required:", "unrecognized arguments:",
        )):
            raise AzureCommandError("CliUsageError", stage=stage)
        # Azure RBAC documented error codes: PrincipalNotFound (replication)
        # and RoleAssignmentExists (concurrent exact assignment). No other
        # failed writes, auth errors or timeouts are retried.
        match = re.search(r"(?:\(|Code:\s*)(PrincipalNotFound|RoleAssignmentExists)\b", result.stderr)
        raise AzureCommandError(match[1] if match else "CommandFailed", stage=stage)
    try:
        return _json(result.stdout)
    except AccessError:
        raise AzureCommandError("InvalidJson", stage=stage) from None


def _setting(run: RunAzure, endpoint: str, key: str) -> dict | None:
    rows = run([
        "appconfig", "kv", "list", "--endpoint", endpoint, "--auth-mode", "login",
        "--key", key, "--label", "agent-lz",
    ])
    if not isinstance(rows, list) or len(rows) > 1:
        raise AccessError("App Configuration metadata was not unique.")
    if not rows:
        return None
    row = _object(rows[0])
    if row.get("key") != key or row.get("label") != "agent-lz":
        raise AccessError("App Configuration key/label binding mismatch.")
    return row


def _config_value(run: RunAzure, endpoint: str, key: str) -> str:
    row = _setting(run, endpoint, key)
    if row is None:
        raise AccessError(f"Required App Configuration key {key} (agent-lz) is missing.")
    return _string(row.get("value"))


def _consistent(environment: Mapping[str, str], keys: tuple[str, ...], extra: object = None) -> str:
    values = [_string(environment[k]) for k in keys if environment.get(k)]
    if extra is not None:
        values.append(_string(extra))
    if not values or len({v.rstrip("/").lower() for v in values}) != 1:
        raise AccessError(f"Missing or conflicting deployment binding: {', '.join(keys)}.")
    return values[0].rstrip("/")


def _account_metadata(run: RunAzure, scope: str, subscription: str, group: str) -> dict:
    """Read validated account JSON directly; no typed-SDK call or fallback."""
    _bound_scope(scope, RESOURCE_PATHS[Role.MODEL], subscription, group)
    account = _object(run([
        "rest", "--method", "get", "--url",
        f"{ARM_ENDPOINT}{scope}?api-version={COGNITIVE_ACCOUNT_API_VERSION}",
    ]))
    if (
        not _same(account.get("id"), scope)
        or not _same(account.get("name"), scope.rsplit("/", 1)[1])
        or not _same(account.get("type"), "Microsoft.CognitiveServices/accounts")
        or account.get("kind") not in {"AIServices", "OpenAI"}
        or not isinstance(account.get("properties"), dict)
    ):
        raise AccessError("Cognitive account ARM metadata identity/type/properties mismatch.")
    return account


@dataclass(frozen=True)
class HostedInstance:
    subscription: str
    resource_group: str
    principal_id: str
    agent_name: str
    agent_version: str


def discover_instance(
    environment: Mapping[str, str], *, name: str | None = None, run: RunAzure = run_az,
) -> HostedInstance:
    """Resolve a live routed identity bound to the declared Foundry project."""
    sub = _guid(environment.get("AZURE_SUBSCRIPTION_ID"))
    group = _string(environment.get("AZURE_RESOURCE_GROUP"))
    if not re.fullmatch(NAME, group):
        raise AccessError("Invalid declared resource group.")
    handoff = _object(_json(environment["HOSTED_AGENT_DEPLOYMENT"])) if environment.get("HOSTED_AGENT_DEPLOYMENT") else {}
    foundry = _object(handoff["foundry"]) if handoff.get("foundry") is not None else {}
    agent = _object(handoff["agent"]) if handoff.get("agent") is not None else {}
    project = _consistent(environment, ("AZURE_AI_PROJECT_RESOURCE_ID", "AZURE_AI_PROJECT_ID", "AI_FOUNDRY_PROJECT_RESOURCE_ID"), foundry.get("projectResourceId"))
    endpoint = _consistent(environment, ("AZURE_AI_PROJECT_ENDPOINT", "FOUNDRY_PROJECT_ENDPOINT", "AI_FOUNDRY_PROJECT_ENDPOINT"), foundry.get("projectEndpoint"))
    _bound_scope(project, PROJECT_PATH, sub, group)
    project_name = project.rsplit("/", 1)[1]
    endpoint = _endpoint(endpoint, ".services.ai.azure.com", rf"/api/projects/{re.escape(project_name)}/?")
    name = name if name is not None else _consistent(environment, ("HOSTED_AGENT_NAME",), agent.get("name", environment.get("HOSTED_AGENT_NAME") or HOSTED_AGENT_NAME_DEFAULT))
    if not re.fullmatch(NAME, name):
        raise AccessError("Invalid expected hosted agent name.")
    account_id = project.rsplit("/", 2)[0]
    project_metadata = _object(run(["resource", "show", "--ids", project]))
    if not _same(project_metadata.get("id"), project):
        raise AccessError("Foundry project ARM identity mismatch.")
    account = _account_metadata(run, account_id, sub, group)
    domain = _string(_object(account.get("properties")).get("customSubDomainName"))
    if not _same(account.get("id"), account_id) or endpoint != f"https://{domain.lower()}.services.ai.azure.com/api/projects/{project_name}":
        raise AccessError("Foundry endpoint does not map to the declared ARM project/account.")

    # Same official v1 agent + routed-version retrieval used by continuity.
    def retrieve(path: str) -> dict:
        return _object(run(["rest", "--method", "GET", "--url", f"{endpoint}/agents/{name}{path}?api-version=v1", "--resource", FOUNDRY_TOKEN_AUDIENCE]))

    live = retrieve("")
    if live.get("name") != name:
        raise AccessError("Deployed agent name does not match the deployment handoff.")
    principal = _guid(_object(live.get("instance_identity")).get("principal_id"))
    agent_endpoint = _object(live.get("agent_endpoint"))
    rules = _object(agent_endpoint.get("version_selector")).get("version_selection_rules")
    if not isinstance(rules, list) or len(rules) != 1:
        raise AccessError("Expected exactly one fully routed hosted agent version.")
    rule = _object(rules[0])
    if str(rule.get("type", "")).lower() != "fixedratio" or type(rule.get("traffic_percentage")) is not int or rule["traffic_percentage"] != 100:
        raise AccessError("Expected a fixed 100 percent hosted agent version.")
    version = _string(rule.get("agent_version"))
    if version == "@latest":
        latest = _object(_object(live.get("versions")).get("latest"))
        if latest.get("name") != name or _object(latest.get("definition")).get("kind") != "hosted":
            raise AccessError("Latest routed version is not the expected hosted agent.")
        version = _string(latest.get("version"))
    if not re.fullmatch(r"[1-9][0-9]*", version):
        raise AccessError("Invalid routed hosted agent version.")
    deployed = retrieve(f"/versions/{version}")
    definition = _object(deployed.get("definition"))
    if deployed.get("name") != name or str(deployed.get("version")) != version or definition.get("kind") != "hosted":
        raise AccessError("Retrieved version is not the expected hosted agent.")
    # Protocol extensions cannot skip identity/name/version validation.
    return HostedInstance(sub, group, principal, name, version)


def discover(environment: Mapping[str, str], *, run: RunAzure = run_az) -> AccessPlan:
    """Discover and validate the entire closed plan before any write."""
    if resolve_mode(environment) is DeploymentMode.CLASSIC:
        return AccessPlan(classic=True)
    instance = discover_instance(environment, run=run)
    sub, group, principal, name, version = (
        instance.subscription, instance.resource_group, instance.principal_id,
        instance.agent_name, instance.agent_version,
    )
    config_endpoint = _endpoint(environment.get("APP_CONFIG_ENDPOINT"), ".azconfig.io")
    store_name = urlsplit(config_endpoint).hostname.split(".")[0]
    prefix = f"/subscriptions/{sub}/resourceGroups/{group}/providers/"
    store_id = prefix + f"Microsoft.AppConfiguration/configurationStores/{store_name}"
    store = _object(run(["appconfig", "show", "--name", store_name, "--resource-group", group, "--subscription", sub]))
    if not _same(store.get("id"), store_id) or _endpoint(store.get("endpoint"), ".azconfig.io") != config_endpoint:
        raise AccessError("App Configuration endpoint/ARM scope mismatch.")
    if not _same(_config_value(run, config_endpoint, "SUBSCRIPTION_ID"), sub) or not _same(_config_value(run, config_endpoint, "AZURE_RESOURCE_GROUP"), group):
        raise AccessError("Configuration store belongs to a different deployment scope.")
    model_name = _config_value(run, config_endpoint, "AI_FOUNDRY_ACCOUNT_NAME")
    if not re.fullmatch(NAME, model_name):
        raise AccessError("Invalid configured model account name.")
    model_id = prefix + f"Microsoft.CognitiveServices/accounts/{model_name}"
    model = _account_metadata(run, model_id, sub, group)
    if not _same(model.get("id"), model_id) or model.get("kind") not in {"AIServices", "OpenAI"}:
        raise AccessError("Configured model account identity/type mismatch.")
    grants = [Grant(Role.CONFIG, store_id), Grant(Role.MODEL, model_id)]
    audit = _setting(run, config_endpoint, "AUDIT_HMAC_KEY")
    if audit is not None:
        content_type = audit.get("contentType")
        if not isinstance(content_type, str) or content_type.split(";", 1)[0].lower() != KV_REFERENCE:
            raise AccessError("AUDIT_HMAC_KEY must be a Key Vault reference, never plaintext; value omitted.")
        reference = _object(_json(audit.get("value")))
        vault_endpoint = _endpoint(_config_value(run, config_endpoint, "KEY_VAULT_URI"), ".vault.azure.net")
        if environment.get("KEY_VAULT_URI") and _endpoint(environment["KEY_VAULT_URI"], ".vault.azure.net") != vault_endpoint:
            raise AccessError("Configured vault binding conflicts with the deployment environment.")
        uri = _endpoint(reference.get("uri"), ".vault.azure.net", r"/secrets/[A-Za-z0-9-]{1,127}(?:/[A-Za-z0-9-]{1,127})?")
        if urlsplit(uri).hostname != urlsplit(vault_endpoint).hostname:
            raise AccessError("Audit reference points outside the configured vault.")
        vault_name = urlsplit(vault_endpoint).hostname.split(".")[0]
        vault_id = prefix + f"Microsoft.KeyVault/vaults/{vault_name}"
        vault = _object(run(["keyvault", "show", "--name", vault_name, "--resource-group", group, "--subscription", sub]))
        properties = _object(vault.get("properties"))
        if not _same(vault.get("id"), vault_id) or _endpoint(properties.get("vaultUri"), ".vault.azure.net") != vault_endpoint or properties.get("enableRbacAuthorization") is not True:
            raise AccessError("Audit vault ARM endpoint/scope or RBAC authorization mismatch.")
        grants.append(Grant(Role.SECRET, f"{vault_id}/secrets/{urlsplit(uri).path.split('/')[2]}"))
    plan = AccessPlan(sub, group, principal, name, version, tuple(grants), "configured" if audit else "not-configured")
    plan.validate()
    return plan


def _has_exact(run: RunAzure, plan: AccessPlan, grant: Grant) -> bool:
    rows = run([
        "role", "assignment", "list", "--assignee-object-id", plan.principal_id,
        "--scope", grant.scope, "--subscription", plan.subscription,
        "--fill-principal-name", "false", "--fill-role-definition-name", "false",
    ])
    if not isinstance(rows, list):
        raise AccessError("Invalid role-assignment metadata.")
    role_id = f"/subscriptions/{plan.subscription}/providers/Microsoft.Authorization/roleDefinitions/{grant.role.value}"
    exact = False
    for raw in rows:
        row = _object(raw)
        if not (_same(row.get("scope"), grant.scope) and _same(row.get("principalId"), plan.principal_id) and _same(row.get("roleDefinitionId"), role_id)):
            continue  # Inherited/broad/different grants never satisfy this plan.
        if row.get("condition") or row.get("conditionVersion") or row.get("principalType") != "ServicePrincipal":
            raise AccessError("Conflicting conditional/non-service-principal assignment; review manually. No assignment was replaced.")
        exact = True
    return exact


def inspect_assignments(plan: AccessPlan, *, run: RunAzure = run_az) -> tuple[bool, ...]:
    """Read-only proof of exact unconditional grants, in plan order.

    ARM visibility is not a data-plane permission/readiness probe. Conditional
    conflicts fail closed; broad or different assignments are not proof.
    """
    plan.validate()
    return tuple(_has_exact(run, plan, grant) for grant in plan.grants)


def apply(plan: AccessPlan, *, run: RunAzure = run_az, sleep: Callable[[float], None] = time.sleep) -> tuple[str, ...]:
    # Preflight every existing grant before the first write.
    existing = inspect_assignments(plan, run=run)
    completed: list[str] = []
    for grant, present in zip(plan.grants, existing):
        try:
            if not present:
                for attempt in range(3):
                    try:
                        run([
                            "role", "assignment", "create", "--name", grant.assignment_name(plan.principal_id),
                            "--assignee-object-id", plan.principal_id,
                            "--assignee-principal-type", "ServicePrincipal",
                            "--role", grant.role.value, "--scope", grant.scope,
                            "--subscription", plan.subscription,
                        ])
                        break
                    except AzureCommandError as exc:
                        if exc.code == "RoleAssignmentExists":
                            break  # Verify exact binding, not merely the error code.
                        if exc.code != "PrincipalNotFound" or attempt == 2:
                            raise
                        sleep(2 * (attempt + 1))
                for attempt in range(3):
                    if _has_exact(run, plan, grant):
                        break
                    if attempt == 2:
                        raise AccessError("Created/racing assignment is not yet exactly visible in ARM.")
                    sleep(2 * (attempt + 1))
            completed.append(grant.role.name)
        except AccessError as exc:
            raise AccessError(
                f"Bootstrap incomplete: {len(completed)}/{len(plan.grants)} grants verified; "
                f"failed dependency {grant.role.name}. Earlier writes are retained; "
                f"the failed write may also exist. No cutover is authorized. {exc} "
                "Rerun --plan and --apply; never remove other assignments to recover."
            ) from None
    return tuple(completed)


def load_azd_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Read selected child environment as JSON, never source/eval its values."""
    command = [shutil.which("azd") or "azd", "env", "get-values", "--output", "json", "--no-prompt"]
    selected = environment.get("AZURE_ENV_NAME")
    if selected:
        command += ["--environment", selected]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        raise AccessError("Cannot read the selected child azd environment.") from None
    if result.returncode:
        raise AccessError("Cannot read the selected child azd environment; bootstrap was not run.")
    values = _object(_json(result.stdout))
    if any(not isinstance(k, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) or not isinstance(v, str) for k, v in values.items()):
        raise AccessError("Invalid azd environment JSON contract.")
    if selected and values.get("AZURE_ENV_NAME") != selected:
        raise AccessError("Child azd environment selection mismatch.")
    return values


def main(argv: list[str] | None = None, *, environment: Mapping[str, str] | None = None, run: RunAzure = run_az) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="Read-only discovery and exact existing-assignment verification (default).")
    mode.add_argument("--apply", action="store_true", help="Explicitly create only the planned scoped assignments.")
    parser.add_argument("--azd-env", action="store_true", help="Load selected azd environment in the current child project; JSON only.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        env = os.environ if environment is None else environment
        if args.azd_env:
            env = load_azd_environment(env)
        plan = discover(env, run=run)
        if args.apply:
            apply(plan, run=run)
            verified = tuple(True for _ in plan.grants)
            if not plan.classic:
                logging.warning(PROPAGATION)
        else:
            verified = inspect_assignments(plan, run=run)
        result = asdict(plan)
        result["grants"] = [
            {**asdict(grant), "exact_unconditional_assignment": exists}
            for grant, exists in zip(plan.grants, verified)
        ]
        result["data_plane_readiness"] = "not-tested"
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 0
    except (AccessError, ValueError) as exc:
        # Topology errors can contain operator values: do not emit those.
        logging.error("%s", exc if isinstance(exc, AccessError) else "Invalid deployment topology; review the selected environment.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
