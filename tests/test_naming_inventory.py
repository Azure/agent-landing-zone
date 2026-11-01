"""Single naming scan (R17) driven by the allow-list in contracts/naming-map.md."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAMING_MAP = ROOT / "contracts" / "naming-map.md"

LEGACY_PATTERN = re.compile(r"gpt-rag|gpt_rag_|gptrag|\balz\b", re.IGNORECASE)


def _allow_block(text: str, name: str) -> list[str]:
    match = re.search(rf"^```{re.escape(name)}\n(.*?)^```", text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"contracts/naming-map.md is missing the '{name}' block")
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def _glob_to_regex(glob: str) -> re.Pattern[str]:
    parts: list[str] = []
    index = 0
    while index < len(glob):
        if glob.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif glob.startswith("**", index):
            parts.append(".*")
            index += 2
        elif glob[index] == "*":
            parts.append("[^/]*")
            index += 1
        elif glob[index] == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(glob[index]))
            index += 1
    return re.compile("".join(parts) + r"\Z")


def load_allow_list() -> tuple[list[str], list[str]]:
    text = NAMING_MAP.read_text(encoding="utf-8").replace("\r\n", "\n")
    return (
        _allow_block(text, "naming-allow-permanent"),
        _allow_block(text, "naming-allow-temporary"),
    )


def load_allowed_lines() -> dict[str, set[str]]:
    text = NAMING_MAP.read_text(encoding="utf-8").replace("\r\n", "\n")
    allowed: dict[str, set[str]] = {}
    for entry in _allow_block(text, "naming-allow-exact-lines"):
        path, separator, line = entry.partition("|")
        path, line = path.strip(), line.strip()
        if not separator or not path or not line or any(token in path for token in ("*", "?", "\\", "..")):
            raise AssertionError("Inherited package exceptions require an exact file and complete source line")
        allowed.setdefault(path, set()).add(line)
    return allowed


def is_allowed(path: str, globs: list[str]) -> bool:
    return any(_glob_to_regex(glob).match(path) for glob in globs)


def find_hits(path: str, text: str, allowed_lines: dict[str, set[str]] | None = None) -> list[str]:
    return [
        f"{path}:{number}: {line.strip()[:160]}"
        for number, line in enumerate(text.splitlines(), start=1)
        if LEGACY_PATTERN.search(line) and line.strip() not in (allowed_lines or {}).get(path, set())
    ]


def tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [item for item in completed.stdout.decode("utf-8").split("\0") if item]


class NamingPatternTests(unittest.TestCase):
    def test_legacy_tokens_are_detected(self) -> None:
        for sample in (
            "gpt-rag",
            "GPT-RAG",
            "GPT_RAG_REPO_ROOT",
            "gptrag-tmp",
            "image gpt-rag-ui:latest",
            "index gpt-rag-index",
            "the alz label",
        ):
            with self.subTest(sample=sample):
                self.assertIsNotNone(LEGACY_PATTERN.search(sample))

    def test_new_runtime_identifiers_are_not_flagged(self) -> None:
        for sample in (
            "agent-lz-ragindex",
            "agent-lz",
            "AGENTLZ_REPO_ROOT",
            "agentlz-tmp",
            "agent-app-orchestrator:v5.0.0",
            "agent-app-ui",
            "ailz_tag",
            "AILZ",
            "realization",
        ):
            with self.subTest(sample=sample):
                self.assertIsNone(LEGACY_PATTERN.search(sample))

    def test_glob_semantics(self) -> None:
        self.assertTrue(is_allowed("docs/adr/ADR-0001.md", ["docs/adr/**"]))
        self.assertTrue(is_allowed("contracts/a.json", ["contracts/*.json"]))
        self.assertFalse(is_allowed("contracts/sub/a.json", ["contracts/*.json"]))
        self.assertTrue(is_allowed("x/RELEASE_NOTES_v4.md", ["**/RELEASE_NOTES*.md"]))
        self.assertFalse(is_allowed("README.md", ["docs/**"]))

    def test_hits_report_file_and_line(self) -> None:
        self.assertEqual(
            ["a.md:2: GPT-RAG here"],
            find_hits("a.md", "clean\nGPT-RAG here\nagent-lz"),
        )

    def test_inherited_package_exception_is_exact_file_and_complete_line_only(self) -> None:
        allowed = load_allowed_lines()
        path = "config/deployment/native_deploy.py"
        line = 'entrypoint = path / "src/gpt_rag_ui/config/native.py"'
        self.assertEqual([], find_hits(path, "    " + line, allowed))
        self.assertTrue(find_hits("config/deployment/other.py", line, allowed))
        self.assertTrue(find_hits(path, line + " # alz fallback", allowed))
        self.assertTrue(find_hits(path, "label = 'gpt-rag'", allowed))


class NamingInventoryTests(unittest.TestCase):
    def test_allow_list_blocks_are_present(self) -> None:
        permanent, temporary = load_allow_list()
        self.assertIn("CHANGELOG.md", permanent)
        self.assertIn("docs/adr/**", permanent)
        self.assertIn("specs/**", permanent)
        self.assertIsInstance(temporary, list)

    def test_no_legacy_names_outside_allow_list(self) -> None:
        permanent, temporary = load_allow_list()
        allowed = permanent + temporary
        allowed_lines = load_allowed_lines()
        violations: list[str] = []
        for path in tracked_files():
            if is_allowed(path, allowed):
                continue
            file_path = ROOT / path
            if not file_path.is_file():
                continue  # submodule gitlinks and deleted files
            data = file_path.read_bytes()
            if b"\0" in data:
                continue  # binary
            violations.extend(find_hits(path, data.decode("utf-8", errors="replace"), allowed_lines))
        self.assertEqual(
            [],
            violations,
            "Legacy names outside the allow-list in contracts/naming-map.md:\n"
            + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
