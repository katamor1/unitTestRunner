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

    def test_runner_output_parser_treats_generated_clean_cases_as_passed(self):
        parsed = parse_runner_output(
            """
UTR RUN TC_Control_Update_001
UTR RUN TC_Control_Update_002
"""
        )
        payload = parsed.to_dict()

        self.assertEqual(2, payload["summary"]["total"])
        self.assertEqual(2, payload["summary"]["passed"])
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
            self.assertIn("# Function Unit Test Evidence Package", package)

    def test_cli_run_tests_prepare_evidence_and_analyze_function_connect_execution_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(temp_dir)

            run_tests = run_module("--json", "run-tests", "--workspace", str(workspace), "--dry-run")
            self.assertEqual(0, run_tests.returncode, run_tests.stderr)
            run_payload = json.loads(run_tests.stdout)
            self.assertEqual("evidence_prepared", run_payload["status"])
            self.assertTrue(Path(run_payload["data"]["test_execution"]["json"]).exists())
            run_report = json.loads((workspace / "reports" / "test_execution_report.json").read_text(encoding="utf-8"))
            self.assertFalse(run_report["policy"]["allow_placeholder_tests"])

            prepare = run_module("--json", "prepare-evidence", "--workspace", str(workspace))
            self.assertEqual(0, prepare.returncode, prepare.stderr)
            prepare_payload = json.loads(prepare.stdout)
            self.assertEqual("evidence_prepared", prepare_payload["status"])

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
            self.assertEqual("evidence_prepared", full_payload["status"])
            self.assertIn("dossier review", full_payload["message"])
            self.assertIn("test_execution", full_payload["data"])
            self.assertIn("evidence", full_payload["data"])
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
            self.assertEqual(0, run_full.returncode, run_full.stderr)
            run_payload = json.loads(run_full.stdout)
            self.assertEqual("blocked", run_payload["data"]["test_execution"]["status"])
            execution_report = json.loads((run_out_dir / "reports" / "test_execution_report.json").read_text(encoding="utf-8"))
            self.assertTrue(execution_report["policy"]["run_tests"])
            self.assertFalse(execution_report["policy"]["dry_run"])


if __name__ == "__main__":
    unittest.main()
