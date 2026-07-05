import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from unit_test_runner.reanalysis.reanalysis_models import (
    AnalysisSnapshot,
    ReanalysisPolicy,
    SnapshotArtifact,
)


class ReanalysisModelTests(unittest.TestCase):
    def test_policy_defaults_preserve_reviewed_test_assets(self):
        policy = ReanalysisPolicy()

        payload = policy.to_dict()

        self.assertTrue(payload["preserve_manual_edits"])
        self.assertTrue(payload["reuse_test_case_ids"])
        self.assertFalse(payload["generate_updated_test_case_design"])
        self.assertFalse(payload["overwrite_test_case_design"])
        self.assertTrue(payload["select_regression_tests"])

    def test_snapshot_serializes_artifact_metadata(self):
        snapshot = AnalysisSnapshot(
            snapshot_id="previous",
            function_name="Control_Update",
            source_path=Path("src/control.c"),
            source_sha256="abc123",
            build_context_hash="ctx123",
            created_at="2026-07-05T00:00:00+00:00",
            artifacts={
                "function_signature": SnapshotArtifact(
                    artifact_kind="function_signature",
                    path=Path("reports/function_signature.json"),
                    sha256="sig123",
                    schema_version="0.1",
                    exists=True,
                )
            },
        )

        payload = snapshot.to_dict()

        self.assertEqual("previous", payload["snapshot_id"])
        self.assertEqual("Control_Update", payload["function_name"])
        self.assertEqual("src/control.c", payload["source_path"])
        self.assertEqual("sig123", payload["artifacts"]["function_signature"]["sha256"])


if __name__ == "__main__":
    unittest.main()
