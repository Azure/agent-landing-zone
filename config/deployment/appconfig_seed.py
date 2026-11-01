"""Seed missing defaults without replacing foundation or operator settings."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from config.deployment.appconfig import _run_az
from config.deployment.composition import APP_CONFIG_LABEL

LOGGER = logging.getLogger(__name__)


def select_missing_settings(desired: object, existing_keys: object) -> dict[str, str]:
    if not isinstance(desired, dict):
        raise ValueError("App Configuration seed input must be an object.")
    validated: dict[str, str] = {}
    for key, value in desired.items():
        if not isinstance(key, str) or not key or not isinstance(value, str):
            raise ValueError("App Configuration seed keys and values must be strings.")
        validated[key] = value
    if not isinstance(existing_keys, list) or any(
        not isinstance(key, str) or not key for key in existing_keys
    ):
        raise ValueError("App Configuration returned an invalid existing-key inventory.")
    present = set(existing_keys)
    return {key: value for key, value in validated.items() if key not in present}


def prepare_seed_file(path: Path, endpoint: str) -> int:
    desired = select_missing_settings(json.loads(path.read_text(encoding="utf-8-sig")), [])
    existing_keys = json.loads(_run_az([
        "appconfig", "kv", "list",
        "--endpoint", endpoint,
        "--label", APP_CONFIG_LABEL,
        "--auth-mode", "login",
        "--all", "--query", "[].key", "--output", "json",
    ]))
    missing = select_missing_settings(desired, existing_keys)
    path.write_text(json.dumps(missing, ensure_ascii=True), encoding="utf-8")
    return len(missing)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        count = prepare_seed_file(args.input, args.endpoint)
    except (OSError, ValueError, RuntimeError) as exc:
        LOGGER.error("Cannot prepare App Configuration defaults: %s", exc)
        return 1
    print(json.dumps({"seedCount": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
