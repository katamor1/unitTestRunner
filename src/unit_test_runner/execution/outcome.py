from __future__ import annotations

from typing import Any

from unit_test_runner.contracts import RunOutcome


def classify_test_execution(
    report: Any,
    *,
    execution_requested: bool,
) -> tuple[RunOutcome, bool | None]:
    if not execution_requested:
        return RunOutcome.PLANNED, None

    state = _canonical_outcome(str(getattr(report, "status", "error")))
    green = _is_green(report) if state is RunOutcome.PASSED else False
    if state is RunOutcome.PASSED and not green:
        state = RunOutcome.INCONCLUSIVE
    return state, green


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


def _is_green(report: Any) -> bool:
    summary = getattr(report, "parsed_result", None)
    if not getattr(report, "executed", False) or summary is None or summary.total <= 0:
        return False
    return (
        summary.passed == summary.total
        and summary.failed == 0
        and summary.inconclusive == 0
        and getattr(summary, "crashed", 0) == 0
        and getattr(summary, "not_run", 0) == 0
    )
