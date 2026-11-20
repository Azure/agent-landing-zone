# Release validation harness

Maintainer tooling that validates a published release with live Bicep and
Terraform deployments of the standard scenario with `NETWORK_ISOLATION=true`.
It is not part of the shipped product.

## Release policy

A release is published as a pre-release (`gh release create --prerelease`). It
stays a pre-release until `.github/workflows/release-validation.yml` passes the
standard scenario with both Bicep and Terraform. The workflow then attaches the
evidence, amends the release notes and makes the release Latest. "Validated"
means the Latest GitHub release.

## Standard scenario

`scenario.env` holds the `azd` settings of the standard scenario: hosted
orchestrator, conversational mode, `BUILD_MODE=acr-task` with the ACR Tasks
agent pool and `NETWORK_ISOLATION=true`. Every other parameter keeps its
`main.parameters.json` default. Both providers use exactly these settings, so
change the file only through a reviewed pull request.

## How it works

1. The workflow runs manually (`workflow_dispatch`) with:
   - `release_tag`: the tag to validate. Empty means the Latest release.
   - `providers`: `both` (default), `bicep` or `terraform`.
   - `location`, `hosted_agent_resource_scope` and `keep_environment`.
   - `promote` (default `true`): promote the release when both providers pass.
2. The `validate` job runs once per provider, one after the other
   (`max-parallel: 1`). Two spokes would create the same privatelink DNS zone
   names in the hub, and Terraform runs with `-lock=false` under `azd`.
3. Each job signs in with OIDC (no stored secret), starts the executor VM in the
   validation hub and launches `run-validation.sh` on it with `launch.sh`
   through Azure Run Command. The VM has no public IP.
4. The VM clones the tag, creates a fresh spoke, peers it with the hub, selects
   the provider in `azure.yaml` (Terraform also gets a remote state backend),
   applies `scenario.env`, runs the documented operator commands
   (`azd provision`, `azd deploy`, smoke test), records the sanitized
   transcript, commands and step results, and always tears the spoke down
   unless `keep_environment` is set. The result depends on the deployment and
   smoke test only. Teardown is best effort and reported separately.
5. `vm-evidence.sh follow` pages the live transcript tail and
   `vm-evidence.sh collect` downloads the evidence, both through Run Command.
   `evidence.py report` builds the report, uploaded as the
   `release-validation-<tag>-<provider>-<run id>` artifact. The job then
   deallocates the VM and waits, so the next provider can start it.
6. The `promote` job runs only when `promote` is set, both providers were
   requested and both passed. It uploads `validation-<tag>-<provider>-<run id>.md`
   as release assets, adds one marked evidence line per provider under
   `## Validation` in the release notes (`evidence.py amend-notes`) and runs
   `gh release edit <tag> --prerelease=false --latest`.

## Daily revalidation

Every day at 09:00 UTC the workflow revalidates the Latest release with both
providers and without promotion. A failure opens a GitHub issue, or comments on
the open one. Fix it on a feature branch, cut a patch release as a pre-release
and validate it. Each run creates and removes two spokes, so it costs about
the hourly price of one standard scenario for a few hours a day.

## Daily cleanup

`.github/workflows/release-validation-cleanup.yml` runs every day at 06:00 UTC
(and on demand, with `max_age_hours` and `dry_run` inputs). It starts the
executor VM and runs `cleanup.sh` on it through Run Command, because only the VM
identity can delete resource groups. The script removes, without waiting:

- the Search shared private links and Search services of `rg-relval-*` groups
  created more than `max_age_hours` (default 48) ago, then those groups, the
  network group last. A network group left alone after a teardown counts as
  old after 6 hours, because Azure can report a recent creation time for it
- every soft-deleted Foundry account of a `rg-relval-*` group (it otherwise
  holds the agent subnet and blocks the network group deletion)
- hub peerings `to-spoke-relval-*` whose spoke is gone or being removed

Groups with a management lock (for example a kept environment), the groups of a
validation running on the executor and the hub are never removed. Failed
actions show as a warning and are retried the next day.
The cleanup shares the validation concurrency group, so it never overlaps a
validation. GitHub keeps one pending run per group, so a cleanup queued behind
a running validation replaces an older pending run.

Some subscriptions run a governance automation (for example
`MCAPSGovernance-AutomationApp`) that deallocates VMs at night, at about
03:00-04:00 UTC. A run that overlaps that window loses the executor. The
`Follow validation` step detects a stopped executor and fails within minutes
with an explicit error instead of waiting for its timeout. Dispatch manual runs
outside that window and redispatch when this error appears.

## One-time setup

Run `bootstrap-hub.sh` once (`--name` sets the hub name prefix, default
`agentlz-relval`. Rerun an existing hub with the `--name` and
`--resource-group` it was created with) with an account that can create resources and role
assignments in the subscription. It creates the hub resource group, VNet, NAT
gateway, executor VM and identities, the private evidence storage account and
its private endpoint, and the GitHub OIDC federated credential. Then create the
`release-validation` GitHub environment with the `RELVAL_*` variables the
script prints.

## Operating notes

- Only one validation runs at a time (workflow concurrency group and
  `max-parallel: 1`). `launch.sh` also refuses to start while a run is active.
  It first stops units left by a cancelled or deleted workflow run, without
  teardown. Delete their resource groups by hand. Give manual runs a `RUN_KEY`
  whose first segment is not a number, such as `manual-1`, so they are never
  stopped.
- Run Command allows one command per VM and about 4 KB of output, so evidence
  is transferred in pages.
- The evidence storage account is private. The executor reaches it through the
  hub private endpoint and an `/etc/hosts` pin.
- The VM deallocates itself after the evidence is collected. The NAT gateway
  and private endpoint have a small permanent cost.
- To run manually, start the VM and invoke `launch.sh` through
  `az vm run-command invoke`, then use `vm-evidence.sh` with `HUB_RG`,
  `HUB_VM` and `RUN_KEY`.
- To check a fix before cutting a release, set `SOURCE_REF` to the candidate
  branch when calling `launch.sh`. It deploys that branch instead of the tag.
  Never publish the evidence of such a run for a release.
- Teardown first removes the Search shared private links and the Search
  services, then starts the resource group deletions and does not wait for
  them. The shared private link otherwise blocks the group deletion and leaks
  one unit of the standard Search quota per run.
  Set `WAIT_FOR_TEARDOWN=true` to run the full `azd down` with verification.
- If teardown leaves resources behind, the daily cleanup removes them after
  48 hours. To clean up by hand earlier, go in this order: delete the
  Search shared private links (`az search shared-private-link-resource
  delete`) and the Search service, delete the
  environment and app resource groups (`rg-relval-<env>` and
  `rg-relval-<env>-app`), purge the soft-deleted Foundry account
  (`az cognitiveservices account purge`, about 30 minutes), then delete the
  network resource group (`rg-relval-<env>-network`). The account holds the
  agent subnet until it is purged.
