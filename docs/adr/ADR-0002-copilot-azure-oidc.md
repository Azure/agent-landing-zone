# ADR-0002: Confine Copilot Azure deployments to one evaluation resource group

**Status:** Accepted (revision 2)<br>
**Date:** 2026-07-26<br>
**Owners:** GPT-RAG maintainers

## Context

GitHub Copilot cloud coding agents working in `Azure/GPT-RAG` need to deploy
and test a complete GPT-RAG environment. The original decision granted a
secretless identity subscription Reader for discovery only. That permission
cannot create GPT-RAG resources or the child-resource role assignments emitted
by the pinned landing-zone Bicep.

The revised boundary is one fixed azd environment,
`agentlz-evaluation`, mapped to one pre-created resource group,
`rg-agentlz-evaluation`, in subscription
`9788a92c-2f71-4629-8173-7ad449cb50e1`. The agent must not deploy to another
resource group or receive subscription-scope Reader, Contributor, Owner, or
role-assignment permissions.

The executable infrastructure pin is resource-group scoped. It creates Azure
resources and `Microsoft.Authorization/roleAssignments` on resources inside the
deployment resource group. The resource group must already exist. Subscription
resource providers and capacity prerequisites are maintainer responsibilities;
the agent cannot register providers, request quota, change policy, or create the
resource group.

Prioritized characteristics and measures are:

1. **Scope confinement:** every direct role assignment on the coding-agent
   identity has the exact scope
   `/subscriptions/9788a92c-2f71-4629-8173-7ad449cb50e1/resourceGroups/rg-agentlz-evaluation`.
2. **Credential security:** token issuance uses GitHub OIDC with no client
   secret or password credential.
3. **Deployment completeness:** the identity can create, update, delete, and
   assign the resource-level roles required by the pinned GPT-RAG Bicep inside
   the evaluation resource group.
4. **Deterministic targeting:** setup creates or selects only azd environment
   `agentlz-evaluation` and writes `AZURE_RESOURCE_GROUP=rg-agentlz-evaluation`.
5. **Observable safety:** an OIDC What-If must succeed and contain no
   subscription-scope, cross-resource-group, or delete operation before the
   configuration is accepted.

## Alternatives considered

### Option A: Static client secret with broad subscription access

- Benefits: simple compatibility with Azure tooling and enough authority for
  all deployment paths.
- Costs and risks: reusable credentials require storage and rotation; Owner or
  subscription Contributor exposes unrelated workloads.
- Security and identity: token use is not bound to this repository and GitHub
  environment.
- Operational consequences: secret expiry can interrupt cloud-agent tasks.
- Component compatibility: works with Azure CLI, azd, and Azure MCP.
- Cost and network: allows accidental deployment outside the evaluation
  boundary, increasing cost and blast radius.
- Reversibility: revocation must cover every copy of the secret.

### Option B: OIDC identity with resource-group deployment roles

- Benefits: short-lived repository-bound tokens and Azure-enforced confinement
  to a disposable evaluation resource group.
- Costs and risks: Contributor can create, mutate, and delete every resource in
  the group. Role Based Access Control Administrator can grant or revoke any
  Azure RBAC role at that group or its children, including delegating access to
  another principal. It cannot assign roles outside the group.
- Security and identity: a dedicated user-assigned managed identity trusts only
  `repo:Azure/GPT-RAG:environment:copilot` with audience
  `api://AzureADTokenExchange`.
- Authorization: Contributor provides resource lifecycle operations; Role Based
  Access Control Administrator provides only the role-assignment operations
  required by the Bicep deployment. Both are scoped to the fixed resource group.
- Operational consequences: maintainers pre-create the group, register
  providers, assess quota and policy, and review cost. The agent runs the
  resource-group deployment and tests.
- Component compatibility: supported by `azure/login`, Azure CLI, azd, the
  pinned resource-group-scoped Bicep, and Azure MCP.
- Cost and network: standard public-network mode is required for the GitHub
  runner. Network-isolated deployment remains a separate jumpbox/VNet flow.
- Reversibility: removing the two resource-group assignments immediately
  disables agent deployment without deleting the managed identity.

### Do not grant Azure access

- Benefits: smallest Azure attack surface and no agent-created cloud cost.
- Costs and risks: Copilot cannot provision or validate GPT-RAG, so a maintainer
  must reproduce every deployment result.
- Security and identity: no Azure token or RBAC assignment.
- Operational consequences: incompatible with the requested deployment and
  testing workflow.
- Reversibility: Option B can be adopted later.

## Decision

Use Option B. Keep `mi-gpt-rag-copilot-agent` in its identity resource group,
`rg-gpt-rag-copilot-agent`, and assign its service principal exactly:

- Contributor at
  `/subscriptions/9788a92c-2f71-4629-8173-7ad449cb50e1/resourceGroups/rg-agentlz-evaluation`;
- Role Based Access Control Administrator at the same scope.

Do not retain subscription Reader or grant subscription Contributor, Owner,
User Access Administrator, or Role Based Access Control Administrator.
Pre-create `rg-agentlz-evaluation` in `eastus`, a region supported by the pinned
GPT-RAG Content Understanding configuration, before assigning the roles.

The setup workflow uses GitHub's default OIDC subject format, delegates azd
authentication to the Azure CLI OIDC session, and creates only local azd
environment `agentlz-evaluation`. It pins the subscription, tenant, locations,
principal type, standard network mode, and empty cross-resource-group inputs.
Azure RBAC is the enforcement boundary if a task changes the local azd values.

The GPT-RAG and landing-zone regional Azure CLI preflight blocks are skipped for
the agent because their provider, quota, SKU, and model catalog reads require
subscription visibility. Maintainers must verify those prerequisites
independently. The landing-zone parameter and topology checks still run. A
provider, quota, policy, or capacity failure is a blocker; it is not
justification to broaden the agent identity.

## Consequences

### Positive

- Azure access remains secretless and tied to the exact GitHub repository and
  `copilot` environment.
- The agent can execute the complete resource-group deployment, including the
  role assignments required by post-provision data-plane configuration.
- Azure rejects resource operations and role assignments outside
  `rg-agentlz-evaluation`.
- The fixed environment and group make cost review, cleanup, and audit
  straightforward.

### Negative or accepted

- The agent can delete all resources and alter access within the evaluation
  resource group.
- Standard public endpoints are required; a network-isolated deployment must
  run from the documented jumpbox/VNet path.
- Skipping regional subscription preflight moves provider, quota, policy, SKU,
  model, and capacity readiness checks to maintainers.
- A full GPT-RAG environment incurs Foundry, model, Search, Cosmos DB, Container
  Apps, registry, storage, monitoring, and related costs until it is removed.
- Post-provision scripts make data-plane changes inside the evaluation
  resources, so the group must not contain shared or production assets.

## Adoption and migration

1. Confirm the pinned infrastructure is resource-group scoped and enumerate its
   role assignments and cross-resource-group options.
2. Verify required resource providers are registered, then create the empty
   `rg-agentlz-evaluation` resource group in `eastus`.
3. Add Contributor and Role Based Access Control Administrator at only that
   resource-group scope.
4. Remove the previous subscription Reader assignment.
5. Update the setup workflow to create/select azd environment
   `agentlz-evaluation`, bind it to `rg-agentlz-evaluation`, set
   `AZURE_PRINCIPAL_TYPE=ServicePrincipal`, and disable cross-group inputs.
6. Run an OIDC-authenticated `azd provision --preview --no-prompt`. Accept only
   a What-If confined to the fixed resource group with no delete.
7. Merge the workflow and this ADR to `main`, where Copilot loads setup steps.

Rollback removes both resource-group role assignments and reverts the workflow.
The managed identity and GitHub federation may remain unprivileged for later
investigation. Restoring subscription access or a static secret is not an
automatic rollback and requires a new security decision. Roll-forward corrects
the environment mapping or pinned deployment inputs without widening scope.

## Compliance verification

- `.github/workflows/copilot-setup-steps.yml` parses as YAML, contains exactly
  one job named `copilot-setup-steps`, and grants only `contents: read` and
  `id-token: write`.
- The managed identity has exactly one GitHub federation with issuer
  `https://token.actions.githubusercontent.com`, subject
  `repo:Azure/GPT-RAG:environment:copilot`, and audience
  `api://AzureADTokenExchange`.
- Its only direct Azure assignments are Contributor and Role Based Access
  Control Administrator at the exact evaluation resource-group scope.
- The GitHub setup run proves OIDC login and writes azd environment
  `agentlz-evaluation` with `AZURE_RESOURCE_GROUP=rg-agentlz-evaluation`.
- An OIDC-authenticated What-If completes without subscription or cross-group
  deployment, role assignment, or delete.
- Required providers are registered without granting the agent provider
  registration permission.
- The GitHub `copilot` environment and repository contain no Azure client secret
  metadata, and the retained legacy applications have no subscription RBAC.

## Documentation impact

This revision changes maintainer behavior, deployment authority, and cost
exposure. The main-branch change keeps this ADR as the authoritative decision.
The matching operator documentation must be updated in a separately coordinated
`docs`-branch change; it must not be duplicated into this repository README.

## Review trigger

Reassess before changing the fixed resource group, enabling network isolation or
cross-resource-group reuse, granting subscription access, adding a custom role,
or changing the Bicep deployment scope. Also review after an infrastructure pin
changes the What-If role-assignment or deployment scopes, or by 2026-10-26.
