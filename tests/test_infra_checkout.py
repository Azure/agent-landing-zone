from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
INFRA_SOURCE_REPO = "https://github.com/Azure/bicep-ptn-aiml-landing-zone.git"


def _manifest() -> dict:
    return json.loads((REPO_ROOT / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_records_infra_source_provenance() -> None:
    manifest = _manifest()
    assert "ailz_tag" not in manifest
    assert "ailz_commit" not in manifest
    source = manifest["infra"]["source"]
    assert set(source) == {"repo", "tag", "commit"}
    assert source["repo"] == INFRA_SOURCE_REPO
    assert re.fullmatch(r"v\d+\.\d+\.\d+", source["tag"])
    assert re.fullmatch(r"[0-9a-f]{40}", source["commit"])


def test_infra_is_repo_owned_not_a_submodule() -> None:
    assert not (REPO_ROOT / ".gitmodules").exists()
    assert not (REPO_ROOT / "infra" / ".git").exists()
    entries = _git(REPO_ROOT, "ls-files", "--stage", "--", "infra")
    assert entries, "infra/ must contain tracked files"
    modes = {line.split()[0] for line in entries.splitlines()}
    assert "160000" not in modes, "infra must not be recorded as a gitlink"
    for required in ("bicep/main.bicep", "shared/roles.json"):
        assert (REPO_ROOT / "infra" / required).is_file()


def test_infra_provenance_commit_matches_manifest() -> None:
    source = _manifest()["infra"]["source"]
    subjects = _git(
        REPO_ROOT, "log", "--format=%s", "--", "infra/bicep/main.bicep", "infra/main.bicep"
    ).splitlines()
    expected = (
        "Incorporate infra from Azure/bicep-ptn-aiml-landing-zone "
        f"{source['tag']} ({source['commit']})"
    )
    shallow = _git(REPO_ROOT, "rev-parse", "--is-shallow-repository") == "true"
    if not subjects or shallow:
        pytest.skip("Git history unavailable (shallow or exported checkout)")
    if expected in subjects:
        return
    # Squash merges fold the provenance commit into a PR commit whose body
    # still records it; accept that as long as the pinned commit is referenced.
    bodies = _git(REPO_ROOT, "log", "--format=%B", "--", "infra/bicep/main.bicep", "infra/main.bicep")
    assert expected in bodies or source["commit"] in bodies


def _git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_infra_parameters_seed_is_tracked_and_marked_skip_worktree() -> None:
    # infra/bicep/main.parameters.json is a tracked seed so a fresh clone can run
    # `azd up`; preProvision regenerates it and marks it skip-worktree so the
    # composed file never dirties the tree.
    relative_path = "infra/bicep/main.parameters.json"
    assert _git(REPO_ROOT, "ls-files", "--", relative_path) == relative_path
    for name in ("preProvision.ps1", "preProvision.sh"):
        content = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8-sig")
        assert "update-index --skip-worktree" in content, name
        assert relative_path in content, name


def test_preprovision_hooks_do_not_write_tracked_infra_files() -> None:
    for name in ("preProvision.ps1", "preProvision.sh"):
        content = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8-sig")
        assert "infra_checkout" not in content
        assert "ailz_" not in content
        assert "git submodule" not in content
        # main.bicep loads ../../manifest.json; the hooks do not copy it into infra/.
        assert '-Destination (Join-Path $infraDir "manifest.json")' not in content
        assert '"$INFRA_DIR/manifest.json"' not in content


def test_main_bicep_reads_root_manifest_and_infra_source_tag() -> None:
    bicep = (REPO_ROOT / "infra" / "bicep" / "main.bicep").read_text(encoding="utf-8")
    assert "loadJsonContent('../../manifest.json')" in bicep
    assert "_manifest.infra.source.tag" in bicep
    assert "_manifest.ailz_tag" not in bicep
