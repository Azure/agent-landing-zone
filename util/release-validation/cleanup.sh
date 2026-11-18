#!/usr/bin/env bash
# Removes leftovers of release validations so they do not keep costing money.
# Runs as root on the executor VM through Run Command, with the VM managed
# identity (the GitHub OIDC identity cannot delete resource groups).
#
# Removes, in this order:
#   1. Search shared private links and Search services in old validation groups
#      (a shared private link blocks the group deletion).
#   2. Old validation resource groups (rg-relval-*), the network group last.
#   3. Soft-deleted Foundry accounts of validation groups (an unpurged account
#      keeps the agent subnet and blocks the network group deletion).
#   4. Hub peerings to-spoke-relval-* whose spoke is gone or being removed.
# A group is old when it was created more than MAX_AGE_HOURS ago. A network
# group whose environment and app groups are already gone counts as old after
# 6 hours. Groups with a management lock (for example a kept environment), the
# groups of a validation running on the executor and the hub are skipped.
# Every deletion is started without waiting. The next run retries whatever
# Azure still refused, such as a network group waiting for a purge.
#
# Inputs (environment): SUBSCRIPTION_ID, EXECUTOR_CLIENT_ID, HUB_VNET_ID,
# MAX_AGE_HOURS (default 48) and DRY_RUN (true or false, default false).
set -uo pipefail
export HOME="${HOME:-/root}" AZURE_CORE_COLLECT_TELEMETRY=no

need() { [[ "${!1:-}" =~ $2 ]] || { echo "Invalid or missing $1" >&2; exit 2; }; }
MAX_AGE_HOURS="${MAX_AGE_HOURS:-48}"
DRY_RUN="${DRY_RUN:-false}"
need SUBSCRIPTION_ID '^[0-9a-fA-F-]{36}$'
need EXECUTOR_CLIENT_ID '^[0-9a-fA-F-]{36}$'
need HUB_VNET_ID '^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9._()-]+/providers/Microsoft\.Network/virtualNetworks/[A-Za-z0-9._-]+$'
need MAX_AGE_HOURS '^[0-9]{1,4}$'
need DRY_RUN '^(true|false)$'
HUB_RG="$(printf '%s' "$HUB_VNET_ID" | awk -F/ '{print $5}')"
HUB_VNET="$(printf '%s' "$HUB_VNET_ID" | awk -F/ '{print $9}')"
ARM="https://management.azure.com/subscriptions/$SUBSCRIPTION_ID"
PREFIX="rg-relval-"
FAILURES=0

act() { # <description> <command...>
  local what="$1"; shift
  if [ "$DRY_RUN" = "true" ]; then
    echo "would $what"
  elif "$@" >/dev/null 2>/tmp/relval-cleanup.err; then
    echo "$what"
  else
    FAILURES=$((FAILURES + 1))
    echo "FAILED $what: $(tr '\n' ' ' < /tmp/relval-cleanup.err | cut -c1-160)"
  fi
}

az login --identity --client-id "$EXECUTOR_CLIENT_ID" --allow-no-subscriptions --only-show-errors >/dev/null \
  || { echo "Managed identity sign-in failed."; exit 1; }
az account set --subscription "$SUBSCRIPTION_ID" || exit 1

cutoff="$(date -u -d "-$MAX_AGE_HOURS hours" +%Y-%m-%dT%H:%M:%SZ)"
# A network group left alone by a teardown (its environment and app groups are
# gone) is a leftover even when Azure reports a recent creation time.
orphan_cutoff="$(date -u -d "-6 hours" +%Y-%m-%dT%H:%M:%SZ)"
echo "Cleanup of $PREFIX* groups created before $cutoff (dry run: $DRY_RUN)"

# Environments of validations running on this executor (same naming as
# run-validation.sh) are never touched, whatever their age.
active_envs=()
for unit in $(systemctl list-units --type=service --state=active --no-legend --plain 'relval-*' 2>/dev/null | awk '{print $1}'); do
  key="${unit#relval-}"; key="${key%.service}"
  active_envs+=("relval-$(printf '%s' "$key" | tr '[:upper:]' '[:lower:]' | sed 's/bicep$/b/;s/terraform$/t/' | tr -cd 'a-z0-9' | tail -c 12)")
done

# name<TAB>createdTime<TAB>provisioningState of every validation group.
groups="$(az rest --method get --url "$ARM/resourcegroups?api-version=2021-04-01&\$expand=createdTime" \
  --query "value[?starts_with(name, '$PREFIX')].[name, createdTime, properties.provisioningState]" -o tsv)" \
  || { echo "Could not list resource groups."; exit 1; }
names="$(cut -f1 <<< "$groups")"

old=()
while IFS=$'\t' read -r name created state; do
  [ -z "$name" ] || [ "$name" = "$HUB_RG" ] && continue
  env_name="${name#rg-}"; env_name="${env_name%-app}"; env_name="${env_name%-network}"
  if [[ " ${active_envs[*]:-} " == *" $env_name "* ]]; then
    echo "keep $name (validation running)"
    continue
  fi
  orphan_network=false
  if [[ "$name" == *-network ]] && ! grep -qxiE "rg-$env_name(-app)?" <<< "$names" \
      && [[ "$created" < "$orphan_cutoff" ]]; then
    orphan_network=true
  fi
  if [[ "$created" > "$cutoff" ]] && [ "$orphan_network" = false ]; then
    echo "keep $name (created $created)"
    continue
  fi
  if [ -n "$(az lock list -g "$name" --query '[0].name' -o tsv 2>/dev/null)" ]; then
    echo "keep $name (locked)"
    continue
  fi
  if [ "$state" = "Deleting" ]; then
    echo "already deleting $name"
    continue
  fi
  old+=("$name")
done <<< "$groups"

for name in "${old[@]:-}"; do
  [ -z "$name" ] && continue
  while read -r svc; do
    [ -z "$svc" ] && continue
    while read -r spl; do
      [ -z "$spl" ] && continue
      act "delete shared private link $svc/$spl" \
        az search shared-private-link-resource delete -g "$name" --service-name "$svc" -n "$spl" --yes --only-show-errors
    done < <(az search shared-private-link-resource list -g "$name" --service-name "$svc" --query '[].name' -o tsv 2>/dev/null)
    act "delete search service $svc" az search service delete -g "$name" -n "$svc" --yes --only-show-errors
  done < <(az search service list -g "$name" --query '[].name' -o tsv 2>/dev/null)
done

# Application and environment groups first, so the network group is free sooner.
for name in "${old[@]:-}"; do
  [ -z "$name" ] || [[ "$name" == *-network ]] && continue
  act "delete group $name" az group delete -n "$name" --yes --no-wait --only-show-errors
done

while IFS=$'\t' read -r id name; do
  [ -z "$id" ] && continue
  act "purge deleted account $name" az rest --method delete --url "https://management.azure.com$id?api-version=2024-10-01"
done < <(az rest --method get --url "$ARM/providers/Microsoft.CognitiveServices/deletedAccounts?api-version=2024-10-01" \
  --query "value[?contains(id, '/resourceGroups/$PREFIX')].[id, name]" -o tsv 2>/dev/null)

for name in "${old[@]:-}"; do
  [ -z "$name" ] || [[ "$name" != *-network ]] && continue
  act "delete group $name" az group delete -n "$name" --yes --no-wait --only-show-errors
done

# A peering is orphaned when its spoke VNet is gone (Disconnected) or lives in
# a group this run removes.
while IFS=$'\t' read -r peering state remote; do
  [ -z "$peering" ] && continue
  remote_rg="$(printf '%s' "$remote" | awk -F/ '{print $5}')"
  orphan=false
  [ "$state" = "Disconnected" ] && orphan=true
  for name in "${old[@]:-}"; do
    [ -n "$name" ] && [ "${remote_rg,,}" = "${name,,}" ] && orphan=true
  done
  if [ "$orphan" = true ]; then
    act "delete hub peering $peering" az network vnet peering delete -g "$HUB_RG" --vnet-name "$HUB_VNET" -n "$peering" --only-show-errors
  else
    echo "keep hub peering $peering ($state)"
  fi
done < <(az network vnet peering list -g "$HUB_RG" --vnet-name "$HUB_VNET" \
  --query "[?starts_with(name, 'to-spoke-relval-')].[name, peeringState, remoteVirtualNetwork.id]" -o tsv 2>/dev/null)

active="$(systemctl list-units --type=service --state=active --no-legend --plain 'relval-*' 2>/dev/null | grep -c relval- || true)"
echo "active validations on executor: $active"
# Run Command does not return the exit code, so the workflow reads this line.
echo "cleanup failures: $FAILURES"
