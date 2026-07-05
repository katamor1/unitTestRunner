from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .execution_models import AssertionResult, TestCaseExecutionResult, TestResultSummary


@dataclass
class ParsedRunnerOutput:
    summary: TestResultSummary
    case_results: list[TestCaseExecutionResult] = field(default_factory=list)
    unknown_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary.to_dict(),
            "case_results": [item.to_dict() for item in self.case_results],
            "unknown_lines": self.unknown_lines,
        }


def parse_runner_output(text: str) -> ParsedRunnerOutput:
    cases: dict[str, TestCaseExecutionResult] = {}
    current_id: str | None = None
    assertion_failures = 0
    unknown: list[str] = []
    explicit_summary: TestResultSummary | None = None
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        run_id = _match_case(raw, r"\[\s*RUN\s*\]\s*(\S+)") or _match_case(raw, r"UTR RUN\s+(\S+)")
        if run_id:
            _mark_current_passed_if_unresolved(cases, current_id)
            current_id = run_id
            cases.setdefault(run_id, TestCaseExecutionResult(run_id, None, "unknown", False, evidence="runner output observed"))
            continue
        ok_id = _match_case(raw, r"\[\s*OK\s*\]\s*(\S+)")
        if ok_id:
            cases.setdefault(ok_id, TestCaseExecutionResult(ok_id, None, "unknown", False)).status = "passed"
            continue
        failed_id = _match_case(raw, r"\[\s*FAILED\s*\]\s*(\S+)")
        if failed_id:
            cases.setdefault(failed_id, TestCaseExecutionResult(failed_id, None, "unknown", False)).status = "failed"
            continue
        skipped_id = _match_case(raw, r"\[\s*SKIPPED\s*\]\s*(\S+)")
        if skipped_id:
            cases.setdefault(skipped_id, TestCaseExecutionResult(skipped_id, None, "unknown", False)).status = "skipped"
            continue
        if raw.startswith("UTR ASSERT"):
            assertion_failures += 1
            assertion = _parse_assertion(raw)
            if current_id:
                case = cases.setdefault(current_id, TestCaseExecutionResult(current_id, None, "failed", False))
                case.status = "failed"
                case.assertions.append(assertion)
            continue
        summary = _parse_summary(raw)
        if summary:
            _mark_current_passed_if_unresolved(cases, current_id)
            summary.assertion_failures = assertion_failures
            explicit_summary = summary
            continue
        unknown.append(raw)
    _mark_current_passed_if_unresolved(cases, current_id)
    if explicit_summary is None:
        explicit_summary = _summary_from_cases(list(cases.values()), assertion_failures)
    else:
        explicit_summary.parser_confidence = "high"
    return ParsedRunnerOutput(explicit_summary, list(cases.values()), unknown)


def _match_case(raw: str, pattern: str) -> str | None:
    match = re.search(pattern, raw)
    return match.group(1) if match else None


def _mark_current_passed_if_unresolved(cases: dict[str, TestCaseExecutionResult], current_id: str | None) -> None:
    if current_id is None:
        return
    case = cases.get(current_id)
    if case is not None and case.status == "unknown":
        case.status = "passed"


def _parse_summary(raw: str) -> TestResultSummary | None:
    if "SUMMARY" not in raw:
        return None
    values = {key: int(value) for key, value in re.findall(r"(total|passed|failed|skipped|inconclusive)=(\d+)", raw)}
    if not values:
        return None
    return TestResultSummary(
        total=values.get("total", 0),
        passed=values.get("passed", 0),
        failed=values.get("failed", 0),
        skipped=values.get("skipped", 0),
        inconclusive=values.get("inconclusive", 0),
        parser_confidence="high",
    )


def _parse_assertion(raw: str) -> AssertionResult:
    match = re.search(r"UTR ASSERT\s+(\S+):\s+(.+?):(\d+)\s+(.+)$", raw)
    if match:
        return AssertionResult(match.group(1), "failed", Path(match.group(2)), int(match.group(3)), None, None, match.group(4), raw)
    return AssertionResult("unknown", "failed", None, None, None, None, None, raw)


def _summary_from_cases(cases: list[TestCaseExecutionResult], assertion_failures: int) -> TestResultSummary:
    passed = len([case for case in cases if case.status == "passed"])
    failed = len([case for case in cases if case.status == "failed"])
    skipped = len([case for case in cases if case.status == "skipped"])
    inconclusive = len([case for case in cases if case.status == "inconclusive"])
    return TestResultSummary(len(cases), passed, failed, skipped, inconclusive, assertion_failures, "medium" if cases else "low")
