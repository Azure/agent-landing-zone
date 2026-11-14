#!/usr/bin/env bash
# One-time, idempotent setup of the persistent release-validation hub used by
# .github/workflows/release-validation.yml.
#
# Creates, in the current Azure CLI subscription:
#   - a hub resource group with a hub VNet (10.250.0.0/24), NAT gateway and a
#     Linux executor VM without public IP or inbound access
#   - a user-assigned identity for the VM (Owner on the subscription, needed to
#     provision and destroy complete landing zones with role assignments)
#   - a user-assigned identity federated with GitHub Actions OIDC for the
#     workflow environment (only starts/stops the VM, runs commands on it and
#     reads evidence)
#   - one Entra-only storage account with "tfstate" and "evidence" containers
# and, when gh is authenticated with admin rights, the GitHub environment and
# its variables. No secret is created or stored anywhere.
#
# Usage (bash: Azure Cloud Shell, Linux, macOS or Git Bash):
#   az account set --subscription <subscription-id>
#   util/release-validation/bootstrap-hub.sh [--location swedencentral] \
#     [--repo Azure/agent-landing-zone] [--environment release-validation] \
#     [--name agentlz-relval] [--resource-group rg-agentlz-relval-hub]
#
# --name is the prefix of every hub resource name. Rerun against an existing hub
# with the same --name and --resource-group it was created with.
set -euo pipefail
export MSYS_NO_PATHCONV=1

LOCATION="swedencentral"
REPO="Azure/agent-landing-zone"
GH_ENVIRONMENT="release-validation"
NAME="agentlz-relval"
RG=""
VM_SIZE="Standard_D2s_v5"
while [ $# -gt 0 ]; do
  case "$1" in
    --location) LOCATION="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --environment) GH_ENVIRONMENT="$2"; shift 2 ;;
    --resource-group) RG="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --vm-size) VM_SIZE="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

RG="${RG:-rg-$NAME-hub}"

azq() { az "$@" --only-show-errors | tr -d '\r'; }
log() { printf '\n==> %s\n' "$*"; }

SUB="$(azq account show --query id -o tsv)"
TENANT="$(azq account show --query tenantId -o tsv)"
SUFFIX="$(printf '%s' "$SUB$RG" | sha256sum | cut -c1-10)"
STORAGE="stalzrv${SUFFIX}"
VNET="vnet-$NAME-hub"
SUBNET="snet-executor"
VM="vm-$NAME"
VM_IDENTITY="id-$NAME-executor"
GH_IDENTITY="id-$NAME-github"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

assign_role() { # <principal-object-id> <role> <scope>
  # New identities can take a while to replicate before RBAC accepts them.
  local attempt output
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if output="$(az role assignment create --assignee-object-id "$1" \
        --assignee-principal-type ServicePrincipal --role "$2" --scope "$3" \
        --only-show-errors 2>&1)"; then
      return 0
    fi
    case "$output" in *RoleAssignmentExists*|*"already exists"*) return 0 ;; esac
    sleep 15
  done
  printf '%s\n' "$output" >&2
  return 1
}

log "Resource group $RG ($LOCATION)"
azq group create -n "$RG" -l "$LOCATION" --tags purpose=agent-lz-release-validation >/dev/null

log "Network: hub VNet, NSG without inbound rules, NAT gateway for outbound"
azq network nsg create -g "$RG" -n "nsg-$SUBNET" -l "$LOCATION" >/dev/null
azq network public-ip create -g "$RG" -n "pip-nat-$NAME" -l "$LOCATION" \
  --sku Standard --allocation-method Static >/dev/null
azq network nat gateway create -g "$RG" -n "nat-$NAME" -l "$LOCATION" \
  --public-ip-addresses "pip-nat-$NAME" >/dev/null
if ! az network vnet show -g "$RG" -n "$VNET" >/dev/null 2>&1; then
  azq network vnet create -g "$RG" -n "$VNET" -l "$LOCATION" --address-prefixes 10.250.0.0/24 \
    --subnet-name "$SUBNET" --subnet-prefixes 10.250.0.0/26 >/dev/null
fi
azq network vnet subnet update -g "$RG" --vnet-name "$VNET" -n "$SUBNET" \
  --network-security-group "nsg-$SUBNET" --nat-gateway "nat-$NAME" >/dev/null
VNET_ID="$(azq network vnet show -g "$RG" -n "$VNET" --query id -o tsv)"

log "Identities"
azq identity create -g "$RG" -n "$VM_IDENTITY" -l "$LOCATION" >/dev/null
azq identity create -g "$RG" -n "$GH_IDENTITY" -l "$LOCATION" >/dev/null
VM_ID_RES="$(azq identity show -g "$RG" -n "$VM_IDENTITY" --query id -o tsv)"
VM_CLIENT="$(azq identity show -g "$RG" -n "$VM_IDENTITY" --query clientId -o tsv)"
VM_PRINCIPAL="$(azq identity show -g "$RG" -n "$VM_IDENTITY" --query principalId -o tsv)"
GH_CLIENT="$(azq identity show -g "$RG" -n "$GH_IDENTITY" --query clientId -o tsv)"
GH_PRINCIPAL="$(azq identity show -g "$RG" -n "$GH_IDENTITY" --query principalId -o tsv)"
azq identity federated-credential create -g "$RG" --identity-name "$GH_IDENTITY" \
  -n "github-${GH_ENVIRONMENT}" \
  --issuer "https://token.actions.githubusercontent.com" \
  --subject "repo:${REPO}:environment:${GH_ENVIRONMENT}" \
  --audiences "api://AzureADTokenExchange" >/dev/null

log "Storage account $STORAGE (Entra ID only, no shared keys)"
azq storage account create -g "$RG" -n "$STORAGE" -l "$LOCATION" --sku Standard_LRS \
  --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access false \
  --allow-shared-key-access false --https-only true >/dev/null
STORAGE_ID="$(azq storage account show -g "$RG" -n "$STORAGE" --query id -o tsv)"
for container in tfstate evidence; do
  azq storage container-rm create --storage-account "$STORAGE" -g "$RG" -n "$container" >/dev/null
done
# Subscription policy may force publicNetworkAccess=Disabled. The executor
# reaches blob storage (Terraform state, evidence) through this endpoint. The
# hub does not host a privatelink.blob zone because each validated spoke links
# its own zone to the hub VNet, so run-validation.sh pins the name in /etc/hosts.
if [ -z "$(az network private-endpoint list -g "$RG" \
    --query "[?privateLinkServiceConnections[0].privateLinkServiceId=='$STORAGE_ID'].name | [0]" -o tsv 2>/dev/null)" ]; then
  azq network private-endpoint create -g "$RG" -n "pe-${STORAGE}-blob" -l "$LOCATION" \
    --vnet-name "$VNET" --subnet "$SUBNET" --private-connection-resource-id "$STORAGE_ID" \
    --group-id blob --connection-name "pe-${STORAGE}-blob" >/dev/null
fi

log "Role assignments"
assign_role "$VM_PRINCIPAL" Owner "/subscriptions/$SUB"
assign_role "$VM_PRINCIPAL" "Storage Blob Data Contributor" "$STORAGE_ID"
assign_role "$GH_PRINCIPAL" "Virtual Machine Contributor" "/subscriptions/$SUB/resourceGroups/$RG"
assign_role "$GH_PRINCIPAL" Reader "/subscriptions/$SUB/resourceGroups/$RG"
assign_role "$GH_PRINCIPAL" "Storage Blob Data Reader" \
  "$STORAGE_ID/blobServices/default/containers/evidence"

log "Executor VM $VM (no public IP, no password)"
if ! az vm show -g "$RG" -n "$VM" >/dev/null 2>&1; then
  azq vm create -g "$RG" -n "$VM" -l "$LOCATION" \
    --image Canonical:ubuntu-24_04-lts:server:latest --size "$VM_SIZE" \
    --vnet-name "$VNET" --subnet "$SUBNET" --public-ip-address "" --nsg "" \
    --assign-identity "$VM_ID_RES" --admin-username relval --generate-ssh-keys \
    --os-disk-size-gb 128 >/dev/null
else
  azq vm start -g "$RG" -n "$VM" >/dev/null
fi
log "Installing tools on the executor"
azq vm run-command invoke -g "$RG" -n "$VM" --command-id RunShellScript \
  --scripts @"$SCRIPT_DIR/install-tools.sh" --query "value[0].message" -o tsv
azq vm deallocate -g "$RG" -n "$VM" --no-wait

cat <<EOF

Hub ready. GitHub environment "$GH_ENVIRONMENT" variables:
  RELVAL_AZURE_CLIENT_ID       = $GH_CLIENT
  RELVAL_AZURE_TENANT_ID       = $TENANT
  RELVAL_AZURE_SUBSCRIPTION_ID = $SUB
  RELVAL_HUB_RESOURCE_GROUP    = $RG
  RELVAL_HUB_VM_NAME           = $VM
  RELVAL_HUB_VNET_ID           = $VNET_ID
  RELVAL_EXECUTOR_CLIENT_ID    = $VM_CLIENT
  RELVAL_STORAGE_ACCOUNT       = $STORAGE
EOF

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  log "Configuring GitHub environment $GH_ENVIRONMENT in $REPO"
  gh api -X PUT "repos/$REPO/environments/$GH_ENVIRONMENT" --input - >/dev/null <<'JSON'
{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}
JSON
  gh api -X POST "repos/$REPO/environments/$GH_ENVIRONMENT/deployment-branch-policies" \
    -f name=main -f type=branch >/dev/null 2>&1 || true
  for pair in \
    "RELVAL_AZURE_CLIENT_ID=$GH_CLIENT" "RELVAL_AZURE_TENANT_ID=$TENANT" \
    "RELVAL_AZURE_SUBSCRIPTION_ID=$SUB" "RELVAL_HUB_RESOURCE_GROUP=$RG" \
    "RELVAL_HUB_VM_NAME=$VM" "RELVAL_HUB_VNET_ID=$VNET_ID" \
    "RELVAL_EXECUTOR_CLIENT_ID=$VM_CLIENT" "RELVAL_STORAGE_ACCOUNT=$STORAGE"; do
    gh variable set "${pair%%=*}" --env "$GH_ENVIRONMENT" --repo "$REPO" --body "${pair#*=}"
  done
fi
