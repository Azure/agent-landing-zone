"""Exact, disjoint owner rules and safe config errors."""

import copy
import json

import pytest

from config.deployment.presentation_settings import validate_settings
from tests.test_presentation_contracts import CONTRACTS


def fixture():
    return json.loads((CONTRACTS / "examples/inline-presentation/settings-valid.json").read_text())


def test_approved_disjoint_rule_and_precision():
    document = fixture()
    assert json.loads(validate_settings(json.dumps(document))) == document


@pytest.mark.parametrize("tests", [
    [{"operator": "gte", "threshold": "0"}],
    [{"operator": "gt", "threshold": "1"}, {"operator": "lt", "threshold": "0"}],
    [{"operator": "gt", "threshold": "0"}, {"operator": "lte", "threshold": "0"}],
])
def test_overlapping_or_empty_cases_error(tests):
    document = fixture()
    rule = document["agents"]["agent-lz-conversation"]["rules"][0]
    rule["cases"][0]["tests"] = tests
    with pytest.raises(ValueError, match="AGENT_PRESENTATION_SETTINGS"):
        validate_settings(json.dumps(document))


def test_duplicate_rule_ids_error():
    document = fixture()
    rules = document["agents"]["agent-lz-conversation"]["rules"]
    rules.append(copy.deepcopy(rules[0]))
    with pytest.raises(ValueError, match="AGENT_PRESENTATION_SETTINGS"):
        validate_settings(json.dumps(document))


def test_error_never_includes_guidance_or_raw_values():
    with pytest.raises(ValueError) as caught:
        validate_settings('{"private-guidance": "do-not-log-this"}')
    assert "do-not-log-this" not in str(caught.value)
