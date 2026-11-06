"""Counterpart wiring/pins complement compiled Bicep and Terraform mock plans."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_native_postgresql_seed_contract():
    aliases = {
        "deployPostgreSql": "${DEPLOY_POSTGRESQL=false}",
        "postgreSqlServerName": "${POSTGRESQL_SERVER_NAME=}",
        "postgreSqlDatabaseName": "${POSTGRESQL_DATABASE_NAME=agentlz}",
        "postgreSqlVersion": "${POSTGRESQL_VERSION=16}",
        "postgreSqlTier": "${POSTGRESQL_TIER=Burstable}",
        "postgreSqlSkuName": "${POSTGRESQL_SKU_NAME=Standard_B1ms}",
        "postgreSqlStorageSizeGb": "${POSTGRESQL_STORAGE_SIZE_GB=32}",
        "postgreSqlBackupRetentionDays": "${POSTGRESQL_BACKUP_RETENTION_DAYS=7}",
        "postgreSqlHighAvailability": "${POSTGRESQL_HIGH_AVAILABILITY=Disabled}",
        "postgreSqlGeoRedundantBackup": "${POSTGRESQL_GEO_REDUNDANT_BACKUP=false}",
        "postgreSqlStorageAutoGrow": "${POSTGRESQL_STORAGE_AUTO_GROW=false}",
        "postgreSqlAdministratorObjectId": "${POSTGRESQL_ADMINISTRATOR_OBJECT_ID=}",
        "postgreSqlAdministratorPrincipalName": "${POSTGRESQL_ADMINISTRATOR_PRINCIPAL_NAME=}",
        "postgreSqlAdministratorPrincipalType": "${POSTGRESQL_ADMINISTRATOR_PRINCIPAL_TYPE=}",
        "postgreSqlAllowedIpRanges": [],
        "existingPrivateDnsZonePostgreSqlResourceId": "",
    }
    for path in (ROOT / "main.parameters.json", ROOT / "infra/bicep/main.parameters.json"):
        parameters = json.loads(path.read_text())["parameters"]
        assert {key: parameters[key]["value"] for key in aliases} == aliases


def test_pinned_avm_has_explicit_safe_wiring():
    source = (ROOT / "infra/terraform/main.postgresql.tf").read_text()
    module = source.split('module "postgresql" {', 1)[1]
    assert re.search(r'version\s*=\s*"0\.2\.3"', module)
    assert re.search(r"lock\s*=\s*null", module)
    assert not re.search(r"^\s*(administrator_login|administrator_password(?:_wo)?)\s*=", module, re.M)
    for field in (
        "server_version", "sku_name", "storage_mb", "backup_retention_days",
        "high_availability", "geo_redundant_backup_enabled", "auto_grow_enabled",
        "authentication", "ad_administrator", "public_network_access_enabled",
    ):
        assert re.search(rf"{field}\s*=\s*local\.postgresql_settings\.{field}", module)
    assert re.search(r"firewall_rules\s*=\s*local\.postgresql_firewall_rules", module)
    assert "delegated_subnet_id" not in module
    assert "private_dns_zone_id" not in module
    bicep = (ROOT / "infra/bicep/main.bicep").read_text()
    assert "br/public:avm/res/db-for-postgre-sql/flexible-server:0.16.1" in bicep


def test_nat_is_dedicated_and_explicit_ipv4():
    source = (ROOT / "infra/terraform/main.networking.tf").read_text()
    module = source.split('module "container_apps_postgresql_nat" {', 1)[1].split('module "network_public_ip"', 1)[0]
    for field, value in (("sku_name", "Standard"), ("sku", "Standard"), ("ip_version", "IPv4"), ("allocation_method", "Static")):
        assert re.search(rf'{field}\s*=\s*"{value}"', module)
    assert "aca-postgresql-" in module
    assert re.search(r"count\s*=\s*local\.postgresql_basic", module)


def test_terraform_upload_excludes_private_artifacts_but_keeps_source(tmp_path):
    """Use Git's actual ignore matcher, which .terraformignore follows."""
    ignore = ROOT / "infra/terraform/.terraformignore"
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    private = [
        ".terraform/providers/provider.exe", "nested/.terraform/modules/main.tf",
        "terraform.tfstate", "terraform.tfstate.backup", "nested/terraform.tfstate",
        "foundation.tfplan", "nested/plan.out", "test.plan.json",
        "terraform.tfvars", "environment.auto.tfvars.json", ".env", ".env.local",
        "nested/.env.production", ".azure/credentials.json", ".azd/state.json",
        "private/binding.json", "cert.pem", "cert.pfx", "private.key",
        "credentials.tfrc.json", ".terraformrc",
    ]
    required = [
        ".terraform.lock.hcl", ".terraformignore", "main.tf", "variables.postgresql.tf",
        "outputs.tf", "tests/postgresql.tftest.hcl", "shared/abbreviations.json",
        "shared/role-definitions.json",
    ]
    result = subprocess.run(
        ["git", "-c", f"core.excludesFile={ignore.as_posix()}",
         "check-ignore", "--no-index", "-z", "--stdin"],
        cwd=tmp_path, input=("\0".join(private + required) + "\0").encode(),
        capture_output=True, check=True,
    )
    assert set(result.stdout.decode().rstrip("\0").split("\0")) == set(private)
    assert "!.terraform.lock.hcl" in ignore.read_text()
