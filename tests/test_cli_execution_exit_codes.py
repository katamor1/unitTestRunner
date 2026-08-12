import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from unit_test_runner.cli import exit_codes
from unit_test_runner.cli.commands import handle_suite_run
from unit_test_runner.cli.errors import CLIError
from unit_test_runner.cli.outcomes import classify_suite_run, classify_test_run
from unit_test_runner.contracts import RunOutcome
from unit_test_runner.suite.models import SuiteRunEntryResult, SuiteRunPolicy, SuiteRunReport


def report(status: str, *, executed: bool, total: int = 0, passed: int = 0, failed: int = 0, inconclusive: int = 0, crashed: int = 0, not_run: int = 0):
    return SimpleNamespace(
        status=status,
        executed=executed,
        parsed_result=SimpleNamespace(
            total=total,
            passed=passed,
            failed=failed,
            inconclusive=inconclusive,
            crashed=crashed,
            not_run=not_run,
        ),
    )


class CliExecutionExitCodeTests(unittest.TestCase):
    def test_suite_run_constructs_only_the_current_policy_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            suite_path = Path(temp_dir) / "suite_manifest.json"
            suite_path.write_text("{}", encoding="utf-8")
            args = SimpleNamespace(
                suite=str(suite_path),
                run=True,
                timeout=5,
                entry_ids=None,
                tag=None,
                all=True,
                command="suite-run",
            )

            with patch(
                "unit_test_runner.cli.commands.run_suite",
                side_effect=ValueError("sentinel"),
            ) as run_suite_mock:
                with self.assertRaises(CLIError):
                    handle_suite_run(args)

            policy = run_suite_mock.call_args.kwargs["policy"]
            self.assertEqual(
                {"run_tests": True, "dry_run": False, "timeout_seconds": 5},
                policy.to_dict(),
            )

    def test_test_run_classification_uses_only_the_seven_public_outcomes(self):
        cases = [
            (report("passed", executed=True, total=2, passed=2), True, RunOutcome.PASSED, exit_codes.EXIT_OK),
            (report("passed", executed=False), True, RunOutcome.FAILED, exit_codes.EXIT_TESTS_FAILED),
            (report("failed", executed=True, total=1, failed=1), True, RunOutcome.FAILED, exit_codes.EXIT_TESTS_FAILED),
            (report("inconclusive", executed=True, total=1, inconclusive=1), True, RunOutcome.ERROR, exit_codes.EXIT_INTERNAL_ERROR),
            (report("timed_out", executed=True, total=1, not_run=1), True, RunOutcome.TIMED_OUT, exit_codes.EXIT_TESTS_TIMED_OUT),
            (report("blocked", executed=False), True, RunOutcome.BLOCKED, exit_codes.EXIT_TESTS_BLOCKED),
            (report("cancelled", executed=True), True, RunOutcome.CANCELLED, exit_codes.EXIT_TESTS_CANCELLED),
            (report("error", executed=False), True, RunOutcome.ERROR, exit_codes.EXIT_INTERNAL_ERROR),
            (report("error", executed=False), False, RunOutcome.PLANNED, exit_codes.EXIT_OK),
        ]

        for value, requested, expected, expected_exit in cases:
            with self.subTest(status=value.status, requested=requested):
                outcome, exit_code = classify_test_run(value, execution_requested=requested)
                self.assertIs(expected, outcome.state)
                self.assertEqual(expected_exit, exit_code)

    def test_suite_classification_never_promotes_a_non_green_pass(self):
        report_value = SimpleNamespace(
            status="passed",
            summary={"total": 2, "green": 1, "not_green": 1},
        )

        outcome, exit_code = classify_suite_run(report_value, execution_requested=True)

        self.assertIs(RunOutcome.FAILED, outcome.state)
        self.assertEqual(exit_codes.EXIT_TESTS_FAILED, exit_code)

    def test_suite_report_serializes_public_terminal_outcomes_and_test_run_path(self):
        entry = SuiteRunEntryResult(
            entry_id="entry-001",
            function_name="sample",
            workspace=Path("workspaces/sample"),
            execution_status=RunOutcome.PASSED.value,
            green_status="green",
            executed=True,
            total_tests=1,
            passed_tests=1,
            failed_tests=0,
            inconclusive_tests=0,
            unresolved_review_count=0,
            report_path=Path("workspaces/sample/runs/run-001/test_run_report.json"),
        )
        report_value = SuiteRunReport(
            suite_id="suite-001",
            status=RunOutcome.PASSED.value,
            selector={"kind": "all"},
            policy=SuiteRunPolicy(run_tests=True, dry_run=False),
            results=[entry],
            summary={"total": 1, "green": 1, "not_green": 0, "executed": 1, "failed": 0},
        )

        payload = report_value.to_dict()

        self.assertEqual("passed", payload["outcome"])
        self.assertEqual("passed", payload["results"][0]["outcome"])
        self.assertEqual("workspaces/sample/runs/run-001/test_run_report.json", payload["results"][0]["report_path"])


if __name__ == "__main__":
    unittest.main()
