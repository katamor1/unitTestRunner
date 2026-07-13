import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dossier import analyze_function_workflow
from unit_test_runner.execution.runner_output_parser import parse_runner_output
from unit_test_runner.execution.test_execution import prepare_test_execution_evidence
from unit_test_runner.contracts import ContractMode
from unit_test_runner.test_spec import (
    build_current_artifact_context,
    load_test_spec,
    save_test_spec,
)
from tests.spec_support import write_canonical_test_spec
from tests.windows_path_alias_support import (
    WINDOWS_8DOT3_PREFIX,
    require_windows_path_alias_pair,
)


def run_module(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class ExecutionEvidenceTests(unittest.TestCase):
    def prepare_workspace(self, temp_dir):
        out_dir = Path(temp_dir) / "Control_Update"
        analyze_function_workflow(
            VC6_FIXTURE_ROOT,
            VC6_FIXTURE_ROOT / "Product.dsw",
            "src/control.c",
            "Control_Update",
            "Win32 Debug",
            out_dir,
            "Control",
        )
        return out_dir

    def test_runner_output_parser_extracts_cases_assertions_and_summary(self):
        parsed = parse_runner_output(
            """
[ RUN      ] TC_Control_Update_001
[       OK ] TC_Control_Update_001
UTR RUN TC_Control_Update_002
UTR ASSERT EQ_INT: test_Control_Update.c:120 actual_return
[  FAILED  ] TC_Control_Update_002
[ SUMMARY  ] total=2 passed=1 failed=1 skipped=0
"""
        )
        payload = parsed.to_dict()

        self.assertEqual(2, payload["summary"]["total"])
        self.assertEqual(1, payload["summary"]["passed"])
        self.assertEqual(1, payload["summary"]["failed"])
        self.assertEqual(1, payload["summary"]["assertion_failures"])
        cases = {case["test_case_id"]: case for case in payload["case_results"]}
        self.assertEqual("passed", cases["TC_Control_Update_001"]["status"])
        self.assertEqual("failed", cases["TC_Control_Update_002"]["status"])

    def test_runner_output_parser_treats_bare_run_markers_as_inconclusive(self):
        parsed = parse_runner_output(
            """
UTR RUN TC_Control_Update_001
UTR RUN TC_Control_Update_002
"""
        )
        payload = parsed.to_dict()

        self.assertEqual(2, payload["summary"]["total"])
        self.assertEqual(0, payload["summary"]["passed"])
        self.assertEqual(2, payload["summary"]["inconclusive"])
        self.assertEqual("low", payload["summary"]["parser_confidence"])
        cases = {case["test_case_id"]: case for case in payload["case_results"]}
        self.assertEqual("inconclusive", cases["TC_Control_Update_001"]["status"])
        self.assertEqual("inconclusive", cases["TC_Control_Update_002"]["status"])

    def test_runner_output_parser_requires_ok_markers_for_passed_cases(self):
        parsed = parse_runner_output(
            """
UTR RUN TC_Control_Update_001
UTR OK TC_Control_Update_001
UTR RUN TC_Control_Update_002
UTR OK TC_Control_Update_002
"""
        )
        payload = parsed.to_dict()

        self.assertEqual(2, payload["summary"]["total"])
        self.assertEqual(2, payload["summary"]["passed"])
        self.assertEqual(0, payload["summary"]["inconclusive"])
        cases = {case["test_case_id"]: case for case in payload["case_results"]}
        self.assertEqual("passed", cases["TC_Control_Update_001"]["status"])
        self.assertEqual("passed", cases["TC_Control_Update_002"]["status"])

    def test_prepare_evidence_dry_run_generates_reports_manifest_and_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(temp_dir)
            report, manifest = prepare_test_execution_evidence(workspace, run_tests=False, dry_run=True)

            self.assertEqual("not_run", report.status)
            self.assertFalse(report.executed)
            self.assertTrue(report.unresolved_review_items)
            self.assertEqual("not_run", manifest.summary.test_execution_status)
            for filename in [
                "test_execution_report.json",
                "test_execution_report.md",
                "test_result.json",
                "test_result.csv",
                "evidence_manifest.json",
                "evidence_package.md",
                "unresolved_review_items.md",
            ]:
                self.assertTrue((workspace / "reports" / filename).exists(), filename)
            csv_text = (workspace / "reports" / "test_result.csv").read_text(encoding="utf-8")
            self.assertIn("test_case_id,status,review_required", csv_text)
            package = (workspace / "reports" / "evidence_package.md").read_text(encoding="utf-8")
            self.assertIn("# 関数単体テストエビデンスパッケージ", package)

    def test_candidate_only_spec_is_reported_but_never_spawned(self):
        from unit_test_runner.execution.execution_models import TestRunRequest
        from unit_test_runner.execution.test_execution import execute_test_run

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / "src" / "sample.c"
            source.parent.mkdir(parents=True)
            source.write_text("int sample(void) { return 0; }\n", encoding="utf-8")
            spec_path = write_canonical_test_spec(
                workspace,
                source_path="src/sample.c",
                function_name="sample",
                test_case_id="TC_sample_candidate",
            )
            spec = load_test_spec(spec_path, mode=ContractMode.STRICT)
            candidate = spec.test_cases.pop()
            candidate["expected_observations"][0]["expected_expression"] = "TBD-review"
            candidate["review_item_ids"] = ["review-candidate-001"]
            spec.additional_case_candidates = [candidate]
            spec.review_item_ids = ["review-candidate-001"]
            spec.unresolved_items = [
                {
                    "item_id": "review-candidate-001",
                    "item_kind": "expected_result_unknown",
                    "related_test_case_ids": ["TC_sample_candidate"],
                    "description": "Candidate oracle requires review.",
                    "suggested_action": "Resolve the oracle before execution.",
                }
            ]
            save_test_spec(
                spec_path,
                spec,
                expected_revision=1,
                current_context=build_current_artifact_context(workspace, spec),
            )
            reports = workspace / "reports"
            (reports / "harness_skeleton_report.json").write_text(
                json.dumps({"unresolved_placeholders": [], "generated_files": []}),
                encoding="utf-8",
            )
            (reports / "build_probe_report.json").write_text(
                json.dumps({"function": {"name": "sample", "status": "succeeded"}}),
                encoding="utf-8",
            )
            (reports / "build_workspace_report.json").write_text(
                json.dumps({"function": {"name": "sample"}, "source": {"path": "src/sample.c"}}),
                encoding="utf-8",
            )
            runner = workspace / "runner.exe"
            runner.write_bytes(b"fixture")

            with mock.patch(
                "unit_test_runner.execution.test_execution.run_test_executable_cases",
                side_effect=AssertionError("candidate must not be passed to the runner"),
            ):
                report = execute_test_run(
                    TestRunRequest(workspace, runner, 5, True)
                )

            self.assertFalse(report.executed)
            self.assertIn(report.status, {"blocked", "inconclusive"})
            self.assertEqual([], report.case_results)
            self.assertTrue(report.unresolved_review_items)
            self.assertIn(
                "TC_sample_candidate",
                {item.related_test_case_id for item in report.unresolved_review_items},
            )

    def test_cli_run_tests_prepare_evidence_and_analyze_function_connect_execution_evidence(self):
        with tempfile.TemporaryDirectory(prefix=WINDOWS_8DOT3_PREFIX) as temp_dir:
            root = Path(temp_dir)
            if os.name == "nt":
                root = require_windows_path_alias_pair(self, root).short
            workspace = self.prepare_workspace(root)

            run_tests = run_module(
                "--json",
                "run-tests",
                "--workspace",
                str(workspace),
                "--run",
                "--allow-placeholder-tests",
            )
            run_payload = json.loads(run_tests.stdout)
            self.assertEqual(run_tests.returncode, run_payload["data"]["exit_code"])
            self.assertEqual("blocked", run_payload["data"]["outcome"])
            run_report_path = Path(run_payload["data"]["details"]["test_execution"]["json"])
            self.assertTrue(run_report_path.exists())
            self.assertEqual(
                "runs",
                run_report_path.resolve().relative_to(workspace.resolve()).parts[0],
            )
            run_report = json.loads(run_report_path.read_text(encoding="utf-8"))
            self.assertTrue(run_report["data"]["policy"]["allow_placeholder_tests"])

            first_evidence_pointer = json.loads(
                (workspace / "reports" / "latest_evidence.json").read_text(encoding="utf-8")
            )

            prepare = run_module("--json", "prepare-evidence", "--workspace", str(workspace))
            self.assertEqual(35, prepare.returncode, prepare.stderr)
            prepare_payload = json.loads(prepare.stdout)
            self.assertEqual("blocked", prepare_payload["data"]["outcome"])
            self.assertFalse(prepare_payload["data"]["green"])
            self.assertTrue(Path(prepare_payload["data"]["details"]["evidence"]["manifest_json"]).exists())
            self.assertTrue(prepare_payload["data"]["artifacts"])
            second_evidence_pointer = json.loads(
                (workspace / "reports" / "latest_evidence.json").read_text(encoding="utf-8")
            )
            self.assertNotEqual(
                first_evidence_pointer["data"]["evidence_id"],
                second_evidence_pointer["data"]["evidence_id"],
            )

            out_dir = Path(temp_dir) / "AnalyzeFunctionExecutionEvidence"
            full = run_module(
                "--json",
                "analyze-function",
                "--workspace",
                str(VC6_FIXTURE_ROOT),
                "--dsw",
                str(VC6_FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--phase",
                "execution",
                "--out",
                str(out_dir),
            )
            self.assertEqual(0, full.returncode, full.stderr)
            full_payload = json.loads(full.stdout)
            self.assertEqual("passed", full_payload["data"]["outcome"])
            self.assertIn("dossier review", full_payload["data"]["message"])
            self.assertIn("test_execution", full_payload["data"]["details"])
            self.assertIn("evidence", full_payload["data"]["details"])
            self.assertTrue((out_dir / "reports" / "evidence_manifest.json").exists())

            run_out_dir = Path(temp_dir) / "AnalyzeFunctionRunTests"
            run_full = run_module(
                "--json",
                "analyze-function",
                "--workspace",
                str(VC6_FIXTURE_ROOT),
                "--dsw",
                str(VC6_FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--phase",
                "execution",
                "--out",
                str(run_out_dir),
                "--run-tests",
            )
            self.assertEqual(35, run_full.returncode, run_full.stderr)
            run_payload = json.loads(run_full.stdout)
            self.assertEqual("blocked", run_payload["data"]["outcome"])
            self.assertEqual("blocked", run_payload["data"]["details"]["test_execution"]["status"])
            latest_run = json.loads(
                (run_out_dir / "reports" / "latest_run.json").read_text(encoding="utf-8")
            )
            execution_report = json.loads(
                (run_out_dir / latest_run["data"]["execution_report"]["path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(execution_report["data"]["policy"]["run_tests"])
            self.assertFalse(execution_report["data"]["policy"]["dry_run"])


if __name__ == "__main__":
    unittest.main()
