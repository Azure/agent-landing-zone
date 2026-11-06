"""Optional PostgreSQL typed inputs and independent data-protection lifecycle.

No SQL is executed here. The non-secret creation intent is a recovery boundary,
not permission to adopt an existing server. Both foundation providers consume
the resolved server name; neither owns the protection lock.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Callable, Mapping
from uuid import UUID

from config import find_repo_root
from config.appdefinition.binding import env_file_path, resolve_env_name
from config.appdefinition.errors import EnvironmentNotFoundError
from config.deployment.app_settings import substitute_values
from config.deployment.resource_groups import ResourceGroupError, _run_azd, resource_group_for
from util.azure_cli import resolve_az_command

LOGGER = logging.getLogger(__name__)
LOCK_NAME = "agentlz-postgresql-data-protection"
FILENAME = "postgresql-binding.json"
SERVER_TYPE = "Microsoft.DBforPostgreSQL/flexibleServers"
SERVER_PATH = re.compile(
    r"^/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/"
    r"Microsoft\.DBforPostgreSQL/flexibleServers/([a-z0-9][a-z0-9-]{1,61}[a-z0-9])$", re.I,
)
DEFAULTS: dict[str, object] = {
    "deployPostgreSql": False, "postgreSqlServerName": "", "postgreSqlDatabaseName": "agentlz",
    "postgreSqlVersion": "16", "postgreSqlTier": "Burstable", "postgreSqlSkuName": "Standard_B1ms",
    "postgreSqlStorageSizeGb": 32, "postgreSqlBackupRetentionDays": 7,
    "postgreSqlHighAvailability": "Disabled", "postgreSqlGeoRedundantBackup": False,
    "postgreSqlStorageAutoGrow": False, "postgreSqlAdministratorObjectId": "",
    "postgreSqlAdministratorPrincipalName": "", "postgreSqlAdministratorPrincipalType": "",
    "postgreSqlAllowedIpRanges": [], "existingPrivateDnsZonePostgreSqlResourceId": "",
}
ENVIRONMENT_KEYS = {
    "deployPostgreSql": "DEPLOY_POSTGRESQL",
    **{name: "POSTGRESQL_" + re.sub(r"(?<!^)(?=[A-Z])", "_", name[len("postgreSql"):]).upper()
       for name in DEFAULTS if name.startswith("postgreSql") and name != "postgreSqlAllowedIpRanges"},
}
# CamelCase acronym splitting above intentionally overridden for the public contract.
ENVIRONMENT_KEYS["postgreSqlAdministratorObjectId"] = "POSTGRESQL_ADMINISTRATOR_OBJECT_ID"


def boolean(value: object, name: str) -> bool:
    if type(value) is bool:
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ValueError(f"{name} must be true or false.")


def guid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} requires a GUID.")
    try:
        parsed = UUID(value)
    except ValueError:
        raise ValueError(f"{name} requires a GUID.") from None
    if str(parsed) != value.lower() or parsed.int == 0:
        raise ValueError(f"{name} requires a nonzero canonical GUID.")
    return str(parsed)


def firewall_ranges(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("postgreSqlAllowedIpRanges requires an IPv4/CIDR array.")
    result = []
    for item in value:
        try:
            network = ipaddress.ip_network(item, strict=False)
        except ValueError:
            raise ValueError("Invalid explicit IPv4 firewall range.") from None
        if network.version != 4:
            raise ValueError("Firewall rules require IPv4.")
        if network.prefixlen == 0 or network.network_address == ipaddress.IPv4Address("0.0.0.0"):
            raise ValueError("Broad or Azure-services firewall range is prohibited.")
        result.append((str(network.network_address), str(network.broadcast_address)))
    if len(result) != len(set(result)):
        raise ValueError("Duplicate firewall range.")
    return result


def resolve_inputs(source: Mapping[str, object], env: Mapping[str, str]) -> dict[str, object]:
    """Resolve whole-value source placeholders once and explicit env overrides."""
    values = substitute_values({name: source[name] for name in DEFAULTS if name in source}, env)
    result = {**copy.deepcopy(DEFAULTS), **values}
    for name, key in ENVIRONMENT_KEYS.items():
        if key in env:
            result[name] = env[key]
    for name in ("deployPostgreSql", "postgreSqlGeoRedundantBackup", "postgreSqlStorageAutoGrow"):
        result[name] = boolean(result[name], name)
    for name in ("postgreSqlStorageSizeGb", "postgreSqlBackupRetentionDays"):
        value = result[name]
        if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
            value = int(value)
        if type(value) is not int:
            raise ValueError(f"{name} requires an integer.")
        result[name] = value
    for name, value in result.items():
        if isinstance(DEFAULTS[name], str) and not isinstance(value, str):
            raise ValueError(f"{name} requires a string.")
    firewall_ranges(result["postgreSqlAllowedIpRanges"])
    if result["postgreSqlVersion"] not in {"13", "14", "15", "16", "17", "18"}:
        raise ValueError("Unsupported PostgreSQL version.")
    tier, sku = result["postgreSqlTier"], result["postgreSqlSkuName"]
    sku_patterns = {
        "Burstable": r"Standard_B(?:1ms|2s|2ms|4ms|8ms|12ms|16ms|20ms)",
        "GeneralPurpose": r"Standard_D[0-9]+(?:d)?s_v[3456]",
        "MemoryOptimized": r"Standard_E[0-9]+(?:d)?s_v[3456]",
    }
    if tier not in sku_patterns or not re.fullmatch(sku_patterns[tier], sku):
        raise ValueError("PostgreSQL tier/SKU mismatch; no automatic downgrade.")
    ha = result["postgreSqlHighAvailability"]
    if ha not in {"Disabled", "SameZone", "ZoneRedundant"} or (tier == "Burstable" and ha != "Disabled"):
        raise ValueError("Invalid HA selection; Burstable requires Disabled.")
    storage = result["postgreSqlStorageSizeGb"]
    if not 32 <= storage <= 65536 or storage & (storage - 1):
        raise ValueError("PostgreSQL storage must be a power of two from 32 to 65536 GiB.")
    if not 7 <= result["postgreSqlBackupRetentionDays"] <= 35:
        raise ValueError("PostgreSQL backup retention must be 7..35 days.")
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_-]{0,62}", result["postgreSqlDatabaseName"]) or result["postgreSqlDatabaseName"].lower() in {"postgres", "template0", "template1", "azure_maintenance", "azure_sys"}:
        raise ValueError("Invalid application database name.")
    if result["postgreSqlServerName"] and not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", result["postgreSqlServerName"]):
        raise ValueError("Invalid PostgreSQL server name.")
    if result["deployPostgreSql"]:
        result["postgreSqlAdministratorObjectId"] = guid(result["postgreSqlAdministratorObjectId"], "Administrator object ID")
        if not result["postgreSqlAdministratorPrincipalName"].strip() or result["postgreSqlAdministratorPrincipalType"] not in {"User", "Group", "ServicePrincipal"}:
            raise ValueError("Administrator principal name and type are required.")
        context = substitute_values(dict(source), env)
        isolated = boolean(context.get("networkIsolation", env.get("NETWORK_ISOLATION", "false")), "networkIsolation")
        if not isolated and not boolean(context.get("deployContainerEnv", True), "deployContainerEnv"):
            raise ValueError("PostgreSQL requires Container Apps workload-profiles environment.")
        if not result["postgreSqlServerName"] and env.get("AZURE_SUBSCRIPTION_ID") and env.get("AZURE_ENV_NAME"):
            seed = json.dumps([env["AZURE_SUBSCRIPTION_ID"].lower(), env["AZURE_ENV_NAME"], env.get("AZURE_LOCATION", context.get("location", ""))], separators=(",", ":"))
            catalog = json.loads((find_repo_root() / "infra" / "shared" / "abbreviations.json").read_text(encoding="utf-8"))
            databases = catalog.get("databases") if isinstance(catalog, dict) else None
            prefix = databases.get("postgreSQLDatabase") if isinstance(databases, dict) else None
            if not isinstance(prefix, str) or len(prefix) > 43 or not re.fullmatch(r"[a-z][a-z0-9-]*-", prefix):
                raise ValueError("Invalid PostgreSQL abbreviation in the shared naming catalog.")
            result["postgreSqlServerName"] = prefix + hashlib.sha256(seed.encode()).hexdigest()[:20]
    return result


def _run_az(args: list[str], *, required: bool = True) -> str:
    completed = subprocess.run([resolve_az_command(), *args, "--only-show-errors"],
                               capture_output=True, text=True, timeout=120, check=False)
    if completed.returncode:
        # Never echo CLI payloads: an injected boundary may contain credentials.
        raise RuntimeError("PostgreSQL Azure verification failed; check permissions and resource context.")
    return completed.stdout


def binding_path(azure_dir: Path, env: Mapping[str, str]) -> Path:
    return env_file_path(azure_dir, resolve_env_name(azure_dir, env)).parent / FILENAME


def _local_outputs(path: Path) -> bool:
    """Retained .env outputs cannot disappear through a caller's scope filter."""
    env_file = path.parent / ".env"
    if not env_file.exists():
        return False
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        match = re.fullmatch(r'\s*(?:export\s+)?(POSTGRESQL_SERVER_RESOURCE_ID|POSTGRESQL_HOST)\s*=\s*(.*?)\s*', line)
        if match and match[2].strip("\"' "):
            return True
    return False


def _fingerprint(binding: dict) -> str:
    return hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        binding = record["binding"]
        if (set(record) != {"schemaVersion", "binding", "fingerprint", "ready"}
            or type(record["schemaVersion"]) is not int or record["schemaVersion"] != 1 or type(record["ready"]) is not bool
            or not isinstance(binding, dict) or record["fingerprint"] != _fingerprint(binding)
            or set(binding) != {"server", "subscription", "group", "database", "isolated", "provider",
                                "adminOid", "adminName", "adminType", "tenant", "environment", "network"}):
            raise ValueError
        if not SERVER_PATH.fullmatch(binding["server"]) or binding["provider"] not in {"bicep", "terraform"}:
            raise ValueError
        if (type(binding["isolated"]) is not bool or not isinstance(binding["network"], dict)
            or any(not isinstance(binding[key], str) or not binding[key] for key in
                   ("server", "subscription", "group", "database", "provider", "adminOid",
                    "adminName", "adminType", "tenant", "environment"))
            or binding["adminType"] not in {"User", "Group", "ServicePrincipal"}):
            raise ValueError
        match = SERVER_PATH.fullmatch(binding["server"])
        if match[1].lower() != guid(binding["subscription"], "subscription") or match[2].lower() != binding["group"].lower():
            raise ValueError
        guid(binding["tenant"], "tenant")
        guid(binding["adminOid"], "Administrator")
    except (ValueError, KeyError, TypeError):
        raise ValueError("Corrupt PostgreSQL binding; restore the original record for explicit recovery.") from None
    return record


def _write(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".postgresql-", text=True)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _json(run_az: Callable, args: list[str]) -> object:
    return json.loads(run_az([*args, "--output", "json"]))


def verify_account(run_az: Callable, subscription: str, tenant: str | None = None) -> str:
    account = _json(run_az, ["account", "show", "--subscription", subscription])
    if not isinstance(account, dict) or str(account.get("id", "")).lower() != subscription:
        raise ValueError("PostgreSQL subscription/tenant mismatch.")
    resolved = guid(account.get("tenantId"), "subscription tenant")
    if tenant is not None and guid(tenant, "tenant") != resolved:
        raise ValueError("PostgreSQL subscription/tenant mismatch.")
    return resolved


def verify_principal(run_az: Callable, oid: str, kind: str, name: str | None = None) -> dict:
    oid = guid(oid, "directory principal object ID")
    noun = {"User": "user", "Group": "group", "ServicePrincipal": "sp"}[kind]
    row = _json(run_az, ["ad", noun, "show", "--id", oid])
    if not isinstance(row, dict) or str(row.get("id", "")).lower() != oid:
        raise ValueError("Administrator/directory principal identity mismatch.")
    if name is not None and name not in {row.get("displayName"), row.get("userPrincipalName"), row.get("appId")}:
        raise ValueError("Administrator principal name mismatch.")
    return row


def _server(run_az: Callable, binding: dict, env: Mapping[str, str], *, complete: bool = True) -> dict:
    if (str(env.get("AZURE_SUBSCRIPTION_ID", "")).lower() != binding["subscription"]
        or any(str(env[key]).lower() != binding["tenant"]
               for key in ("AZURE_TENANT_ID", "TENANT_ID") if env.get(key))
        or resource_group_for(env, "application").lower() != binding["group"].lower()
        or env.get("AZURE_ENV_NAME") != binding["environment"]
        or boolean(env.get("NETWORK_ISOLATION", str(binding["isolated"]).lower()), "NETWORK_ISOLATION") != binding["isolated"]
        or ("DEPLOY_POSTGRESQL" in env and not boolean(env["DEPLOY_POSTGRESQL"], "DEPLOY_POSTGRESQL"))):
        raise ValueError("PostgreSQL environment binding mismatch.")
    # The immutable intent replaces additional Bicep outputs (ARM's limit is 64).
    # Missing transport fields are derived, but explicit conflicting fields fail.
    server_id = env.get("POSTGRESQL_SERVER_RESOURCE_ID", binding["server"])
    if server_id.lower() != binding["server"].lower():
        raise ValueError("PostgreSQL server binding mismatch.")
    verify_account(run_az, binding["subscription"], binding["tenant"])
    server = _json(run_az, ["resource", "show", "--ids", server_id])
    if not isinstance(server, dict) or str(server.get("id", "")).lower() != server_id.lower():
        raise ValueError("PostgreSQL resource binding mismatch.")
    properties = server.get("properties") or {}
    if complete and properties.get("state") != "Ready":
        raise ValueError("PostgreSQL server is not Ready; protection/publication remains incomplete.")
    auth = properties.get("authConfig") or {}
    if auth.get("activeDirectoryAuth") != "Enabled" or auth.get("passwordAuth") != "Disabled" or str(auth.get("tenantId", "")).lower() != binding["tenant"]:
        raise ValueError("PostgreSQL must use verified Entra-only authentication.")
    host = binding["server"].rsplit("/", 1)[-1].lower() + ".postgres.database.azure.com"
    if properties.get("fullyQualifiedDomainName", "").lower() != host or env.get("POSTGRESQL_HOST", host).lower() != host:
        raise ValueError("PostgreSQL host binding mismatch.")
    if env.get("POSTGRESQL_DATABASE_NAME", binding["database"]) != binding["database"] or str(env.get("POSTGRESQL_PORT", "5432")) != "5432":
        raise ValueError("PostgreSQL database/port binding mismatch.")
    if (server.get("tags") or {}).get("azd-env-name") != binding["environment"]:
        raise ValueError("PostgreSQL ownership tag mismatch.")
    if (properties.get("network") or {}).get("publicNetworkAccess") != ("Disabled" if binding["isolated"] else "Enabled"):
        raise ValueError("PostgreSQL network binding mismatch.")
    admins = _json(run_az, ["postgres", "flexible-server", "microsoft-entra-admin", "list", "--resource-group",
                           binding["group"], "--server-name", host.split(".")[0], "--subscription", binding["subscription"]])
    if not isinstance(admins, list) or len(admins) > 1 or (complete and not admins):
        raise ValueError("PostgreSQL Administrator mapping mismatch.")
    if admins:
        admin = admins[0].get("properties", admins[0])
        if any(str(admin.get(key, "")).lower() != str(binding[field]).lower()
               for key, field in (("objectId", "adminOid"), ("tenantId", "tenant"), ("principalName", "adminName"), ("principalType", "adminType"))):
            raise ValueError("PostgreSQL Administrator binding mismatch.")
    if complete:
        database = _json(run_az, ["resource", "show", "--ids", server_id + "/databases/" + binding["database"]])
        if not isinstance(database, dict) or str(database.get("id", "")).lower() != (server_id + "/databases/" + binding["database"]).lower():
            raise ValueError("PostgreSQL database resource binding mismatch.")
    return server


def _lock(run_az: Callable, binding: dict) -> None:
    expected = binding["server"] + "/providers/Microsoft.Authorization/locks/" + LOCK_NAME
    lock = _json(run_az, ["lock", "show", "--ids", expected])
    if not isinstance(lock, dict) or str(lock.get("id", "")).lower() != expected.lower() or (lock.get("properties") or {}).get("level", lock.get("level")) != "CanNotDelete":
        raise ValueError("Independent PostgreSQL protection lock verification failed.")


def _settings(binding: dict) -> dict[str, str]:
    return {"AGENTLZ_POSTGRESQL_HOST": binding["server"].rsplit("/", 1)[-1].lower() + ".postgres.database.azure.com",
            "AGENTLZ_POSTGRESQL_PORT": "5432", "AGENTLZ_POSTGRESQL_DATABASE": binding["database"],
            "AGENTLZ_POSTGRESQL_SSLMODE": "verify-full", "AGENTLZ_POSTGRESQL_AUTH_MODE": "entra"}


def _verify_network(context: Mapping[str, object], inputs: dict, isolated: bool, run_az: Callable) -> None:
    zone = inputs["existingPrivateDnsZonePostgreSqlResourceId"]
    if zone:
        if not re.fullmatch(r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.Network/privateDnsZones/privatelink\.postgres\.database\.azure\.com", zone, re.I):
            raise ValueError("Invalid existing PostgreSQL private DNS binding.")
        row = _json(run_az, ["resource", "show", "--ids", zone])
        if not isinstance(row, dict) or str(row.get("id", "")).lower() != zone.lower():
            raise ValueError("Existing PostgreSQL private DNS ownership binding mismatch.")
    if not boolean(context.get("useExistingVNet", False), "useExistingVNet"):
        return
    vnet_id = context.get("existingVnetResourceId")
    if not isinstance(vnet_id, str) or not re.fullmatch(r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.Network/virtualNetworks/[^/]+", vnet_id, re.I):
        raise ValueError("BYO PostgreSQL requires an explicit existing VNet binding.")
    vnet = _json(run_az, ["resource", "show", "--ids", vnet_id])
    if not isinstance(vnet, dict) or str(vnet.get("id", "")).lower() != vnet_id.lower():
        raise ValueError("Existing PostgreSQL VNet binding mismatch.")
    subnets = (vnet.get("properties") or {}).get("subnets", [])
    name_key = "applicationPeSubnetName" if isolated else "acaEnvironmentSubnetName"
    create_key = "deployApplicationPeSubnet" if isolated else "deployAcaEnvironmentSubnet"
    matches = [row for row in subnets if row.get("name") == context.get(name_key)]
    if not matches:
        if not boolean(context.get(create_key, True), create_key):
            raise ValueError("Required existing PostgreSQL subnet binding is missing.")
        return
    if len(matches) != 1:
        raise ValueError("Nonunique PostgreSQL subnet binding.")
    properties = matches[0].get("properties") or {}
    delegations = properties.get("delegations") or []
    if isolated:
        if delegations:
            raise ValueError("PostgreSQL Private Endpoint subnet must not be delegated.")
        return
    if not any((item.get("properties") or {}).get("serviceName") == "Microsoft.App/environments" for item in delegations):
        raise ValueError("Container Apps subnet requires workload-profiles delegation.")
    prefixes = properties.get("addressPrefixes") or [properties.get("addressPrefix", "")]
    if not prefixes or any(ipaddress.ip_network(prefix).version != 4 or ipaddress.ip_network(prefix).prefixlen > 27 for prefix in prefixes):
        raise ValueError("Container Apps subnet requires IPv4 /27 capacity.")
    table_id = (properties.get("routeTable") or {}).get("id")
    if table_id:
        table = _json(run_az, ["resource", "show", "--ids", table_id])
        if not isinstance(table, dict) or str(table.get("id", "")).lower() != table_id.lower():
            raise ValueError("Container Apps route-table binding mismatch.")
        if any((route.get("properties") or {}).get("addressPrefix") == "0.0.0.0/0"
               for route in (table.get("properties") or {}).get("routes", [])):
            raise ValueError("Basic PostgreSQL rejects forced default routes that bypass dedicated NAT.")


def preflight(source: Mapping[str, object], env: Mapping[str, str], azure_dir: Path, provider: str,
              *, run_az: Callable = _run_az) -> None:
    inputs = resolve_inputs(source, env)
    path = binding_path(azure_dir, env)
    record = _read(path)
    if not inputs["deployPostgreSql"]:
        if record or _local_outputs(path) or env.get("POSTGRESQL_SERVER_RESOURCE_ID") or env.get("POSTGRESQL_HOST"):
            raise ValueError("Cannot disable bound PostgreSQL; explicit backup/removal review is required.")
        return
    if record is None and (_local_outputs(path) or env.get("POSTGRESQL_SERVER_RESOURCE_ID") or env.get("POSTGRESQL_HOST")):
        raise ValueError("Missing PostgreSQL creation-intent binding with prior outputs; restore the original record.")
    if provider not in {"bicep", "terraform"}:
        raise ValueError("Unsupported PostgreSQL provider.")
    context = substitute_values(dict(source), env)
    if not isinstance(context.get("deploymentTags", {}), dict) or (
        "azd-env-name" in context.get("deploymentTags", {})
        and context["deploymentTags"]["azd-env-name"] != resolve_env_name(azure_dir, env)
    ):
        raise ValueError("PostgreSQL ownership tag cannot override the selected environment.")
    sub = guid(env.get("AZURE_SUBSCRIPTION_ID"), "subscription")
    if env.get("AZURE_TENANT_ID") and env.get("TENANT_ID") and env["AZURE_TENANT_ID"].lower() != env["TENANT_ID"].lower():
        raise ValueError("PostgreSQL tenant inputs conflict.")
    tenant = verify_account(run_az, sub, env.get("AZURE_TENANT_ID") or env.get("TENANT_ID"))
    group = resource_group_for(env, "application")
    name = inputs["postgreSqlServerName"]
    server = f"/subscriptions/{sub}/resourceGroups/{group}/providers/{SERVER_TYPE}/{name}"
    isolated = boolean(context.get("networkIsolation", env.get("NETWORK_ISOLATION", "false")), "networkIsolation")
    binding = {"server": server, "subscription": sub, "group": group, "database": inputs["postgreSqlDatabaseName"],
               "isolated": isolated, "provider": provider, "tenant": tenant, "environment": resolve_env_name(azure_dir, env),
               "adminOid": inputs["postgreSqlAdministratorObjectId"], "adminName": inputs["postgreSqlAdministratorPrincipalName"],
               "adminType": inputs["postgreSqlAdministratorPrincipalType"],
               "network": {key: context.get(key) for key in (
                   "useExistingVNet", "existingVnetResourceId", "acaEnvironmentSubnetName", "acaEnvironmentSubnetPrefix",
                   "containerEnvName", "applicationPeSubnetName", "policyManagedPrivateDns",
                   "existingPrivateDnsZonePostgreSqlResourceId", "location")}}
    if record and record["binding"] != binding:
        raise ValueError("Immutable PostgreSQL binding changed; replacement is blocked.")
    verify_principal(run_az, binding["adminOid"], binding["adminType"], binding["adminName"])
    if isolated and boolean(context.get("policyManagedPrivateDns", False), "policyManagedPrivateDns") and inputs["existingPrivateDnsZonePostgreSqlResourceId"]:
        raise ValueError("Competing PostgreSQL private DNS ownership modes.")
    if not isolated:
        prefix = context.get("acaEnvironmentSubnetPrefix", "10.0.8.0/24")
        if ipaddress.ip_network(prefix).version != 4 or ipaddress.ip_network(prefix).prefixlen > 27:
            raise ValueError("Container Apps workload-profiles subnet requires IPv4 /27 or larger.")
        if context.get("hubIntegrationEgressNextHopIp") or context.get("hubIntegrationExistingRouteTableResourceId"):
            raise ValueError("Basic PostgreSQL cannot bypass conflicting forced routes.")
    _verify_network(context, inputs, isolated, run_az)
    exists = json.loads(run_az(["group", "exists", "--name", group, "--subscription", sub, "--output", "json"]))
    if type(exists) is not bool:
        raise ValueError("Invalid PostgreSQL resource-group inventory.")
    if not exists and record and record["ready"]:
        raise ValueError("Protected PostgreSQL resource group is missing; explicit recovery required.")
    for kind in (SERVER_TYPE, "Microsoft.App/managedEnvironments"):
        rows = _json(run_az, ["resource", "list", "--resource-group", group, "--subscription", sub, "--resource-type", kind]) if exists else []
        if not isinstance(rows, list):
            raise ValueError("Invalid existing resource inventory.")
        if not record and rows:
            raise ValueError("PostgreSQL requires a fresh environment; existing server/ACA retrofit is blocked.")
        if record and kind == SERVER_TYPE and any(str(row.get("id", "")).lower() != server.lower() for row in rows):
            raise ValueError("Unexpected existing PostgreSQL server ownership.")
        if record and not record["ready"] and kind == SERVER_TYPE and rows:
            expected_env = {**env, "POSTGRESQL_SERVER_RESOURCE_ID": server,
                            "POSTGRESQL_HOST": name.lower() + ".postgres.database.azure.com",
                            "POSTGRESQL_DATABASE_NAME": binding["database"], "POSTGRESQL_PORT": "5432"}
            # Only known creation intent can resume unfinished child resources.
            # Protection/discovery still require complete Ready/admin/db checks.
            _server(run_az, binding, expected_env, complete=False)
        if record and kind == "Microsoft.App/managedEnvironments":
            for row in rows:
                aca_id = str(row.get("id", ""))
                expected_prefix = f"/subscriptions/{sub}/resourceGroups/{group}/providers/Microsoft.App/managedEnvironments/"
                if not aca_id.lower().startswith(expected_prefix.lower()) or "/" in aca_id[len(expected_prefix):]:
                    raise ValueError("Existing Container Apps resource binding mismatch.")
                # Generic ARM inventories omit resource-specific properties.
                aca = _json(run_az, ["resource", "show", "--ids", aca_id])
                if not isinstance(aca, dict) or str(aca.get("id", "")).lower() != aca_id.lower():
                    raise ValueError("Existing Container Apps resource binding mismatch.")
                if (aca.get("tags") or {}).get("azd-env-name") != binding["environment"]:
                    raise ValueError("Existing Container Apps environment ownership mismatch.")
                if context.get("containerEnvName") and aca.get("name") != context["containerEnvName"]:
                    raise ValueError("Existing Container Apps environment name binding mismatch.")
                props = aca.get("properties") or {}
                if not props.get("workloadProfiles") or not (props.get("vnetConfiguration") or {}).get("infrastructureSubnetId"):
                    raise ValueError("Existing Container Apps environment is not a compatible workload-profiles VNet binding.")
                subnet_id = props["vnetConfiguration"]["infrastructureSubnetId"]
                if context.get("acaEnvironmentSubnetName") and not str(subnet_id).lower().endswith("/subnets/" + str(context["acaEnvironmentSubnetName"]).lower()):
                    raise ValueError("Existing Container Apps subnet binding mismatch.")
    if record:
        if record["ready"]:
            _server(run_az, binding, env)
            _lock(run_az, binding)
        return
    _write(path, {"schemaVersion": 1, "binding": binding, "fingerprint": _fingerprint(binding), "ready": False})


def protect(env: Mapping[str, str], azure_dir: Path, *, run_az: Callable = _run_az) -> dict[str, str]:
    path = binding_path(azure_dir, env)
    record = _read(path)
    if not record:
        if env.get("POSTGRESQL_SERVER_RESOURCE_ID") or env.get("POSTGRESQL_HOST") or boolean(env.get("DEPLOY_POSTGRESQL", "false"), "DEPLOY_POSTGRESQL"):
            raise ValueError("Missing PostgreSQL creation-intent binding; explicit recovery required.")
        return {}
    binding = record["binding"]
    # Mark incomplete before attempting protection so failures never publish ready.
    record["ready"] = False
    _write(path, record)
    _server(run_az, binding, env)
    _json(run_az, ["lock", "create", "--name", LOCK_NAME, "--lock-type", "CanNotDelete",
                   "--resource", binding["server"], "--notes", "Independent Agent Landing Zone PostgreSQL data protection"])
    _lock(run_az, binding)
    record["ready"] = True
    _write(path, record)
    return _settings(binding)


def discovery_settings(env: Mapping[str, str], azure_dir: Path, *, run_az: Callable = _run_az) -> dict[str, str]:
    try:
        path = binding_path(azure_dir, env)
    except EnvironmentNotFoundError:
        if env.get("POSTGRESQL_SERVER_RESOURCE_ID") or env.get("POSTGRESQL_HOST") or boolean(env.get("DEPLOY_POSTGRESQL", "false"), "DEPLOY_POSTGRESQL"):
            raise
        return {}
    record = _read(path)
    if not record:
        if env.get("POSTGRESQL_SERVER_RESOURCE_ID") or env.get("POSTGRESQL_HOST") or boolean(env.get("DEPLOY_POSTGRESQL", "false"), "DEPLOY_POSTGRESQL"):
            raise ValueError("Missing PostgreSQL protection binding.")
        return {}
    if not record["ready"]:
        raise ValueError("PostgreSQL protection is incomplete; rerun post-provision protection.")
    _server(run_az, record["binding"], env)
    _lock(run_az, record["binding"])
    return _settings(record["binding"])


def _egress_ip(binding: dict, env: Mapping[str, str], run_az: Callable) -> str:
    if binding["isolated"]:
        return ""
    rows = _json(run_az, ["resource", "list", "--resource-group", binding["group"],
                         "--subscription", binding["subscription"],
                         "--resource-type", "Microsoft.App/managedEnvironments"])
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("PostgreSQL requires one verified Container Apps egress binding.")
    aca_id = str(rows[0].get("id", ""))
    prefix = f"/subscriptions/{binding['subscription']}/resourceGroups/{binding['group']}/providers/Microsoft.App/managedEnvironments/"
    if not aca_id.lower().startswith(prefix.lower()) or "/" in aca_id[len(prefix):] or not aca_id[len(prefix):]:
        raise ValueError("Container Apps egress resource scope mismatch.")
    aca = _json(run_az, ["resource", "show", "--ids", aca_id])
    if (not isinstance(aca, dict) or str(aca.get("id", "")).lower() != aca_id.lower()
        or (aca.get("tags") or {}).get("azd-env-name") != binding["environment"]
        or not (aca.get("properties") or {}).get("workloadProfiles")):
        raise ValueError("Container Apps egress ownership/profile mismatch.")
    subnet_id = ((aca.get("properties") or {}).get("vnetConfiguration") or {}).get("infrastructureSubnetId", "")
    network = binding["network"]
    vnet = network.get("existingVnetResourceId")
    subnet_prefix = (str(vnet) + "/subnets/") if network.get("useExistingVNet") and vnet else (
        f"/subscriptions/{binding['subscription']}/resourceGroups/{resource_group_for(env, 'network')}"
        "/providers/Microsoft.Network/virtualNetworks/")
    if (not isinstance(subnet_id, str) or not subnet_id.lower().startswith(subnet_prefix.lower())
        or not re.fullmatch(r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.Network/virtualNetworks/[^/]+/subnets/[^/]+", subnet_id, re.I)
        or (network.get("acaEnvironmentSubnetName") and not subnet_id.lower().endswith("/subnets/" + str(network["acaEnvironmentSubnetName"]).lower()))):
        raise ValueError("Container Apps egress subnet binding mismatch.")
    subnet = _json(run_az, ["resource", "show", "--ids", subnet_id])
    if not isinstance(subnet, dict) or str(subnet.get("id", "")).lower() != subnet_id.lower():
        raise ValueError("Container Apps egress subnet readback mismatch.")
    nat_id = ((subnet.get("properties") or {}).get("natGateway") or {}).get("id", "")
    network_prefix = f"/subscriptions/{binding['subscription']}/resourceGroups/{resource_group_for(env, 'network')}/providers/Microsoft.Network/"
    if (not isinstance(nat_id, str) or not nat_id.lower().startswith((network_prefix + "natGateways/ng-aca-postgresql-").lower())
        or "/" in nat_id[len(network_prefix + "natGateways/"):]):
        raise ValueError("Container Apps requires its dedicated PostgreSQL NAT, not corporate/jumpbox NAT.")
    nat = _json(run_az, ["resource", "show", "--ids", nat_id])
    if (not isinstance(nat, dict) or str(nat.get("id", "")).lower() != nat_id.lower()
        or (nat.get("sku") or {}).get("name") != "Standard"
        or (nat.get("tags") or {}).get("azd-env-name") != binding["environment"]):
        raise ValueError("PostgreSQL NAT ownership/SKU mismatch.")
    addresses = (nat.get("properties") or {}).get("publicIpAddresses", [])
    if (not isinstance(addresses, list) or len(addresses) != 1 or not isinstance(addresses[0], dict)
        or (nat.get("properties") or {}).get("publicIpPrefixes")):
        raise ValueError("PostgreSQL NAT requires exactly one dedicated public IPv4.")
    address_id = addresses[0].get("id", "")
    if (not isinstance(address_id, str) or not address_id.lower().startswith((network_prefix + "publicIPAddresses/").lower())
        or "/" in address_id[len(network_prefix + "publicIPAddresses/"):]):
        raise ValueError("PostgreSQL NAT public IP scope mismatch.")
    address = _json(run_az, ["resource", "show", "--ids", address_id])
    if (not isinstance(address, dict) or str(address.get("id", "")).lower() != address_id.lower()
        or (address.get("sku") or {}).get("name") != "Standard"
        or (address.get("tags") or {}).get("azd-env-name") != binding["environment"]
        or (address.get("properties") or {}).get("publicIPAllocationMethod") != "Static"):
        raise ValueError("PostgreSQL NAT public IP ownership/SKU/allocation mismatch.")
    value = str((address.get("properties") or {}).get("ipAddress", ""))
    try:
        ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        raise ValueError("PostgreSQL NAT has no assigned IPv4.") from None
    firewall_ranges([value])
    return value


def environment_outputs(env: Mapping[str, str], azure_dir: Path, *,
                        run_az: Callable = _run_az) -> dict[str, str]:
    """Materialize verified azd metadata without consuming ARM output slots."""
    settings = discovery_settings(env, azure_dir, run_az=run_az)
    if not settings:
        return {}
    record = _read(binding_path(azure_dir, env))
    if not record or not record["ready"]:
        raise ValueError("PostgreSQL protection binding changed during metadata verification.")
    binding = record["binding"]
    values = {
        "POSTGRESQL_SERVER_RESOURCE_ID": binding["server"],
        "POSTGRESQL_HOST": settings["AGENTLZ_POSTGRESQL_HOST"],
        "POSTGRESQL_PORT": settings["AGENTLZ_POSTGRESQL_PORT"],
        "POSTGRESQL_DATABASE_NAME": settings["AGENTLZ_POSTGRESQL_DATABASE"],
        "CONTAINER_APPS_POSTGRESQL_EGRESS_IP": _egress_ip(binding, env, run_az),
    }
    if ("CONTAINER_APPS_POSTGRESQL_EGRESS_IP" in env
        and env["CONTAINER_APPS_POSTGRESQL_EGRESS_IP"] != values["CONTAINER_APPS_POSTGRESQL_EGRESS_IP"]):
        raise ValueError("PostgreSQL egress output does not match the verified NAT binding.")
    return values


def persist_outputs(env: Mapping[str, str], azure_dir: Path, values: Mapping[str, str], *,
                    run_azd: Callable = _run_azd) -> None:
    for key, value in values.items():
        try:
            run_azd(azure_dir, ["env", "set", key, value, "--environment",
                               resolve_env_name(azure_dir, env), "--no-prompt"])
        except ResourceGroupError:
            raise RuntimeError("Cannot persist verified PostgreSQL metadata; restore azd access and rerun protection.") from None


def require_safe_teardown(env: Mapping[str, str], azure_dir: Path) -> None:
    path = binding_path(azure_dir, env)
    record = _read(path)
    if record or _local_outputs(path) or env.get("POSTGRESQL_SERVER_RESOURCE_ID") or env.get("POSTGRESQL_HOST") or boolean(env.get("DEPLOY_POSTGRESQL", "false"), "DEPLOY_POSTGRESQL"):
        raise ValueError("PostgreSQL teardown is blocked; review backups, ownership and explicit lock removal.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "protect"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--provider", choices=("bicep", "terraform"))
    parser.add_argument("--azure-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        if args.action == "preflight":
            if not args.input or not args.provider:
                parser.error("preflight requires --input and --provider")
            document = json.loads(args.input.read_text(encoding="utf-8"))
            source = {key: entry["value"] for key, entry in document["parameters"].items()}
            preflight(source, os.environ, args.azure_dir, args.provider)
        else:
            settings = protect(os.environ, args.azure_dir)
            if settings:
                persist_outputs(os.environ, args.azure_dir, environment_outputs(os.environ, args.azure_dir))
    except (ValueError, RuntimeError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
        LOGGER.error("PostgreSQL lifecycle failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
