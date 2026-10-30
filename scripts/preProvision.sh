#!/bin/sh

## Displays a warning to the user if AZURE_NETWORK_ISOLATION is set

YELLOW='\033[0;33m'
BLUE='\033[0;34m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

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
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "${YELLOW}Error: Python is required to compose the Agent Landing Zone deployment mode.${NC}"
    exit 1
fi

load_azd_environment_json() {
    if [ -n "${AZURE_ENV_NAME:-}" ]; then
        azd env get-values --output json --environment "$AZURE_ENV_NAME"
    else
        azd env get-values --output json
    fi
}

import_azd_environment() {
AZD_ENVIRONMENT_JSON="$(load_azd_environment_json)" || {
    echo "Cannot load the selected azd environment; provisioning has not started." >&2
    exit 1
}
AZD_ENVIRONMENT_EXPORTS="$(printf '%s' "$AZD_ENVIRONMENT_JSON" | "$PYTHON_CMD" -c '
import json, shlex, sys
import re
try:
    values = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit("Cannot read valid JSON from the selected azd environment; provisioning has not started.")
if not isinstance(values, dict) or not values:
    sys.exit("The selected azd environment must be a nonempty object.")
if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or not isinstance(value, str) or "\0" in value for key, value in values.items()):
    sys.exit("Invalid azd environment key or value; provisioning has not started.")
for key, value in values.items():
    print("export " + key + "=" + shlex.quote(value))
')" || exit 1
eval "$AZD_ENVIRONMENT_EXPORTS"
}

# BEGIN azd environment import
import_azd_environment
# END azd environment import

# BEGIN infrastructure provider validation
PROVIDER_OUTPUT="$(cd "$PROJECT_ROOT" && "$PYTHON_CMD" -m config.deployment.provider --repo-root "$PROJECT_ROOT")"
PROVIDER_EXIT=$?
if [ "$PROVIDER_EXIT" -ne 0 ]; then
    echo "Infrastructure provider validation failed; provisioning has not started." >&2
    exit "$PROVIDER_EXIT"
fi
INFRA_PROVIDER="$(printf '%s' "$PROVIDER_OUTPUT" | "$PYTHON_CMD" -c '
import json, sys
configuration = json.load(sys.stdin)
if not isinstance(configuration, dict) or configuration.get("provider") not in ("bicep", "terraform"):
    sys.exit("Infrastructure provider validation returned an unsupported provider.")
print(configuration["provider"])
')"
if [ $? -ne 0 ]; then
    echo "Infrastructure provider validation returned invalid configuration." >&2
    exit 1
fi
# END infrastructure provider validation

# Bicep composition follows azd's selected path/module. Terraform's separate
# parameter envelope is only diagnostic input for the shared preflights.
PARAMETER_DESTINATION="$(printf '%s' "$PROVIDER_OUTPUT" | "$PYTHON_CMD" -c '
import json, sys
from pathlib import Path
provider = json.load(sys.stdin)
root = Path(sys.argv[1])
if provider["provider"] == "bicep":
    print((root / provider["path"] / (provider["module"] + ".parameters.json")).resolve())
else:
    print(root / "infra/shared/main.parameters.json")
' "$PROJECT_ROOT")" || exit 1
MAIN_BICEP="${PARAMETER_DESTINATION%.parameters.json}.bicep"

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

# Terraform records ownership without creating groups; Bicep retains its bootstrap.
echo "${CYAN}Preparing workload resource-group destinations...${NC}"
RESOURCE_GROUP_MODULE="config.deployment.resource_groups"
if [ "$INFRA_PROVIDER" = "terraform" ]; then
    RESOURCE_GROUP_MODULE="config.deployment.terraform_groups"
    AZD_ENVIRONMENT_JSON="$(load_azd_environment_json)" || {
        echo "Cannot load the selected azd environment; provisioning has not started." >&2
        exit 1
    }
    prepare_terraform_groups() {
        set -- --environment - --azure-dir "$PROJECT_ROOT/.azure"
        if [ -n "${AZURE_ENV_NAME:-}" ]; then set -- "$@" --env-name "$AZURE_ENV_NAME"; fi
        cd "$PROJECT_ROOT" && "$PYTHON_CMD" -m "$RESOURCE_GROUP_MODULE" "$@"
    }
    RESOURCE_GROUP_OUTPUT="$(printf '%s' "$AZD_ENVIRONMENT_JSON" | prepare_terraform_groups)"
elif [ -n "${AZURE_ENV_NAME:-}" ]; then
    RESOURCE_GROUP_OUTPUT="$(cd "$PROJECT_ROOT" && "$PYTHON_CMD" -m "$RESOURCE_GROUP_MODULE" --azure-dir "$PROJECT_ROOT/.azure" --env-name "$AZURE_ENV_NAME")"
else
    RESOURCE_GROUP_OUTPUT="$(cd "$PROJECT_ROOT" && "$PYTHON_CMD" -m "$RESOURCE_GROUP_MODULE" --azure-dir "$PROJECT_ROOT/.azure")"
fi
RESOURCE_GROUP_EXIT=$?
if [ $RESOURCE_GROUP_EXIT -ne 0 ]; then
    echo "${YELLOW}Error: Resource-group destination preparation failed. Review the reported configuration or access error; no automatic cleanup is performed.${NC}"
    exit $RESOURCE_GROUP_EXIT
fi
RESOURCE_GROUP_EXPORTS="$(printf '%s' "$RESOURCE_GROUP_OUTPUT" | "$PYTHON_CMD" -c '
import json, shlex, sys
groups = json.load(sys.stdin)
for key, field in (
    ("AZURE_RESOURCE_GROUP", "foundry"),
    ("AZURE_APP_RESOURCE_GROUP", "application"),
    ("AZURE_NETWORK_RESOURCE_GROUP", "network"),
):
    if groups[field] is not None:
        print("export " + key + "=" + shlex.quote(groups[field]))
print("export CREATE_RESOURCE_GROUPS=" + str(groups["create_resource_groups"]).lower())
')"
if [ $? -ne 0 ]; then
    echo "${YELLOW}Error: Cannot load the resolved resource-group destinations.${NC}"
    exit 1
fi
eval "$RESOURCE_GROUP_EXPORTS"

###############################################################################
# Infrastructure is repository-owned source under infra/ (no submodule).
###############################################################################
if [ ! -f "$PROJECT_ROOT/manifest.json" ]; then
    echo "${YELLOW}Error: manifest.json is required to resolve release pins.${NC}"
    exit 1
fi
if [ "$INFRA_PROVIDER" = "bicep" ] && [ ! -f "$MAIN_BICEP" ]; then
    echo "${YELLOW}Error: $MAIN_BICEP was not found. Restore the configured infrastructure entry point from source control.${NC}"
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
FIREWALL_OUTPUT="$(cd "$PROJECT_ROOT" && "$PYTHON_CMD" -m config.deployment.firewall --input "$PROJECT_ROOT/main.parameters.json")"
FIREWALL_EXIT=$?
if [ $FIREWALL_EXIT -ne 0 ]; then
    echo "${YELLOW}Error: Firewall input resolution failed; provisioning has not started.${NC}" >&2
    exit $FIREWALL_EXIT
fi
TOPOLOGY_OUTPUT="$(printf '%s\n%s' "$TOPOLOGY_OUTPUT" "$FIREWALL_OUTPUT" | tr -d '\r')"

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
if [ "$INFRA_PROVIDER" = "terraform" ]; then
    AZD_ENVIRONMENT_JSON="$(load_azd_environment_json)" || {
        echo "Cannot reload the selected azd environment before input composition." >&2
        exit 1
    }
    TERRAFORM_PARAMETER_DESTINATION="$(printf '%s' "$PROVIDER_OUTPUT" | "$PYTHON_CMD" -c '
import json, sys
from pathlib import Path
provider = json.load(sys.stdin)
print((Path(sys.argv[1]) / provider["path"] / (provider["module"] + ".tfvars.json")).resolve())
' "$PROJECT_ROOT")" || exit 1
    TERRAFORM_OWNERSHIP_FILE="$(printf '%s' "$RESOURCE_GROUP_OUTPUT" | "$PYTHON_CMD" -c 'import json,sys; print(json.load(sys.stdin)["ownershipFile"])')" || exit 1
    printf '%s' "$AZD_ENVIRONMENT_JSON" | (
        cd "$PROJECT_ROOT" &&
        "$PYTHON_CMD" -m config.deployment.terraform_inputs \
            --input "$PROJECT_ROOT/main.parameters.json" \
            --environment - \
            --app-definition "$APP_DEFINITION_PATH" \
            --output "$TERRAFORM_PARAMETER_DESTINATION" \
            --diagnostic-output "$PARAMETER_DESTINATION" \
            --resource-group-ownership "$TERRAFORM_OWNERSHIP_FILE" \
            --hosted-source-commit "$HOSTED_SOURCE_COMMIT"
    ) >/dev/null
else
    (
        cd "$PROJECT_ROOT" &&
        "$PYTHON_CMD" -m config.deployment.composition \
            --input "$PROJECT_ROOT/main.parameters.json" \
            --output "$PARAMETER_DESTINATION" \
            --hosted-source-commit "$HOSTED_SOURCE_COMMIT"
    )
fi
COMPOSE_EXIT=$?
if [ $COMPOSE_EXIT -ne 0 ]; then
    echo "${YELLOW}Error: Agent Landing Zone deployment mode composition failed.${NC}"
    exit $COMPOSE_EXIT
fi
if [ "$INFRA_PROVIDER" = "terraform" ]; then import_azd_environment; fi

# BEGIN component runtime egress
(cd "$PROJECT_ROOT" && "$PYTHON_CMD" -m config.deployment.egress --plan --save) || {
    echo "Component egress planning failed; provisioning has not started." >&2
    exit 1
}
# END component runtime egress

# The composed infra/bicep/main.parameters.json is environment-specific; hide local
# regeneration from git status so the committed seed stays untouched.
if [ "$INFRA_PROVIDER" = "bicep" ] &&
    [ "$("$PYTHON_CMD" -c '
from pathlib import Path
import sys
print(Path(sys.argv[2]).resolve() == (Path(sys.argv[1]) / "infra/bicep/main.parameters.json").resolve())
' "$PROJECT_ROOT" "$PARAMETER_DESTINATION")" = "True" ] &&
    command -v git >/dev/null 2>&1 &&
    [ "$(git -C "$PROJECT_ROOT" rev-parse --is-inside-work-tree 2>/dev/null)" = "true" ] &&
    git -C "$PROJECT_ROOT" ls-files --error-unmatch infra/bicep/main.parameters.json >/dev/null 2>&1; then
    git -C "$PROJECT_ROOT" update-index --skip-worktree infra/bicep/main.parameters.json >/dev/null 2>&1 ||
        echo "${YELLOW}Note: could not mark infra/bicep/main.parameters.json as skip-worktree; it may appear as modified in git status.${NC}"
fi

###############################################################################
# Agent Landing Zone regional readiness preflight
###############################################################################

REGIONAL_PREFLIGHT_SCRIPT="$SCRIPT_DIR/Invoke-RegionalPreflight.ps1"
if [ -f "$REGIONAL_PREFLIGHT_SCRIPT" ] && [ "$PREFLIGHT_SKIP" != "true" ] && [ "$PREFLIGHT_SKIP" != "1" ] && [ "$AGENTLZ_REGIONAL_PREFLIGHT_SKIP" != "true" ] && [ "$AGENTLZ_REGIONAL_PREFLIGHT_SKIP" != "1" ]; then
    if command -v pwsh >/dev/null 2>&1; then
        echo "${CYAN}Running Agent Landing Zone regional preflight...${NC}"
        pwsh -NoProfile -File "$REGIONAL_PREFLIGHT_SCRIPT" -ProjectRoot "$PROJECT_ROOT" -ParameterFile "$PARAMETER_DESTINATION"
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

PREFLIGHT_SCRIPT="$SCRIPT_DIR/infra/Invoke-PreflightChecks.ps1"
if [ -f "$PREFLIGHT_SCRIPT" ] && [ "$PREFLIGHT_SKIP" != "true" ] && [ "$PREFLIGHT_SKIP" != "1" ]; then
    if command -v pwsh >/dev/null 2>&1; then
        echo "${CYAN}Running landing-zone preflight checks...${NC}"
        pwsh -NoProfile -File "$PREFLIGHT_SCRIPT" -ParametersFile "$PARAMETER_DESTINATION"
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
