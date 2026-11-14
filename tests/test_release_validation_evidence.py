"""Release-notes amendment contract of util/release-validation/evidence.py."""

import importlib.util
from pathlib import Path
import unittest

_PATH = Path(__file__).resolve().parents[1] / "util" / "release-validation" / "evidence.py"
_SPEC = importlib.util.spec_from_file_location("release_validation_evidence", _PATH)
evidence = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(evidence)

NOTES = (
    "## Changed\n- Fix.\n\n## Component versions\n\n| Component | Version |\n| --- | --- |\n"
    "| agent-app-ui | v1.0.0 |\n\n## Validation\n- Offline contracts passed.\n"
)


def status(provider, updated="2026-11-14T10:00:00Z"):
    return {"provider": provider, "location": "swedencentral", "updated": updated, "result": "passed"}


class AmendNotesTests(unittest.TestCase):
    def amend(self, notes, provider, **kwargs):
        return evidence.amend_notes(notes, status(provider, **kwargs), "https://run", f"https://{provider}.md")

    def test_adds_one_line_per_provider_and_keeps_headings_at_line_start(self):
        notes = self.amend(self.amend(NOTES, "bicep"), "terraform")
        lines = notes.splitlines()
        self.assertEqual([line for line in lines if line.startswith("## ")],
                         ["## Changed", "## Component versions", "## Validation"])
        validation = lines[lines.index("## Validation") + 1:]
        self.assertEqual(validation[0], "- Offline contracts passed.")
        self.assertIn("Live Bicep deployment", validation[1])
        self.assertIn("<!-- release-validation:bicep -->", validation[1])
        self.assertIn("Live Terraform deployment", validation[2])
        self.assertIn("<!-- release-validation:terraform -->", validation[2])
        self.assertIn("| agent-app-ui | v1.0.0 |", lines)

    def test_revalidation_replaces_only_the_same_provider_line(self):
        notes = self.amend(self.amend(NOTES, "bicep"), "terraform")
        notes = self.amend(notes, "bicep", updated="2026-11-21T10:00:00Z")
        self.assertEqual(notes.count("<!-- release-validation:bicep -->"), 1)
        self.assertEqual(notes.count("<!-- release-validation:terraform -->"), 1)
        self.assertIn("passed on 2026-11-21", notes)

    def test_appends_validation_section_when_missing(self):
        notes = self.amend("## Changed\n- Fix.\n\n", "terraform")
        self.assertTrue(notes.splitlines()[-2:][0] == "## Validation")
        self.assertIn("<!-- release-validation:terraform -->", notes.splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
