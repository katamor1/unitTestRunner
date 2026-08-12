import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from unit_test_runner.suite import (
    SuiteRunPolicy,
    default_suite_manifest_path,
    load_suite_manifest,
    register_workspace,
    remove_entry,
    run_suite,
)
from unit_test_runner.suite.manager import _manifest_write_lock, save_suite_manifest
from unit_test_runner.cli.outcomes import classify_suite_run
from unit_test_runner.contracts import RunOutcome


class SuiteManagerTests(unittest.TestCase):
    def test_default_manifest_path_stays_under_output_root(self):
        output_root = Path("D:/unit-test-output")

        manifest_path = default_suite_manifest_path(output_root)

        self.assertEqual(Path("D:/unit-test-output/suites/default/suite_manifest.json"), manifest_path)

    def test_register_workspace_creates_manifest_and_updates_same_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            workspace = self._write_function_workspace(root / "Control_Update", function_name="Control_Update")

            first = register_workspace(suite_path, workspace, tags=["regression", "selected"], expected_revision=0)
            stale = load_suite_manifest(suite_path)
            second = register_workspace(suite_path, workspace, expected_revision=1)

            self.assertEqual(1, len(first.entries))
            self.assertEqual(1, len(second.entries))
            entry = second.entries[0]
            self.assertTrue(entry.entry_id.startswith("Control_Update-"))
            self.assertEqual(["regression", "selected"], entry.tags)
            self.assertEqual("Control_Update", entry.function["name"])
            self.assertEqual("src/control.c", entry.function["source"])
            self.assertEqual("Control", entry.function["project"])
            self.assertEqual("Win32 Debug", entry.function["configuration"])
            self.assertEqual(workspace.resolve(), entry.workspace)
            loaded = load_suite_manifest(suite_path)
            self.assertEqual(entry.entry_id, loaded.entries[0].entry_id)
            self.assertEqual(2, loaded.revision)
            persisted = json.loads(suite_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {"schema_version", "artifact_kind", "subject", "data"},
                set(persisted),
            )
            self.assertEqual("1.0.0", persisted["schema_version"])
            self.assertEqual("suite_manifest", persisted["artifact_kind"])
            self.assertEqual(entry.subject, persisted["subject"])
            persisted_entry = persisted["data"]["entries"][0]
            self.assertEqual("Control_Update", persisted_entry["workspace"])
            self.assertNotIn("\\", persisted_entry["workspace"])
            self.assertEqual(
                hashlib.sha256((workspace / "reports" / "test_spec.json").read_bytes()).hexdigest(),
                persisted_entry["test_spec_sha256"],
            )
            self.assertEqual(
                hashlib.sha256((workspace / "reports" / "harness_skeleton_report.json").read_bytes()).hexdigest(),
                persisted_entry["harness_sha256"],
            )
            before = suite_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "revision"):
                save_suite_manifest(suite_path, stale, expected_revision=stale.revision)
            self.assertEqual(before, suite_path.read_bytes())

            changed_anchor = load_suite_manifest(suite_path)
            changed_anchor.subject = {
                **changed_anchor.subject,
                "function": "DifferentAnchor",
            }
            with self.assertRaisesRegex(ValueError, "anchor subject"):
                save_suite_manifest(
                    suite_path,
                    changed_anchor,
                    expected_revision=changed_anchor.revision,
                )
            self.assertEqual(before, suite_path.read_bytes())

            with _manifest_write_lock(suite_path):
                with self.assertRaisesRegex(ValueError, "being updated"):
                    save_suite_manifest(
                        suite_path,
                        load_suite_manifest(suite_path),
                        expected_revision=2,
                    )
            self.assertEqual(before, suite_path.read_bytes())

            lock_path = suite_path.with_name(f".{suite_path.name}.lock")
            lock_path.write_text("stale process marker", encoding="utf-8")
            try:
                recovered = load_suite_manifest(suite_path)
                save_suite_manifest(
                    suite_path,
                    recovered,
                    expected_revision=recovered.revision,
                )
                self.assertEqual(3, recovered.revision)
            finally:
                lock_path.unlink(missing_ok=True)

    def test_register_workspace_rejects_an_invalid_public_dossier(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            workspace = self._write_function_workspace(
                root / "Control_Update",
                function_name="Control_Update",
            )
            dossier_path = workspace / "reports" / "function_dossier.json"
            dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
            dossier["unexpected"] = True
            dossier_path.write_text(json.dumps(dossier), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Invalid function_dossier"):
                register_workspace(
                    suite_path,
                    workspace,
                    expected_revision=0,
                )

    def test_remove_entry_persists_manifest_without_target_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            workspace = self._write_function_workspace(root / "Control_Update", function_name="Control_Update")
            manifest = register_workspace(suite_path, workspace, tags=["selected"], expected_revision=0)
            entry_id = manifest.entries[0].entry_id

            updated = remove_entry(suite_path, entry_id, expected_revision=1)

            self.assertEqual([], updated.entries)
            self.assertEqual([], load_suite_manifest(suite_path).entries)

    def test_run_suite_dry_run_selected_entries_writes_summary_reports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            selected = self._write_function_workspace(root / "Control_Update", function_name="Control_Update")
            skipped = self._write_function_workspace(root / "Control_Stop", function_name="Control_Stop")
            register_workspace(suite_path, selected, tags=["selected"], expected_revision=0)
            register_workspace(suite_path, skipped, tags=["other"], expected_revision=1)

            with mock.patch(
                "unit_test_runner.suite.manager.validate_test_run_preflight",
                return_value=([], []),
            ):
                report, paths = run_suite(
                    suite_path,
                    tag="selected",
                    policy=SuiteRunPolicy(run_tests=False, dry_run=True, timeout_seconds=5),
                )

            self.assertEqual("planned", report.status)
            self.assertEqual(1, report.summary["total"])
            self.assertEqual(0, report.summary["green"])
            self.assertEqual(1, report.summary["not_green"])
            self.assertEqual("not_green", report.results[0].green_status)
            self.assertEqual("planned", report.results[0].execution_status)
            for key in ("json", "markdown", "csv"):
                self.assertTrue(paths[key].exists(), key)
            report_payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(
                {"schema_version", "artifact_kind", "subject", "data"},
                set(report_payload),
            )
            self.assertEqual("suite_run_report", report_payload["artifact_kind"])
            self.assertEqual("planned", report_payload["data"]["outcome"])
            self.assertEqual("planned", report_payload["data"]["results"][0]["outcome"])
            self.assertNotIn("suite_run_completed", json.dumps(report_payload))
            self.assertIn("Control_Update", paths["markdown"].read_text(encoding="utf-8"))
            self.assertIn("entry_id,function,status,green_status", paths["csv"].read_text(encoding="utf-8"))

    def test_run_suite_plan_remains_non_green_until_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            workspace = self._write_function_workspace(root / "Control_Update", function_name="Control_Update")
            register_workspace(suite_path, workspace, tags=["selected"], expected_revision=0)

            report, _ = run_suite(
                suite_path,
                tag="selected",
                policy=SuiteRunPolicy(run_tests=False, dry_run=True),
            )

            self.assertEqual("planned", report.status)
            self.assertEqual(1, report.summary["not_green"])

    def test_actual_suite_persists_non_green_outcome_and_exact_originating_run_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            workspace = self._write_function_workspace(root / "Control_Update", function_name="Control_Update")
            second_workspace = self._write_function_workspace(root / "Control_Stop", function_name="Control_Stop")
            register_workspace(suite_path, workspace, tags=["selected"], expected_revision=0)
            register_workspace(suite_path, second_workspace, tags=["selected"], expected_revision=1)
            exact_report = workspace / "runs" / "run-exact" / "test_run_report.json"
            passed_execution = SimpleNamespace(
                status="passed",
                executed=True,
                parsed_result=SimpleNamespace(total=1, passed=1, failed=0, inconclusive=0),
                case_results=[],
                unresolved_review_items=[],
                run_paths=SimpleNamespace(public_report=exact_report),
            )
            failed_execution = SimpleNamespace(
                status="failed",
                executed=True,
                parsed_result=SimpleNamespace(total=1, passed=0, failed=1, inconclusive=0),
                case_results=[],
                unresolved_review_items=[],
                run_paths=SimpleNamespace(
                    public_report=second_workspace / "runs" / "run-failed" / "test_run_report.json"
                ),
            )

            with mock.patch(
                "unit_test_runner.suite.manager.execute_test_run",
                side_effect=[passed_execution, failed_execution],
            ) as execute:
                report, paths = run_suite(
                    suite_path,
                    tag="selected",
                    policy=SuiteRunPolicy(run_tests=True, dry_run=False),
                )

            outcome, exit_code = classify_suite_run(report, execution_requested=True)
            persisted = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertIs(RunOutcome.FAILED, outcome.state)
            self.assertEqual(32, exit_code)
            self.assertEqual("failed", report.status)
            self.assertEqual(2, execute.call_count)
            self.assertEqual(2, len(report.results))
            self.assertEqual(1, report.summary["passed"])
            self.assertEqual(1, report.summary["failed"])
            self.assertEqual("failed", persisted["data"]["outcome"])
            self.assertEqual(
                Path("Control_Update/runs/run-exact/test_run_report.json"),
                report.results[0].report_path,
            )
            self.assertEqual(
                "Control_Update/runs/run-exact/test_run_report.json",
                persisted["data"]["results"][0]["report_path"],
            )

            def flaky_fingerprint(path: Path) -> str:
                if path == workspace / "src" / "control.c":
                    raise OSError("source changed during fingerprint read")
                return hashlib.sha256(path.read_bytes()).hexdigest()

            with mock.patch(
                "unit_test_runner.suite.manager._sha256_file",
                side_effect=flaky_fingerprint,
            ), mock.patch(
                "unit_test_runner.suite.manager.execute_test_run",
                return_value=failed_execution,
            ) as execute_after_read_error:
                read_error_report, _ = run_suite(
                    suite_path,
                    tag="selected",
                    policy=SuiteRunPolicy(run_tests=True, dry_run=False),
                )

            self.assertEqual(2, len(read_error_report.results))
            self.assertEqual("blocked", read_error_report.results[0].execution_status)
            self.assertEqual(
                ["source_sha256"],
                read_error_report.results[0].changed_fields,
            )
            self.assertEqual(1, execute_after_read_error.call_count)

    def test_suite_rejects_report_outside_workspace_without_absolute_leakage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            workspace = self._write_function_workspace(
                root / "Control_Update",
                function_name="Control_Update",
            )
            register_workspace(
                suite_path,
                workspace,
                tags=["selected"],
                expected_revision=0,
            )
            outside_report = (
                root
                / "outside"
                / "runs"
                / "run-external"
                / "test_run_report.json"
            )
            execution = SimpleNamespace(
                status="passed",
                executed=True,
                parsed_result=SimpleNamespace(
                    total=1,
                    passed=1,
                    failed=0,
                    inconclusive=0,
                ),
                case_results=[],
                unresolved_review_items=[],
                run_paths=SimpleNamespace(public_report=outside_report),
            )

            with mock.patch(
                "unit_test_runner.suite.manager.execute_test_run",
                return_value=execution,
            ):
                report, paths = run_suite(
                    suite_path,
                    tag="selected",
                    policy=SuiteRunPolicy(run_tests=True, dry_run=False),
                )

            result = report.results[0]
            persisted = json.loads(paths["json"].read_text(encoding="utf-8"))
            persisted_text = json.dumps(persisted)
            self.assertEqual("error", report.status)
            self.assertEqual("error", result.execution_status)
            self.assertIsNone(result.report_path)
            self.assertNotIn("report_path", result.to_dict())
            self.assertNotIn("report_path", persisted["data"]["results"][0])
            self.assertNotIn(outside_report.as_posix(), persisted_text)
            self.assertNotIn(root.as_posix(), persisted_text)

    def test_suite_never_falls_back_to_registered_or_flat_report_paths(self):
        for case, relative in (
            ("source_sha256", Path("src/control.c")),
            ("test_spec_sha256", Path("reports/test_spec.json")),
            ("harness_sha256", Path("reports/harness_skeleton_report.json")),
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                suite_path = root / "suites" / "default" / "suite_manifest.json"
                workspace = self._write_function_workspace(
                    root / "Control_Update",
                    function_name="Control_Update",
                )
                register_workspace(suite_path, workspace, tags=["selected"], expected_revision=0)
                target = workspace / relative
                target.write_bytes(target.read_bytes() + b"stale")

                with mock.patch(
                    "unit_test_runner.suite.manager.execute_test_run",
                ) as execute:
                    report, paths = run_suite(
                        suite_path,
                        tag="selected",
                        policy=SuiteRunPolicy(run_tests=True, dry_run=False),
                    )

                result = report.results[0]
                persisted = json.loads(paths["json"].read_text(encoding="utf-8"))
                execute.assert_not_called()
                self.assertEqual("blocked", result.execution_status)
                self.assertEqual([case], result.changed_fields)
                self.assertIsNone(result.report_path)
                self.assertNotIn("report_path", result.to_dict())
                self.assertNotIn("report_path", persisted["data"]["results"][0])
                self.assertEqual([case], persisted["data"]["results"][0]["changed_fields"])

    def _write_function_workspace(self, workspace: Path, function_name: str) -> Path:
        reports = workspace / "reports"
        reports.mkdir(parents=True)
        source = workspace / "src" / "control.c"
        source.parent.mkdir(parents=True)
        source.write_text(
            f"int {function_name}(void) {{ return 0; }}\n",
            encoding="utf-8",
        )
        target = {
            "source": "src/control.c",
            "function": function_name,
            "configuration": "Win32 Debug",
            "project": "Control",
        }
        source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        subject = {
            "source_path": "src/control.c",
            "source_sha256": source_sha256,
            "function": function_name,
            "project": "Control",
            "configuration": "Win32 Debug",
        }
        (reports / "function_dossier.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "artifact_kind": "function_dossier",
                    "subject": subject,
                    "data": {
                        "target": target,
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
        (reports / "test_spec.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "artifact_kind": "test_spec",
                    "subject": subject,
                    "data": {
                        "spec_id": f"spec-{function_name}",
                        "revision": 1,
                        "source": {"path": "src/control.c", "sha256": source_sha256},
                        "function": {
                            "function_id": f"fn-{function_name}",
                            "name": function_name,
                            "signature_sha256": "c" * 64,
                        },
                        "generated_from": [],
                        "generation_policy": {"dependency_ids": []},
                        "test_cases": [],
                        "additional_case_candidates": [],
                        "coverage_summary": {
                            "total_coverage_items": 0,
                            "covered_by_design_count": 0,
                            "uncovered_coverage_ids": [],
                            "coverage_to_test_cases": {},
                        },
                        "unresolved_items": [],
                        "warnings": [],
                        "review_item_ids": [],
                    },
                }
            ),
            encoding="utf-8",
        )
        (reports / "harness_skeleton_report.json").write_text(
            json.dumps({"schema_version": "0.1", "function": {"name": function_name}, "unresolved_placeholders": []}),
            encoding="utf-8",
        )
        (reports / "build_probe_report.json").write_text(
            json.dumps({"schema_version": "0.1", "function": {"name": function_name, "status": "succeeded"}}),
            encoding="utf-8",
        )
        (reports / "build_workspace_report.json").write_text(
            json.dumps({"schema_version": "0.1", "function": {"name": function_name}, "source": {"path": "src/control.c"}}),
            encoding="utf-8",
        )
        return workspace


if __name__ == "__main__":
    unittest.main()
