#!/bin/sh
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD=python
else
    echo "Error: Python is required to inspect teardown scope." >&2
    exit 1
fi

cd "$REPO_ROOT"
exec "$PYTHON_CMD" -m config.deployment.teardown --azure-dir "$REPO_ROOT/.azure"
