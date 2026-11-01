# ADR-0028: Integrated Terraform composition

**Status:** Accepted<br>
**Date:** 2026-10-27<br>
**Owners:** Agent Landing Zone maintainers<br>
**Decision basis:** Approved implementation plan for issue #798

## Context

Terraform users need the same infrastructure-to-application lifecycle as
Bicep users. The external AI Landing Zone pattern is infrastructure-only and
does not expose the complete Agent Landing Zone deployment contract.
Synchronizing another repository does not establish a validated application
deployment path.

The operator chooses Bicep or Terraform when initializing a checkout and keeps
that choice. Converting deployed environments between tools is not required.

Prioritized characteristics:

1. Supported scenarios and effective defaults have a traceable parity matrix;
   no accepted option is silently ignored.
2. Both providers reuse the application definition, configuration and deployment
   lifecycle, including destination binding and authorization checks.
3. Dependencies are reproducible and reviewed, with explicit module versions
   and a version-controlled provider lock file.
4. Provisioning never replaces an application image already published by deploy.
5. Infrastructure and application compatibility are reviewed in one product
   change, without external synchronization or automatic publication.

## Alternatives

### Consume the existing external pattern

This reuses its composition but requires coordinating feature coverage,
defaults, outputs and releases with a separate product. It is not selected as
the mandatory foundation. Individual modules remain candidates where their
contracts fit.

### Maintain a local composition using AVM where appropriate (selected)

The product owns its Terraform root and connects relatively flat modules using
explicit inputs and outputs. AVM resource modules are preferred where they
preserve supported behavior. AzureRM or AzAPI resources can implement verified
gaps without invoking Bicep or an ARM deployment as a Terraform substitute.

### Leave Terraform infrastructure-only

This preserves current behavior but does not address issue #798.

## Decision

- Keep the Bicep entry point and paths unchanged. Add the Terraform composition
  under `infra/terraform`.
- Preserve Bicep as the initial `azure.yaml` default. Terraform users configure
  the native provider and infrastructure path once, then use normal `azd`
  lifecycle commands. No provider-switching or migration tool is introduced.
- Share resolved deployment intent and validation, not ARM parameter documents.
  Provider-specific adapters emit their respective native inputs.
- Preserve `app-definition.json`, `manifest.json`, the `agent-lz` label,
  platform-output schemas and the complete deployment-output contract.
- Keep provisioning foundation-only. Application builds and publication remain
  in the existing deployment lifecycle.
- Make Terraform's ownership of infrastructure distinct from deployment's
  ownership of application image revisions. Any lifecycle exclusions must be
  narrow, tested and must not hide security or identity drift.
- Pin external module versions separately from provider constraints. Commit
  `.terraform.lock.hcl` for the root configuration, including checksums for
  supported execution platforms. Do not commit plans, state or credentials.
- Use an explicitly configured state backend outside the workload teardown
  boundary. State prerequisites, authentication, locking and recovery must be
  documented and verified independently of dependency locking.
- Retire the obsolete external parity publication/assessment automation and
  its exclusive agents, skills and operational assets. Remove the dedicated
  GitHub environment and credentials only after checking other consumers.
  Do not remove shared GitHub Apps or historical runs/deployments.
- Replace external publication with ordinary local CI contract, regression and
  parity checks. This supersedes ADR-0015 only for Terraform location and the
  external synchronization requirement; Bicep provenance remains unchanged.

## Verified native integration constraints

The native contract was checked against Azure Developer CLI `1.37.1`, commit
`6bd1275b6b31104034673946953533eb860dd646`, and Terraform `1.13.0`. These are
verification versions, not a claim that every earlier version is supported.

- Provisioning initializes with `-upgrade`. Exact root constraints for every
  direct and transitive provider prevent version reselection; a separate
  read-only-lock initialization in CI verifies the committed lock file.
  Passing `-lockfile=readonly` into native provisioning conflicts with
  `-upgrade` and is not an integration mechanism.
- Native plan and apply pass `-lock=false`, disabling the Terraform backend's
  own state lock, including the Azure Blob lease. Remote state storage alone
  does not restore this protection. The local azd environment-file lock is
  not a lock around infrastructure operations.
- Retain native azd with an explicitly approved single-writer operating model.
  Individual environments may use local azd. Shared and production states have
  one authorized executor, normally a pipeline, with queued, non-canceling
  serialization for the actual backend subscription, account, container and
  state key. Restrict state write permissions to that executor; separate
  branches, repositories and manual CLI sessions must not bypass the same
  execution boundary. Per-ref concurrency and cancel-in-progress are not
  sufficient protection.
- This is an operational and authorization boundary, not a restored Terraform
  state lock or permission to write concurrently. Direct Terraform invocation
  with backend-native locking was considered but not selected because the
  approved product entry point remains azd. Evidence of the writer boundary,
  backend access and recovery remains a release gate alongside deployment
  evidence; do not describe an unverified path as supported.
- Native inputs are generated, ignored `<module>.tfvars.json` artifacts,
  not tracked templates overwritten with private values. The shared resolver
  emits native typed JSON and a separate diagnostic parameter envelope for
  existing preflight checks. Literal dollar signs are escaped in JSON before
  azd substitution and restored by JSON decoding.
- Lifecycle outputs must retain concrete scalar and collection types,
  including absent optional values. Do not emit untyped null outputs into
  azd's output conversion.
- Bind the selected backend subscription, resource group, account, container,
  exact state key and cloud in private `terraform-backend.json` before emitting
  inputs. Subsequent operations verify that address rather than silently
  retargeting state. Restore this record with the original group and application
  bindings on a clean runner; a deployed environment cannot invent a new binding.
- Native Terraform teardown destroys state-owned resources, not every resource
  in an azd destination group. The shared guard verifies the original group
  ownership and separate backend before allowing split/BYO group teardown.
  Existing Bicep teardown restrictions remain unchanged. In the verified azd,
  noninteractive teardown without `--force` previews but skips destruction.
- Publish foundation-owned App Configuration values declaratively. Shared
  default seeding fills only missing `agent-lz` keys, preserving existing
  content types and Key Vault references. Resolve explicit runtime intent from
  the private declared parameter source and selected environment through the
  shared resolver, never from state or public outputs. A single ownership
  inventory separates ordinary overrides from authoritative routing, identity
  and evidence. Conflicting protected settings fail before publication.

The upstream locking limitation is tracked in
[Azure/azure-dev#4882](https://github.com/Azure/azure-dev/issues/4882).
The CLI invocation is visible in the
[verified Terraform adapter](https://github.com/Azure/azure-dev/blob/6bd1275b6b31104034673946953533eb860dd646/cli/azd/pkg/tools/terraform/terraform.go).
Public consuming examples demonstrate native integration, not proof of
safe concurrent writes to a persistent shared state.

## Fitness functions

- Every supported option, default and consumed output has a mapped Terraform
  implementation and an observable acceptance criterion.
- Provider-specific rendering tests preserve Bicep behavior and reject malformed
  configuration before any Azure changes.
- Contract tests cover scalar and structured output transport through `azd`.
- Public and isolated deployment evidence includes positive and negative access
  checks, provision/deploy separation and image preservation on reprovision.
- PowerShell and shell hooks remain behaviorally equivalent.
- CI respects the committed provider lock file; updates do not occur implicitly.
- Shared-state execution queues a second operation without interrupting an
  active apply, and an unauthorized executor cannot write the backend state.
- No active workflow dispatches changes to the external Terraform repository.

Static validation does not establish deployed parity. Missing Azure evidence
must remain explicit rather than becoming a successful fallback.

## Adoption and recovery

Inventory supported behavior and verify the native `azd` contract first.
Implement the provider adapters, foundation, shared hooks and state handling,
then verify the complete scenario matrix before declaring Terraform supported.
Maintain the existing Bicep path throughout adoption.

Operators recover within their chosen provider using reviewed code versions
and state backups. Do not provide automatic rollback, switch infrastructure
tools as recovery, or imply destructive recreation is safe.

## Documentation impact

Central AI Landing Zones documentation contains four deployment runbooks,
grouped first by outcome (`Deploy infra only` or `Deploy full stack`) and then
by `With Bicep` or `With Terraform`. Preserve existing Bicep URLs.

The Terraform templates page is a high-level overview with a diagram and
runbook links, not a duplicated procedure. Coordinate publication with verified
implementation; do not describe an unverified path as shipped.

## Review trigger

Reassess if `azd` changes its Terraform contract, a provider cannot express a
supported scenario, state ownership changes, or an independently versioned
public Terraform module becomes a product requirement.
