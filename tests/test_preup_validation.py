"""Exercise both preup hooks against the real definition and binding CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PreUpValidationTests(unittest.TestCase):
    def check_hook(self, shell: str) -> None:
        suffix = "ps1" if shell == "pwsh" else "sh"
        with tempfile.TemporaryDirectory(prefix="preup validation ") as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            script = scripts / f"preUp.{suffix}"
            shutil.copyfile(ROOT / "scripts" / script.name, script)
            shutil.copytree(ROOT / "contracts", root / "contracts")
            for name in ("manifest.json", "azure.yaml", "app-definition.json"):
                shutil.copyfile(ROOT / name, root / name)
            definition = root / "app-definition.json"
            valid = json.loads(definition.read_text(encoding="utf-8"))
            env_file = root / ".azure" / "offline" / ".env"
            env_file.parent.mkdir(parents=True)
            env_file.write_text('AZURE_ENV_NAME="offline"\n', encoding="utf-8")
            before = env_file.read_bytes()
            environment = dict(
                os.environ, PYTHONPATH=str(ROOT), AGENTLZ_REPO_ROOT=str(root),
                AGENTLZ_APP_DEFINITION=str(definition), AZURE_ENV_NAME="offline",
            )
            command = ([shutil.which(shell), "-NoProfile", "-NonInteractive", "-File", str(script)]
                       if shell == "pwsh" else [shutil.which(shell), str(script)])
            for case, code, message in (
                ("valid", 0, "is valid"),
                ("missing-id", 1, "/id"),
                ("unknown-profile", 1, "/components/0/profiles/0"),
                ("changed-binding", 2, "Create a new azd environment"),
            ):
                with self.subTest(shell=shell, case=case):
                    data = json.loads(json.dumps(valid))
                    if case == "missing-id":
                        del data["id"]
                    elif case == "unknown-profile":
                        data["components"][0]["profiles"] = ["not-a-profile"]
                    elif case == "changed-binding":
                        env_file.write_text('AGENTLZ_APP_ID="other-app"\n', encoding="utf-8")
                        before = env_file.read_bytes()
                    definition.write_text(json.dumps(data), encoding="utf-8")
                    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                                            text=True, timeout=30)
                    output = result.stdout + result.stderr
                    self.assertEqual(code, result.returncode, output)
                    self.assertIn(message, output)
                    self.assertEqual(before, env_file.read_bytes())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_preup_validation(self) -> None:
        self.check_hook("pwsh")

    @unittest.skipUnless(shutil.which("bash"), "Bash is not installed")
    def test_shell_preup_validation(self) -> None:
        self.check_hook("bash")


if __name__ == "__main__":
    unittest.main()
