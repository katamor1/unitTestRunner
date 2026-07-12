import json
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

            first = register_workspace(suite_path, workspace, tags=["regression", "selected"])
            second = register_workspace(suite_path, workspace, tags=["selected", "smoke"])

            self.assertEqual(1, len(first.entries))
            self.assertEqual(1, len(second.entries))
            entry = second.entries[0]
            self.assertTrue(entry.entry_id.startswith("Control_Update-"))
            self.assertEqual(["selected", "smoke"], entry.tags)
            self.assertEqual("Control_Update", entry.function["name"])
            self.assertEqual("src/control.c", entry.function["source"])
            self.assertEqual("Control", entry.function["project"])
            self.assertEqual("Win32 Debug", entry.function["configuration"])
            self.assertEqual(workspace.resolve(), entry.workspace)
            loaded = load_suite_manifest(suite_path)
            self.assertEqual(entry.entry_id, loaded.entries[0].entry_id)

    def test_remove_entry_persists_manifest_without_target_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            workspace = self._write_function_workspace(root / "Control_Update", function_name="Control_Update")
            manifest = register_workspace(suite_path, workspace, tags=["selected"])
            entry_id = manifest.entries[0].entry_id

            updated = remove_entry(suite_path, entry_id)

            self.assertEqual([], updated.entries)
            self.assertEqual([], load_suite_manifest(suite_path).entries)

    def test_run_suite_dry_run_selected_entries_writes_summary_reports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            selected = self._write_function_workspace(root / "Control_Update", function_name="Control_Update")
            skipped = self._write_function_workspace(root / "Control_Stop", function_name="Control_Stop")
            register_workspace(suite_path, selected, tags=["selected"])
            register_workspace(suite_path, skipped, tags=["other"])

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
            self.assertEqual("planned", report_payload["outcome"])
            self.assertEqual("planned", report_payload["results"][0]["outcome"])
            self.assertNotIn("suite_run_completed", json.dumps(report_payload))
            self.assertIn("Control_Update", paths["markdown"].read_text(encoding="utf-8"))
            self.assertIn("entry_id,function,status,green_status", paths["csv"].read_text(encoding="utf-8"))

    def test_run_suite_require_green_marks_non_green_report_failed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            workspace = self._write_function_workspace(root / "Control_Update", function_name="Control_Update")
            register_workspace(suite_path, workspace, tags=["selected"])

            report, _ = run_suite(
                suite_path,
                tag="selected",
                policy=SuiteRunPolicy(run_tests=False, dry_run=True, require_green=True),
            )

            self.assertEqual("planned", report.status)
            self.assertEqual(1, report.summary["not_green"])

    def test_actual_suite_persists_non_green_outcome_and_exact_originating_run_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "suites" / "default" / "suite_manifest.json"
            workspace = self._write_function_workspace(root / "Control_Update", function_name="Control_Update")
            register_workspace(suite_path, workspace, tags=["selected"])
            exact_report = workspace / "runs" / "run-exact" / "test_execution_report.json"
            execution = SimpleNamespace(
                status="passed",
                executed=True,
                parsed_result=SimpleNamespace(total=1, passed=1, failed=0, inconclusive=0),
                case_results=[],
                unresolved_review_items=[{"code": "review_required"}],
                run_paths=SimpleNamespace(execution_report=exact_report),
            )

            with mock.patch(
                "unit_test_runner.suite.manager.prepare_test_execution_evidence",
                return_value=(execution, SimpleNamespace()),
            ):
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
            self.assertEqual("failed", persisted["outcome"])
            self.assertEqual(exact_report, report.results[0].report_path)
            self.assertEqual(exact_report.as_posix(), persisted["results"][0]["report_path"])

    def _write_function_workspace(self, workspace: Path, function_name: str) -> Path:
        reports = workspace / "reports"
        reports.mkdir(parents=True)
        target = {
            "source": "src/control.c",
            "function": function_name,
            "configuration": "Win32 Debug",
            "project": "Control",
        }
        (reports / "function_dossier.json").write_text(
            json.dumps({"schema_version": "0.1", "target": target, "function": {"name": function_name}}),
            encoding="utf-8",
        )
        (reports / "test_case_design.json").write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "function": {"name": function_name},
                    "test_cases": [
                        {
                            "test_case_id": f"TC_{function_name}_001",
                            "review_status": "ready",
                            "coverage_links": [{"coverage_id": "BR_001"}],
                            "expected_observations": [{"expected_expression": "0"}],
                        }
                    ],
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
