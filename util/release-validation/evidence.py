"""Evidence report and release-notes amendment for live release validation.

Used by .github/workflows/release-validation.yml. The executor VM
already redacts identifiers; this module redacts again before anything is
published, because release assets and notes are public and permanent.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

LOGGER = logging.getLogger(__name__)
PROVIDER_TITLES = {"bicep": "Bicep", "terraform": "Terraform"}
PRIVATE_ENV = re.compile(r"(rg-)?gptrag-\d{10}")
TRANSCRIPT_TAIL = 400
HISTORY_MARKER = "<!-- release-validation:history -->"
HISTORY_KEEP = 30


def provider_title(status: dict) -> str:
    return PROVIDER_TITLES.get(status.get("provider") or "", "Unknown provider")


def marker(status: dict) -> str:
    return f"<!-- release-validation:{status.get('provider') or 'unknown'} -->"


def redact(text: str, values: list[str]) -> str:
    for value in values:
        if value:
            text = re.sub(re.escape(value), "<redacted>", text, flags=re.IGNORECASE)
    return PRIVATE_ENV.sub("<environment>", text)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def build_report(evidence: Path, release: str, run_url: str, values: list[str]) -> tuple[str, str]:
    """Return (full report, job summary) as Markdown."""
    status = json.loads(_read(evidence / "status.json") or "{}")
    commands = redact(_read(evidence / "commands.sh"), values).strip()
    transcript = redact(_read(evidence / "transcript.log"), values).rstrip()
    result = status.get("result") or "unknown"
    header = [
        f"# Release validation: {release} ({provider_title(status)}, NETWORK_ISOLATION=true)",
        "",
        f"- Result: **{result}**",
        f"- Teardown (best effort, not part of the result): {status.get('teardown', 'unknown')}",
        f"- Region: {status.get('location', 'unknown')}",
        f"- Started: {status.get('started', 'unknown')}, last update: {status.get('updated', 'unknown')}",
        f"- Workflow run: {run_url}",
        "",
        "Commands marked `user` are the documented operator commands. Commands marked",
        "`harness` exist only because the validation runs from an automated hub VNet",
        "instead of an operator VPN.",
        "",
        "## Steps",
        "",
        "| Step | Kind | Exit | Seconds |",
        "| --- | --- | --- | --- |",
    ]
    for step in status.get("steps") or []:
        header.append(
            f"| {step.get('name')} | {step.get('kind')} | {step.get('exit')} | {step.get('seconds')} |"
        )
    body = header + ["", "## Operator commands", "", "```bash", commands, "```", ""]
    report = "\n".join(body + ["## Transcript", "", "```text", transcript, "```", ""])
    tail = "\n".join(transcript.splitlines()[-TRANSCRIPT_TAIL:])
    summary = "\n".join(body + [
        f"## Transcript (last {TRANSCRIPT_TAIL} lines, full log in the artifact)",
        "", "```text", tail, "```", "",
    ])
    return report, summary


def amend_notes(notes: str, status: dict, run_url: str, asset_url: str) -> str:
    """Add or replace the live-validation bullet of this provider under ## Validation."""
    date = (status.get("updated") or "")[:10]
    bullet = (
        f"- Live {provider_title(status)} deployment of the standard scenario with `NETWORK_ISOLATION=true` in "
        f"`{status.get('location', 'unknown')}` passed on {date}: provision, deferred "
        "data-plane configuration from a VNet-connected host, `azd deploy` with the "
        "agent smoke test. "
        f"Evidence: [workflow run]({run_url}), [commands and transcript]({asset_url}). {marker(status)}"
    )
    lines = [line for line in notes.replace("\r\n", "\n").split("\n") if marker(status) not in line]
    return _insert_in_validation(lines, [bullet], before_history=True)


def _insert_in_validation(lines: list[str], bullets: list[str], before_history: bool) -> str:
    """Insert bullets at the end of ## Validation, or before its history when asked."""
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "## Validation")
    except StopIteration:
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines + ["", "## Validation"] + bullets) + "\n"
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines)
    )
    insert = end
    while insert > start + 1 and not lines[insert - 1].strip():
        insert -= 1
    if before_history:
        insert = next(
            (i for i in range(start + 1, insert) if HISTORY_MARKER in lines[i]), insert
        )
    lines[insert:insert] = bullets
    return "\n".join(lines).rstrip("\n") + "\n"


def amend_history(notes: str, statuses: list[dict], run_url: str, keep: int = HISTORY_KEEP) -> str:
    """Append a compact revalidation entry under ## Validation and keep the last `keep`."""
    date = max((status.get("updated") or "")[:10] for status in statuses)
    providers = " and ".join(provider_title(status) for status in statuses)
    entry = f"- Revalidated on {date}: {providers} passed ([workflow run]({run_url})). {HISTORY_MARKER}"
    lines = notes.replace("\r\n", "\n").split("\n")
    history = [line for line in lines if HISTORY_MARKER in line and run_url not in line]
    lines = [line for line in lines if HISTORY_MARKER not in line]
    return _insert_in_validation(lines, (history + [entry])[-keep:], before_history=False)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report")
    report.add_argument("--evidence-dir", type=Path, required=True)
    report.add_argument("--release", required=True)
    report.add_argument("--run-url", required=True)
    report.add_argument("--redact", action="append", default=[])
    report.add_argument("--summary", type=Path)
    notes = sub.add_parser("amend-notes")
    notes.add_argument("--notes", type=Path, required=True)
    notes.add_argument("--status", type=Path, required=True)
    notes.add_argument("--run-url", required=True)
    notes.add_argument("--asset-url", required=True)
    history = sub.add_parser("amend-history")
    history.add_argument("--notes", type=Path, required=True)
    history.add_argument("--status", type=Path, action="append", required=True)
    history.add_argument("--run-url", required=True)
    args = parser.parse_args()

    if args.command == "report":
        full, summary = build_report(args.evidence_dir, args.release, args.run_url, args.redact)
        (args.evidence_dir / "report.md").write_text(full, encoding="utf-8")
        if args.summary:
            with args.summary.open("a", encoding="utf-8") as handle:
                handle.write(summary)
        LOGGER.info("Wrote %s", args.evidence_dir / "report.md")
        return 0
    if args.command == "amend-history":
        statuses = [json.loads(path.read_text(encoding="utf-8")) for path in args.status]
        if any(status.get("result") != "passed" for status in statuses):
            LOGGER.error("Release notes history is amended only when every provider passed.")
            return 1
        args.notes.write_text(
            amend_history(args.notes.read_text(encoding="utf-8"), statuses, args.run_url),
            encoding="utf-8",
        )
        LOGGER.info("Amended history in %s", args.notes)
        return 0
    status = json.loads(args.status.read_text(encoding="utf-8"))
    if status.get("result") != "passed":
        LOGGER.error("Release notes are amended only for a passed validation.")
        return 1
    args.notes.write_text(
        amend_notes(args.notes.read_text(encoding="utf-8"), status, args.run_url, args.asset_url),
        encoding="utf-8",
    )
    LOGGER.info("Amended %s", args.notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
