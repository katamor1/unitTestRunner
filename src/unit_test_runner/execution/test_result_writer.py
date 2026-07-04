from __future__ import annotations

import csv
import json
from pathlib import Path

from .execution_models import ExecutionReviewItem, TestExecutionReport


def write_test_execution_reports(workspace: Path | str, report: TestExecutionReport) -> None:
    workspace = Path(workspace).resolve()
    reports = workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "test_execution_report.json").write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (reports / "test_result.json").write_text(
        json.dumps({"schema_version": "0.1", "summary": report.parsed_result.to_dict() if report.parsed_result else {}, "case_results": [case.to_dict() for case in report.case_results]}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with (reports / "test_result.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["test_case_id", "status", "review_required", "coverage_ids", "assertion_failures", "expected", "actual", "evidence", "warnings"])
        writer.writeheader()
        for case in report.case_results:
            writer.writerow(
                {
                    "test_case_id": case.test_case_id or "",
                    "status": case.status,
                    "review_required": str(case.review_required).lower(),
                    "coverage_ids": ";".join(case.related_coverage_ids),
                    "assertion_failures": len(case.assertions),
                    "expected": "",
                    "actual": "",
                    "evidence": case.evidence,
                    "warnings": ";".join(warning.code for warning in case.warnings),
                }
            )
    (reports / "test_execution_report.md").write_text(render_execution_markdown(report), encoding="utf-8")
    (reports / "unresolved_review_items.md").write_text(render_review_items(report.unresolved_review_items), encoding="utf-8")


def render_execution_markdown(report: TestExecutionReport) -> str:
    lines = ["# Test Execution Report", "", "## Target", f"- Function: {report.function_name}", f"- Status: {report.status}", f"- Executed: {'yes' if report.executed else 'no'}", "", "## Results", "| Test Case | Status | Review Required | Evidence |", "|---|---|---|---|"]
    for case in report.case_results:
        lines.append(f"| {case.test_case_id or ''} | {case.status} | {'yes' if case.review_required else 'no'} | {case.evidence} |")
    return "\n".join(lines) + "\n"


def render_review_items(items: list[ExecutionReviewItem]) -> str:
    lines = ["# Unresolved Review Items", "", "| Kind | Test Case | Description | Suggested Action |", "|---|---|---|---|"]
    for item in items:
        lines.append(f"| {item.item_kind} | {item.related_test_case_id or ''} | {item.description} | {item.suggested_action} |")
    return "\n".join(lines) + "\n"
