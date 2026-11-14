#!/usr/bin/env bash
# Reads validation evidence from the executor VM through Azure Run Command.
# The harness storage account can be private (subscription policy), so the
# GitHub-hosted runner never reads blobs directly. Run Command returns about
# 4 KB of output per call, so the transcript and the final archive are paged.
#
#   vm-evidence.sh follow <evidence-dir>    print progress until the run completes
#   vm-evidence.sh collect <evidence-dir>   copy the sanitized out/ directory
#
# Requires HUB_RG, HUB_VM and RUN_KEY, and an az session that may run commands
# on the VM.
set -euo pipefail

[[ "${RUN_KEY:-}" =~ ^[0-9A-Za-z-]{1,40}$ ]] || { echo "Invalid RUN_KEY" >&2; exit 2; }
: "${HUB_RG:?}" "${HUB_VM:?}"
OUT="/var/lib/relval/$RUN_KEY/out"
PAGE=3000

vm() {
  local script="$1" attempt
  for attempt in 1 2 3 4 5; do
    if az vm run-command invoke -g "$HUB_RG" -n "$HUB_VM" --command-id RunShellScript \
        --scripts "$script" --query 'value[0].message' -o tsv --only-show-errors 2>/dev/null \
        | tr -d '\r' | sed -n '/^\[stdout\]$/,/^\[stderr\]$/p' | sed '1d;$d'; then
      return 0
    fi
    sleep $((attempt * 15))
  done
  return 1
}

# Prints the transcript lines added since the last poll. When more than one
# page was added, older lines are skipped (the artifact keeps the full log).
follow() {
  local dir="$1" offset=0 last_step="" reply header state step size start
  mkdir -p "$dir"
  while true; do
    reply="$(vm "o=$OUT; s=\$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get(\"state\") or \"pending\", d.get(\"step\") or \"-\")' \$o/status.json 2>/dev/null || echo pending -); n=\$(stat -c %s \$o/transcript.log 2>/dev/null || echo 0); b=$offset; [ \$((n - b)) -gt $PAGE ] && b=\$((n - $PAGE)); echo \"@@ \$s \$n \$b\"; tail -c +\$((b + 1)) \$o/transcript.log 2>/dev/null | head -c \$((n - b))")" || reply=""
    header="$(printf '%s\n' "$reply" | grep -m1 '^@@ ' || true)"
    if [ -n "$header" ]; then
      read -r _ state step size start <<< "$header"
      [ "$start" -gt "$offset" ] && echo "[... $((start - offset)) bytes skipped, see the evidence artifact ...]"
      printf '%s\n' "$reply" | awk 'f; /^@@ /{f=1}'
      offset="$size"
      [ "$step" != "$last_step" ] && echo "::notice::step: $step" && last_step="$step"
      [ "$state" = "completed" ] && return 0
    fi
    sleep 60
  done
}

collect() {
  local dir="$1" total i b64 page=3400
  mkdir -p "$dir"
  total="$(vm "tar -C $OUT -czf /tmp/relval-$RUN_KEY.tgz . && base64 -w0 /tmp/relval-$RUN_KEY.tgz > /tmp/relval-$RUN_KEY.b64 && stat -c %s /tmp/relval-$RUN_KEY.b64" | tr -dc 0-9)"
  [ -n "$total" ] || { echo "No evidence on the executor" >&2; return 1; }
  b64=""
  for ((i = 0; i < total; i += page)); do
    b64+="$(vm "tail -c +$((i + 1)) /tmp/relval-$RUN_KEY.b64 | head -c $page" | tr -d '\r\n')"
  done
  [ "${#b64}" -eq "$total" ] || { echo "Incomplete evidence transfer (${#b64}/$total)" >&2; return 1; }
  printf '%s' "$b64" | base64 -d | tar -C "$dir" -xzf -
  # Lets the executor deallocate itself now instead of waiting for its timeout.
  vm "touch $OUT/collected; rm -f /tmp/relval-$RUN_KEY.tgz /tmp/relval-$RUN_KEY.b64" >/dev/null
  ls -l "$dir"
}

case "${1:-}" in
  follow) follow "${2:?evidence dir}" ;;
  collect) collect "${2:?evidence dir}" ;;
  *) echo "usage: $0 follow|collect <evidence-dir>" >&2; exit 2 ;;
esac
