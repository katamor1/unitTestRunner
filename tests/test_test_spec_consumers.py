from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.dossier.workflow import load_test_spec_for_consumer
from unit_test_runner.execution.test_execution import _read_canonical_test_spec

from tests.test_test_spec_cli import create_workspace


class TestSpecConsumerTests(unittest.TestCase):
    def test_canonical_envelope_is_normalized_to_consumer_data_and_views_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = create_workspace(workspace)

            canonical = json.loads(path.read_text(encoding="utf-8"))
            payload = load_test_spec_for_consumer(path)

            self.assertEqual(canonical["data"]["spec_id"], payload["spec_id"])
            self.assertEqual(
                canonical["data"]["test_cases"][0]["test_case_id"],
                payload["test_cases"][0]["test_case_id"],
            )
            markdown = workspace / "reports" / "test_spec.md"
            markdown.write_text("generated view; edits are not imported", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_test_spec_for_consumer(markdown)

    def test_canonical_consumers_fail_closed_after_source_becomes_stale(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = create_workspace(workspace)
            (workspace / "src" / "control.c").write_text(
                "int Control_Update(int mode) { return mode + 1; }\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_test_spec_for_consumer(path)
            with self.assertRaises(ValueError):
                _read_canonical_test_spec(workspace / "reports")


if __name__ == "__main__":
    unittest.main()
