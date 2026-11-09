"""Optional cross-component wheel receipt, never downloading dependencies."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


@unittest.skipUnless(os.environ.get("INLINE_ORCH_WHEEL") and os.environ.get("INLINE_UI_WHEEL"),
                     "Supply explicitly built local component wheels")
class PresentationPackagingTests(unittest.TestCase):
    def test_exact_schema_assets_and_package_only_reader_paths(self):
        root = Path(__file__).parents[1]
        names = ("agent-presentation-settings", "presentation-selection", "turn-presentation")
        for variable, package in (("INLINE_ORCH_WHEEL", "native"), ("INLINE_UI_WHEEL", "gpt_rag_ui")):
            with self.subTest(package=package), tempfile.TemporaryDirectory() as directory:
                with zipfile.ZipFile(os.environ[variable]) as wheel:
                    for name in names:
                        filename = name + "-v1.schema.json"
                        reviewed = (root / "contracts" / filename).read_bytes()
                        self.assertNotIn(b"\r", reviewed)
                        actual = wheel.read(f"{package}/contracts/{filename}")
                        integrity = wheel.read(f"{package}/contracts/{filename}.sha256")
                        self.assertEqual(actual, reviewed)
                        self.assertEqual(integrity, (root / "contracts" / (filename + ".sha256")).read_bytes())
                        self.assertEqual(hashlib.sha256(actual).hexdigest(), integrity.decode().split()[0])
                    wheel.extractall(directory)
                script = """
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
package_root = pathlib.Path(sys.argv[1]).resolve()
if sys.argv[2] == 'native':
    import native.presentation as implementation
    assert pathlib.Path(implementation.ROOT) == package_root / 'native/contracts'
    implementation.validator('turn-presentation').check_schema(implementation.validator('turn-presentation').schema)
else:
    import gpt_rag_ui.services.native_presentation as implementation
    assert pathlib.Path(implementation.SCHEMA) == package_root / 'gpt_rag_ui/contracts/turn-presentation-v1.schema.json'
    assert json.loads(implementation.SCHEMA.read_text())['properties']['schemaVersion']['const'] == 1
assert pathlib.Path(implementation.__file__).resolve().is_relative_to(package_root)
"""
                completed = subprocess.run([sys.executable, "-c", script, directory, package],
                                           capture_output=True, text=True, timeout=30, check=False)
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
