#!/usr/bin/env bash
# Prints a Run Command script that installs run-validation.sh on the executor VM
# and starts it as a transient systemd unit, so it survives the Run Command
# time limit. Inputs come from the environment and are validated here because
# they are embedded in the generated script.
set -euo pipefail

need() { [[ "${!1:-}" =~ $2 ]] || { echo "Invalid or missing $1" >&2; exit 2; }; }
need RELEASE_TAG '^v[0-9]+\.[0-9]+\.[0-9]+$'
need PROVIDER '^(bicep|terraform)$'
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
SOURCE_REF="${SOURCE_REF:-$RELEASE_TAG}"
need SOURCE_REF '^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$'

payload="$(base64 -w0 "$(dirname "$0")/run-validation.sh")"
scenario="$(base64 -w0 "$(dirname "$0")/scenario.env")"
work="/var/lib/relval/$RUN_KEY"

cat <<EOF
set -eu
# A cancelled or deleted workflow run leaves its unit running and blocks the
# executor. Units named after a workflow run id are stopped once GitHub reports
# that run as completed or missing. Other units, such as manual runs, are kept.
for unit in \$(systemctl list-units --type=service --state=active --no-legend --plain 'relval-*' | awk '{print \$1}'); do
  owner="\${unit#relval-}"; owner="\${owner%%-*}"
  case "\$owner" in ''|*[!0-9]*) continue ;; esac
  code="\$(curl -sS --max-time 20 -o /tmp/relval-owner.json -w '%{http_code}' \
    "https://api.github.com/repos/$REPOSITORY/actions/runs/\$owner" || true)"
  state="\$(jq -r '.status // empty' /tmp/relval-owner.json 2>/dev/null || true)"
  if [ "\$code" = 404 ] || { [ "\$code" = 200 ] && [ "\$state" = completed ]; }; then
    echo "Stopping \$unit: workflow run \$owner is no longer running."
    systemctl stop "\$unit" || true
  fi
done
if systemctl list-units --type=service --state=active --no-legend 'relval-*' | grep -q relval-; then
  echo "Another validation is still running on this executor."; exit 1
fi
mkdir -p "$work"
chmod 700 /var/lib/relval "$work"
echo '$payload' | base64 -d > "$work/run-validation.sh"
echo '$scenario' | base64 -d > "$work/scenario.env"
cat > "$work/params.env" <<'PARAMS'
RELEASE_TAG=$RELEASE_TAG
PROVIDER=$PROVIDER
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
SOURCE_REF=$SOURCE_REF
SELF_DEALLOCATE=true
PARAMS
systemd-run --unit "relval-$RUN_KEY" --collect --property=EnvironmentFile="$work/params.env" \
  /bin/bash "$work/run-validation.sh"
echo "launched relval-$RUN_KEY"
EOF
