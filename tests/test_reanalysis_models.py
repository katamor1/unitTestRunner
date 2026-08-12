import json
import tempfile
import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from unit_test_runner.reanalysis.reanalysis_models import (
    AnalysisSnapshot,
    ChangeImpactReport,
    RegressionSelection,
    ReanalysisPolicy,
    SnapshotArtifact,
    TestCaseReconciliationReport,
)
from unit_test_runner.reanalysis.reanalysis_report_writer import write_reanalysis_reports
from unit_test_runner.workspace_artifacts import (
    apply_reanalysis_candidate,
    artifact_sha256,
    load_public_artifact,
    write_canonical_artifact,
)
from unit_test_runner.contracts import ArtifactKind


def test_spec_data(
    revision: int,
    test_cases: list[dict],
    unresolved_items: list[dict] | None = None,
) -> dict:
    return {
        "spec_id": "spec-control-update",
        "revision": revision,
        "source": {"path": "src/control.c", "sha256": "a" * 64},
        "function": {"name": "Control_Update"},
        "generated_from": [],
        "generation_policy": {},
        "test_cases": test_cases,
        "additional_case_candidates": [],
        "coverage_summary": {},
        "unresolved_items": list(unresolved_items or []),
        "warnings": [],
        "review_item_ids": [],
    }


class ReanalysisModelTests(unittest.TestCase):
    def test_apply_candidate_requires_exact_sha_and_revision_then_invalidates_downstream_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            subject = {
                "source_path": "src/control.c",
                "source_sha256": "a" * 64,
                "function": "Control_Update",
                "project": "Control",
                "configuration": "Control - Win32 Debug",
            }
            write_canonical_artifact(
                workspace,
                ArtifactKind.TEST_SPEC,
                subject,
                test_spec_data(3, [{"test_case_id": "old"}]),
            )
            candidate = workspace / "reports" / "reanalysis_candidate_test_spec.json"
            candidate.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "artifact_kind": "test_spec",
                        "subject": subject,
                        "data": test_spec_data(3, [{"test_case_id": "new"}]),
                    }
                ),
                encoding="utf-8",
            )
            review = workspace / "reports" / "review_record.json"
            build = workspace / "reports" / "build_probe_report.json"
            review.write_text("stale", encoding="utf-8")
            build.write_text("stale", encoding="utf-8")

            applied, revision = apply_reanalysis_candidate(
                workspace,
                candidate,
                candidate_sha256=artifact_sha256(candidate),
                expected_revision=3,
            )

            payload = load_public_artifact(applied, ArtifactKind.TEST_SPEC)
            self.assertEqual(4, revision)
            self.assertEqual(4, payload["data"]["revision"])
            self.assertEqual("new", payload["data"]["test_cases"][0]["test_case_id"])
            self.assertFalse(review.exists())
            self.assertFalse(build.exists())

    def test_apply_candidate_rejects_conflicts_and_preserves_canonical_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            subject = {
                "source_path": "src/control.c",
                "source_sha256": "a" * 64,
                "function": "Control_Update",
                "project": "Control",
                "configuration": "Control - Win32 Debug",
            }
            canonical = write_canonical_artifact(
                workspace,
                ArtifactKind.TEST_SPEC,
                subject,
                test_spec_data(1, []),
            )
            before = canonical.read_bytes()
            candidate = workspace / "reports" / "reanalysis_candidate_test_spec.json"
            candidate.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "artifact_kind": "test_spec",
                        "subject": subject,
                        "data": test_spec_data(
                            1,
                            [],
                            [{"item_kind": "reanalysis_merge_conflict"}],
                        ),
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "conflict"):
                apply_reanalysis_candidate(
                    workspace,
                    candidate,
                    candidate_sha256=artifact_sha256(candidate),
                    expected_revision=1,
                )
            self.assertEqual(before, canonical.read_bytes())

    def test_policy_defaults_preserve_reviewed_test_assets(self):
        policy = ReanalysisPolicy()

        payload = policy.to_dict()

        self.assertTrue(payload["preserve_manual_edits"])
        self.assertTrue(payload["reuse_test_case_ids"])
        self.assertTrue(payload["generate_updated_test_case_design"])
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

    def test_writer_publishes_one_reanalysis_envelope_and_keeps_views(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            reports = workspace / "reports"
            reports.mkdir()
            subject = {
                "source_path": "src/control.c",
                "source_sha256": "a" * 64,
                "function": "Control_Update",
                "project": "Control",
                "configuration": "Win32 Debug",
            }
            current_subject = {**subject, "source_sha256": "b" * 64}
            (reports / "function_dossier.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "artifact_kind": "function_dossier",
                        "subject": subject,
                        "data": {
                            "target": subject,
                            "project_membership": [],
                            "build_context": {},
                            "function": {},
                            "test_design": {},
                            "diagnostics": [],
                            "workspace_root": ".",
                            "created_at": "2026-08-11T00:00:00Z",
                            "artifact_index": [],
                            "summaries": {},
                            "traceability": [],
                            "review_items": [],
                            "unresolved_items": [],
                            "next_actions": [],
                            "readiness": {},
                            "warnings": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            previous = AnalysisSnapshot(
                "previous",
                "Control_Update",
                Path("src/control.c"),
                "a" * 64,
                None,
                None,
            )
            current = AnalysisSnapshot(
                "current",
                "Control_Update",
                Path("src/control.c"),
                "b" * 64,
                None,
                None,
            )
            paths = write_reanalysis_reports(
                workspace,
                ChangeImpactReport("Control_Update", "changed", previous, current),
                TestCaseReconciliationReport("Control_Update", "completed"),
                RegressionSelection("Control_Update", "completed"),
                candidate={
                    "path": "reports/reanalysis_candidate_test_spec.json",
                    "sha256": "d" * 64,
                    "base_revision": 1,
                    "conflict_count": 0,
                },
            )

            payload = json.loads(paths["reanalysis_report_json"].read_text(encoding="utf-8"))
            self.assertEqual(
                {"schema_version", "artifact_kind", "subject", "data"},
                set(payload),
            )
            self.assertEqual("1.0.0", payload["schema_version"])
            self.assertEqual("reanalysis_report", payload["artifact_kind"])
            self.assertEqual(current_subject, payload["subject"])
            self.assertEqual(
                {
                    "change_impact",
                    "test_case_reconciliation",
                    "regression_selection",
                    "candidate",
                },
                set(payload["data"]),
            )
            self.assertEqual(
                "d" * 64,
                payload["data"]["candidate"]["sha256"],
            )
            self.assertEqual("changed", payload["data"]["change_impact"]["status"])
            self.assertEqual(
                "completed",
                payload["data"]["test_case_reconciliation"]["status"],
            )
            self.assertFalse((reports / "change_impact_report.json").exists())
            self.assertFalse((reports / "test_case_reconciliation_report.json").exists())
            self.assertFalse((reports / "regression_selection.json").exists())
            for key in (
                "change_impact_report_md",
                "test_case_reconciliation_report_md",
                "regression_selection_csv",
            ):
                self.assertTrue(paths[key].is_file(), key)

            invalid_dossier = json.loads(
                (reports / "function_dossier.json").read_text(encoding="utf-8")
            )
            invalid_dossier["unexpected"] = True
            (reports / "function_dossier.json").write_text(
                json.dumps(invalid_dossier),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Invalid function_dossier"):
                write_reanalysis_reports(
                    workspace,
                    ChangeImpactReport("Control_Update", "changed", previous, current),
                    TestCaseReconciliationReport("Control_Update", "completed"),
                    RegressionSelection("Control_Update", "completed"),
                )


if __name__ == "__main__":
    unittest.main()
