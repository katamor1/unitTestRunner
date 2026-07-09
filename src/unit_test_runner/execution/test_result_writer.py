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
        writer = csv.DictWriter(handle, fieldnames=["test_case_id", "status", "review_required", "status_label", "coverage_ids", "assertion_failures", "expected", "actual", "evidence", "warnings"])
        writer.writeheader()
        for case in report.case_results:
            writer.writerow(
                {
                    "test_case_id": case.test_case_id or "",
                    "status": case.status,
                    "review_required": str(case.review_required).lower(),
                    "status_label": ja_label(case.status),
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
    summary = report.parsed_result
    lines = [
        "# テスト実行レポート",
        "",
        "## 対象",
        f"- 関数: {report.function_name}",
        f"- 状態: {ja_label(report.status)}",
        f"- 実行済み: {'はい' if report.executed else 'いいえ'}",
    ]
    if report.command_result and report.command_result.exit_code is not None:
        lines.append(f"- 終了コード: {report.command_result.exit_code} / 0x{report.command_result.exit_code & 0xFFFFFFFF:08X}")
    if report.command_result and report.command_result.timed_out:
        lines.append("- タイムアウト: はい")
    if summary:
        lines.extend(
            [
                "",
                "## サマリ",
                "| 項目 | 件数 |",
                "|---|---:|",
                f"| 設計/表示対象ケース | {summary.total} |",
                f"| 開始されたケース | {summary.started} |",
                f"| 完了したケース | {summary.completed} |",
                f"| 成功 | {summary.passed} |",
                f"| 失敗 | {summary.failed} |",
                f"| 異常終了/タイムアウト | {summary.crashed} |",
                f"| 未実行 | {summary.not_run} |",
                f"| 判定保留 | {summary.inconclusive} |",
                f"| parser confidence | {md_cell(summary.parser_confidence)} |",
            ]
        )
    lines.extend(["", "## 結果", "| テストケース | 状態 | レビュー要否 | エビデンス |", "|---|---|---|---|"])
    for case in report.case_results:
        lines.append(f"| {case.test_case_id or ''} | {md_label_cell(case.status)} | {'はい' if case.review_required else 'いいえ'} | {md_cell(case.evidence)} |")
    return "\n".join(lines) + "\n"


def render_review_items(items: list[ExecutionReviewItem]) -> str:
    lines = ["# 未解決レビュー項目", "", "| 種別 | テストケース | 説明 | 推奨アクション |", "|---|---|---|---|"]
    for item in items:
        lines.append(f"| {md_label_cell(item.item_kind)} | {item.related_test_case_id or ''} | {md_cell(item.description)} | {md_cell(item.suggested_action)} |")
    return "\n".join(lines) + "\n"
