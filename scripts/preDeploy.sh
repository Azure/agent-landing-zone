#!/usr/bin/env bash
# Cross-platform bash (Linux/macOS) parent deployer for Agent Landing Zone
# Runs child scripts/deploy.sh in each component directory.

set -uo pipefail
IFS=$'\n\t'

# ---------- Colors ----------
cyan()   { printf "\033[36m%s\033[0m\n" "$*"; }
green()  { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }

# ---------- Helpers ----------
find_repo_root() {
  local start="$1"
  local p
  if ! p="$(cd "$start" 2>/dev/null && pwd -P)"; then return 1; fi
  while :; do
    if [ -f "$p/manifest.json" ] && [ -f "$p/azure.yaml" ]; then
      printf "%s" "$p"; return 0
    fi
    local parent; parent="$(dirname "$p")"
    [ "$parent" = "$p" ] && break
    p="$parent"
  done
  return 1
}

tag_exists()    { [ -n "$(git ls-remote --tags  "$1" "$2" 2>/dev/null || true)" ]; }
branch_exists() { [ -n "$(git ls-remote --heads "$1" "$2" 2>/dev/null || true)" ]; }

get_azd_value() {
  local project_root="$1" key="$2" val=""
  # Root values must come from the same validated snapshot as the probe.
  if [ "$project_root" = "$repo_root" ]; then
    printf "%s" "${!key:-}"
    return 0
  fi
  if command -v azd >/dev/null 2>&1; then
    if pushd "$project_root" >/dev/null 2>&1; then
      local lines
      if lines="$(azd env get-values 2>/dev/null)"; then
        val="$(printf "%s\n" "$lines" | tr -d '\r' | awk -F= -v k="$key" '
          $1==k { sub(/^[ \t"]+/, "", $2); sub(/[ \t"]+$/, "", $2); gsub(/^"/,"",$2); gsub(/"$/,"",$2); print $2; exit }')"
      fi
      popd >/dev/null 2>&1 || true
    fi
  fi
  if [ -z "$val" ]; then
    local env_dir
    env_dir="$(find "$project_root/.azure" -type d -maxdepth 1 -mindepth 1 2>/dev/null | head -n1 || true)"
    if [ -n "$env_dir" ] && [ -f "$env_dir/.env" ]; then
      val="$(tr -d '\r' < "$env_dir/.env" | awk -F= -v k="$key" '
        $1==k { sub(/^[ \t"]+/, "", $2); sub(/[ \t"]+$/, "", $2); gsub(/^"/,"",$2); gsub(/"$/,"",$2); print $2; exit }')"
    fi
  fi
  printf "%s" "$val"
}

rg_exists() {
  if ! command -v az >/dev/null 2>&1; then
    red "Azure CLI (az) not found; cannot verify resource group '$1'."
    return 1
  fi
  local args=(group exists -n "$1")
  [ -n "${2:-}" ] && args+=("--subscription" "$2")
  local res; res="$(az "${args[@]}" 2>/dev/null)" || return 1
  [ "$(printf "%s" "$res" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')" = "true" ]
}

copy_dot_azure() {
  [ -d "$1" ] || return 0
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$1/" "$2/.azure/" >/dev/null 2>&1 || cp -R "$1" "$2"/ >/dev/null 2>&1
  else
    cp -R "$1" "$2"/ >/dev/null 2>&1
  fi
}

# ---------- Locate repo root ----------
start_dir="${BASH_SOURCE[0]:-}"
if [ -n "$start_dir" ] && [ -f "$start_dir" ]; then
  start_dir="$(cd "$(dirname "$start_dir")" && pwd -P)"
else
  start_dir="$(pwd -P)"
fi

repo_root="$(find_repo_root "$start_dir")" || { red "Run this from inside the Agent Landing Zone repository (a folder containing manifest.json and azure.yaml)."; exit 1; }
command -v git >/dev/null 2>&1 || { red "Git not found in PATH."; exit 1; }
export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"
export AGENTLZ_REPO_ROOT="$repo_root"

manifest_path="$repo_root/manifest.json"
[ -f "$manifest_path" ] || { red "manifest.json not found at $manifest_path"; exit 1; }
command -v jq >/dev/null 2>&1 || { red "jq is required to parse $manifest_path. Please install jq."; exit 1; }

base_dir="$(cd "$repo_root/.." && pwd -P)"
dot_azure="$repo_root/.azure"

# Mirror the materialized azd environment before invoking shared Python
# publishers. In particular, the final hosted cutover requires App
# Configuration, resource-group, resource-token, and deploy-handoff values
# that are not inherited by a clean shell merely because get_azd_value reads
# them into local variables below.
azd_values="$(cd "$repo_root" && azd env get-values --output json)" || {
  red "Could not load the selected azd environment; refusing to deploy."
  exit 1
}
jq -e 'type == "object" and length > 0 and all(to_entries[];
  (.key | test("^[A-Za-z_][A-Za-z0-9_]*$")) and
  (.value | type == "string") and (.value | contains("\u0000") | not))' \
  <<< "$azd_values" >/dev/null || { red "Invalid azd environment JSON, key or value."; exit 1; }
while IFS= read -r -d '' key && IFS= read -r -d '' value; do
  export "$key=$value"
done < <(jq -b -j 'to_entries[] | .key, "\u0000", .value, "\u0000"' <<< "$azd_values")

# ---------- Global env & RG early check ----------
global_rg="$(get_azd_value "$repo_root" "AZURE_RESOURCE_GROUP")"
global_sub="$(get_azd_value "$repo_root" "AZURE_SUBSCRIPTION_ID")"
network_isolation="$(get_azd_value "$repo_root" "NETWORK_ISOLATION" | tr '[:upper:]' '[:lower:]')"
acr_task_agent_pool="$(get_azd_value "$repo_root" "ACR_TASK_AGENT_POOL")"

# Foundation guard (first step, before any Azure change): azd deploy only
# deploys applications onto a foundation created by azd provision.
if [ -z "$global_rg" ]; then
  red "The foundation is not provisioned. Run azd provision first."
  exit 3
fi
command -v python3 >/dev/null 2>&1 || { red "python3 is required to verify the foundation."; exit 1; }
python3 -m config.deployment.resource_groups --azure-dir "$dot_azure" --check >/dev/null || {
  red "Resource-group binding check failed. No changes were made."; exit 3;
}
# BEGIN deployment metadata verification
python3 -m config.deployment.metadata --check --environment "${AZURE_ENV_NAME:-}" --project-root "$repo_root" || {
  metadata_exit=$?
  exit "$metadata_exit"
}
# END deployment metadata verification

# Re-validate the application definition and compare it with the binding.
app_definition_path="${AGENTLZ_APP_DEFINITION:-$repo_root/app-definition.json}"
case "$app_definition_path" in
  /*) ;;
  *) app_definition_path="$repo_root/$app_definition_path" ;;
esac
if [ -d "$app_definition_path" ]; then
  app_definition_path="$app_definition_path/app-definition.json"
fi
[ -f "$app_definition_path" ] || { red "AGENTLZ_APP_DEFINITION points to $app_definition_path, which does not exist."; exit 1; }
command -v python3 >/dev/null 2>&1 || { red "python3 is required to validate the application definition."; exit 1; }
if [ -z "${AGENTLZ_APP_ID:-}" ]; then
  red "This environment is not bound to an application. Run azd provision first."
  exit 1
fi
appdef_args=(--validate "$app_definition_path" --check-binding --azure-dir "$dot_azure")
[ -n "${AZURE_ENV_NAME:-}" ] && appdef_args+=(--env-name "$AZURE_ENV_NAME")
# Exit codes: 1 invalid definition, 2 binding mismatch (message names both ids).
(cd "$repo_root" && python3 -m config.appdefinition "${appdef_args[@]}")
appdef_exit=$?
if [ "$appdef_exit" -eq 2 ]; then
  red "Application definition binding check failed. No changes were made."
  exit 2
fi
if [ "$appdef_exit" -ne 0 ]; then
  red "Application definition validation failed. No changes were made."
  exit 1
fi
app_definition_dir="$(cd "$(dirname "$app_definition_path")" && pwd -P)"
definition_id="$(jq -er '.id' "$app_definition_path")" || { red "Application definition has no id."; exit 1; }


# Echo the manifest component name that a definition component maps to.
manifest_component_for() {
  jq -r --arg n "$1" '[.components[].name | select(. == $n or endswith("-" + $n))][0] // empty' "$manifest_path"
}
definition_manifest_names=" "
while IFS= read -r dname; do
  [ -z "$dname" ] && continue
  mname="$(manifest_component_for "$dname")"
  [ -n "$mname" ] && definition_manifest_names="$definition_manifest_names$mname "
done < <(jq -r '.components[].name' "$app_definition_path")

# The validated azd snapshot is already imported above; never reload other selectors.
command -v python3 >/dev/null 2>&1 || { red "python3 is required to resolve native application selection."; exit 1; }
topology_json="$(cd "$repo_root" && python3 -m config.deployment.topology --describe)" || {
  red "Failed to resolve native application selection. Ensure scripts/preProvision ran successfully before azd deploy."
  exit 1
}
orchestration_host="$(printf "%s" "$topology_json" | jq -er '.ORCHESTRATION_HOST | select(. == "hosted" or . == "container_apps")')" &&
application_mode="$(printf "%s" "$topology_json" | jq -er '.APPLICATION_MODE | select(. == "conversational" or . == "workflow" or . == "both")')" &&
selected_components="$(printf "%s" "$topology_json" | jq -er '.components | if type == "array" then join(" ") else error("invalid component selection") end')" || {
  red "Resolved application JSON is incomplete or invalid; refusing to select a deployment path."
  exit 1
}
hosted_mode=false
[ "$orchestration_host" = "hosted" ] && hosted_mode=true
deployment_mode="$orchestration_host/$application_mode"
cyan "Native application selection: $deployment_mode"

python3 -m config.deployment.private_network --stage pre-deploy || {
  network_exit=$?
  red "Private deployment prerequisites failed. Use a VPN/VNet-connected host; RUN_FROM_JUMPBOX is not a connectivity bypass."
  exit "$network_exit"
}

# BEGIN component runtime egress
(cd "$repo_root" && python3 -m config.deployment.egress --apply) || {
  red "Component egress reconciliation failed; application deployment has not started."
  exit 1
}
# END component runtime egress

# Under network isolation the registry has no public access, so ACR Task builds
# only work through the in-VNet agent pool (#741). Fail before touching any app.
build_mode_override="$(printf '%s' "${BUILD_MODE:-}" | tr '[:upper:]' '[:lower:]')"
if [ "$network_isolation" = "true" ] && [ -z "$acr_task_agent_pool" ] && [ "$build_mode_override" != "local" ]; then
  red "NETWORK_ISOLATION=true but no ACR Task agent pool was provisioned (ACR_TASK_AGENT_POOL is empty). Run 'azd env set DEPLOY_ACR_TASK_AGENT_POOL true' and 'azd provision', or set BUILD_MODE=local on a VNet-connected host with Docker."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  if [ "$network_isolation" = "true" ] || [ -n "$acr_task_agent_pool" ]; then
    yellow "Docker is not available; component deploys will use ACR remote builds."
  else
    yellow "Docker daemon is not running; component deploy scripts will fall back to ACR remote builds where supported."
  fi
fi


had_errors=0
release_default="$(jq -r '.release // empty' "$manifest_path")"

native_mode="$(printf "%s" "$topology_json" | jq -r '.bundled_application // false')"
# BEGIN optional MCP lifecycle
if [ "$native_mode" = "true" ]; then
  (cd "$repo_root" && python3 -m config.deployment.mcp --deploy) || {
    red "MCP preparation/deployment failed; consumers have not been deployed."
    exit 1
  }
  mcp_environment="$(cd "$repo_root" && azd env get-values --output json)" || exit 1
  mcp_exports="$(printf '%s' "$mcp_environment" | python3 -c '
import json, shlex, sys
for key, value in json.load(sys.stdin).items():
    if key.startswith("MCP_"):
        print("export " + key + "=" + shlex.quote(str(value)))
')" || exit 1
  eval "$mcp_exports"
fi
# END optional MCP lifecycle
# BEGIN native application lifecycle
if [ "$native_mode" = "true" ]; then
  (cd "$repo_root" && python3 -m config.deployment.native_deploy --deploy) || {
    red "Native application preparation/publication failed; component deployment has not started."
    exit 1
  }
  if [[ "${APP_RUNTIME_CONFIGURATION_MODE:-appConfig}" == "appConfig" ]]; then
  (cd "$repo_root" && python3 -m config.deployment.appconfig --require-hosted-endpoint) || {
    red "Native runtime settings could not be published."
    exit 1
  }
  fi
fi
# END native application lifecycle

# ---------- Iterate components ----------
while IFS= read -r comp; do
  name="$(printf "%s" "$comp" | jq -r '.name')"
  if [ "$native_mode" = "true" ] && [ "$name" = "agent-app-mcp" ]; then continue; fi
  if [[ " $selected_components " != *" $name "* ]]; then
    yellow "$name is not deployed in $deployment_mode mode."
    continue
  fi
  if [[ "$definition_manifest_names" != *" $name "* ]]; then
    yellow "$name is not part of application '$definition_id'."
    continue
  fi
  repo="$(printf "%s" "$comp" | jq -r '.repo')"
  c_tag="$(printf "%s" "$comp" | jq -r '.tag // empty')"
  c_branch="$(printf "%s" "$comp" | jq -r '.branch // empty')"
  expected_commit="$(printf "%s" "$comp" | jq -r '.commit // empty')"

  # Desired ref (no implicit fallback)
  ref_type=""; ref=""
  if [ -n "$c_tag" ]; then
    if tag_exists "$repo" "$c_tag"; then ref_type="tag"; ref="$c_tag"
    else
      yellow "$name: tag '$c_tag' not found. Skipping."
      [ "$hosted_mode" = "true" ] && had_errors=1
      continue
    fi
  elif [ -n "$release_default" ]; then
    if tag_exists "$repo" "$release_default"; then ref_type="tag"; ref="$release_default"
    else
      yellow "$name: tag '$release_default' not found. Skipping."
      [ "$hosted_mode" = "true" ] && had_errors=1
      continue
    fi
  elif [ -n "$c_branch" ]; then
    if branch_exists "$repo" "$c_branch"; then ref_type="branch"; ref="$c_branch"
    else
      yellow "$name: branch '$c_branch' not found. Skipping."
      [ "$hosted_mode" = "true" ] && had_errors=1
      continue
    fi
  else
    yellow "$name: neither tag nor branch specified. Skipping."
    [ "$hosted_mode" = "true" ] && had_errors=1
    continue
  fi

  target="$base_dir/$name"
  cyan "Deploying $name ($ref_type:$ref) -> $target"

  if [ -d "$target" ]; then
    yellow "  ℹ️  '$name' already exists at $target, verifying pin."
  else
    if [ "$ref_type" = "branch" ]; then
      if ! git clone --depth 1 --branch "$ref" --quiet "$repo" "$target" >/dev/null 2>&1; then
        red "$name: git clone failed."; had_errors=1; continue
      fi
    else
      if ! git clone --depth 1 --quiet "$repo" "$target" >/dev/null 2>&1; then
        red "$name: git clone failed."; had_errors=1; continue
      fi
      if ! git -C "$target" fetch --tags --force --depth 1 --quiet origin "$ref" >/dev/null 2>&1; then
        red "$name: git fetch tag failed."; had_errors=1; continue
      fi
      if ! git -C "$target" -c advice.detachedHead=false checkout -q -f "$ref" >/dev/null 2>&1; then
        red "$name: git checkout tag failed."; had_errors=1; continue
      fi
    fi
  fi

  if [ -n "$expected_commit" ]; then
    actual_commit="$(git -C "$target" rev-parse HEAD 2>/dev/null || true)"
    if [ "$actual_commit" != "$expected_commit" ]; then
      red "$name must resolve to $expected_commit but $target is at $actual_commit. Remove or relocate the stale sibling checkout."
      had_errors=1
      continue
    fi
  fi

  if [ "$native_mode" = "true" ]; then
    (cd "$repo_root" && python3 -m config.deployment.native_deploy --validate-component-source "$target" --component "$name") || {
      red "$name is not a compatible native component; deployment has not started."
      had_errors=1
      continue
    }
  fi
  git config --global --add safe.directory "$target" >/dev/null 2>&1 || true
  copy_dot_azure "$dot_azure" "$target"

  deploy_sh="$target/scripts/deploy.sh"
  if [ -f "$deploy_sh" ]; then
    log_dir="$target/.logs"; mkdir -p "$log_dir"
    ts="$(date +%Y%m%d_%H%M%S)"
    log="$log_dir/deploy_${ts}.log"

    echo "Running child deploy in $target: scripts/deploy.sh -> $(basename "$log")"
    (
      cd "$target" && bash "scripts/deploy.sh"
    ) >"$log" 2>&1
    exit_code=$?
    if [ "$exit_code" -ne 0 ]; then
      red "$name: deploy script failed with exit code $exit_code. See log: $log"
      had_errors=1
    else
      green "$name: deploy script finished. Log: $log"
    fi
  else
    echo "$name: no scripts/deploy.sh found, skipping child deploy."
    [ "$hosted_mode" = "true" ] && had_errors=1
  fi
done < <(jq -c '.components[]' "$manifest_path")
# Components from the application definition that are not release-managed
# (manifest.json) components: each folder is its own azd project.
while IFS= read -r dcomp; do
  [ -z "$dcomp" ] && continue
  c_name="$(printf "%s" "$dcomp" | jq -r '.name')"
  [ "$native_mode" = "true" ] && [ -n "$(manifest_component_for "$c_name")" ] && continue
  c_kind="$(printf "%s" "$dcomp" | jq -r '.kind')"
  c_path="$app_definition_dir/$(printf "%s" "$dcomp" | jq -r '.path')"
  c_commit="$(printf "%s" "$dcomp" | jq -r '.source.commit // empty')"
  c_digest="$(printf "%s" "$dcomp" | jq -r '.source.imageDigest // empty')"
  if [ ! -f "$app_definition_dir/azure.yaml" ]; then
    red "The app folder $app_definition_dir must contain its own azure.yaml."
    had_errors=1; continue
  fi
  if [ -n "$c_commit" ]; then
    actual_commit="$(git -C "$c_path" rev-parse HEAD 2>/dev/null || true)"
    if [ "$actual_commit" != "$c_commit" ]; then
      red "$c_name must resolve to $c_commit but $c_path is at '$actual_commit'."
      had_errors=1; continue
    fi
  fi
  copy_dot_azure "$dot_azure" "$app_definition_dir" || {
    red "$c_name: failed to copy the azd environment."; had_errors=1; continue
  }
  cyan "Deploying $c_name ($c_kind) from $c_path"
  env_name="${AZURE_ENV_NAME:-}"
  if [ -n "$c_digest" ]; then
    (cd "$app_definition_dir" && azd env set AGENTLZ_IMAGE_DIGEST "$c_digest" --environment "$env_name" --no-prompt >/dev/null) || {
      red "$c_name: failed to pin image digest."; had_errors=1; continue
    }
  fi
  if [ "$c_kind" = "azure.ai.agent" ]; then
    smoke_protocol="$(cd "$repo_root" && python3 -m config.deployment.hosted --service-protocol "$app_definition_dir/azure.yaml" --service-name "$c_name")" || {
      red "$c_name: cannot resolve the greeting protocol."; had_errors=1; continue
    }
    # Custom images use the shared immutable/private build path, not the
    # manifest-pinned orchestrator's derived hosted entrypoint.
    (
      cd "$app_definition_dir" &&
      azd env set FOUNDRY_PROJECT_ENDPOINT "${AZURE_AI_PROJECT_ENDPOINT:-}" --environment "$env_name" --no-prompt >/dev/null &&
      azd env set AZURE_AI_PROJECT_ID "${AZURE_AI_PROJECT_RESOURCE_ID:-}" --environment "$env_name" --no-prompt >/dev/null &&
      python3 -c "import os, runpy, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); sys.argv = ['config.deployment.custom_application'] + sys.argv[1:]; runpy.run_module('config.deployment.custom_application', run_name='__main__')" --definition "$app_definition_path" --service "$c_name" --environment "$env_name"
    ) || { red "$c_name: hosted agent deployment failed."; had_errors=1; continue; }
    agent_smoke_payload="$(mktemp "${TMPDIR:-/tmp}/agentlz-agent-smoke-XXXXXX")"
    smoke_options=()
    smoke_validation=--validate-smoke
    if [ "$smoke_protocol" = responses ]; then
      printf '%s\n' '{"input":[{"role":"user","content":"Hello!"}],"stream":true}' >"$agent_smoke_payload"
      smoke_options=(--output raw)
      smoke_validation=--validate-responses-smoke
    else
      printf '%s\n' '{"messages":[{"role":"user","content":"Hello!"}]}' >"$agent_smoke_payload"
    fi
    if ! agent_smoke_output="$(cd "$app_definition_dir" && azd ai agent invoke "$c_name" --protocol "$smoke_protocol" --new-session --timeout 180 --environment "$env_name" --no-prompt --input-file "$agent_smoke_payload" "${smoke_options[@]}" 2>&1)"; then
      rm -f "$agent_smoke_payload"
      red "$c_name: smoke request failed."; had_errors=1; continue
    fi
    rm -f "$agent_smoke_payload"
    if ! printf '%s\n' "$agent_smoke_output" | (cd "$repo_root" && python3 -m config.deployment.hosted "$smoke_validation"); then
      red "$c_name: smoke test did not pass."; had_errors=1; continue
    fi
  else
    (cd "$app_definition_dir" && python3 -c "import os, runpy, sys; sys.path.insert(0, os.environ['AGENTLZ_REPO_ROOT']); sys.argv = ['config.deployment.custom_application'] + sys.argv[1:]; runpy.run_module('config.deployment.custom_application', run_name='__main__')" --definition "$app_definition_path" --service "$c_name" --environment "$env_name") || {
      red "$c_name: Container App deployment failed."; had_errors=1; continue
    }
  fi
  green "$c_name: deployed."
done < <(jq -c '.components[]' "$app_definition_path")

if [ "$had_errors" -ne 0 ]; then
  red "One or more components failed. See logs above."
  exit 1
fi

if [ "$native_mode" = "true" ]; then
  (cd "$repo_root" && python3 -m config.deployment.mcp --activate) || {
    red "MCP caller authorization/activation failed."
    exit 1
  }
fi

green "All components processed."
