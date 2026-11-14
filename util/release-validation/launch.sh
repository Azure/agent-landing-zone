#!/usr/bin/env bash
# Prints a Run Command script that installs run-validation.sh on the executor VM
# and starts it as a transient systemd unit, so it survives the Run Command
# time limit. Inputs come from the environment and are validated here because
# they are embedded in the generated script.
set -euo pipefail

need() { [[ "${!1:-}" =~ $2 ]] || { echo "Invalid or missing $1" >&2; exit 2; }; }
need RELEASE_TAG '^v[0-9]+\.[0-9]+\.[0-9]+$'
need RUN_KEY '^[0-9A-Za-z-]{1,40}$'
need AZ_LOCATION '^[a-z0-9]+$'
need HOSTED_SCOPE '^[A-Za-z0-9:/._-]+/\.default$'
need KEEP_ENVIRONMENT '^(true|false)$'
need SUBSCRIPTION_ID '^[0-9a-fA-F-]{36}$'
need TENANT_ID '^[0-9a-fA-F-]{36}$'
need EXECUTOR_CLIENT_ID '^[0-9a-fA-F-]{36}$'
need HUB_VNET_ID '^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9._()-]+/providers/Microsoft\.Network/virtualNetworks/[A-Za-z0-9._-]+$'
need STORAGE_ACCOUNT '^[a-z0-9]{3,24}$'
need HUB_RG '^[A-Za-z0-9._()-]+$'
REPOSITORY="${GITHUB_REPOSITORY:-Azure/agent-landing-zone}"
need REPOSITORY '^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$'

payload="$(base64 -w0 "$(dirname "$0")/run-validation.sh")"
work="/var/lib/relval/$RUN_KEY"

cat <<EOF
set -eu
if systemctl list-units --type=service --state=active --no-legend 'relval-*' | grep -q relval-; then
  echo "Another validation is still running on this executor."; exit 1
fi
mkdir -p "$work"
chmod 700 /var/lib/relval "$work"
echo '$payload' | base64 -d > "$work/run-validation.sh"
cat > "$work/params.env" <<'PARAMS'
RELEASE_TAG=$RELEASE_TAG
RUN_ID=$RUN_KEY
AZURE_SUBSCRIPTION_ID=$SUBSCRIPTION_ID
AZURE_TENANT_ID=$TENANT_ID
AZURE_LOCATION=$AZ_LOCATION
EXECUTOR_CLIENT_ID=$EXECUTOR_CLIENT_ID
HUB_VNET_ID=$HUB_VNET_ID
STORAGE_ACCOUNT=$STORAGE_ACCOUNT
STORAGE_RESOURCE_GROUP=$HUB_RG
HOSTED_AGENT_RESOURCE_SCOPE=$HOSTED_SCOPE
KEEP_ENVIRONMENT=$KEEP_ENVIRONMENT
REPOSITORY=$REPOSITORY
SELF_DEALLOCATE=true
PARAMS
systemd-run --unit "relval-$RUN_KEY" --collect --property=EnvironmentFile="$work/params.env" \
  /bin/bash "$work/run-validation.sh"
echo "launched relval-$RUN_KEY"
EOF
