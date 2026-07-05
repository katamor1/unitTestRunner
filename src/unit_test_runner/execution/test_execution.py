from __future__ import annotations

import csv
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unit_test_runner.harness.c90_writer import sha256_file

from .execution_models import (
    EvidenceFile,
    EvidenceManifest,
    EvidenceSummary,
    ExecutableInfo,
    ExecutionCommand,
    ExecutionCommandResult,
    ExecutionReviewItem,
    TestCaseExecutionResult,
    TestExecutionPolicy,
    TestExecutionReport,
    TestExecutionWarning,
    TestResultSummary,
)
from .evidence_manifest import build_evidence_manifest, write_evidence_package
from .executable_resolver import resolve_executable
from .execution_runner import build_execution_command, environment_summary, run_test_executable
from .precondition_validator import validate_execution_preconditions
from .runner_output_parser import parse_runner_output
from .test_result_writer import render_execution_markdown, render_review_items, write_test_execution_reports


def prepare_test_execution_evidence(
    workspace: Path | str,
    executable: Path | str | None = None,
    run_tests: bool = False,
    dry_run: bool = True,
    timeout_seconds: int = 60,
    allow_placeholder_tests: bool = True,
    treat_placeholder_as_inconclusive: bool = True,
) -> tuple[TestExecutionReport, EvidenceManifest]:
    workspace = Path(workspace).resolve()
    reports = workspace / "reports"
    logs = workspace / "logs"
    reports.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    test_case_design = _read_json(reports / "test_case_design.json")
    harness_report = _read_json(reports / "harness_skeleton_report.json")
    build_probe = _read_json(reports / "build_probe_report.json")
    build_workspace = _read_json(reports / "build_workspace_report.json")
    completion_report = _read_optional_json(reports / "build_completion_iteration_report.json")
    policy = TestExecutionPolicy(
        run_tests=run_tests,
        dry_run=dry_run,
        timeout_seconds=timeout_seconds,
        allow_placeholder_tests=allow_placeholder_tests,
        treat_placeholder_as_inconclusive=treat_placeholder_as_inconclusive,
    )
    function_name = test_case_design.get("function", {}).get("name") or build_workspace.get("function", {}).get("name") or "unknown_function"
    source_path = Path(build_workspace.get("source", {}).get("path") or "")
    executable_info = resolve_executable(workspace, executable, build_probe)
    command = build_execution_command(workspace, executable_info, timeout_seconds=timeout_seconds, dry_run=dry_run or not run_tests)
    review_items = _placeholder_review_items(harness_report, test_case_design)
    warnings: list[TestExecutionWarning] = []
    command_result: ExecutionCommandResult | None = None
    parsed_summary = TestResultSummary()
    case_results = _case_results_from_design(test_case_design)
    status = "not_run"
    executed = False
    if run_tests and not dry_run:
        precondition_status, precondition_warnings, precondition_review_items = validate_execution_preconditions(build_probe, executable_info, policy)
        if precondition_status == "blocked":
            status = "blocked"
            warnings.extend(precondition_warnings)
            review_items.extend(precondition_review_items)
        else:
            executed = True
            command_result, parsed_summary, case_results, status = run_test_executable(workspace, executable_info, timeout_seconds)
    else:
        (logs / "test_execution.log").write_text("DRY RUN\n" + command.command_line + "\n", encoding="utf-8")
        command_result = ExecutionCommandResult(None, None, None, None, None, None, Path("logs/test_execution.log"), False)
    if review_items and policy.treat_placeholder_as_inconclusive and status in {"passed", "executed", "not_run"}:
        if status != "not_run":
            status = "inconclusive"
        for case in case_results:
            case.review_required = True
            if case.status == "passed":
                case.status = "inconclusive"
        parsed_summary.inconclusive = len([case for case in case_results if case.review_required])
    report = TestExecutionReport(
        source_path=source_path,
        function_name=function_name,
        status=status,
        executed=executed,
        executable=executable_info,
        command=command,
        command_result=command_result,
        parsed_result=parsed_summary,
        case_results=case_results,
        unresolved_review_items=review_items,
        evidence_files=[],
        warnings=warnings,
        policy=policy,
    )
    write_test_execution_reports(workspace, report)
    manifest = build_evidence_manifest(workspace, report, build_probe, build_workspace, completion_report)
    write_evidence_package(workspace, manifest, report)
    return report, manifest


def _resolve_executable(workspace: Path, executable: Path | str | None, build_probe: dict[str, Any]) -> ExecutableInfo:
    path = Path(executable) if executable else Path("bin") / "utr_probe.exe"
    if not path.is_absolute():
        absolute = workspace / path
        relative = path
    else:
        absolute = path
        try:
            relative = path.relative_to(workspace)
        except ValueError:
            relative = path
    warnings = []
    if not absolute.exists():
        warnings.append(TestExecutionWarning("executable_not_found", f"Executable not found: {relative}", related_file=relative))
    return ExecutableInfo(relative, absolute.exists(), sha256_file(absolute), "build_probe", build_probe.get("function", {}).get("status", "unknown"), warnings)


def _run_executable(workspace: Path, executable: Path, timeout_seconds: int):
    started = datetime.now(timezone.utc)
    start = time.monotonic()
    stdout_log = workspace / "logs" / "test_stdout.log"
    stderr_log = workspace / "logs" / "test_stderr.log"
    combined_log = workspace / "logs" / "test_execution.log"
    try:
        completed = subprocess.run([str(workspace / executable)], cwd=workspace, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_seconds, check=False)
        duration = int((time.monotonic() - start) * 1000)
        stdout_log.write_text(completed.stdout, encoding="utf-8")
        stderr_log.write_text(completed.stderr, encoding="utf-8")
        combined_log.write_text(completed.stdout + completed.stderr, encoding="utf-8")
        parsed = parse_runner_output(completed.stdout + completed.stderr)
        status = "passed" if completed.returncode == 0 and parsed.summary.failed == 0 else "failed"
        result = ExecutionCommandResult(completed.returncode, started.isoformat(), datetime.now(timezone.utc).isoformat(), duration, Path("logs/test_stdout.log"), Path("logs/test_stderr.log"), Path("logs/test_execution.log"), False)
        return result, parsed.summary, parsed.case_results, status
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        stdout_log.write_text(stdout, encoding="utf-8")
        stderr_log.write_text(stderr, encoding="utf-8")
        combined_log.write_text(stdout + stderr, encoding="utf-8")
        result = ExecutionCommandResult(None, started.isoformat(), datetime.now(timezone.utc).isoformat(), int((time.monotonic() - start) * 1000), Path("logs/test_stdout.log"), Path("logs/test_stderr.log"), Path("logs/test_execution.log"), True)
        return result, TestResultSummary(parser_confidence="low"), [], "timeout"


def _case_results_from_design(test_case_design: dict[str, Any]) -> list[TestCaseExecutionResult]:
    results = []
    for case in test_case_design.get("test_cases", []):
        coverage = [link.get("coverage_id", "") for link in case.get("coverage_links", []) if link.get("coverage_id")]
        review = case.get("review_status") == "review_required"
        results.append(
            TestCaseExecutionResult(
                test_case_id=case.get("test_case_id"),
                generated_function_name=None,
                status="not_found_in_output",
                exit_related=False,
                related_coverage_ids=coverage,
                review_required=review,
                evidence="test execution was not run" if review else "",
            )
        )
    return results


def _placeholder_review_items(harness_report: dict[str, Any], test_case_design: dict[str, Any]) -> list[ExecutionReviewItem]:
    items = []
    for index, placeholder in enumerate(harness_report.get("unresolved_placeholders", []), start=1):
        items.append(
            ExecutionReviewItem(
                f"REVIEW_PLACEHOLDER_{index:03d}",
                "placeholder_expected_value",
                placeholder.get("related_test_case_id"),
                f"Placeholder remains: {placeholder.get('name')}",
                placeholder.get("suggested_action", "Review generated test expected values."),
                "warning",
            )
        )
    for case in test_case_design.get("test_cases", []):
        for observation in case.get("expected_observations", []):
            expected = observation.get("expected_expression")
            if expected is None or str(expected).startswith("TBD"):
                items.append(
                    ExecutionReviewItem(
                        f"REVIEW_EXPECTED_{len(items) + 1:03d}",
                        "placeholder_expected_value",
                        case.get("test_case_id"),
                        "Expected observation is not finalized.",
                        "Review function specification and replace TBD expected value.",
                        "warning",
                    )
                )
                break
    return items


def _write_test_reports(workspace: Path, report: TestExecutionReport) -> None:
    reports = workspace / "reports"
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
    (reports / "test_execution_report.md").write_text(_render_execution_markdown(report), encoding="utf-8")
    (reports / "unresolved_review_items.md").write_text(_render_review_items(report.unresolved_review_items), encoding="utf-8")


def _build_manifest(workspace: Path, report: TestExecutionReport, build_probe: dict[str, Any], build_workspace: dict[str, Any], completion_report: dict[str, Any] | None) -> EvidenceManifest:
    summary = EvidenceSummary(
        build_probe_status=build_probe.get("function", {}).get("status", "unknown"),
        test_execution_status=report.status,
        total_tests=report.parsed_result.total if report.parsed_result else 0,
        passed_tests=report.parsed_result.passed if report.parsed_result else 0,
        failed_tests=report.parsed_result.failed if report.parsed_result else 0,
        inconclusive_tests=report.parsed_result.inconclusive if report.parsed_result else 0,
        unresolved_review_count=len(report.unresolved_review_items),
        ready_for_review=True,
    )
    source_files = [_evidence_file(workspace, Path(item["workspace_path"]), "source", item.get("file_kind", "source")) for item in build_workspace.get("copied_files", [])]
    generated_files = [_evidence_file(workspace, Path(item["path"]), "generated_source", item.get("file_kind", "generated")) for item in _read_json(workspace / "reports" / "harness_skeleton_report.json").get("generated_files", []) if str(item.get("path", "")).startswith("generated/")]
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


def _write_manifest_and_package(workspace: Path, manifest: EvidenceManifest, report: TestExecutionReport) -> None:
    reports = workspace / "reports"
    manifest_path = reports / "evidence_manifest.json"
    package_path = reports / "evidence_package.md"
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    package_path.write_text(_render_evidence_package(manifest, report), encoding="utf-8")


def _evidence_file(workspace: Path, relative: Path, kind: str, description: str) -> EvidenceFile:
    return EvidenceFile(relative, kind, sha256_file(workspace / relative), True, description)


def _render_execution_markdown(report: TestExecutionReport) -> str:
    lines = ["# Test Execution Report", "", "## Target", f"- Function: {report.function_name}", f"- Status: {report.status}", f"- Executed: {'yes' if report.executed else 'no'}", "", "## Results", "| Test Case | Status | Review Required | Evidence |", "|---|---|---|---|"]
    for case in report.case_results:
        lines.append(f"| {case.test_case_id or ''} | {case.status} | {'yes' if case.review_required else 'no'} | {case.evidence} |")
    return "\n".join(lines) + "\n"


def _render_review_items(items: list[ExecutionReviewItem]) -> str:
    lines = ["# Unresolved Review Items", "", "| Kind | Test Case | Description | Suggested Action |", "|---|---|---|---|"]
    for item in items:
        lines.append(f"| {item.item_kind} | {item.related_test_case_id or ''} | {item.description} | {item.suggested_action} |")
    return "\n".join(lines) + "\n"


def _render_evidence_package(manifest: EvidenceManifest, report: TestExecutionReport) -> str:
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


def _environment_summary() -> dict[str, str]:
    return {"cwd": str(Path.cwd()), "path_set": "yes" if os.environ.get("PATH") else "no"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)
