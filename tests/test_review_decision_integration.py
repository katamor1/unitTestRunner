from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.contracts import ArtifactKind, ContractMode, load_artifact
from unit_test_runner.dossier.finalizer import finalize_function_dossier
from unit_test_runner.dossier.review_assessment import discover_review_snapshot
from unit_test_runner.dossier.workflow import analyze_function_workflow


REPO_ROOT = Path(__file__).resolve().parents[1]
VC6_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


class ReviewDecisionDossierIntegrationTests(unittest.TestCase):
    def test_finalize_writes_current_dossier_with_exact_noncyclic_review_subjects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "Control_Update"
            analyze_function_workflow(
                VC6_FIXTURE,
                VC6_FIXTURE / "Product.dsw",
                "src/control.c",
                "Control_Update",
                "Win32 Debug",
                workspace,
                "Control",
                phase="design",
            )

            finalize_function_dossier(workspace)

            dossier_path = workspace / "reports" / "function_dossier.json"
            payload = json.loads(dossier_path.read_text(encoding="utf-8"))
            self.assertEqual("function_dossier", payload["artifact_kind"])
            self.assertEqual("1.1.0", payload["schema_version"])
            self.assertTrue(payload["subject"]["function_id"].startswith("fn_"))
            self.assertEqual("src/control.c", payload["subject"]["source_path"])
            self.assertNotIn('"done"', dossier_path.read_text(encoding="utf-8"))
            for item in payload["data"]["review_items"]:
                self.assertTrue(item["subject_artifacts"], item["review_id"])
                self.assertNotIn(
                    "reports/function_dossier.json",
                    {ref["path"] for ref in item["subject_artifacts"]},
                )

            loaded = load_artifact(
                dossier_path,
                expected_kind=ArtifactKind.FUNCTION_DOSSIER,
                mode=ContractMode.STRICT,
            )
            self.assertEqual((), loaded.violations)
            snapshot = discover_review_snapshot(workspace)
            self.assertEqual(
                {item["review_id"] for item in payload["data"]["review_items"]},
                {item.review_id for item in snapshot.items.items},
            )
            self.assertEqual(payload["subject"]["function_id"], snapshot.function_id)
            self.assertEqual(payload["subject"]["source_path"], snapshot.source_path)
            self.assertEqual(payload["subject"]["source_sha256"], snapshot.source_sha256)

            manifest_path = workspace / "reports" / "dossier_manifest.json"
            manifest = load_artifact(
                manifest_path,
                expected_kind=ArtifactKind.DOSSIER_MANIFEST,
                mode=ContractMode.STRICT,
            )
            self.assertEqual((), manifest.violations)


if __name__ == "__main__":
    unittest.main()
