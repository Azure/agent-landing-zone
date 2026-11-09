"""Validate owner-edited presentation configuration; no runtime production."""

from decimal import Decimal
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

KEY = "AGENT_PRESENTATION_SETTINGS"
SCHEMA = Path(__file__).resolve().parents[2] / "contracts/agent-presentation-settings-v1.schema.json"


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("nonfinite JSON")


def _interval(tests):
    lower, upper = Decimal("-Infinity"), Decimal("Infinity")
    lower_closed = upper_closed = False
    for test in tests:
        value, operator = Decimal(test["threshold"]), test["operator"]
        if operator in ("gt", "gte", "eq"):
            closed = operator != "gt"
            if value > lower:
                lower, lower_closed = value, closed
            elif value == lower:
                lower_closed = lower_closed and closed
        if operator in ("lt", "lte", "eq"):
            closed = operator != "lt"
            if value < upper:
                upper, upper_closed = value, closed
            elif value == upper:
                upper_closed = upper_closed and closed
    if lower > upper or (lower == upper and not (lower_closed and upper_closed)):
        raise ValueError("empty rule interval")
    return lower, lower_closed, upper, upper_closed


def validate_settings(value: str) -> str:
    """Return compact JSON or a safe, actionable error without source values."""
    try:
        if len(value.encode("utf-8")) > 10000:
            raise ValueError("value exceeds App Configuration limit")
        document = json.loads(value, object_pairs_hook=_pairs, parse_constant=_nonfinite)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        if not Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(document):
            raise ValueError("unsupported version or invalid settings shape")
        for agent in document["agents"].values():
            identifiers = set()
            for rule in agent.get("rules", []):
                if rule["id"] in identifiers:
                    raise ValueError("duplicate rule ID")
                identifiers.add(rule["id"])
                intervals = [_interval(case["tests"]) for case in rule["cases"]]
                for index, left in enumerate(intervals):
                    for right in intervals[index + 1:]:
                        a, b = sorted((left, right), key=lambda item: item[0])
                        if a[2] > b[0] or (a[2] == b[0] and a[3] and b[1]):
                            raise ValueError("overlapping rule cases")
        return json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise ValueError(f"{KEY}: invalid JSON object, version, identifiers or disjoint rules.") from None
