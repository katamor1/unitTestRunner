from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.workspace_artifacts import (
    WorkspaceRegenerationRequired,
    artifact_sha256,
    is_current_review_approved,
    load_public_artifact,
    set_review_record,
    write_canonical_artifact,
    write_test_run_report,
)
from unit_test_runner.execution.execution_models import TestRunRequest
from unit_test_runner.execution.test_execution import execute_test_run


def subject() -> dict[str, str]:
    return {
        "source_path": "src/control.c",
        "source_sha256": "a" * 64,
        "function": "Control_Update",
        "project": "Control",
        "configuration": "Control - Win32 Debug",
    }


def dossier_data() -> dict[str, object]:
    return {
        "target": {}, "project_membership": [], "build_context": {},
        "function": {}, "test_design": {}, "diagnostics": [],
        "workspace_root": ".", "created_at": "2026-08-11T00:00:00Z",
        "artifact_index": [], "summaries": {}, "traceability": [],
        "review_items": [], "unresolved_items": [], "next_actions": [],
        "readiness": {}, "warnings": [],
    }


def test_spec_data(revision: int = 1) -> dict[str, object]:
    return {
        "spec_id": "spec-control-update", "revision": revision,
        "source": {"path": "src/control.c", "sha256": "a" * 64},
        "function": {"name": "Control_Update"}, "generated_from": [],
        "generation_policy": {}, "test_cases": [],
        "additional_case_candidates": [], "coverage_summary": {},
        "unresolved_items": [], "warnings": [], "review_item_ids": [],
    }


def test_run_data(run_id: str = "run-0001", outcome: str = "passed") -> dict[str, object]:
    return {
        "run_id": run_id, "outcome": outcome, "executed": True,
        "test_spec_sha256": "b" * 64, "requested_case_ids": [],
        "started_case_ids": [], "completed_case_ids": [],
        "not_run_case_ids": [], "summary": {}, "case_results": [],
        "warnings": [],
    }


class V01WorkspacePersistenceTests(unittest.TestCase):
    def test_dossier_and_test_spec_use_only_canonical_report_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dossier = write_canonical_artifact(
                root,
                ArtifactKind.FUNCTION_DOSSIER,
                subject(),
                dossier_data(),
            )
            spec = write_canonical_artifact(
                root,
                ArtifactKind.TEST_SPEC,
                subject(),
                test_spec_data(),
            )

            self.assertEqual(root / "reports" / "function_dossier.json", dossier)
            self.assertEqual(root / "reports" / "test_spec.json", spec)
            for path, kind in (
                (dossier, ArtifactKind.FUNCTION_DOSSIER),
                (spec, ArtifactKind.TEST_SPEC),
            ):
                payload = load_public_artifact(path, kind)
                self.assertEqual(
                    {"schema_version", "artifact_kind", "subject", "data"},
                    set(payload),
                )

    def test_old_workspace_requires_explicit_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "reports" / "test_spec.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.1.0",
                        "artifact_kind": "test_spec",
                        "subject": subject(),
                        "data": {"revision": 4},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(WorkspaceRegenerationRequired, "regenerate"):
                load_public_artifact(path, ArtifactKind.TEST_SPEC)

    def test_review_record_approves_only_the_current_artifact_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = write_canonical_artifact(
                root,
                ArtifactKind.TEST_SPEC,
                subject(),
                test_spec_data(),
            )
            digest = artifact_sha256(spec)

            review = set_review_record(
                root,
                artifact_kind=ArtifactKind.TEST_SPEC,
                artifact_sha256_value=digest,
                decision="approved",
                reviewer="reviewer@example.com",
                reviewed_at="2026-08-11T00:00:00Z",
                comment="ready",
            )

            self.assertEqual(root / "reports" / "review_record.json", review)
            self.assertTrue(is_current_review_approved(root, ArtifactKind.TEST_SPEC))

    def test_artifact_change_invalidates_previous_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = write_canonical_artifact(
                root,
                ArtifactKind.TEST_SPEC,
                subject(),
                test_spec_data(),
            )
            set_review_record(
                root,
                artifact_kind=ArtifactKind.TEST_SPEC,
                artifact_sha256_value=artifact_sha256(spec),
                decision="approved",
                reviewer="reviewer@example.com",
                reviewed_at="2026-08-11T00:00:00Z",
                comment="ready",
            )

            write_canonical_artifact(
                root,
                ArtifactKind.TEST_SPEC,
                subject(),
                test_spec_data(2),
            )

            self.assertFalse(is_current_review_approved(root, ArtifactKind.TEST_SPEC))

    def test_test_run_is_an_ordinary_run_report_without_pointer_or_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = write_test_run_report(
                root,
                "run-0001",
                subject(),
                test_run_data(),
            )

            self.assertEqual(root / "runs" / "run-0001" / "test_run_report.json", path)
            self.assertFalse((root / "runs" / "latest.json").exists())
            self.assertFalse((root / "evidence").exists())
            self.assertNotIn("previous_sha256", path.read_text(encoding="utf-8"))

    def test_test_run_rejects_path_like_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "run_id"):
                write_test_run_report(
                    Path(temp),
                    "../escape",
                    subject(),
                    test_run_data("escape"),
                )

    def test_test_run_does_not_overwrite_an_existing_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_test_run_report(
                root,
                "run-0001",
                subject(),
                test_run_data(),
            )
            with self.assertRaisesRegex(FileExistsError, "already exists"):
                write_test_run_report(
                    root,
                    "run-0001",
                    subject(),
                    test_run_data(outcome="failed"),
                )

    def test_real_run_requires_current_approval_before_runner_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_canonical_artifact(
                root,
                ArtifactKind.TEST_SPEC,
                subject(),
                test_spec_data(),
            )
            with patch(
                "unit_test_runner.execution.test_execution.run_test_executable_cases"
            ) as runner:
                with self.assertRaisesRegex(PermissionError, "approved review_record"):
                    execute_test_run(
                        TestRunRequest(
                            workspace=root,
                            executable=None,
                            timeout_seconds=60,
                            allow_placeholder_tests=False,
                            run_id="run-0001",
                        )
                    )
            runner.assert_not_called()
            self.assertFalse((root / "runs").exists())

    def test_real_run_rejects_an_invalid_build_probe_before_runner_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reports = root / "reports"
            reports.mkdir(parents=True)
            spec_data = test_spec_data()
            spec_data["test_cases"] = [{"test_case_id": "case-a"}]
            spec = write_canonical_artifact(
                root,
                ArtifactKind.TEST_SPEC,
                subject(),
                spec_data,
            )
            set_review_record(
                root,
                artifact_kind=ArtifactKind.TEST_SPEC,
                artifact_sha256_value=artifact_sha256(spec),
                decision="approved",
                reviewer="reviewer@example.com",
                reviewed_at="2026-08-11T00:00:00Z",
                comment="ready",
            )
            (reports / "harness_skeleton_report.json").write_text("{}", encoding="utf-8")
            (reports / "build_workspace_report.json").write_text("{}", encoding="utf-8")
            (reports / "build_probe_report.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.1.0",
                        "artifact_kind": "build_probe_report",
                        "subject": subject(),
                        "data": {"status": "succeeded"},
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "unit_test_runner.execution.test_execution.run_test_executable_cases"
            ) as runner:
                with self.assertRaisesRegex(WorkspaceRegenerationRequired, "regenerate"):
                    execute_test_run(
                        TestRunRequest(
                            workspace=root,
                            executable=None,
                            timeout_seconds=60,
                            allow_placeholder_tests=False,
                            run_id="run-invalid-probe",
                            selector_kind="all",
                        )
                    )
            runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
