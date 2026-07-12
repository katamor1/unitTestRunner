import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dossier import analyze_function_workflow
from unit_test_runner.execution.runner_output_parser import parse_runner_output
from unit_test_runner.execution.test_execution import prepare_test_execution_evidence


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

    def test_cli_run_tests_prepare_evidence_and_analyze_function_connect_execution_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(temp_dir)

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
            self.assertEqual("runs", run_report_path.relative_to(workspace).parts[0])
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
