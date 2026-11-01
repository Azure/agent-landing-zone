# ADR-0026: Prepare the hosted image during application deployment

**Status:** Accepted<br>
**Date:** 2026-10-27<br>
**Owners:** Agent Landing Zone maintainers

## Context

Fresh hosted deployments currently require provision, explicit image
preparation, another provision, and deployment. The foundation does not create
the data-plane agent: `infra/main.bicep` exposes project, registry, network and
build prerequisites, while `scripts/preDeploy.*` creates the agent through the
child `azure.ai.agent` project. The second provision only binds the image to
that deployment handoff.

Priorities are immutable image provenance, unchanged identity and private
network controls, resumable deployments, and fewer operator commands. The
affected repositories are Azure/agent-landing-zone and Azure/AI-Landing-Zones;
no runtime component or foundation schema change is required.

## Alternatives considered

### Prepare the real image during deploy (selected)

Reuse the manifest-pinned ACR build and digest persistence, then combine the
application image configuration with the provisioned foundation handoff.
This keeps builds and application publication out of foundation provisioning.
It preserves project registry-pull grants, private build pools, runtime
bootstrap, smoke validation and explicit cutover. Deployment takes the build
time, but no placeholder runtime is billed or maintained.

### Publish and later replace a hosted placeholder

A protocol-compatible image could test hosting independently. It adds image
distribution, another agent version, identity/routing transition risks and
potential session costs without removing the need to build the real image.
It would also require separate isolated-network pull validation.

### Do not change

Retains the tested manual sequence but exposes an internal application-build
dependency as an extra operator command and a redundant foundation deployment.

## Decision

Root `azd deploy` prepares or reuses the immutable hosted image and materializes
the application handoff from the existing foundation outputs. It does not run
`azd provision`, create a placeholder or relax any permission, network, greeting
or cutover gate. PowerShell and Bash use the same Python implementation.

## Consequences

Fresh deployments use `azd provision` followed by `azd deploy`, or `azd up`.
An unchanged generated image is reused; stale manifest/startup provenance is
rebuilt at deployment. Explicit immutable image overrides remain supported.
Image preparation errors stop deployment before agent publication.

## Adoption and migration

Land the shared implementation and paired hooks together, then update central
operator documentation on a feature branch. Existing prepared environments
remain usable; retain standalone preparation wrappers for compatibility, not
as required steps. No data migration or runtime pin change is involved.
Rollback to the earlier tooling retains its manual prepare/provision sequence.
Existing classic deployments and explicit classic-to-hosted cutover semantics
are unchanged.

## Compliance verification

Regression tests cover a prepare-only foundation, image reuse and rebuild,
explicit digest overrides, preservation and validation of foundation context,
failed persistence/builds, and both actual hook preparation blocks. Existing
deployment, topology, bootstrap, continuity and private-network suites must
remain green. Live Basic and isolated deploys remain necessary before claiming
Azure runtime validation.

## Documentation impact

Update full-stack deployment, hosted image redeployment, Azure DevOps guidance
and affected troubleshooting text in Azure/AI-Landing-Zones. Product guidance
describes the resulting workflow, not release-comparison instructions.

## Review trigger

Revisit when the Foundry deployment extension changes its image/startup
contract, prebuilt hosted images become available, or live validation exposes
a foundation operation that cannot be completed before the image build.
