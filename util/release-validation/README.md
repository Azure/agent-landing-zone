# Release validation harness

Maintainer tooling that validates a published release with a live Terraform
deployment and `NETWORK_ISOLATION=true`. It is not part of the shipped product.

## How it works

1. `.github/workflows/release-validation-terraform.yml` runs manually
   (`workflow_dispatch`) and asks for the release tag.
2. The GitHub-hosted runner signs in with OIDC (no stored secret), starts the
   executor VM in the validation hub and launches `run-validation.sh` on it
   with `launch.sh` through Azure Run Command. The VM has no public IP.
3. The VM clones the tag, creates a fresh spoke, peers it with the hub, runs the
   documented operator commands (`azd provision`, `azd deploy`, smoke test),
   records the sanitized transcript, commands and step results, and always
   tears the spoke down unless `keep_environment` is set.
4. `vm-evidence.sh follow` pages the live transcript tail and
   `vm-evidence.sh collect` downloads the evidence, both through Run Command.
5. `evidence.py report` builds the report. On success,
   `evidence.py amend-notes` uploads it as a release asset and adds a marked
   evidence section to the release notes.

## One-time setup

Run `bootstrap-hub.sh` once with an account that can create resources and role
assignments in the subscription. It creates the hub resource group, VNet, NAT
gateway, executor VM and identities, the private evidence storage account and
its private endpoint, and the GitHub OIDC federated credential. Then create the
`release-validation` GitHub environment with the `RELVAL_*` variables the
script prints.

## Operating notes

- Only one validation runs at a time (workflow concurrency group).
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
