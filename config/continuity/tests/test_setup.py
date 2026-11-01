"""The retired configurator cannot activate, reconcile, or remove Azure state."""

import ast
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from config.continuity import setup


@pytest.mark.parametrize("activate", [False, True])
@pytest.mark.parametrize("environment", [
    {},
    {"PRESERVE_CLASSIC_RUNTIME": "true", "HOSTED_CUTOVER_COMPLETE": "true"},
    {"ORCHESTRATION_HOST": "hosted", "APPLICATION_MODE": "both"},
])
def test_retired_command_fails_without_mutating_environment(activate, environment):
    with patch.dict(os.environ, environment, clear=True):
        before = dict(os.environ)
        with pytest.raises(ValueError, match="obsolete.*ORCHESTRATION_HOST"):
            setup.main(activate=activate)
        assert dict(os.environ) == before


def test_retired_command_has_no_azure_or_reconciliation_dependencies():
    tree = ast.parse(Path(setup.__file__).read_text())
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree))
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == {"main"}
