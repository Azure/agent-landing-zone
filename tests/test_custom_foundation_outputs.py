"""Foundation endpoint handoff must not depend on bundled hosted selection."""

from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name,flag,value", [
    ("AZURE_AI_PROJECT_RESOURCE_ID", "deployAiFoundry", "aiFoundryProjectResourceId"),
    ("AZURE_AI_PROJECT_ENDPOINT", "deployAiFoundry", "aiFoundryProjectEndpoint"),
    ("AZURE_CONTAINER_REGISTRY_RESOURCE_ID", "deployContainerRegistry",
     "_hostedAgentContainerRegistryResourceId"),
    ("AZURE_CONTAINER_REGISTRY_ENDPOINT", "deployContainerRegistry",
     "_hostedAgentContainerRegistryEndpoint"),
])
def test_foundation_handoff_preserves_disabled_and_external_hosted_cases(name, flag, value):
    text = (ROOT / "infra" / "main.bicep").read_text(encoding="utf-8")
    expression = re.search(rf"^output {name} string = (.+)$", text, re.MULTILINE)[1]
    assert expression == f"({flag} || _hostedAgentPrerequisitesEnabled) ? {value} : ''"
    for provisioned, hosted, expected in (
        (False, False, ""), (True, False, value),
        (False, True, value), (True, True, value),
    ):
        assert (value if provisioned or hosted else "") == expected
