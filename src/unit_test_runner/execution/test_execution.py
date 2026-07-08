from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .execution_models import (
    EvidenceManifest,
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
from .execution_runner import build_execution_command, run_test_executable
from .precondition_validator import validate_execution_preconditions
from .test_result_writer import write_test_execution_reports


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
    design_case_results = _case_results_from_design(test_case_design)
    case_results = list(design_case_results)
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
            if parsed_summary.total == 0 and design_case_results:
                warnings.append(
                    TestExecutionWarning(
                        "runner_output_missing",
                        "runner出力からテストケース結果を取得できなかったため、テストケース設計から生成済みケースを表示します。logs/test_execution.log を確認してください。",
                    )
                )
                case_results = _case_results_without_runner_output(design_case_results, status)
                parsed_summary = TestResultSummary(
                    total=len(case_results),
                    passed=0,
                    failed=0,
                    skipped=0,
                    inconclusive=len(case_results),
                    assertion_failures=0,
                    parser_confidence="low",
                )
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
                evidence="テストは未実行です。" if review else "",
            )
        )
    return results


def _case_results_without_runner_output(design_case_results: list[TestCaseExecutionResult], execution_status: str) -> list[TestCaseExecutionResult]:
    results: list[TestCaseExecutionResult] = []
    evidence = "runner出力からケース結果を取得できませんでした。logs/test_execution.log を確認してください。"
    if execution_status == "failed":
        evidence = "実行バイナリは失敗しましたが、runner出力からケース結果を取得できませんでした。logs/test_execution.log を確認してください。"
    for case in design_case_results:
        results.append(
            TestCaseExecutionResult(
                test_case_id=case.test_case_id,
                generated_function_name=case.generated_function_name,
                status="inconclusive",
                exit_related=case.exit_related,
                related_coverage_ids=list(case.related_coverage_ids),
                review_required=True,
                evidence=evidence,
                warnings=[TestExecutionWarning("runner_output_missing", evidence, related_test_case_id=case.test_case_id)],
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
                f"プレースホルダが残っています: {placeholder.get('name')}",
                placeholder.get("suggested_action", "生成テストの期待値を確認してください。"),
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
                        "期待値の確認が未完了です。",
                        "関数仕様を確認し、TBD の期待値を置き換えてください。",
                        "warning",
                    )
                )
                break
    return items


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)
