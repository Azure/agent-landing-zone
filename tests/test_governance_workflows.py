import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.load(
        (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def test_quality_gate_runs_unconditionally_without_cloud_authentication():
    gate = workflow("quality-gate.yml")
    assert set(gate["on"]) == {"pull_request", "push", "merge_group", "workflow_dispatch"}
    assert gate["on"]["push"]["branches"] == ["main", "develop"]
    for event in gate["on"].values():
        assert not isinstance(event, dict) or not {"paths", "paths-ignore"} & event.keys()
    jobs = gate["jobs"]
    final = jobs["quality-gate"]
    assert final["if"] == "always()"
    assert set(final["needs"]) == set(jobs) - {"quality-gate"}
    assert gate["permissions"] == {"contents": "read"}
    text = json.dumps(jobs)
    for prohibited in ("azure/login", "id-token", "secrets.", "az deployment", "azd up"):
        assert prohibited not in text


@pytest.mark.parametrize("result", ["success", "failure", "cancelled", "skipped", None])
def test_quality_gate_fails_closed(result):
    final = workflow("quality-gate.yml")["jobs"]["quality-gate"]
    needs = {name: {"result": "success"} for name in final["needs"]}
    name = final["needs"][0]
    if result is None:
        del needs[name]
    else:
        needs[name]["result"] = result
    script = final["steps"][0]["run"].split("\n", 1)[1].rsplit("\nPY", 1)[0]
    completed = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "NEEDS_JSON": json.dumps(needs)},
        capture_output=True,
        text=True,
    )
    assert (completed.returncode == 0) == (result == "success"), completed.stdout + completed.stderr


@pytest.mark.parametrize(
    ("branch", "head_repo", "allowed"),
    [
        ("release/1.2.3", "Azure/agent-landing-zone", True),
        ("release/01.2.3", "Azure/agent-landing-zone", True),
        ("release/1.2.3", "fork/agent-landing-zone", False),
        ("feature/example", "Azure/agent-landing-zone", False),
        ("release/1.2.3-extra", "Azure/agent-landing-zone", False),
        ("release/1.2.3/nested", "Azure/agent-landing-zone", False),
        ("release/1x2x3", "Azure/agent-landing-zone", False),
        ("release/1.2.3\n", "Azure/agent-landing-zone", False),
        ("release/$(echo injected).2.3", "Azure/agent-landing-zone", False),
    ],
)
def test_release_guard_accepts_only_same_repository_exact_release_branches(branch, head_repo, allowed):
    guard = workflow("release-branch-guard.yml")
    assert guard["permissions"] == {"contents": "read"}
    assert set(guard["on"]) == {"pull_request_target"}
    assert guard["on"]["pull_request_target"]["branches"] == ["main"]
    steps = guard["jobs"]["release-branch-required"]["steps"]
    assert all("uses" not in step for step in steps)
    bash = shutil.which("bash")
    assert bash, "Bash is required to exercise the actual release guard"
    completed = subprocess.run(
        [bash, "-c", steps[0]["run"]],
        env={**os.environ, "HEAD_REF": branch, "HEAD_REPO": head_repo, "BASE_REPO": "Azure/agent-landing-zone"},
        capture_output=True,
        text=True,
    )
    assert (completed.returncode == 0) == allowed, completed.stdout + completed.stderr
