"""Transient provision failure detection in util/release-validation/run-validation.sh."""

import re
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "util" / "release-validation" / "run-validation.sh"
_FUNCTION = re.search(
    r"^provision_failed_transiently\(\) \{\n.*?^\}\n", _SCRIPT.read_text(encoding="utf-8"), re.M | re.S
).group(0)

PLAN = (
    '          + error_message_regex  = [\n'
    '              + "AnotherOperationInProgress",\n'
    '              + "InternalServerError",\n'
    '\x1b[32m              ~ "InternalServerError"\x1b[0m\r\n'
    '            ]\n'
)


def transient(tmp_path: Path, log: str, offset: int = 0) -> bool:
    raw = tmp_path / "transcript.raw.log"
    raw.write_bytes(log.encode("utf-8"))
    script = f"set -euo pipefail\n{_FUNCTION}provision_failed_transiently {offset}\n"
    env = {**os.environ, "RAW_LOG": str(raw)}
    return subprocess.run(["bash", "-c", script], env=env, check=False).returncode == 0


# The harness runs only on the Linux validation executor.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or not shutil.which("bash") or not shutil.which("awk"), reason="Linux harness"
)


def test_terraform_plan_retry_settings_are_not_a_transient_failure(tmp_path):
    assert not transient(tmp_path, PLAN + "ERROR: Invalid application database name.\n")


@pytest.mark.parametrize("error", [
    '  "code": "InternalServerError",\n',
    "\x1b[31m│\x1b[0m Error: creating Private Endpoint: ERROR CODE: InternalServerError\r\n",
    (
        "ManagedEnvironmentOperationFailed: The managed environment's operation failed due to internal server error," +
        " please retry later.\n"
    ),
])
def test_azure_internal_server_error_is_transient(tmp_path, error):
    assert transient(tmp_path, PLAN + error)


def test_only_the_current_provision_attempt_is_read(tmp_path):
    earlier = '  "code": "InternalServerError",\n'
    assert not transient(tmp_path, earlier + PLAN, offset=len(earlier.encode()))
