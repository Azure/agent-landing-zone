#!/bin/sh
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -f "$REPO_ROOT/manifest.json" ]; then
    echo "Error: Cannot locate the Agent Landing Zone repository." >&2
    exit 1
fi
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD=python
else
    echo "Error: Python is required to validate the application definition." >&2
    exit 1
fi

# azd can create a resource group before preprovision; reject invalid input at preup.
cd "$REPO_ROOT"
set -- --validate --check-binding --azure-dir "$REPO_ROOT/.azure"
if [ -n "${AZURE_ENV_NAME:-}" ]; then
    set -- "$@" --env-name "$AZURE_ENV_NAME"
fi
exec "$PYTHON_CMD" -m config.appdefinition "$@"
