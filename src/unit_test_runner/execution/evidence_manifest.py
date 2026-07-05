from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unit_test_runner.harness.c90_writer import sha256_file

from .execution_models import EvidenceFile, EvidenceManifest, EvidenceSummary, TestExecutionReport


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
        failed_tests=report.parsed_result.failed if report.parsed_result else 0,
        inconclusive_tests=report.parsed_result.inconclusive if report.parsed_result else 0,
        unresolved_review_count=len(report.unresolved_review_items),
        ready_for_review=True,
    )
    source_files = [_evidence_file(workspace, Path(item["workspace_path"]), "source", item.get("file_kind", "source")) for item in build_workspace_report.get("copied_files", [])]
    generated_files = [
        _evidence_file(workspace, Path(item["path"]), "generated_source", item.get("file_kind", "generated"))
        for item in _read_json(workspace / "reports" / "harness_skeleton_report.json").get("generated_files", [])
        if str(item.get("path", "")).startswith("generated/")
    ]
    build_reports = [
        _evidence_file(workspace, Path("reports/build_workspace_report.json"), "build_report", "Build workspace report"),
        _evidence_file(workspace, Path("reports/build_probe_report.json"), "build_report", "Build probe report"),
        _evidence_file(workspace, Path("reports/build_completion_iteration_report.json"), "completion_report", "Build completion iteration report"),
    ]
    test_reports = [
        _evidence_file(workspace, Path("reports/test_execution_report.json"), "execution_report", "Test execution report"),
        _evidence_file(workspace, Path("reports/test_result.json"), "test_result_json", "Test result JSON"),
        _evidence_file(workspace, Path("reports/test_result.csv"), "test_result_csv", "Test result CSV"),
    ]
    logs = [_evidence_file(workspace, Path("logs/test_execution.log"), "test_log", "Test execution log")]
    return EvidenceManifest(report.function_name, workspace, datetime.now(timezone.utc).isoformat(), source_files, generated_files, build_reports, test_reports, logs, report.unresolved_review_items, summary)


def write_evidence_package(workspace: Path | str, manifest: EvidenceManifest, report: TestExecutionReport) -> None:
    workspace = Path(workspace).resolve()
    reports = workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "evidence_manifest.json").write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (reports / "evidence_package.md").write_text(render_evidence_package(manifest, report), encoding="utf-8")


def _evidence_file(workspace: Path, relative: Path, kind: str, description: str) -> EvidenceFile:
    return EvidenceFile(relative, kind, sha256_file(workspace / relative), True, description)


def render_evidence_package(manifest: EvidenceManifest, report: TestExecutionReport) -> str:
    summary = manifest.summary
    lines = [
        "# Function Unit Test Evidence Package",
        "",
        "## Target",
        f"- Function: {manifest.function_name}",
        f"- Workspace: {manifest.workspace_root.as_posix()}",
        f"- Build Probe Status: {summary.build_probe_status}",
        f"- Test Execution Status: {summary.test_execution_status}",
        "",
        "## Summary",
        "| Item | Count |",
        "|---|---:|",
        f"| Total Tests | {summary.total_tests} |",
        f"| Passed | {summary.passed_tests} |",
        f"| Failed | {summary.failed_tests} |",
        f"| Inconclusive | {summary.inconclusive_tests} |",
        f"| Review Items | {summary.unresolved_review_count} |",
        "",
        "## Evidence Files",
        "| File | Kind | SHA-256 |",
        "|---|---|---|",
    ]
    for item in manifest.source_files + manifest.generated_files + manifest.build_reports + manifest.test_reports + manifest.logs:
        lines.append(f"| {item.path.as_posix()} | {item.file_kind} | {item.sha256 or ''} |")
    lines.extend(["", "## Unresolved Review Items", "| Kind | Description | Suggested Action |", "|---|---|---|"])
    for item in report.unresolved_review_items:
        lines.append(f"| {item.item_kind} | {item.description} | {item.suggested_action} |")
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
