import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from unit_test_runner.reanalysis.snapshot_builder import build_analysis_snapshot


class ReanalysisSnapshotBuilderTests(unittest.TestCase):
    def test_snapshot_hashing_keeps_missing_and_parse_warnings_separate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reports = root / "reports"
            reports.mkdir()
            (reports / "source_digest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "0.1",
                        "source": {"path": "src/control.c", "sha256": "source123"},
                    }
                ),
                encoding="utf-8",
            )
            (reports / "function_signature.json").write_text("{not json", encoding="utf-8")

            snapshot, warnings, payloads = build_analysis_snapshot(
                "previous",
                root,
                "Control_Update",
                report_subdir=Path("reports"),
            )

        self.assertEqual("source123", snapshot.source_sha256)
        self.assertTrue(snapshot.artifacts["source_digest"].exists)
        self.assertTrue(snapshot.artifacts["function_signature"].exists)
        self.assertIn("source_digest", payloads)
        codes = {warning.code for warning in warnings}
        self.assertIn("artifact_parse_failed", codes)
        self.assertIn("previous_artifact_missing", codes)


if __name__ == "__main__":
    unittest.main()
