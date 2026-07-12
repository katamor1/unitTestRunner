from __future__ import annotations

import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.test_spec import TestSpec, export_test_spec_views, save_test_spec

from tests.spec_support import copied_payload, current_context


class TestSpecExportTests(unittest.TestCase):
    def test_exports_are_utf8_bom_views_tied_to_exact_canonical_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            canonical = workspace / "reports" / "test_spec.json"
            spec = TestSpec.from_payload(copied_payload())
            save_test_spec(canonical, spec, expected_revision=None, current_context=current_context(workspace))
            paths = export_test_spec_views(spec, canonical.parent, canonical_path=canonical)
            canonical_sha = hashlib.sha256(canonical.read_bytes()).hexdigest()

            self.assertEqual({"markdown", "csv"}, set(paths))
            markdown = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("generated view; edits are not imported", markdown)
            self.assertIn("spec-control-update", markdown)
            self.assertIn("revision: 1", markdown)
            self.assertIn(canonical_sha, markdown)
            self.assertTrue(paths["csv"].read_bytes().startswith(b"\xef\xbb\xbf"))
            with paths["csv"].open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual("generated view; edits are not imported", rows[0]["notice"])
            self.assertEqual(canonical_sha, rows[0]["canonical_sha256"])
            self.assertEqual("1", rows[0]["revision"])


if __name__ == "__main__":
    unittest.main()
