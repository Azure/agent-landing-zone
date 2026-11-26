"""Regression checks for the repository's managed Spec Kit installation."""

import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("integration", ["copilot", "speckit"])
def test_managed_files_match_installation_manifest(integration):
    manifest = json.loads(
        (ROOT / ".specify" / "integrations" / f"{integration}.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    for relative_path, expected_hash in manifest["files"].items():
        content = (ROOT / relative_path).read_bytes()
        assert hashlib.sha256(content).hexdigest() == expected_hash, relative_path


def test_installation_metadata_agrees():
    state = json.loads((ROOT / ".specify" / "integration.json").read_text(encoding="utf-8"))
    options = json.loads(
        (ROOT / ".specify" / "init-options.json").read_text(encoding="utf-8")
    )
    assert state["version"] == options["speckit_version"]
    assert state["integration_settings"]["copilot"]["script"] == "ps"
    assert state["integration_settings"]["copilot"]["parsed_options"]["skills"] is True
    for integration in ("copilot", "speckit"):
        manifest = json.loads(
            (
                ROOT / ".specify" / "integrations" / f"{integration}.manifest.json"
            ).read_text(encoding="utf-8")
        )
        assert manifest["version"] == state["version"]
