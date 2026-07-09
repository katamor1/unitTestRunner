import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.execution.execution_models import TestCaseExecutionResult
from unit_test_runner.execution.test_execution import _merge_runner_case_results_with_design, _summary_from_case_results
from unit_test_runner.execution.execution_runner import run_test_executable_cases


class ExecutionCrashReconciliationTests(unittest.TestCase):
    def test_design_cases_missing_from_runner_output_are_not_run_after_crash(self):
        design_cases = [
            TestCaseExecutionResult(f"TC_Shared3_{index:03d}", None, "not_found_in_output", False)
            for index in range(1, 5)
        ]
        runner_cases = [
            TestCaseExecutionResult(
                "TC_Shared3_001",
                None,
                "crashed",
                True,
                evidence="UTR RUN 後に OK/FAILED/SKIPPED/SUMMARY が出る前にプロセスが終了しました。exit_code=3221225477。",
            )
        ]

        merged = _merge_runner_case_results_with_design(design_cases, runner_cases, "failed")
        summary = _summary_from_case_results(merged)
        statuses = {case.test_case_id: case.status for case in merged}

        self.assertEqual("crashed", statuses["TC_Shared3_001"])
        self.assertEqual("not_run", statuses["TC_Shared3_002"])
        self.assertEqual("not_run", statuses["TC_Shared3_003"])
        self.assertEqual("not_run", statuses["TC_Shared3_004"])
        self.assertEqual(4, summary.total)
        self.assertEqual(1, summary.started)
        self.assertEqual(0, summary.completed)
        self.assertEqual(1, summary.crashed)
        self.assertEqual(3, summary.not_run)
        self.assertEqual(0, summary.passed)

    def test_case_isolated_execution_continues_after_one_case_crashes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "logs").mkdir()
            script = workspace / "fake_runner.py"
            script.write_text(
                textwrap.dedent(
                    """
                    import sys
                    case = sys.argv[2]
                    print(f"UTR RUN {case}")
                    if case == "TC_001":
                        sys.exit(3)
                    print(f"UTR OK {case}")
                    print("UTR SUMMARY total=1 passed=1 failed=0 skipped=0 inconclusive=0")
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            if os.name != "nt":
                script.chmod(0o755)
            executable = [sys.executable, str(script)]
            # run_test_executable_cases expects one executable path, so wrap the Python script in a tiny shell/batch-like shim.
            shim = workspace / ("fake_runner.cmd" if os.name == "nt" else "fake_runner.sh")
            if os.name == "nt":
                shim.write_text(f'@echo off\n"{sys.executable}" "{script}" %*\n', encoding="utf-8")
            else:
                shim.write_text(f'#!/bin/sh\n"{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
                shim.chmod(0o755)

            result, summary, case_results, status = run_test_executable_cases(workspace, shim, ["TC_001", "TC_002"], 10)
            statuses = {case.test_case_id: case.status for case in case_results}

            self.assertEqual("failed", status)
            self.assertEqual(3, result.exit_code)
            self.assertEqual("crashed", statuses["TC_001"])
            self.assertEqual("passed", statuses["TC_002"])
            self.assertEqual(2, summary.started)
            self.assertEqual(1, summary.completed)
            self.assertEqual(1, summary.crashed)
            self.assertEqual(1, summary.passed)


if __name__ == "__main__":
    unittest.main()
