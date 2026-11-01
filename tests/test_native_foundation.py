"""Native foundation provider contracts. Static/compiled evidence, not Azure parity."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def compiled():
    executable = shutil.which("bicep")
    if not executable:
        pytest.skip("Bicep compiler not installed")
    result = subprocess.run([executable, "build", str(ROOT / "infra/bicep/main.bicep"), "--stdout"],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_real_scheduler_hub_outputs_and_network_gates_in_compiled_foundation(compiled):
    modules = compiled["resources"]
    assert isinstance(modules, dict), "Repository Bicep symbolic-name compilation must stay enabled"
    module = modules["durableTask"]
    assert module["condition"] == "[parameters('deployDurableTaskScheduler')]"
    template = module["properties"]["template"]
    scheduler, hub = template["resources"]
    assert scheduler["type"] == "Microsoft.DurableTask/schedulers"
    assert hub["type"] == "Microsoft.DurableTask/schedulers/taskHubs"
    assert scheduler["apiVersion"] == hub["apiVersion"] == "2026-02-01"
    assert scheduler["properties"]["publicNetworkAccess"] == "[if(parameters('networkIsolation'), 'Disabled', 'Enabled')]"
    assert "endpoint" in template["outputs"]["backend"]["value"]
    assert "reference(" in template["outputs"]["backend"]["value"]["endpoint"]
    roles = json.dumps(modules["durableTaskRoles"])
    assert "taskHubResourceId" in roles
    assert "DurableTaskDataContributor" in roles
    assert "0ad04412-c4d5-4796-b79c-f76d14c8d402" in json.dumps(compiled["variables"])
    assert "durableTask" in compiled["outputs"]["HOSTED_AGENT_DEPLOYMENT"]["value"]


def test_terraform_real_scheduler_hub_mi_and_ingress_counterpart():
    text = (ROOT / "infra/terraform/main.durable.tf").read_text()
    assert 'Microsoft.DurableTask/schedulers@2026-02-01' in text
    assert 'Microsoft.DurableTask/schedulers/taskHubs@2026-02-01' in text
    assert "output.properties.endpoint" in text
    assert "scope                            = azapi_resource.durable_hub[0].id" in text
    assert "DurableTaskDataContributor.guid" in text
    assert 'publicNetworkAccess = var.networkIsolation ? "Disabled" : "Enabled"' in text
    assert 'durableTask = local.durable_backend' in (ROOT / "infra/terraform/outputs.tf").read_text()
    assert "disableIngress: app.?disable_ingress ?? false" in (ROOT / "infra/bicep/main.bicep").read_text()
    assert 'for_each = try(each.value.disable_ingress, false) ? [] : [each.value]' in (
        ROOT / "infra/terraform/main.compute.tf"
    ).read_text()
    assert "disable_ingress = optional(bool, false)" in (ROOT / "infra/terraform/variables.tf").read_text()


def test_private_scheduler_contract_both_providers_and_no_new_execution_store():
    bicep = (ROOT / "infra/bicep/main.bicep").read_text()
    terraform = (ROOT / "infra/terraform/main.networking.tf").read_text()
    for text in (bicep, terraform):
        assert "privatelink.durabletask.io" in text
        assert "existingPrivateDnsZoneDurableTaskResourceId" in text
        assert "durableTaskConnection" in text
        assert "'scheduler'" in text or '["scheduler"]' in text
    module = (ROOT / "infra/bicep/modules/application/durable-task.bicep").read_text()
    assert "Microsoft.Web/sites" not in module and "Microsoft.Cache" not in module
    assert "Microsoft.DocumentDB" not in module
