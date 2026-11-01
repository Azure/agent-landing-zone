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
