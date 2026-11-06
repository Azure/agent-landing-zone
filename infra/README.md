# Agent Landing Zone infrastructure

This directory contains the Bicep and Terraform implementations of the
Agent Landing Zone infrastructure.

```text
infra/
  bicep/       Bicep templates and modules
  terraform/   Terraform configuration and tests
  shared/      Naming and role catalogs used by both implementations
  tests/       Infrastructure checks and test fixtures
  LICENSE      License for the incorporated foundation
```

Run `azd` commands from the [repository root](../README.md). Configure your
deployment in [`main.parameters.json`](../main.parameters.json).
[`manifest.json`](../manifest.json) lists the component versions and the
upstream foundation version used by this repository.

Deployment hooks are in [`scripts/`](../scripts/), with infrastructure helpers
in [`scripts/infra/`](../scripts/infra/).

See the [deployment documentation](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/)
to get started. For development details, see the [Terraform README](terraform/README.md),
[infrastructure tests](tests/README.md) and
[directory layout decision](../docs/adr/ADR-0032-infrastructure-source-layout.md).

## PostgreSQL provider output difference

Bicep preserves its original **64 native outputs**, without disabling the ARM
output-budget check or retiring legacy fields. Terraform retains the additive
`POSTGRESQL_SERVER_RESOURCE_ID`, `POSTGRESQL_HOST`, `POSTGRESQL_PORT`,
`POSTGRESQL_DATABASE_NAME` and `CONTAINER_APPS_POSTGRESQL_EGRESS_IP` outputs.
The common **verified postProvision adapter is authoritative for both
providers**: it materializes these five azd environment keys from the immutable
preflight binding and verified live resources before discovery is published.
They are not additions to the closed platform-outputs v1 object.

The binding must carry the exact resolved `postgreSqlServerName` supplied to
IaC. Native empty-name defaults use the shared `psql-` prefix with the legacy
resource token or trimmed CAF stem; explicit names win. Existing Bicep outputs
`SUBSCRIPTION_ID`, `AZURE_APP_RESOURCE_GROUP`, `AZURE_NETWORK_RESOURCE_GROUP`,
`VNET_RESOURCE_ID` and `RESOURCE_TOKEN` remain available for verification.
Basic egress is discovered through the bound ACA subnet's NAT association,
then its single Standard static IPv4 public IP—not the ACA ingress IP.
Isolated egress is empty. Bicep tags the NAT public IP; Terraform tags both
gateway and public IP, so ownership verification must account for that detail.

This implementation difference is covered by the compiled PostgreSQL contract,
`tests/test_terraform_interface.py`, infrastructure interface tests and
Terraform mock plans. These checks are offline evidence, not deployed parity;
product operations and adapter behavior are documented in the central site.
