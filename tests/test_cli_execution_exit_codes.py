import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.cli import exit_codes
from unit_test_runner.cli.commands import handle_run_tests, handle_suite_run
from unit_test_runner.cli.outcomes import classify_test_run
from unit_test_runner.contracts import RunOutcome
from unit_test_runner.suite.models import (
    SuiteRunEntryResult,
    SuiteRunPolicy,
    SuiteRunReport,
)


def report(
    status: str,
    *,
    executed: bool,
    total: int = 0,
    passed: int = 0,
    failed: int = 0,
    inconclusive: int = 0,
    crashed: int = 0,
    not_run: int = 0,
):
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
    def test_classify_test_run_maps_every_canonical_outcome_to_one_exit_code(self):
        cases = [
            (
                "all passed",
                report("passed", executed=True, total=2, passed=2),
                True,
                RunOutcome.PASSED,
                True,
                exit_codes.EXIT_OK,
            ),
            (
                "claimed pass without executed green evidence",
                report("passed", executed=False),
                True,
                RunOutcome.INCONCLUSIVE,
                False,
                exit_codes.EXIT_TESTS_INCONCLUSIVE,
            ),
            (
                "assertion failure",
                report("failed", executed=True, total=1, failed=1),
                True,
                RunOutcome.FAILED,
                False,
                exit_codes.EXIT_TESTS_FAILED,
            ),
            (
                "runner crash",
                report("failed", executed=True, total=1, crashed=1),
                True,
                RunOutcome.FAILED,
                False,
                exit_codes.EXIT_TESTS_FAILED,
            ),
            (
                "unreached case",
                report("inconclusive", executed=True, total=2, passed=1, not_run=1),
                True,
                RunOutcome.INCONCLUSIVE,
                False,
                exit_codes.EXIT_TESTS_INCONCLUSIVE,
            ),
            (
                "timeout",
                report("timed_out", executed=True, total=1, not_run=1),
                True,
                RunOutcome.TIMED_OUT,
                False,
                exit_codes.EXIT_TESTS_TIMED_OUT,
            ),
            (
                "precondition blocked",
                report("blocked", executed=False),
                True,
                RunOutcome.BLOCKED,
                False,
                exit_codes.EXIT_TESTS_BLOCKED,
            ),
            (
                "cancelled",
                report("cancelled", executed=True),
                True,
                RunOutcome.CANCELLED,
                False,
                exit_codes.EXIT_TESTS_CANCELLED,
            ),
            (
                "internal error",
                report("error", executed=False),
                True,
                RunOutcome.ERROR,
                False,
                exit_codes.EXIT_INTERNAL_ERROR,
            ),
            (
                "explicit plan",
                report("error", executed=False),
                False,
                RunOutcome.PLANNED,
                None,
                exit_codes.EXIT_OK,
            ),
        ]

        for label, value, requested, expected_state, expected_green, expected_exit in cases:
            with self.subTest(label=label):
                outcome, exit_code = classify_test_run(
                    value,
                    execution_requested=requested,
                )

                self.assertEqual("test_run", outcome.kind)
                self.assertIs(expected_state, outcome.state)
                self.assertIs(expected_green, outcome.green)
                self.assertEqual(expected_exit, exit_code)

    def test_run_tests_handler_keeps_report_envelope_and_evidence_outcomes_equal(self):
        cases = [
            ("passed", True, 1, 1, 0, 0, RunOutcome.PASSED, exit_codes.EXIT_OK),
            ("failed", True, 1, 0, 1, 0, RunOutcome.FAILED, exit_codes.EXIT_TESTS_FAILED),
            ("inconclusive", True, 1, 0, 0, 1, RunOutcome.INCONCLUSIVE, exit_codes.EXIT_TESTS_INCONCLUSIVE),
            ("timed_out", True, 1, 0, 0, 0, RunOutcome.TIMED_OUT, exit_codes.EXIT_TESTS_TIMED_OUT),
            ("blocked", False, 0, 0, 0, 0, RunOutcome.BLOCKED, exit_codes.EXIT_TESTS_BLOCKED),
            ("cancelled", True, 0, 0, 0, 0, RunOutcome.CANCELLED, exit_codes.EXIT_TESTS_CANCELLED),
            ("error", False, 0, 0, 0, 0, RunOutcome.ERROR, exit_codes.EXIT_INTERNAL_ERROR),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            args = Namespace(
                command="run-tests",
                workspace=temp_dir,
                executable=None,
                run=True,
                plan=False,
                dry_run=False,
                timeout=60,
                run_id=None,
                allow_placeholder_tests=True,
                treat_placeholder_as_inconclusive=True,
            )
            for status, executed, total, passed, failed, inconclusive, expected, expected_exit in cases:
                value = report(
                    status,
                    executed=executed,
                    total=total,
                    passed=passed,
                    failed=failed,
                    inconclusive=inconclusive,
                )
                value.run_paths = None
                manifest = SimpleNamespace(
                    summary=SimpleNamespace(test_execution_status=status),
                    evidence_paths=None,
                )
                with self.subTest(status=status), mock.patch(
                    "unit_test_runner.cli.commands.prepare_test_execution_evidence",
                    return_value=(value, manifest),
                ):
                    result = handle_run_tests(args)
                    envelope = result.to_dict()

                self.assertIs(expected, result.outcome.state)
                self.assertEqual(expected_exit, result.exit_code)
                self.assertEqual(expected.value, envelope["data"]["outcome"])
                self.assertEqual(expected_exit, envelope["data"]["exit_code"])
                self.assertEqual(
                    expected.value,
                    envelope["data"]["details"]["test_execution"]["status"],
                )
                self.assertEqual(
                    expected.value,
                    envelope["data"]["details"]["evidence"]["status"],
                )

    def test_suite_handler_keeps_fixture_envelope_and_exit_outcomes_equal(self):
        cases = [
            (RunOutcome.PASSED, exit_codes.EXIT_OK),
            (RunOutcome.FAILED, exit_codes.EXIT_TESTS_FAILED),
            (RunOutcome.INCONCLUSIVE, exit_codes.EXIT_TESTS_INCONCLUSIVE),
            (RunOutcome.TIMED_OUT, exit_codes.EXIT_TESTS_TIMED_OUT),
            (RunOutcome.BLOCKED, exit_codes.EXIT_TESTS_BLOCKED),
            (RunOutcome.CANCELLED, exit_codes.EXIT_TESTS_CANCELLED),
            (RunOutcome.ERROR, exit_codes.EXIT_INTERNAL_ERROR),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_path = root / "suite_manifest.json"
            suite_path.write_text("{}", encoding="utf-8")
            reports = root / "reports"
            reports.mkdir()
            paths = {
                "json": reports / "suite_run_report.json",
                "markdown": reports / "suite_run_report.md",
                "csv": reports / "suite_run_report.csv",
            }
            for path in paths.values():
                path.write_text(path.name, encoding="utf-8")
            args = Namespace(
                command="suite-run",
                suite=str(suite_path),
                entry_ids=None,
                tag=None,
                all=True,
                run=True,
                plan=False,
                dry_run=False,
                fail_fast=False,
                timeout=60,
                require_green=True,
            )
            for expected, expected_exit in cases:
                green = 1 if expected is RunOutcome.PASSED else 0
                fixture = {
                    "outcome": expected.value,
                    "summary": {
                        "total": 1,
                        "green": green,
                        "not_green": 1 - green,
                        "executed": 1,
                        "failed": 0 if expected is RunOutcome.PASSED else 1,
                    },
                }
                paths["json"].write_text(
                    json.dumps({"schema_version": "0.1", **fixture}),
                    encoding="utf-8",
                )
                report_value = SimpleNamespace(
                    status=expected.value,
                    summary=fixture["summary"],
                    to_dict=lambda value=fixture: dict(value),
                )
                with self.subTest(outcome=expected.value), mock.patch(
                    "unit_test_runner.cli.commands.run_suite",
                    return_value=(report_value, paths),
                ):
                    result = handle_suite_run(args)
                    envelope = result.to_dict()

                self.assertIs(expected, result.outcome.state)
                self.assertEqual(expected_exit, result.exit_code)
                self.assertEqual(expected.value, result.data["outcome"])
                self.assertEqual(expected.value, envelope["data"]["outcome"])
                self.assertEqual(expected_exit, envelope["data"]["exit_code"])
                self.assertEqual(
                    {
                        "reports/suite_run_report.json",
                        "reports/suite_run_report.md",
                        "reports/suite_run_report.csv",
                    },
                    {artifact.path for artifact in result.artifacts},
                )

    def test_new_suite_fixture_contains_only_canonical_terminal_outcomes(self):
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
            report_path=Path("workspaces/sample/runs/run-001/test_execution_report.json"),
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

        self.assertEqual(RunOutcome.PASSED.value, payload["outcome"])
        self.assertEqual(RunOutcome.PASSED.value, payload["results"][0]["outcome"])
        serialized = str(payload)
        self.assertNotIn("suite_run_completed", serialized)
        self.assertNotIn("test_executed", serialized)

    def test_suite_aggregate_uses_run_outcome_precedence_and_planned_for_no_execution(self):
        from unit_test_runner.suite.manager import _suite_outcome

        planned = _suite_outcome([], SuiteRunPolicy(run_tests=False, dry_run=True))
        self.assertIs(RunOutcome.PLANNED, planned)

        cases = [
            (["passed"], RunOutcome.PASSED),
            (["passed", "inconclusive"], RunOutcome.INCONCLUSIVE),
            (["passed", "failed"], RunOutcome.FAILED),
            (["failed", "blocked"], RunOutcome.BLOCKED),
            (["blocked", "timed_out"], RunOutcome.TIMED_OUT),
            (["timed_out", "cancelled"], RunOutcome.CANCELLED),
            (["cancelled", "error"], RunOutcome.ERROR),
        ]
        for states, expected in cases:
            with self.subTest(states=states):
                results = [
                    SimpleNamespace(
                        execution_status=state,
                        green_status="green" if state == "passed" else "not_green",
                    )
                    for state in states
                ]
                self.assertIs(
                    expected,
                    _suite_outcome(results, SuiteRunPolicy(run_tests=True, dry_run=False)),
                )


if __name__ == "__main__":
    unittest.main()
