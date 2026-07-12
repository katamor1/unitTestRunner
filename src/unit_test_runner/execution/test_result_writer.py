from __future__ import annotations

import csv
import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from unit_test_runner import __version__
from unit_test_runner.contracts import ArtifactKind, validate_payload
from unit_test_runner.contracts.registry import get_contract
from unit_test_runner.harness.c90_writer import sha256_file
from unit_test_runner.reports.japanese import ja_label, md_cell, md_label_cell

from .execution_models import EvidenceFile, ExecutionReviewItem, TestExecutionReport
from .run_paths import RunPaths


def write_test_execution_reports(
    workspace: Path | str | RunPaths,
    report: TestExecutionReport,
    *,
    subject: dict[str, str] | None = None,
    producer_commit: str | None = None,
    extensions: dict[str, Any] | None = None,
    materialize_missing_logs: bool = True,
) -> dict[str, Any] | None:
    if isinstance(workspace, RunPaths):
        if subject is None:
            raise ValueError("subject is required for an immutable test run")
        return _write_immutable_test_execution_reports(
            workspace,
            report,
            subject=subject,
            producer_commit=producer_commit or current_producer_commit(),
            extensions=extensions,
            materialize_missing_logs=materialize_missing_logs,
        )
    workspace = Path(workspace).resolve()
    reports = workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "test_execution_report.json").write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (reports / "test_result.json").write_text(
        json.dumps({"schema_version": "0.1", "summary": report.parsed_result.to_dict() if report.parsed_result else {}, "case_results": [case.to_dict() for case in report.case_results]}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_result_csv(reports / "test_result.csv", report)
    (reports / "test_execution_report.md").write_text(render_execution_markdown(report), encoding="utf-8")
    (reports / "unresolved_review_items.md").write_text(render_review_items(report.unresolved_review_items), encoding="utf-8")


def _write_immutable_test_execution_reports(
    paths: RunPaths,
    report: TestExecutionReport,
    *,
    subject: dict[str, str],
    producer_commit: str,
    extensions: dict[str, Any] | None,
    materialize_missing_logs: bool,
) -> dict[str, Any]:
    if materialize_missing_logs:
        for log_path in (paths.stdout_log, paths.stderr_log, paths.combined_log):
            if not log_path.exists():
                log_path.write_bytes(b"")
    result_data = {
        "summary": report.parsed_result.to_dict() if report.parsed_result else {},
        "case_results": [case.to_dict() for case in report.case_results],
    }
    result_payload = build_artifact_payload(
        ArtifactKind.TEST_RESULT,
        result_data,
        subject=subject,
        producer_commit=producer_commit,
    )
    write_validated_artifact(paths.result_json, ArtifactKind.TEST_RESULT, result_payload)
    _write_result_csv(paths.result_csv, report)
    workspace = paths.root.parents[1]
    report.evidence_files = [
        _run_evidence_file(workspace, paths.result_json, "test_result", "テスト結果JSON"),
        _run_evidence_file(workspace, paths.result_csv, "test_result_csv", "テスト結果CSV"),
        _run_evidence_file(workspace, paths.stdout_log, "execution_stdout_log", "標準出力ログ"),
        _run_evidence_file(workspace, paths.stderr_log, "execution_stderr_log", "標準エラー出力ログ"),
        _run_evidence_file(workspace, paths.combined_log, "execution_log", "テスト実行ログ"),
    ]
    report_data = report.to_dict()
    report_data.pop("schema_version", None)
    report_payload = build_artifact_payload(
        ArtifactKind.TEST_EXECUTION_REPORT,
        report_data,
        subject=subject,
        producer_commit=producer_commit,
        extensions=extensions,
    )
    write_validated_artifact(
        paths.execution_report,
        ArtifactKind.TEST_EXECUTION_REPORT,
        report_payload,
    )
    return report_payload


def _write_result_csv(path: Path, report: TestExecutionReport) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
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


def _run_evidence_file(workspace: Path, path: Path, kind: str, description: str) -> EvidenceFile:
    return EvidenceFile(
        path=path.relative_to(workspace),
        file_kind=kind,
        required=True,
        exists=path.is_file(),
        sha256=sha256_file(path),
        integrity_status="valid" if path.is_file() else "missing",
        description=description,
    )


def build_artifact_payload(
    kind: ArtifactKind,
    data: dict[str, Any],
    *,
    subject: dict[str, str],
    producer_commit: str,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_kind": kind.value,
        "schema_version": get_contract(kind).current_version,
        "producer": {
            "name": "unit-test-runner",
            "version": __version__,
            "commit": producer_commit,
        },
        "subject": dict(subject),
        "data": data,
        "extensions": dict(extensions or {}),
    }


def write_validated_artifact(
    path: Path,
    kind: ArtifactKind,
    payload: dict[str, Any],
    *,
    atomic: bool = False,
) -> None:
    violations = validate_payload(kind, payload)
    if violations:
        detail = "; ".join(
            f"{item.code} at {item.json_path}: {item.message}" for item in violations
        )
        raise ValueError(f"Invalid {kind.value}: {detail}")
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if not atomic:
        path.write_text(serialized, encoding="utf-8")
        return
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(serialized, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@lru_cache(maxsize=1)
def current_producer_commit() -> str:
    configured = os.environ.get("UNIT_TEST_RUNNER_PRODUCER_COMMIT")
    if configured:
        return configured
    for parent in Path(__file__).resolve().parents:
        if not (parent / ".git").exists():
            continue
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        commit = completed.stdout.strip()
        if completed.returncode == 0 and commit:
            return commit
    return f"package-{__version__}"


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
