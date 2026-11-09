"""Customer sample uses the matched reader, not another envelope parser."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "contracts/examples/inline-presentation"


def adapter():
    spec = importlib.util.spec_from_file_location(
        "customer_text_adapter", EXAMPLES / "text_only_adapter.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def native_message(presentation):
    return {
        "id": "synthetic-native-message",
        "role": "assistant",
        "type": "message",
        "content": [{"type": "output_text", "text": json.dumps(presentation)}],
    }


def test_customer_adapter_requires_existing_owner_admission():
    with pytest.raises(PermissionError):
        adapter().render_text({"content": "private"}, owner_admitted=False)


@pytest.mark.parametrize("future", ["none", "block", "version"])
def test_customer_adapter_exact_text_survives_future_blocks_and_versions(future):
    value = json.loads((EXAMPLES / "presentation-valid.json").read_text(encoding="utf-8"))
    if future == "block":
        value["contributions"][0]["blocks"].append(
            {"blockId": "future", "type": "future-widget", "url": "https://invalid.example"}
        )
    elif future == "version":
        value["schemaVersion"] = 2
    result = adapter().render_text(native_message(value), owner_admitted=True)
    assert result == value["markdown"]
    assert "9.750" in result and "-2.750 (down)" in result
    assert "future-widget" not in result and "invalid.example" not in result


def test_customer_adapter_legacy_narration_and_ordinary_followup_are_not_envelopes():
    value = {"role": "assistant", "content": [{"type": "output_text", "text": "Plain answer."}]}
    assert adapter().render_text(value, owner_admitted=True) == "Plain answer."
    # Ordinary user input remains ordinary input, never assistant-carrier admission.
    followup = {"role": "user", "content": [{"type": "text", "text": "Compare March with January."}]}
    assert adapter().render_text(followup, owner_admitted=True) == "Compare March with January."
