from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import SuiteRunReport


def write_suite_run_report(suite_path: Path | str, report: SuiteRunReport) -> dict[str, Path]:
    suite_path = Path(suite_path).resolve()
    reports = suite_path.parent / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": reports / "suite_run_report.json",
        "markdown": reports / "suite_run_report.md",
        "csv": reports / "suite_run_report.csv",
    }
    paths["json"].write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["markdown"].write_text(render_suite_run_markdown(report), encoding="utf-8")
    write_suite_run_csv(paths["csv"], report)
    return paths


def render_suite_run_markdown(report: SuiteRunReport) -> str:
    lines = [
        "# Suite Run Report",
        "",
        f"- Suite: `{report.suite_id}`",
        f"- Status: `{report.status}`",
        f"- Total: {report.summary.get('total', 0)}",
        f"- GREEN: {report.summary.get('green', 0)}",
        f"- Not GREEN: {report.summary.get('not_green', 0)}",
        "",
        "| Entry | Function | Status | GREEN | Workspace |",
        "|---|---|---|---|---|",
    ]
    for result in report.results:
        lines.append(
            f"| {result.entry_id} | {result.function_name} | {result.execution_status} | {result.green_status} | {result.workspace.as_posix()} |"
        )
    return "\n".join(lines) + "\n"


def write_suite_run_csv(path: Path, report: SuiteRunReport) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "entry_id",
                "function",
                "status",
                "green_status",
                "executed",
                "total_tests",
                "passed_tests",
                "failed_tests",
                "inconclusive_tests",
                "unresolved_review_count",
                "workspace",
                "report_path",
                "error",
            ],
        )
        writer.writeheader()
        for result in report.results:
            writer.writerow(
                {
                    "entry_id": result.entry_id,
                    "function": result.function_name,
                    "status": result.execution_status,
                    "green_status": result.green_status,
                    "executed": str(result.executed).lower(),
                    "total_tests": result.total_tests,
                    "passed_tests": result.passed_tests,
                    "failed_tests": result.failed_tests,
                    "inconclusive_tests": result.inconclusive_tests,
                    "unresolved_review_count": result.unresolved_review_count,
                    "workspace": result.workspace.as_posix(),
                    "report_path": result.report_path.as_posix() if result.report_path is not None else "",
                    "error": result.error or "",
                }
            )
