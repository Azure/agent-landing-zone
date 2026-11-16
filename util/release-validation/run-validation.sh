#!/usr/bin/env bash
# Release validation executor for the standard network-isolated scenario
# (scenario.env) with the Bicep or Terraform provider.
#
# Runs as root on the validation hub VM (started by
# .github/workflows/release-validation.yml through Azure Run Command).
# It reproduces the documented operator commands for a released tag, records
# every command with its output and exit code, and always tears the spoke down
# unless KEEP_ENVIRONMENT=true.
#
# Two kinds of commands are recorded:
#   user    - what an operator runs in their own VPN/VNet-connected terminal
#   harness - what only this automated hub needs (peering back to the spoke,
#             linking the spoke private DNS zones to the hub, cleanup)
#
# Required environment: RELEASE_TAG RUN_ID AZURE_SUBSCRIPTION_ID AZURE_TENANT_ID
# AZURE_LOCATION EXECUTOR_CLIENT_ID HUB_VNET_ID STORAGE_ACCOUNT
# STORAGE_RESOURCE_GROUP PROVIDER (bicep|terraform). The scenario settings are
# read from scenario.env next to this script. Optional: HOSTED_AGENT_RESOURCE_SCOPE, KEEP_ENVIRONMENT,
# REPOSITORY (default Azure/agent-landing-zone), SOURCE_REF (maintainer-only: a
# candidate branch to deploy instead of the tag, for iterating on a fix before
# release. Evidence from such a run must not be published for the tag).
set -uo pipefail

for required in RELEASE_TAG RUN_ID AZURE_SUBSCRIPTION_ID AZURE_TENANT_ID AZURE_LOCATION \
  EXECUTOR_CLIENT_ID HUB_VNET_ID STORAGE_ACCOUNT STORAGE_RESOURCE_GROUP PROVIDER; do
  [ -n "${!required:-}" ] || { echo "Missing required variable $required" >&2; exit 2; }
done
[[ "$PROVIDER" =~ ^(bicep|terraform)$ ]] || { echo "Invalid PROVIDER" >&2; exit 2; }
SCENARIO_FILE="$(dirname "$0")/scenario.env"
[ -s "$SCENARIO_FILE" ] || { echo "Missing $SCENARIO_FILE" >&2; exit 2; }
if grep -vE '^(#.*|[A-Z][A-Z0-9_]*=[A-Za-z0-9._:/-]*|)$' "$SCENARIO_FILE" >&2; then
  echo "Invalid scenario line(s) above" >&2; exit 2
fi
case "$PROVIDER" in bicep) PROVIDER_TITLE="Bicep" ;; terraform) PROVIDER_TITLE="Terraform" ;; esac
[[ "$RELEASE_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Invalid RELEASE_TAG" >&2; exit 2; }
[[ "$RUN_ID" =~ ^[0-9A-Za-z-]{1,40}$ ]] || { echo "Invalid RUN_ID" >&2; exit 2; }
SOURCE_REF="${SOURCE_REF:-$RELEASE_TAG}"
[[ "$SOURCE_REF" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$ ]] || { echo "Invalid SOURCE_REF" >&2; exit 2; }

REPOSITORY="${REPOSITORY:-Azure/agent-landing-zone}"
HOSTED_AGENT_RESOURCE_SCOPE="${HOSTED_AGENT_RESOURCE_SCOPE:-https://ai.azure.com/.default}"
KEEP_ENVIRONMENT="${KEEP_ENVIRONMENT:-false}"
ENV_NAME="relval-$(printf '%s' "$RUN_ID" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9' | tail -c 12)"
HUB_RG="$(printf '%s' "$HUB_VNET_ID" | awk -F/ '{print $5}')"
HUB_VNET="$(printf '%s' "$HUB_VNET_ID" | awk -F/ '{print $9}')"
HUB_LINK="relval-hub-link"
HUB_PEERING="to-spoke-$ENV_NAME"

WORK="/var/lib/relval/$RUN_ID"
OUT="$WORK/out"
RAW_LOG="$WORK/transcript.raw.log"
RAW_CMDS="$WORK/commands.raw.sh"
mkdir -p "$OUT"
: > "$RAW_LOG"
printf '#!/usr/bin/env bash\n# Operator commands for %s (%s, NETWORK_ISOLATION=true), in execution order.\n' \
  "$RELEASE_TAG" "$PROVIDER_TITLE" > "$RAW_CMDS"

export HOME=/root
export NO_COLOR=1 TF_IN_AUTOMATION=1 AZD_SKIP_UPDATE_CHECK=1 AZURE_CORE_COLLECT_TELEMETRY=no
export AZURE_DEV_COLLECT_TELEMETRY=no PIP_DISABLE_PIP_VERSION_CHECK=1 DEBIAN_FRONTEND=noninteractive

STATE="running"
STEP="starting"
RESULT=""
TEARDOWN="not-started"
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
declare -a STEPS=()

sanitize() {
  sed -E \
    -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r$//' \
    -e "s/${AZURE_SUBSCRIPTION_ID}/<subscription-id>/gI" \
    -e "s/${AZURE_TENANT_ID}/<tenant-id>/gI" \
    -e "s/${EXECUTOR_CLIENT_ID}/<executor-client-id>/gI" \
    ${EXECUTOR_PRINCIPAL_ID:+-e "s/${EXECUTOR_PRINCIPAL_ID}/<executor-principal-id>/gI"} \
    -e 's/(eyJ[A-Za-z0-9_-]{10,}\.)[A-Za-z0-9_.-]+/\1<redacted-token>/g' \
    -e 's/gptrag-[0-9]{10}/<environment>/g'
}

write_status() {
  local steps_json
  steps_json="$(printf '%s\n' "${STEPS[@]:-}" | jq -R 'select(length>0) | split("|") | {name:.[0], kind:.[1], exit:(.[2]|tonumber), seconds:(.[3]|tonumber)}' | jq -s '.')"
  jq -n --arg state "$STATE" --arg step "$STEP" --arg result "$RESULT" --arg teardown "$TEARDOWN" \
    --arg release "$RELEASE_TAG" --arg source_ref "$SOURCE_REF" --arg env "$ENV_NAME" --arg location "$AZURE_LOCATION" \
    --arg started "$STARTED" --arg updated "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg provider "$PROVIDER" \
    --argjson steps "$steps_json" \
    '{state:$state, step:$step, result:$result, teardown:$teardown, release:$release, source_ref:$source_ref,
      environment:$env, location:$location, provider:$provider, network_isolation:true,
      started:$started, updated:$updated, steps:$steps}' > "$OUT/status.json.tmp"
  mv -f "$OUT/status.json.tmp" "$OUT/status.json"
}

# Refreshes the sanitized logs and uploads the evidence. Only the main process
# writes status.json, so the periodic uploader never publishes stale state.
publish_logs() {
  sanitize < "$RAW_LOG" > "$OUT/transcript.log.tmp" && mv -f "$OUT/transcript.log.tmp" "$OUT/transcript.log"
  sanitize < "$RAW_CMDS" > "$OUT/commands.sh.tmp" && mv -f "$OUT/commands.sh.tmp" "$OUT/commands.sh"
  az storage blob upload-batch --auth-mode login --account-name "$STORAGE_ACCOUNT" \
    --destination evidence --destination-path "$RUN_ID" --source "$OUT" --overwrite \
    --only-show-errors >/dev/null 2>&1 || true
}

publish() {
  write_status
  publish_logs
}

log() { printf '\n### %s\n' "$*" | tee -a "$RAW_LOG" >/dev/null; }

# run <user|harness> <step-name> <command...>
run() {
  local kind="$1" name="$2"; shift 2
  local started rc
  STEP="$name"
  write_status
  printf '\n$ %s\n' "$*" >> "$RAW_LOG"
  [ "$kind" = user ] && printf '%s\n' "$*" >> "$RAW_CMDS"
  started="$(date +%s)"
  "$@" < /dev/null >> "$RAW_LOG" 2>&1
  rc=$?
  printf '[exit %s, %ss]\n' "$rc" "$(( $(date +%s) - started ))" >> "$RAW_LOG"
  STEPS+=("$name|$kind|$rc|$(( $(date +%s) - started ))")
  publish
  return "$rc"
}

# Records an operator shell-state command (cd, source) that the harness applies itself.
note_user() { printf '\n$ %s\n' "$*" >> "$RAW_LOG"; printf '%s\n' "$*" >> "$RAW_CMDS"; }

spoke_groups() {
  local key value
  for key in AZURE_RESOURCE_GROUP AZURE_APP_RESOURCE_GROUP AZURE_NETWORK_RESOURCE_GROUP; do
    value="$(cd "$REPO_DIR" && azd env get-value "$key" 2>/dev/null)" || continue
    [ -n "$value" ] && az group exists -n "$value" 2>/dev/null | grep -q true && printf '%s\n' "$value"
  done | sort -u
}

connect_hub() {
  local rg spoke_vnet zone
  spoke_vnet=""
  for rg in $(spoke_groups); do
    [ -z "$spoke_vnet" ] && spoke_vnet="$(az network vnet list -g "$rg" --query '[0].id' -o tsv)"
  done
  [ -n "$spoke_vnet" ] || { echo "Spoke VNet not found in the deployment resource groups."; return 1; }
  echo "Spoke VNet: $spoke_vnet"
  az network vnet peering create -g "$HUB_RG" --vnet-name "$HUB_VNET" -n "$HUB_PEERING" \
    --remote-vnet "$spoke_vnet" --allow-vnet-access --allow-forwarded-traffic --only-show-errors \
    --query '{name:name,state:peeringState}' -o tsv || return 1
  for rg in $(spoke_groups); do
    for zone in $(az network private-dns zone list -g "$rg" --query '[].name' -o tsv); do
      printf 'link %s: ' "$zone"
      az network private-dns link vnet create -g "$rg" -z "$zone" -n "$HUB_LINK" \
        --virtual-network "$HUB_VNET_ID" --registration-enabled false --only-show-errors \
        --query virtualNetworkLinkState -o tsv || return 1
    done
  done
}

disconnect_hub() {
  local rg zone rc=0
  for rg in $(spoke_groups); do
    for zone in $(az network private-dns zone list -g "$rg" --query '[].name' -o tsv 2>/dev/null); do
      if az network private-dns link vnet show -g "$rg" -z "$zone" -n "$HUB_LINK" >/dev/null 2>&1; then
        az network private-dns link vnet delete -g "$rg" -z "$zone" -n "$HUB_LINK" --yes \
          --only-show-errors && echo "unlinked $zone" || rc=1
      fi
    done
  done
  if az network vnet peering show -g "$HUB_RG" --vnet-name "$HUB_VNET" -n "$HUB_PEERING" >/dev/null 2>&1; then
    az network vnet peering delete -g "$HUB_RG" --vnet-name "$HUB_VNET" -n "$HUB_PEERING" \
      --only-show-errors && echo "deleted peering $HUB_PEERING" || rc=1
  fi
  return "$rc"
}

verify_removed() {
  local rg rc=0
  for rg in "${TRACKED_GROUPS[@]:-}"; do
    [ -z "$rg" ] && continue
    if [ "$(az group exists -n "$rg")" = "true" ]; then
      echo "Resource group $rg still exists."; rc=1
    else
      echo "Resource group $rg removed."
    fi
  done
  return "$rc"
}

purge_deleted_accounts() {
  # A soft-deleted Foundry account keeps its service association link on the
  # agent subnet, which blocks deleting the network group until it is purged.
  local rg id name location
  for rg in "${TRACKED_GROUPS[@]:-}"; do
    [ -z "$rg" ] && continue
    while IFS=$'\t' read -r id name location; do
      [ -z "$id" ] && continue
      az cognitiveservices account purge -g "$rg" -n "$name" -l "$location" --only-show-errors \
        && echo "purged deleted account $name"
    done < <(az cognitiveservices account list-deleted \
      --query "[?contains(id, '/resourceGroups/$rg/')].[id, name, location]" -o tsv 2>/dev/null)
  done
}

force_delete_groups() {
  local rg attempt
  for rg in "${TRACKED_GROUPS[@]:-}"; do
    [ -z "$rg" ] || [[ "$rg" == *-network ]] && continue
    [ "$(az group exists -n "$rg")" = "true" ] && az group delete -n "$rg" --yes --only-show-errors
  done
  purge_deleted_accounts
  for attempt in 1 2 3; do
    for rg in "${TRACKED_GROUPS[@]:-}"; do
      [ -z "$rg" ] && continue
      [ "$(az group exists -n "$rg")" = "true" ] && az group delete -n "$rg" --yes --only-show-errors
    done
    verify_removed && return 0
    sleep 120
    purge_deleted_accounts
  done
  verify_removed
}

TRACKED_GROUPS=()
PROVISIONED=false

teardown() {
  [ "$PROVISIONED" = true ] || { TEARDOWN="skipped-not-provisioned"; return 0; }
  if [ "$KEEP_ENVIRONMENT" = "true" ]; then
    TEARDOWN="kept-on-request"
    log "Environment kept on request. Remove it later with: azd down --force --purge"
    return 0
  fi
  log "Teardown"
  cd "$REPO_DIR" || return 1
  local current
  current="$(spoke_groups)"
  [ -n "$current" ] && mapfile -t TRACKED_GROUPS <<< "$current"
  if [ "${#TRACKED_GROUPS[@]}" -eq 0 ]; then
    TEARDOWN="nothing-to-remove"
    log "No resource group was created, nothing to remove"
    return 0
  fi
  run harness "disconnect-hub" disconnect_hub
  if [ "${WAIT_FOR_TEARDOWN:-false}" != "true" ]; then
    # Deletion often hangs on locked resources, so start it and do not wait.
    local rg
    for rg in "${TRACKED_GROUPS[@]}"; do
      [ -n "$rg" ] && az group delete -n "$rg" --yes --no-wait --only-show-errors || true
    done
    TEARDOWN="started-no-wait"
    log "Deletion started without waiting for: ${TRACKED_GROUPS[*]}"
    return 0
  fi
  if { run user "azd-down" azd down --force --purge --no-prompt \
        || { sleep 120; run user "azd-down-retry" azd down --force --purge --no-prompt; }; } \
      && run harness "verify-removed" verify_removed; then
    TEARDOWN="succeeded"
  else
    run harness "force-delete-groups" force_delete_groups
    TEARDOWN="failed-forced-cleanup"
  fi
}

finish() {
  local rc=$?
  trap - EXIT
  [ -n "$RESULT" ] || RESULT="failed"
  # The result reflects deploy and smoke test only. Teardown is best effort and
  # reported separately, because Azure often keeps a resource locked for a while.
  teardown
  STATE="completed"
  STEP="done"
  log "Result: $RESULT (teardown: $TEARDOWN)"
  publish
  kill "${UPLOADER_PID:-0}" 2>/dev/null || true
  if [ "${SELF_DEALLOCATE:-false}" = "true" ]; then
    # Wait until the workflow collected the evidence (it writes the marker),
    # at most 30 minutes, then stop the VM.
    for _ in $(seq 1 180); do
      [ -e "$OUT/collected" ] && break
      sleep 10
    done
    az vm deallocate -g "$HUB_RG" -n "$(hostname)" --no-wait --only-show-errors || true
  fi
  exit "$rc"
}
trap finish EXIT

# Periodic upload so the workflow can follow long Terraform operations.
( while sleep 60; do publish_logs; done ) &
UPLOADER_PID=$!

fail() { RESULT="failed"; log "FAILED at step: $STEP"; exit 1; }

log "Release validation $RELEASE_TAG ($PROVIDER_TITLE, NETWORK_ISOLATION=true) in $AZURE_LOCATION"

log "Sign in (the executor uses its managed identity; operators use az login and azd auth login)"
run harness "az-login" az login --identity --client-id "$EXECUTOR_CLIENT_ID" --allow-no-subscriptions \
  --query '[0].user.type' -o tsv || fail
EXECUTOR_PRINCIPAL_ID="$(az identity list -g "$HUB_RG" \
  --query "[?clientId=='$EXECUTOR_CLIENT_ID'].principalId | [0]" -o tsv 2>/dev/null || true)"
run user "az-account-set" az account set --subscription "$AZURE_SUBSCRIPTION_ID" || fail
pin_storage_endpoint() {
  local id ip host
  id="$(az storage account show -g "$STORAGE_RESOURCE_GROUP" -n "$STORAGE_ACCOUNT" --query id -o tsv)" || return 1
  ip="$(az network private-endpoint list -g "$STORAGE_RESOURCE_GROUP" \
    --query "[?privateLinkServiceConnections[0].privateLinkServiceId=='$id'].customDnsConfigs[0].ipAddresses[0] | [0]" -o tsv)" || return 1
  [ -n "$ip" ] || { echo "no private endpoint for the harness storage account"; return 1; }
  host="$STORAGE_ACCOUNT.blob.core.windows.net"
  sed -i "/[[:space:]]$host\$/d" /etc/hosts
  echo "$ip $host" >> /etc/hosts
  echo "$host -> $ip"
}
run harness "pin-storage-endpoint" pin_storage_endpoint || fail
publish
run harness "azd-use-az-cli-auth" azd config set auth.useAzCliAuth true || fail
run harness "tool-versions" bash -c 'az version --query "\"azure-cli\"" -o tsv; azd version; terraform version | head -n1; python3 --version' || fail
run harness "azd-ai-agents-extension" bash -c 'azd extension list --installed 2>/dev/null | grep -q azure.ai.agents || azd extension install azure.ai.agents --no-prompt' || fail

log "Get the release"
cd "$WORK" || fail
run user "git-clone" git clone --depth 1 --branch "$SOURCE_REF" "https://github.com/$REPOSITORY.git" agent-landing-zone || fail
REPO_DIR="$WORK/agent-landing-zone"
note_user "cd agent-landing-zone"
cd "$REPO_DIR" || fail

if [ "$PROVIDER" = "terraform" ]; then
  log "Select the Terraform provider in azure.yaml"
  run user "select-terraform" sed -i -E \
    -e 's#^(  provider:).*#\1 terraform#' -e 's#^(  path:) infra/bicep.*#\1 infra/terraform#' \
    -e 's#^(  module:).*#\1 main#' azure.yaml || fail
fi
run harness "show-infra-block" bash -c "sed -n '/^infra:/,/^hooks:/p' azure.yaml" || fail
grep -qE "^  provider: $PROVIDER\b" azure.yaml || { log "azure.yaml does not select $PROVIDER"; fail; }

log "Python environment for the lifecycle hooks"
run user "python-venv" python3 -m venv .venv || fail
note_user "source .venv/bin/activate"
# shellcheck disable=SC1091
source .venv/bin/activate || fail
run user "pip-install" pip install --quiet -r config/requirements.txt || fail

log "Create and configure the azd environment"
run user "azd-env-new" azd env new "$ENV_NAME" --subscription "$AZURE_SUBSCRIPTION_ID" \
  --location "$AZURE_LOCATION" --no-prompt || fail
set_env() { run user "azd-env-set-$1" azd env set "$1" "$2" || fail; }
set_env AZURE_SUBSCRIPTION_ID "$AZURE_SUBSCRIPTION_ID"
set_env AZURE_LOCATION "$AZURE_LOCATION"
set_env AZURE_RESOURCE_GROUP "rg-$ENV_NAME"
set_env CREATE_RESOURCE_GROUPS true
if [ "$PROVIDER" = "terraform" ]; then
  set_env TF_STATE_RESOURCE_GROUP "$STORAGE_RESOURCE_GROUP"
  set_env TF_STATE_STORAGE_ACCOUNT "$STORAGE_ACCOUNT"
  set_env TF_STATE_CONTAINER tfstate
fi
set_env HOSTED_AGENT_RESOURCE_SCOPE "$HOSTED_AGENT_RESOURCE_SCOPE"
while IFS='=' read -r key value; do
  [[ -z "$key" || "$key" == \#* ]] && continue
  set_env "$key" "$value"
done < "$SCENARIO_FILE"
set_env HUB_INTEGRATION_HUB_VNET_RESOURCE_ID "$HUB_VNET_ID"
# The spoke private endpoints are reachable only after provisioning, so the
# first postprovision run defers data-plane configuration (documented flow).
set_env RUN_FROM_JUMPBOX false

log "Provision the foundation"
PROVISIONED=true
PROVISION_LOG_START="$(wc -c < "$RAW_LOG")"
run user "azd-provision" azd provision --no-prompt
PROVISION_RC=$?
# Azure intermittently fails private endpoint operations with a bare
# InternalServerError. azd provision is idempotent, so the operator reruns it.
# grep reads a process substitution, not a pipe: grep -q exits on the first
# match, tail then gets SIGPIPE, and pipefail would turn the match into a miss.
provision_failed_transiently() {
  grep -q 'InternalServerError' < <(tail -c +"$(($1 + 1))" "$RAW_LOG")
}
PROVISION_RETRY=0
while [ "$PROVISION_RC" -ne 0 ] && [ "$PROVISION_RETRY" -lt 2 ] \
  && provision_failed_transiently "$PROVISION_LOG_START"; do
  PROVISION_RETRY=$((PROVISION_RETRY + 1))
  log "Rerun provisioning after a transient Azure InternalServerError (retry $PROVISION_RETRY)"
  PROVISION_LOG_START="$(wc -c < "$RAW_LOG")"
  run user "azd-provision-retry-$PROVISION_RETRY" azd provision --no-prompt
  PROVISION_RC=$?
done
mapfile -t TRACKED_GROUPS < <(spoke_groups)
[ "$PROVISION_RC" -eq 0 ] || fail

log "Connect the validation hub to the spoke (operators use their own VPN or VNet)"
run harness "connect-hub" connect_hub || fail
run harness "dns-propagation-wait" sleep 60 || fail

log "Resume the deferred data-plane configuration from the connected host"
set_env RUN_FROM_JUMPBOX true
set_env AZURE_SKIP_NETWORK_ISOLATION_WARNING false
run user "azd-hooks-postprovision" azd hooks run postprovision --no-prompt || fail

log "Deploy the applications (preDeploy runs the private network gate and agent smoke test)"
run user "azd-deploy" azd deploy --no-prompt || fail

log "Post-deployment checks"
run harness "deployment-inventory" bash -c '
  for rg in $(printf "%s\n" "$@" | sort -u); do
    echo "Resource group $rg:"
    az resource list -g "$rg" --query "[].type" -o tsv | sort | uniq -c
  done' _ "${TRACKED_GROUPS[@]}" || fail

RESULT="passed"
exit 0
