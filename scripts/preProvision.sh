#!/bin/sh

## Displays a warning to the user if AZURE_NETWORK_ISOLATION is set

YELLOW='\033[0;33m'
BLUE='\033[0;34m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

###############################################################################
# Mirror azd environment variables into process environment
# This avoids persisting secrets in the User environment, and makes any
# previously-persisted Agent Landing Zone topology markers (AZURE_RESOURCE_GROUP,
# APP_CONFIG_ENDPOINT, DEPLOYMENT_TOPOLOGY, ...) visible to the topology
# resolution step below on a second/subsequent 'azd provision' run.
# 'azd env get-values' already emits POSIX-shell-safe KEY="value" lines, so
# eval'ing them directly (rather than piping into a subshell 'while read'
# loop, whose exports would not survive the pipe under POSIX sh) is safe.
###############################################################################
eval "$(azd env get-values 2>/dev/null | sed 's/^/export /')" || true

###############################################################################
# Locate the repository root by its markers (manifest.json plus azure.yaml),
# not by folder name.
###############################################################################
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
find_repo_root() {
    p="$1"
    while :; do
        if [ -f "$p/manifest.json" ] && [ -f "$p/azure.yaml" ]; then
            printf '%s' "$p"
            return 0
        fi
        parent="$(dirname "$p")"
        [ "$parent" = "$p" ] && return 1
        p="$parent"
    done
}
if ! PROJECT_ROOT="$(find_repo_root "$SCRIPT_DIR")"; then
    echo "${YELLOW}Error: Could not locate the repository root (a folder containing manifest.json and azure.yaml).${NC}"
    exit 1
fi
AGENTLZ_REPO_ROOT="$PROJECT_ROOT"
export AGENTLZ_REPO_ROOT
INFRA_DIR="$PROJECT_ROOT/infra"
MAIN_BICEP="$INFRA_DIR/main.bicep"
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "${YELLOW}Error: Python is required to compose the Agent Landing Zone deployment mode.${NC}"
    exit 1
fi

###############################################################################
# Application definition: validate and bind before any Azure change.
###############################################################################
APP_DEFINITION_PATH="${AGENTLZ_APP_DEFINITION:-$PROJECT_ROOT/app-definition.json}"
case "$APP_DEFINITION_PATH" in
    /*) ;;
    *) APP_DEFINITION_PATH="$PROJECT_ROOT/$APP_DEFINITION_PATH" ;;
esac
if [ -d "$APP_DEFINITION_PATH" ]; then
    APP_DEFINITION_PATH="$APP_DEFINITION_PATH/app-definition.json"
fi
if [ ! -f "$APP_DEFINITION_PATH" ]; then
    echo "${YELLOW}Error: AGENTLZ_APP_DEFINITION points to $APP_DEFINITION_PATH, which does not exist.${NC}"
    exit 1
fi
echo "${CYAN}Validating and binding application definition...${NC}"
# Exit codes: 1 invalid definition, 2 binding mismatch (see config/appdefinition/__main__.py).
if [ -n "${AZURE_ENV_NAME:-}" ]; then
    (cd "$PROJECT_ROOT" && "$PYTHON_CMD" -m config.appdefinition --validate "$APP_DEFINITION_PATH" --bind --azure-dir "$PROJECT_ROOT/.azure" --env-name "$AZURE_ENV_NAME")
else
    (cd "$PROJECT_ROOT" && "$PYTHON_CMD" -m config.appdefinition --validate "$APP_DEFINITION_PATH" --bind --azure-dir "$PROJECT_ROOT/.azure")
fi
APPDEF_EXIT=$?
if [ $APPDEF_EXIT -eq 2 ]; then
    echo "${YELLOW}Error: Application definition binding failed. No Azure changes were made.${NC}"
    exit $APPDEF_EXIT
fi
if [ $APPDEF_EXIT -ne 0 ]; then
    echo "${YELLOW}Error: Application definition validation failed. No Azure changes were made.${NC}"
    exit $APPDEF_EXIT
fi

###############################################################################
# Infrastructure is repository-owned source under infra/ (no submodule).
###############################################################################
if [ ! -f "$PROJECT_ROOT/manifest.json" ]; then
    echo "${YELLOW}Error: manifest.json is required to resolve release pins.${NC}"
    exit 1
fi
if [ ! -f "$MAIN_BICEP" ]; then
    echo "${YELLOW}Error: infra/main.bicep was not found. The infrastructure is part of this repository; restore infra/ from source control.${NC}"
    exit 1
fi

###############################################################################
# ADR-0001 rev. 5: resolve and materialize the Agent Landing Zone deployment topology
###############################################################################
# Resolve the topology (fresh default, sticky existing/persisted-classic,
# explicit override, or a fail-closed error with migration guidance on
# conflicting persisted signals) before composing main.parameters.json.
# Materializing DEPLOYMENT_TOPOLOGY (and the paired legacy flags) into both
# the process environment and the azd environment here is what lets
# preDeploy/postProvision read back the exact same decision later via
# 'config.deployment.topology --describe', with no further Azure CLI lookups
# and no duplicated detection logic.
echo "${CYAN}Resolving Agent Landing Zone deployment topology...${NC}"
TOPOLOGY_OUTPUT="$(cd "$PROJECT_ROOT" && "$PYTHON_CMD" -m config.deployment.topology)"
TOPOLOGY_EXIT=$?
if [ $TOPOLOGY_EXIT -ne 0 ]; then
    echo "${YELLOW}Error: Agent Landing Zone deployment topology resolution failed.${NC}"
    exit $TOPOLOGY_EXIT
fi

eval "$(printf '%s\n' "$TOPOLOGY_OUTPUT" | sed 's/^\([^=]*\)=\(.*\)$/export \1="\2"/')"

TOPOLOGY_PERSIST_FAILED=false
while IFS='=' read -r TOPO_KEY TOPO_VALUE; do
    [ -z "$TOPO_KEY" ] && continue
    if [ -n "${AZURE_ENV_NAME:-}" ]; then
        if ! azd env set "$TOPO_KEY" "$TOPO_VALUE" --environment "$AZURE_ENV_NAME" --no-prompt >/dev/null; then
            TOPOLOGY_PERSIST_FAILED=true
            break
        fi
    else
        if ! azd env set "$TOPO_KEY" "$TOPO_VALUE" --no-prompt >/dev/null; then
            TOPOLOGY_PERSIST_FAILED=true
            break
        fi
    fi
done <<EOF
$TOPOLOGY_OUTPUT
EOF
if [ "$TOPOLOGY_PERSIST_FAILED" = "true" ]; then
    echo "${YELLOW}Error: Failed to persist the resolved deployment topology.${NC}"
    exit 1
fi

echo "${CYAN}Composing Agent Landing Zone deployment mode...${NC}"
HOSTED_SOURCE_COMMIT="$("$PYTHON_CMD" -c 'import json,sys; print(next(c["commit"] for c in json.load(open(sys.argv[1], encoding="utf-8"))["components"] if c["name"].endswith("-orchestrator")))' "$PROJECT_ROOT/manifest.json")"
(
    cd "$PROJECT_ROOT" &&
    "$PYTHON_CMD" -m config.deployment.composition \
        --input "$PROJECT_ROOT/main.parameters.json" \
        --output "$INFRA_DIR/main.parameters.json" \
        --hosted-source-commit "$HOSTED_SOURCE_COMMIT"
)
COMPOSE_EXIT=$?
if [ $COMPOSE_EXIT -ne 0 ]; then
    echo "${YELLOW}Error: Agent Landing Zone deployment mode composition failed.${NC}"
    exit $COMPOSE_EXIT
fi

# The composed infra/main.parameters.json is environment-specific; hide local
# regeneration from git status so the committed seed stays untouched.
if command -v git >/dev/null 2>&1 &&
    [ "$(git -C "$PROJECT_ROOT" rev-parse --is-inside-work-tree 2>/dev/null)" = "true" ] &&
    git -C "$PROJECT_ROOT" ls-files --error-unmatch infra/main.parameters.json >/dev/null 2>&1; then
    git -C "$PROJECT_ROOT" update-index --skip-worktree infra/main.parameters.json >/dev/null 2>&1 ||
        echo "${YELLOW}Note: could not mark infra/main.parameters.json as skip-worktree; it may appear as modified in git status.${NC}"
fi

###############################################################################
# Agent Landing Zone regional readiness preflight
###############################################################################

REGIONAL_PREFLIGHT_SCRIPT="$SCRIPT_DIR/Invoke-RegionalPreflight.ps1"
if [ -f "$REGIONAL_PREFLIGHT_SCRIPT" ] && [ "$PREFLIGHT_SKIP" != "true" ] && [ "$PREFLIGHT_SKIP" != "1" ] && [ "$AGENTLZ_REGIONAL_PREFLIGHT_SKIP" != "true" ] && [ "$AGENTLZ_REGIONAL_PREFLIGHT_SKIP" != "1" ]; then
    if command -v pwsh >/dev/null 2>&1; then
        echo "${CYAN}Running Agent Landing Zone regional preflight...${NC}"
        pwsh -NoProfile -File "$REGIONAL_PREFLIGHT_SCRIPT" -ProjectRoot "$PROJECT_ROOT" -ParameterFile "$INFRA_DIR/main.parameters.json"
        REGIONAL_PREFLIGHT_EXIT=$?
        if [ $REGIONAL_PREFLIGHT_EXIT -ne 0 ]; then
            echo "${YELLOW}Agent Landing Zone regional preflight failed. Fix the reported blockers, or set AGENTLZ_REGIONAL_PREFLIGHT_SKIP=true to bypass only this check.${NC}"
            exit $REGIONAL_PREFLIGHT_EXIT
        fi
    else
        echo "${CYAN}Skipping Agent Landing Zone regional preflight (pwsh not installed; install PowerShell 7 to enable).${NC}"
    fi
fi

###############################################################################
# AI Landing Zone v2.0.4+ preflight validation
# https://github.com/Azure/bicep-ptn-aiml-landing-zone/blob/v2.0.4/scripts/Invoke-PreflightChecks.ps1
# Covers parameter/topology/BYO/IP checks plus regional readiness (subscription
# drift, provider/location, AI Search & Cosmos capacity warnings, jumpbox VM SKU,
# model quota).
###############################################################################

PREFLIGHT_SCRIPT="$INFRA_DIR/scripts/Invoke-PreflightChecks.ps1"
if [ -f "$PREFLIGHT_SCRIPT" ] && [ "$PREFLIGHT_SKIP" != "true" ] && [ "$PREFLIGHT_SKIP" != "1" ]; then
    if command -v pwsh >/dev/null 2>&1; then
        echo "${CYAN}Running landing-zone preflight checks...${NC}"
        pwsh -NoProfile -File "$PREFLIGHT_SCRIPT"
        PREFLIGHT_EXIT=$?
        if [ $PREFLIGHT_EXIT -ne 0 ]; then
            echo "${YELLOW}Preflight checks failed. Fix the reported parameter issues, or set PREFLIGHT_SKIP=true to bypass.${NC}"
            exit $PREFLIGHT_EXIT
        fi
    else
        echo "${CYAN}Skipping preflight checks (pwsh not installed; install PowerShell 7 to enable).${NC}"
    fi
fi

###############################################################################
# 1) Network Isolation Warning
###############################################################################

# Skip warning if AZURE_SKIP_NETWORK_ISOLATION_WARNING is set
if [ "$AZURE_SKIP_NETWORK_ISOLATION_WARNING" -ge 1 ] 2>/dev/null || [ "$AZURE_SKIP_NETWORK_ISOLATION_WARNING" = "true" ] || [ "$AZURE_SKIP_NETWORK_ISOLATION_WARNING" = "t" ]; then
    exit 0
fi

# Show warning if AZURE_NETWORK_ISOLATION is enabled
if [ "$AZURE_NETWORK_ISOLATION" -ge 1 ] 2>/dev/null || [ "$AZURE_NETWORK_ISOLATION" = "true" ] || [ "$AZURE_NETWORK_ISOLATION" = "t" ]; then
    
    echo "${YELLOW}Warning!${NC} AZURE_NETWORK_ISOLATION is enabled."
    echo " - After provisioning, you must switch to the ${GREEN}Virtual Machine & Bastion${NC} to continue deploying components."
    echo " - Infrastructure will only be reachable from within the Bastion host."

    echo -n "${BLUE}?${NC} Continue with Zero Trust provisioning? [Y/n]: "
    read confirmation

    if [ "$confirmation" != "Y" ] && [ "$confirmation" != "y" ] && [ -n "$confirmation" ]; then
        exit 1
    fi
fi

exit 0
