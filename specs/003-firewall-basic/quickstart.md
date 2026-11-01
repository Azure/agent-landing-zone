# Validation guide for new deployments

This guide describes implementation acceptance. Release evidence records the
checks actually completed. Run from the repository root unless `-chdir` is supplied.

## Prerequisites

Use the project's Python/pytest dependencies, PowerShell 7, Bicep with restored
modules, and Terraform 1.13 with the committed provider lock. Follow CI setup.
Reviewing the plan requires no dependency installation or Azure access.

## Focused checks after implementation

```powershell
python -m pytest tests\test_firewall_dns_proxy.py tests\test_private_build_egress.py tests\test_component_egress.py tests\test_component_egress_hooks.py tests\test_terraform_interface.py tests\test_topology_cli.py tests\test_infra_provider_hooks.py -q

pwsh -NoProfile -File .\infra\tests\scripts\Invoke-PreflightChecks.Tests.ps1
pwsh -NoProfile -File .\infra\tests\contracts\Test-SubnetLayoutContract.ps1

terraform -chdir=infra\terraform fmt -check -recursive
terraform -chdir=infra\terraform init -backend=false -lockfile=readonly
terraform -chdir=infra\terraform validate
terraform -chdir=infra\terraform test -filter='tests\networking.tftest.hcl'
```

Include new focused selection/Basic contract tests when their filenames exist.
Verify Terraform actually discovers cases rather than reporting zero tests.

## Affected infrastructure gates

```powershell
az bicep build --file .\infra\main.bicep --outfile "$env:TEMP\agent-lz-firewall-plan-main.json"
az bicep lint --file .\infra\main.bicep
pwsh -NoProfile -File .\infra\tests\Invoke-OfflineContracts.ps1
terraform -chdir=infra\terraform test
```

Exercise both hook variants and provider transports using Linux/Windows CI.
Clean up only the specific temporary compiler output after use.

## Scenario assertions

| New deployment/scenario | Required evidence |
| --- | --- |
| Standalone Basic default | Matching policy, data/management IP configs and required subnets |
| Explicit Standard | Data-plane topology, optional proxy, no management dependencies |
| External hub with/without gateway | No unintended local firewall subnets/IPs; no hub policy/subnet writes |
| Explicit data/gateway reservation | Requested subnet only; no implicit service deployment |
| GatewaySubnet omitted | No reservation, including standalone |
| Public/non-isolated | None of the scoped network resources |
| Auto versus explicit creation | Default only for auto; true/false honored; required BYO validated |
| Invalid Basic/proxy or subnet | Blocking, actionable failure before writes |
| BYO | Correct association; no implicit ownership/deletion |
| Repeat provision | Stable selection, resources and scoped rule ownership |
| Address layout | No overlap or moved workload range; management only for active Basic |

## Authorized Azure acceptance

Do not provision as part of planning. After separate approval, create disposable
environments for each provider using the central runbooks and record evidence
privately. Review resource ownership before proceeding.

Check management routing, policy updates, diagnostics, repeat provision and
provider-owned teardown. Exercise managed identity/Entra, ACR pool bootstrap,
image/package downloads, selected hosted/Container App workloads, cold tokenizer
downloads, retrieval and selected ingestion/media.

For a local VPN Gateway, explicitly set `DEPLOY_GATEWAY_SUBNET=true` before
provision. A shared hub gateway needs no local reservation. Use the runbook's
forwarder/Private Resolver DNS path.

Verify real allowed requests and a controlled unapproved destination, with
firewall logs, from the intended source subnets. A TCP handshake alone is not
acceptance. Assess peak throughput and SNAT pressure; report missing scenarios.
Do not claim deployed parity from compilation, mocks or plan previews.
