"""Local presentation contract integrity, not runtime or live acceptance."""

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
DESIGN = ROOT / "specs/005-inline-visual-output/contracts"
PAIRS = (
    ("agent-presentation-settings-v1", "settings"),
    ("presentation-selection-v1", "selection"),
    ("turn-presentation-v1", "presentation"),
)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


@pytest.mark.parametrize("name,fixture", PAIRS)
def test_promoted_schema_integrity_and_examples(name, fixture):
    path = CONTRACTS / (name + ".schema.json")
    data = path.read_bytes()
    assert b"\r" not in data
    assert data == (DESIGN / path.name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == path.with_suffix(
        path.suffix + ".sha256"
    ).read_text().split()[0]
    schema = json.loads(data, object_pairs_hook=unique_pairs)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for suffix in ("valid", "invalid"):
        value = json.loads(
            (CONTRACTS / "examples/inline-presentation" / f"{fixture}-{suffix}.json").read_text(),
            object_pairs_hook=unique_pairs,
        )
        assert bool(list(validator.iter_errors(value))) == (suffix == "invalid")


def test_default_settings_and_measurement_free_selection():
    schema = json.loads((CONTRACTS / "agent-presentation-settings-v1.schema.json").read_text())
    Draft202012Validator(schema).validate({"schemaVersion": 1, "agents": {}})
    selection = json.loads((CONTRACTS / "presentation-selection-v1.schema.json").read_text())
    # Numeric measurements belong to hydration, never a selection proposal.
    properties = [
        definition.get("properties", {})
        for definition in selection["$defs"].values()
    ]
    assert not any("values" in fields or "value" in fields for fields in properties)


def test_duplicate_keys_are_not_valid_contract_input():
    with pytest.raises(ValueError, match="Duplicate"):
        json.loads('{"schemaVersion":1,"schemaVersion":2}', object_pairs_hook=unique_pairs)
