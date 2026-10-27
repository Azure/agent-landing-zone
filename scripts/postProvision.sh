#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Ensure the temporary venv is always cleaned up, even on early exits.
# Cleanup failures must never cause the post-provision hook to report failure.
cleanup() {
  deactivate 2>/dev/null || true
  rm -rf config/.venv_temp 2>/dev/null || true
}
trap cleanup EXIT

echo "🔧 Running post-provision steps..."
echo

#-------------------------------------------------------------------------------
# Mirror azd environment variables into process environment
# This avoids persisting secrets in the User environment (registry)
#-------------------------------------------------------------------------------

command -v jq >/dev/null 2>&1 || { echo "jq is required to load the selected azd environment." >&2; exit 1; }
azd_values="$(azd env get-values --output json)" || {
  echo "Could not load the selected azd environment; refusing to configure resources." >&2
  exit 1
}
jq -e 'type == "object" and length > 0 and all(to_entries[];
  (.key | test("^[A-Za-z_][A-Za-z0-9_]*$")) and
  (.value | type == "string") and (.value | contains("\u0000") | not))' \
  <<< "$azd_values" >/dev/null || { echo "Invalid azd environment JSON, key or value." >&2; exit 1; }
while IFS= read -r -d '' key && IFS= read -r -d '' value; do
  export "$key=$value"
done < <(jq -b -j 'to_entries[] | .key, "\u0000", .value, "\u0000"' <<< "$azd_values")

is_truthy() {
  case "$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|t|yes|y) return 0 ;;
    *) return 1 ;;
  esac
}

#-------------------------------------------------------------------------------
# Private deployment-host prerequisite (before data-plane configuration)
#-------------------------------------------------------------------------------
(cd "$PROJECT_ROOT" && python3 -m config.deployment.resource_groups --azure-dir "$PROJECT_ROOT/.azure" --bind-only) >/dev/null || {
  echo "Resource-group destination binding failed; configuration has not started." >&2
  exit 1
}
network_exit=0
(cd "$PROJECT_ROOT" && python3 -m config.deployment.private_network --stage post-provision) || network_exit=$?
if [ "$network_exit" -eq 20 ]; then
  echo "Post-provision configuration explicitly deferred; application setup is incomplete."
  exit 0
elif [ "$network_exit" -ne 0 ]; then
  echo "Private post-provision prerequisites failed. Connect through VPN/VNet and rerun postProvision; configuration has not started." >&2
  exit "$network_exit"
fi

#-------------------------------------------------------------------------------
# Container APP API Keys Warning
#-------------------------------------------------------------------------------
echo
if is_truthy "${USE_CAPP_API_KEY:-false}"; then
  echo "🔑 Using API Key for Container Apps access."
  echo "⚠️ IMPORTANT: Each App API Key was initialized with resourceToken."
  echo "    Please update to a custom API key ASAP."
fi

###############################################################################
# Check required environment variable
###############################################################################
echo "📋 Current environment variables:"
for v in APP_CONFIG_ENDPOINT ; do
  printf "  %s=%s\n" "$v" "${!v:-<unset>}"
done

if [[ -z "${APP_CONFIG_ENDPOINT:-}" ]]; then
  echo "❗️ APP_CONFIG_ENDPOINT environment variable must be set before running this script."
  exit 1
fi

echo "⚙️ Publishing Agent Landing Zone deployment-mode configuration…"
(
  cd "$PROJECT_ROOT"
  python3 -m config.deployment.appconfig
)
echo "✅ Deployment-mode configuration published."

###############################################################################
# Setup Python environment
###############################################################################
echo "📦 Creating temporary venv…"
python3 -m venv --without-pip config/.venv_temp
source config/.venv_temp/bin/activate
echo "⬇️ Manually bootstrapping pip…"
curl -sS https://bootstrap.pypa.io/get-pip.py | python

echo "⬇️  Installing requirements…"
pip install --upgrade pip
pip install -r config/requirements.txt

###############################################################################
# Application definition: placeholder plan for containerapp components only
# (from config.appdefinition effective_components), capability-profile roles,
# then platform outputs. No application image is built during provision.
###############################################################################
echo "📦 Checking placeholder Container Apps for the application definition…"
(cd "$PROJECT_ROOT" && python -m config.deployment.existing_images) || {
  echo "Failed to plan placeholder Container Apps for the application definition." >&2
  exit 1
}
echo "🔐 Assigning capability-profile roles to component identities…"
(cd "$PROJECT_ROOT" && python -m config.appdefinition --assign-roles) || {
  echo "Failed to assign capability-profile roles to component identities." >&2
  exit 1
}
echo "📤 Publishing platform outputs (AGENTLZ_PLATFORM_OUTPUTS)…"
(cd "$PROJECT_ROOT" && python -m config.deployment.outputs) || {
  echo "Failed to publish platform outputs to App Configuration." >&2
  exit 1
}

###############################################################################
# 1) Governance and audit configuration
###############################################################################
echo
echo "🔐 Governance and audit configuration…"
python -m config.governance.setup
echo "✅ Governance and audit configuration finished."

###############################################################################
# 2) Hosted conversation continuity
###############################################################################
echo
echo "🔐 Publishing fail-closed delegated continuity defaults…"
python -m config.continuity.setup
echo "✅ Fail-closed delegated continuity defaults published."

###############################################################################
# 3) AI Foundry Setup
###############################################################################
echo
echo "📑 AI Foundry Setup…"
{
  echo "🚀 Running config.aifoundry.aifoundry_setup…"
  python -m config.aifoundry.setup
  echo "✅ AI Foundry setup script finished."
} || {
  echo "❗️ Error during AI Foundry setup." >&2
  exit 1
}

###############################################################################
# 4) Container Apps Setup
###############################################################################
echo
echo "🔍 ContainerApp setup…"
{
  echo "🚀 Running config.containerapps.setup…"
  python -m config.containerapps.setup
  echo "✅ Container Apps setup script finished."
} || {
  echo "❗️ Error during Container Apps setup." >&2
  exit 1
}

###############################################################################
# 5) AI Search Setup
###############################################################################
echo
echo "🔍 AI Search setup…"
{
  echo "🚀 Running config.search.setup…"
  python -m config.search.setup
  echo "✅ Search setup script finished."
} || {
  echo "❗️ Error during Search setup." >&2
  exit 1
}

###############################################################################
# 6) Administrative panel Cosmos RBAC (issue #611, ADR-0004)
###############################################################################
echo
echo "🔐 Administrative panel Cosmos RBAC…"
{
  echo "🚀 Running config.panel.setup…"
  python -m config.panel.setup
  echo "✅ Administrative panel Cosmos RBAC finished (no-op unless DEPLOY_ADMINISTRATIVE_PANEL=true)."
} || {
  echo "❗️ Error during administrative panel Cosmos RBAC setup." >&2
  exit 1
}

###############################################################################
# Cleaning up
###############################################################################
echo
echo "🧹 Cleaning Python environment up…"
# `deactivate` only restores shell variables (PATH, PS1) — it deletes nothing.
# Since the script is ending, there is nothing to restore. We skip it and
# go straight to removing the venv directory.
# python3's shutil.rmtree handles locked files and open __pycache__ handles
# (common on macOS with Python 3.12+) without raising, unlike `rm -rf`.
python3 -c "import shutil; shutil.rmtree('config/.venv_temp', ignore_errors=True)"

echo
echo "✅ postProvisioning completed."
