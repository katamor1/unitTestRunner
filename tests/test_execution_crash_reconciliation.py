import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.execution.execution_models import TestCaseExecutionResult
from unit_test_runner.execution.test_execution import _merge_runner_case_results_with_design, _summary_from_case_results


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


if __name__ == "__main__":
    unittest.main()
