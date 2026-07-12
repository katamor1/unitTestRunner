from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from unit_test_runner.contracts import RunOutcome

from .exit_codes import (
    EXIT_INTERNAL_ERROR,
    EXIT_OK,
    EXIT_TESTS_BLOCKED,
    EXIT_TESTS_CANCELLED,
    EXIT_TESTS_FAILED,
    EXIT_TESTS_INCONCLUSIVE,
    EXIT_TESTS_TIMED_OUT,
)

if TYPE_CHECKING:
    from unit_test_runner.execution.execution_models import TestExecutionReport
    from unit_test_runner.suite.models import SuiteRunReport


@dataclass(frozen=True)
class DomainOutcome:
    kind: str
    state: RunOutcome
    green: bool | None


_EXIT_BY_OUTCOME = {
    RunOutcome.PLANNED: EXIT_OK,
    RunOutcome.PASSED: EXIT_OK,
    RunOutcome.FAILED: EXIT_TESTS_FAILED,
    RunOutcome.INCONCLUSIVE: EXIT_TESTS_INCONCLUSIVE,
    RunOutcome.TIMED_OUT: EXIT_TESTS_TIMED_OUT,
    RunOutcome.BLOCKED: EXIT_TESTS_BLOCKED,
    RunOutcome.CANCELLED: EXIT_TESTS_CANCELLED,
    RunOutcome.ERROR: EXIT_INTERNAL_ERROR,
}


def classify_test_run(
    report: TestExecutionReport,
    *,
    execution_requested: bool,
) -> tuple[DomainOutcome, int]:
    if not execution_requested:
        outcome = DomainOutcome("test_run", RunOutcome.PLANNED, None)
        return outcome, EXIT_OK

    state = _canonical_outcome(report.status)
    green = _is_green(report) if state is RunOutcome.PASSED else False
    if state is RunOutcome.PASSED and not green:
        state = RunOutcome.INCONCLUSIVE
    outcome = DomainOutcome("test_run", state, green)
    return outcome, _EXIT_BY_OUTCOME[state]


def classify_suite_run(
    report: SuiteRunReport,
    *,
    execution_requested: bool,
) -> tuple[DomainOutcome, int]:
    if not execution_requested:
        outcome = DomainOutcome("suite_run", RunOutcome.PLANNED, None)
        return outcome, EXIT_OK
    state = _canonical_outcome(report.status)
    summary = report.summary
    green = (
        state is RunOutcome.PASSED
        and summary.get("total", 0) > 0
        and summary.get("green") == summary.get("total")
        and summary.get("not_green", 0) == 0
    )
    if state is RunOutcome.PASSED and not green:
        state = (
            RunOutcome.FAILED
            if summary.get("total", 0) > 0 and summary.get("not_green", 0) > 0
            else RunOutcome.INCONCLUSIVE
        )
    outcome = DomainOutcome("suite_run", state, green if state is not RunOutcome.PLANNED else None)
    return outcome, _EXIT_BY_OUTCOME[state]


def classify_domain_state(
    kind: str,
    state: RunOutcome,
    *,
    green: bool | None,
) -> tuple[DomainOutcome, int]:
    outcome = DomainOutcome(kind, state, green)
    return outcome, _EXIT_BY_OUTCOME[state]


def _canonical_outcome(value: str) -> RunOutcome:
    aliases = {
        "not_run": RunOutcome.INCONCLUSIVE,
        "timeout": RunOutcome.TIMED_OUT,
    }
    if value in aliases:
        return aliases[value]
    try:
        return RunOutcome(value)
    except ValueError:
        return RunOutcome.ERROR


def _is_green(report: TestExecutionReport) -> bool:
    summary = report.parsed_result
    if not report.executed or summary is None or summary.total <= 0:
        return False
    return (
        summary.passed == summary.total
        and summary.failed == 0
        and summary.inconclusive == 0
        and getattr(summary, "crashed", 0) == 0
        and getattr(summary, "not_run", 0) == 0
    )
