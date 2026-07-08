from __future__ import annotations

import csv
import json
from pathlib import Path

from unit_test_runner.reports.japanese import ja_label, md_cell, md_label_cell

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
        writer = csv.DictWriter(handle, fieldnames=["test_case_id", "status", "status_label", "review_required", "coverage_ids", "assertion_failures", "expected", "actual", "evidence", "warnings"])
        writer.writeheader()
        for case in report.case_results:
            writer.writerow(
                {
                    "test_case_id": case.test_case_id or "",
                    "status": case.status,
                    "status_label": ja_label(case.status),
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
    lines = ["# テスト実行レポート", "", "## 対象", f"- 関数: {report.function_name}", f"- 状態: {ja_label(report.status)}", f"- 実行済み: {'はい' if report.executed else 'いいえ'}", "", "## 結果", "| テストケース | 状態 | レビュー要否 | エビデンス |", "|---|---|---|---|"]
    for case in report.case_results:
        lines.append(f"| {case.test_case_id or ''} | {md_label_cell(case.status)} | {'はい' if case.review_required else 'いいえ'} | {md_cell(case.evidence)} |")
    return "\n".join(lines) + "\n"


def render_review_items(items: list[ExecutionReviewItem]) -> str:
    lines = ["# 未解決レビュー項目", "", "| 種別 | テストケース | 説明 | 推奨アクション |", "|---|---|---|---|"]
    for item in items:
        lines.append(f"| {md_label_cell(item.item_kind)} | {item.related_test_case_id or ''} | {md_cell(item.description)} | {md_cell(item.suggested_action)} |")
    return "\n".join(lines) + "\n"
