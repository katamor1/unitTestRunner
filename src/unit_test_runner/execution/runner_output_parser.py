from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .execution_models import AssertionResult, TestCaseExecutionResult, TestExecutionWarning, TestResultSummary


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


def parse_runner_output(text: str, exit_code: int | None = None, timed_out: bool = False) -> ParsedRunnerOutput:
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
            _mark_current_incomplete(cases, current_id, exit_code=None, timed_out=False)
            current_id = run_id
            cases.setdefault(run_id, TestCaseExecutionResult(run_id, None, "unknown", False, evidence="UTR RUN を観測しました。完了マーカー待ちです。"))
            continue
        ok_id = _match_case(raw, r"\[\s*OK\s*\]\s*(\S+)") or _match_case(raw, r"UTR OK\s+(\S+)")
        if ok_id:
            case = cases.setdefault(ok_id, TestCaseExecutionResult(ok_id, None, "unknown", False))
            case.status = "passed"
            case.evidence = "UTR OK を観測しました。"
            if current_id == ok_id:
                current_id = None
            continue
        failed_id = _match_case(raw, r"\[\s*FAILED\s*\]\s*(\S+)") or _match_case(raw, r"UTR FAILED\s+(\S+)")
        if failed_id:
            case = cases.setdefault(failed_id, TestCaseExecutionResult(failed_id, None, "unknown", False))
            case.status = "failed"
            case.evidence = "UTR FAILED を観測しました。"
            if current_id == failed_id:
                current_id = None
            continue
        skipped_id = _match_case(raw, r"\[\s*SKIPPED\s*\]\s*(\S+)") or _match_case(raw, r"UTR SKIPPED\s+(\S+)")
        if skipped_id:
            case = cases.setdefault(skipped_id, TestCaseExecutionResult(skipped_id, None, "unknown", False))
            case.status = "skipped"
            case.evidence = "UTR SKIPPED を観測しました。"
            if current_id == skipped_id:
                current_id = None
            continue
        if raw.startswith("UTR ASSERT"):
            assertion_failures += 1
            assertion = _parse_assertion(raw)
            if current_id:
                case = cases.setdefault(current_id, TestCaseExecutionResult(current_id, None, "failed", False))
                case.status = "failed"
                case.evidence = "UTR ASSERT を観測しました。"
                case.assertions.append(assertion)
            continue
        summary = _parse_summary(raw)
        if summary:
            _mark_current_incomplete(cases, current_id, exit_code=None, timed_out=False)
            summary.assertion_failures = assertion_failures
            explicit_summary = summary
            current_id = None
            continue
        unknown.append(raw)
    _mark_current_incomplete(cases, current_id, exit_code=exit_code, timed_out=timed_out)
    if explicit_summary is None:
        explicit_summary = _summary_from_cases(list(cases.values()), assertion_failures)
    else:
        derived = _summary_from_cases(list(cases.values()), assertion_failures)
        explicit_summary.crashed = derived.crashed
        explicit_summary.not_run = derived.not_run
        explicit_summary.started = derived.started
        explicit_summary.completed = derived.completed
        explicit_summary.parser_confidence = "high"
    return ParsedRunnerOutput(explicit_summary, list(cases.values()), unknown)


def _match_case(raw: str, pattern: str) -> str | None:
    match = re.search(pattern, raw)
    return match.group(1) if match else None


def _mark_current_incomplete(cases: dict[str, TestCaseExecutionResult], current_id: str | None, exit_code: int | None, timed_out: bool) -> None:
    if current_id is None:
        return
    case = cases.get(current_id)
    if case is None or case.status != "unknown":
        return
    case.exit_related = timed_out or (exit_code not in {None, 0})
    if timed_out:
        case.status = "timeout"
        case.evidence = "UTR RUN 後に完了マーカーが出る前にタイムアウトしました。"
        case.warnings.append(TestExecutionWarning("runner_case_timeout", case.evidence, related_test_case_id=case.test_case_id))
        return
    if exit_code not in {None, 0}:
        case.status = "crashed"
        case.evidence = f"UTR RUN 後に OK/FAILED/SKIPPED/SUMMARY が出る前にプロセスが終了しました。exit_code={exit_code}。"
        case.warnings.append(TestExecutionWarning("runner_case_incomplete", case.evidence, related_test_case_id=case.test_case_id))
        return
    case.status = "inconclusive"
    case.evidence = "UTR RUN は観測しましたが、OK/FAILED/SKIPPED の完了マーカーがありません。"
    case.warnings.append(TestExecutionWarning("runner_case_incomplete", case.evidence, related_test_case_id=case.test_case_id))


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
    inconclusive = len([case for case in cases if case.status in {"inconclusive", "not_found_in_output"}])
    crashed = len([case for case in cases if case.status in {"crashed", "timeout"}])
    not_run = len([case for case in cases if case.status == "not_run"])
    completed = passed + failed + skipped + inconclusive
    started = len([case for case in cases if case.status not in {"not_run", "not_found_in_output"}])
    confidence = "medium" if cases else "low"
    if crashed or any(case.status == "unknown" for case in cases):
        confidence = "low"
    return TestResultSummary(len(cases), passed, failed, skipped, inconclusive, assertion_failures, confidence, crashed, not_run, started, completed)
