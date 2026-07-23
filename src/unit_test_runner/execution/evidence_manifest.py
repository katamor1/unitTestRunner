from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.harness.c90_writer import sha256_file
from unit_test_runner.reports.japanese import ja_label, md_cell, md_label_cell

from .evidence_paths import EvidencePaths
from .evidence_validator import required_evidence_is_valid, validate_evidence_files
from .execution_models import (
    EvidenceFile,
    EvidenceManifest,
    EvidenceSummary,
    TestExecutionReport,
    TestResultSummary,
)
from .report_loader import LoadedExecutionRun
from .test_result_writer import build_artifact_payload, write_validated_artifact


def build_evidence_manifest_from_run(
    workspace: Path,
    loaded_run: LoadedExecutionRun,
    paths: EvidencePaths,
    *,
    producer_commit: str,
) -> EvidenceManifest:
    workspace = Path(workspace).resolve()
    report = loaded_run.report
    subject = loaded_run.payload["subject"]
    execution_hash = sha256_file(loaded_run.report_path)
    if execution_hash is None:
        raise FileNotFoundError(loaded_run.report_path)
    source_run_payload = build_artifact_payload(
        ArtifactKind.EVIDENCE_SOURCE_RUN,
        {
            "source_run_id": loaded_run.run_id,
            "execution_report": {
                "artifact_kind": ArtifactKind.TEST_EXECUTION_REPORT.value,
                "path": loaded_run.report_path.relative_to(workspace).as_posix(),
                "sha256": execution_hash,
            },
            "logs": [
                {
                    "artifact_kind": item.file_kind,
                    "path": item.path.as_posix(),
                    "sha256": item.sha256,
                }
                for item in report.evidence_files
                if item.file_kind in {
                    "execution_stdout_log",
                    "execution_stderr_log",
                    "execution_log",
                }
                and item.sha256 is not None
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        subject=subject,
        producer_commit=producer_commit,
    )
    write_validated_artifact(
        paths.source_run,
        ArtifactKind.EVIDENCE_SOURCE_RUN,
        source_run_payload,
    )
    source_file = EvidenceFile(
        path=Path(subject["source_path"]),
        file_kind="source",
        required=True,
        exists=False,
        sha256=subject["source_sha256"],
        integrity_status="missing",
        description="テスト対象ソース",
    )
    run_files = [
        EvidenceFile(
            path=loaded_run.report_path.relative_to(workspace),
            file_kind="test_execution_report",
            required=True,
            exists=True,
            sha256=execution_hash,
            integrity_status="valid",
            description="テスト実行レポート",
        ),
        *report.evidence_files,
        _existing_file(
            workspace,
            paths.source_run,
            "evidence_source_run",
            "実行元ラン固定レコード",
        ),
    ]
    for blocker_path, kind, description in (
        (
            loaded_run.report_path.with_name("test_execution_blockers.json"),
            "test_execution_blocker_report",
            "テスト実行ブロッカーJSON",
        ),
        (
            loaded_run.report_path.with_name("test_execution_blockers.md"),
            "test_execution_blocker_report_markdown",
            "テスト実行ブロッカーMarkdown",
        ),
    ):
        if blocker_path.is_file():
            run_files.append(
                _existing_file(workspace, blocker_path, kind, description)
            )
    test_reports = [
        item
        for item in run_files
        if item.file_kind
        in {
            "test_execution_report",
            "test_result",
            "test_result_csv",
            "evidence_source_run",
            "test_execution_blocker_report",
            "test_execution_blocker_report_markdown",
        }
    ]
    logs = [
        item
        for item in run_files
        if item.file_kind
        in {"execution_stdout_log", "execution_stderr_log", "execution_log"}
    ]
    build_reports = [
        _existing_file(workspace, path, kind, description)
        for path, kind, description in (
            (
                workspace / "reports" / "build_workspace_report.json",
                "build_workspace_report",
                "ビルドworkspaceレポート",
            ),
            (
                workspace / "reports" / "build_probe_report.json",
                "build_probe_report",
                "ビルドプローブレポート",
            ),
        )
    ]
    all_files = validate_evidence_files(
        workspace,
        [source_file, *build_reports, *test_reports, *logs],
    )
    source_files = all_files[:1]
    build_count = len(build_reports)
    validated_build_reports = all_files[1 : 1 + build_count]
    validated_test_reports = all_files[
        1 + build_count : 1 + build_count + len(test_reports)
    ]
    validated_logs = all_files[1 + build_count + len(test_reports) :]
    summary = _evidence_summary(
        report,
        build_probe_status=_build_probe_status(workspace),
        files=all_files,
    )
    manifest = EvidenceManifest(
        function_name=report.function_name,
        workspace_root=Path("."),
        created_at=datetime.now(timezone.utc).isoformat(),
        source_files=source_files,
        generated_files=[],
        build_reports=validated_build_reports,
        test_reports=validated_test_reports,
        logs=validated_logs,
        unresolved_items=report.unresolved_review_items,
        summary=summary,
        schema_version="1.0.0",
    )
    paths.evidence_package.write_text(
        render_evidence_package(manifest, report),
        encoding="utf-8",
    )
    package_file = _existing_file(
        workspace,
        paths.evidence_package,
        "evidence_package",
        "エビデンスパッケージ",
    )
    manifest.generated_files = validate_evidence_files(workspace, [package_file])
    manifest.summary.ready_for_review = required_evidence_is_valid(
        manifest.source_files
        + manifest.generated_files
        + manifest.build_reports
        + manifest.test_reports
        + manifest.logs
    )
    manifest_data = manifest.to_dict()
    manifest_data.pop("schema_version", None)
    manifest_payload = build_artifact_payload(
        ArtifactKind.EVIDENCE_MANIFEST,
        manifest_data,
        subject=subject,
        producer_commit=producer_commit,
    )
    write_validated_artifact(
        paths.evidence_manifest,
        ArtifactKind.EVIDENCE_MANIFEST,
        manifest_payload,
    )
    return manifest


def _evidence_summary(
    report: TestExecutionReport,
    *,
    build_probe_status: str,
    files: list[EvidenceFile],
) -> EvidenceSummary:
    parsed = report.parsed_result or TestResultSummary()
    test_green = bool(
        report.executed
        and report.status == "passed"
        and parsed.total > 0
        and parsed.passed == parsed.total
        and parsed.failed == 0
        and parsed.crashed == 0
        and parsed.inconclusive == 0
        and parsed.not_run == 0
    )
    return EvidenceSummary(
        build_probe_status=build_probe_status,
        test_execution_status=report.status,
        total_tests=parsed.total,
        passed_tests=parsed.passed,
        failed_tests=parsed.failed + parsed.crashed,
        inconclusive_tests=parsed.inconclusive + parsed.not_run,
        unresolved_review_count=len(report.unresolved_review_items),
        test_green=test_green,
        ready_for_review=required_evidence_is_valid(files),
    )


def _existing_file(
    workspace: Path,
    path: Path,
    kind: str,
    description: str,
) -> EvidenceFile:
    return EvidenceFile(
        path=path.relative_to(workspace),
        file_kind=kind,
        required=True,
        exists=path.is_file(),
        sha256=sha256_file(path),
        integrity_status="valid" if path.is_file() else "missing",
        description=description,
    )


def _build_probe_status(workspace: Path) -> str:
    path = workspace / "reports" / "build_probe_report.json"
    if not path.is_file():
        return "unknown"
    return _read_json(path).get("function", {}).get("status", "unknown")


def build_evidence_manifest(
    workspace: Path | str,
    report: TestExecutionReport,
    build_probe_report: dict[str, Any],
    build_workspace_report: dict[str, Any],
    completion_report: dict[str, Any] | None = None,
) -> EvidenceManifest:
    workspace = Path(workspace).resolve()
    summary = EvidenceSummary(
        build_probe_status=build_probe_report.get("function", {}).get("status", "unknown"),
        test_execution_status=report.status,
        total_tests=report.parsed_result.total if report.parsed_result else 0,
        passed_tests=report.parsed_result.passed if report.parsed_result else 0,
        failed_tests=(report.parsed_result.failed + report.parsed_result.crashed) if report.parsed_result else 0,
        inconclusive_tests=report.parsed_result.inconclusive if report.parsed_result else 0,
        unresolved_review_count=len(report.unresolved_review_items),
        test_green=report.status == "passed" and report.executed,
        ready_for_review=True,
    )
    source_files = [_evidence_file(workspace, Path(item["workspace_path"]), "source", item.get("file_kind", "source")) for item in build_workspace_report.get("copied_files", [])]
    generated_files = [
        _evidence_file(workspace, Path(item["path"]), "generated_source", item.get("file_kind", "generated"))
        for item in _read_json(workspace / "reports" / "harness_skeleton_report.json").get("generated_files", [])
        if str(item.get("path", "")).startswith("generated/")
    ]
    build_reports = [
        _evidence_file(workspace, Path("reports/build_workspace_report.json"), "build_report", "ビルドworkspaceレポート"),
        _evidence_file(workspace, Path("reports/build_probe_report.json"), "build_report", "ビルドプローブレポート"),
        _evidence_file(workspace, Path("reports/build_completion_iteration_report.json"), "completion_report", "ビルド補完イテレーションレポート"),
    ]
    test_reports = [
        _evidence_file(workspace, Path("reports/test_execution_report.json"), "execution_report", "テスト実行レポート"),
        _evidence_file(workspace, Path("reports/test_result.json"), "test_result_json", "テスト結果JSON"),
        _evidence_file(workspace, Path("reports/test_result.csv"), "test_result_csv", "テスト結果CSV"),
    ]
    logs = [_evidence_file(workspace, Path("logs/test_execution.log"), "test_log", "テスト実行ログ")]
    return EvidenceManifest(report.function_name, workspace, datetime.now(timezone.utc).isoformat(), source_files, generated_files, build_reports, test_reports, logs, report.unresolved_review_items, summary)


def write_evidence_package(workspace: Path | str, manifest: EvidenceManifest, report: TestExecutionReport) -> None:
    workspace = Path(workspace).resolve()
    reports = workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "evidence_manifest.json").write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (reports / "evidence_package.md").write_text(render_evidence_package(manifest, report), encoding="utf-8")


def _evidence_file(workspace: Path, relative: Path, kind: str, description: str) -> EvidenceFile:
    path = workspace / relative
    return EvidenceFile(
        path=relative,
        file_kind=kind,
        required=True,
        exists=path.is_file(),
        sha256=sha256_file(path),
        integrity_status="valid" if path.is_file() else "missing",
        description=description,
    )


def render_evidence_package(manifest: EvidenceManifest, report: TestExecutionReport) -> str:
    summary = manifest.summary
    lines = [
        "# 関数単体テストエビデンスパッケージ",
        "",
        "## 対象",
        f"- 関数: {manifest.function_name}",
        f"- workspace: {manifest.workspace_root.as_posix()}",
        f"- ビルドプローブ状態: {ja_label(summary.build_probe_status)}",
        f"- テスト実行状態: {ja_label(summary.test_execution_status)}",
        "",
        "## サマリ",
        "| 項目 | 件数 |",
        "|---|---:|",
        f"| テスト総数 | {summary.total_tests} |",
        f"| 成功 | {summary.passed_tests} |",
        f"| 失敗 | {summary.failed_tests} |",
        f"| 判定保留 | {summary.inconclusive_tests} |",
        f"| レビュー項目 | {summary.unresolved_review_count} |",
        f"| テストGREEN | {'はい' if summary.test_green else 'いいえ'} |",
        f"| レビュー準備完了 | {'はい' if summary.ready_for_review else 'いいえ'} |",
        "",
        "## エビデンスファイル",
        "| ファイル | 種別 | SHA-256 | 整合性 |",
        "|---|---|---|---|",
    ]
    for item in manifest.source_files + manifest.generated_files + manifest.build_reports + manifest.test_reports + manifest.logs:
        lines.append(
            f"| {item.path.as_posix()} | {md_label_cell(item.file_kind)} | "
            f"{item.sha256 or ''} | {item.integrity_status} |"
        )
    lines.extend(["", "## 未解決レビュー項目", "| 種別 | 説明 | 推奨アクション |", "|---|---|---|"])
    for item in report.unresolved_review_items:
        lines.append(f"| {md_label_cell(item.item_kind)} | {md_cell(item.description)} | {md_cell(item.suggested_action)} |")
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
