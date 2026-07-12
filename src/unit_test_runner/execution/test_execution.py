from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unit_test_runner.contracts import ArtifactKind, RunOutcome
from unit_test_runner.harness.c90_writer import sha256_file

from .execution_models import (
    EvidenceManifest,
    ExecutionCommandResult,
    ExecutionReviewItem,
    TestCaseExecutionResult,
    TestExecutionPolicy,
    TestExecutionReport,
    TestExecutionWarning,
    TestRunRequest,
    TestResultSummary,
)
from .evidence_manifest import (
    build_evidence_manifest,
    build_evidence_manifest_from_run,
    write_evidence_package,
)
from .evidence_paths import EvidencePaths, create_evidence_paths
from .executable_resolver import resolve_executable
from .execution_runner import build_execution_command, run_test_executable, run_test_executable_cases
from .precondition_validator import validate_execution_preconditions
from .report_loader import load_execution_run
from .run_paths import create_run_paths
from .test_result_writer import (
    build_artifact_payload,
    current_producer_commit,
    write_test_execution_reports,
    write_validated_artifact,
)


def execute_test_run(request: TestRunRequest) -> TestExecutionReport:
    workspace = Path(request.workspace).resolve()
    paths = create_run_paths(workspace, request.run_id)
    reports = workspace / "reports"
    test_case_design = _read_json(reports / "test_case_design.json")
    harness_report = _read_json(reports / "harness_skeleton_report.json")
    build_probe = _read_json(reports / "build_probe_report.json")
    build_workspace = _read_json(reports / "build_workspace_report.json")
    policy = TestExecutionPolicy(
        run_tests=True,
        dry_run=False,
        timeout_seconds=request.timeout_seconds,
        allow_placeholder_tests=request.allow_placeholder_tests,
        treat_placeholder_as_inconclusive=True,
    )
    function_name = (
        test_case_design.get("function", {}).get("name")
        or build_workspace.get("function", {}).get("name")
        or "unknown_function"
    )
    source_path = _workspace_relative_source_path(workspace, build_workspace)
    executable_info = resolve_executable(workspace, request.executable, build_probe)
    command = build_execution_command(
        workspace,
        executable_info,
        timeout_seconds=request.timeout_seconds,
        dry_run=False,
    )
    command.working_directory = Path(".")
    review_items = _placeholder_review_items(harness_report, test_case_design)
    warnings: list[TestExecutionWarning] = []
    command_result: ExecutionCommandResult | None = None
    parsed_summary = TestResultSummary()
    design_case_results = _case_results_from_design(test_case_design)
    case_results = list(design_case_results)
    status = RunOutcome.BLOCKED.value
    executed = False
    precondition_status, precondition_warnings, precondition_review_items = validate_execution_preconditions(
        build_probe,
        executable_info,
        policy,
    )
    warnings.extend(precondition_warnings)
    review_items.extend(precondition_review_items)
    if review_items and not request.allow_placeholder_tests and precondition_status == "ready":
        warnings.append(
            TestExecutionWarning(
                "placeholder_tests_not_allowed",
                "未確定の期待値を含むため、テスト実行をブロックしました。",
            )
        )
    elif precondition_status == "ready":
        executed = True
        test_case_ids = [
            case.test_case_id for case in design_case_results if case.test_case_id
        ]
        if test_case_ids:
            command_result, parsed_summary, runner_case_results, raw_status = run_test_executable_cases(
                workspace,
                executable_info,
                test_case_ids,
                request.timeout_seconds,
                run_paths=paths,
            )
        else:
            command_result, parsed_summary, runner_case_results, raw_status = run_test_executable(
                workspace,
                executable_info,
                request.timeout_seconds,
                run_paths=paths,
            )
        status = _canonical_run_outcome(raw_status)
        if parsed_summary.total == 0 and design_case_results:
            warnings.append(
                TestExecutionWarning(
                    "runner_output_missing",
                    "runner出力からテストケース結果を取得できなかったため、テストケース設計から生成済みケースを表示します。logs/test_execution.log を確認してください。",
                )
            )
            case_results = _case_results_without_runner_output(design_case_results, raw_status)
            parsed_summary = _summary_from_case_results(case_results, parser_confidence="low")
        else:
            case_results = _merge_runner_case_results_with_design(
                design_case_results,
                runner_case_results,
                raw_status,
            )
            parsed_summary = _summary_from_case_results(
                case_results,
                assertion_failures=parsed_summary.assertion_failures,
                parser_confidence=parsed_summary.parser_confidence,
            )
            status = _canonical_run_outcome(_status_from_summary(parsed_summary, raw_status))
    if review_items and executed and policy.treat_placeholder_as_inconclusive:
        if status == RunOutcome.PASSED.value:
            status = RunOutcome.INCONCLUSIVE.value
        for case in case_results:
            case.review_required = True
            if case.status == "passed":
                case.status = "inconclusive"
        parsed_summary = _summary_from_case_results(
            case_results,
            assertion_failures=parsed_summary.assertion_failures,
            parser_confidence=parsed_summary.parser_confidence,
        )
    if not executed:
        parsed_summary = _summary_from_case_results(
            case_results,
            parser_confidence="low",
        )
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
        schema_version="1.0.0",
        run_paths=paths,
    )
    subject = _execution_subject(workspace, source_path, function_name)
    producer_commit = current_producer_commit()
    write_test_execution_reports(
        paths,
        report,
        subject=subject,
        producer_commit=producer_commit,
    )
    execution_hash = sha256_file(paths.execution_report)
    if execution_hash is None:
        raise ValueError("Execution report was not published.")
    pointer = build_artifact_payload(
        ArtifactKind.LATEST_RUN_POINTER,
        {
            "run_id": paths.run_id,
            "execution_report": {
                "artifact_kind": ArtifactKind.TEST_EXECUTION_REPORT.value,
                "path": paths.execution_report.relative_to(workspace).as_posix(),
                "sha256": execution_hash,
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        subject=subject,
        producer_commit=producer_commit,
    )
    write_validated_artifact(
        workspace / "reports" / "latest_run.json",
        ArtifactKind.LATEST_RUN_POINTER,
        pointer,
        atomic=True,
    )
    return report


def validate_test_run_preflight(
    workspace: Path | str,
    executable: Path | str | None = None,
    *,
    allow_placeholder_tests: bool = True,
) -> tuple[list[TestExecutionWarning], list[ExecutionReviewItem]]:
    workspace = Path(workspace).resolve()
    reports = workspace / "reports"
    test_case_design = _read_json(reports / "test_case_design.json")
    harness_report = _read_json(reports / "harness_skeleton_report.json")
    build_probe = _read_json(reports / "build_probe_report.json")
    build_workspace = _read_json(reports / "build_workspace_report.json")
    _workspace_relative_source_path(workspace, build_workspace)
    executable_info = resolve_executable(workspace, executable, build_probe)
    if executable is not None and not executable_info.exists:
        message = executable_info.warnings[0].message if executable_info.warnings else "Explicit executable does not exist."
        raise ValueError(message)
    policy = TestExecutionPolicy(
        run_tests=True,
        dry_run=False,
        allow_placeholder_tests=allow_placeholder_tests,
    )
    status, warnings, review_items = validate_execution_preconditions(
        build_probe,
        executable_info,
        policy,
    )
    placeholder_items = _placeholder_review_items(harness_report, test_case_design)
    if placeholder_items and not allow_placeholder_tests:
        warnings.append(
            TestExecutionWarning(
                "placeholder_tests_not_allowed",
                "未確定の期待値を含むため、テスト実行はブロックされます。",
            )
        )
        review_items.extend(placeholder_items)
    return warnings, review_items


def prepare_evidence_from_existing_run(
    workspace: Path,
    run_id: str | None = None,
) -> tuple[EvidencePaths, TestExecutionReport, EvidenceManifest]:
    workspace = Path(workspace).resolve()
    loaded_run = load_execution_run(workspace, run_id)
    paths = create_evidence_paths(workspace, loaded_run.run_id)
    try:
        producer_commit = current_producer_commit()
        manifest = build_evidence_manifest_from_run(
            workspace,
            loaded_run,
            paths,
            producer_commit=producer_commit,
        )
        manifest.evidence_paths = paths
        manifest_hash = sha256_file(paths.evidence_manifest)
        if manifest_hash is None:
            raise ValueError("Evidence manifest was not published.")
        pointer = build_artifact_payload(
            ArtifactKind.LATEST_EVIDENCE_POINTER,
            {
                "evidence_id": paths.evidence_id,
                "source_run_id": loaded_run.run_id,
                "evidence_manifest": {
                    "artifact_kind": ArtifactKind.EVIDENCE_MANIFEST.value,
                    "path": paths.evidence_manifest.relative_to(workspace).as_posix(),
                    "sha256": manifest_hash,
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            subject=loaded_run.payload["subject"],
            producer_commit=producer_commit,
        )
        write_validated_artifact(
            workspace / "reports" / "latest_evidence.json",
            ArtifactKind.LATEST_EVIDENCE_POINTER,
            pointer,
            atomic=True,
        )
    except Exception:
        shutil.rmtree(paths.root, ignore_errors=True)
        raise
    return paths, loaded_run.report, manifest


def _workspace_relative_source_path(
    workspace: Path,
    build_workspace: dict[str, Any],
) -> Path:
    raw = Path(build_workspace.get("source", {}).get("path") or "")
    absolute = raw if raw.is_absolute() else workspace / raw
    try:
        relative = absolute.resolve().relative_to(workspace)
    except ValueError:
        relative = _mapped_workspace_source(workspace, absolute, build_workspace)
        absolute = workspace / relative
    if not absolute.is_file():
        raise ValueError(f"Execution source file does not exist: {absolute}")
    return relative


def _mapped_workspace_source(
    workspace: Path,
    source: Path,
    build_workspace: dict[str, Any],
) -> Path:
    resolved_source = source.resolve()
    for item in build_workspace.get("copied_files", []):
        original = item.get("source_path")
        mapped = item.get("workspace_path")
        if not original or not mapped:
            continue
        if Path(original).resolve() != resolved_source:
            continue
        candidate = (workspace / str(mapped)).resolve()
        try:
            return candidate.relative_to(workspace)
        except ValueError as error:
            raise ValueError(
                f"Mapped execution source path escapes workspace: {mapped}"
            ) from error
    raise ValueError(f"Execution source path is outside workspace: {source}")


def _execution_subject(
    workspace: Path,
    source_path: Path,
    function_name: str,
) -> dict[str, str]:
    source_hash = sha256_file(workspace / source_path)
    if source_hash is None:
        raise ValueError(f"Execution source file does not exist: {source_path}")
    identity_seed = f"{source_path.as_posix()}\0{function_name}".encode("utf-8")
    suffix = hashlib.sha256(identity_seed).hexdigest()[:12]
    slug = re.sub(r"[^a-z0-9]+", "_", function_name.lower()).strip("_")
    return {
        "function_id": f"fn_{slug or 'function'}_{suffix}",
        "source_path": source_path.as_posix(),
        "source_sha256": source_hash,
    }


def _canonical_run_outcome(status: str) -> str:
    if status == "timeout":
        return RunOutcome.TIMED_OUT.value
    if status == "not_run":
        return RunOutcome.INCONCLUSIVE.value
    try:
        return RunOutcome(status).value
    except ValueError:
        return RunOutcome.ERROR.value


def prepare_test_execution_evidence(
    workspace: Path | str,
    executable: Path | str | None = None,
    run_tests: bool = False,
    dry_run: bool = True,
    timeout_seconds: int = 60,
    allow_placeholder_tests: bool = True,
    treat_placeholder_as_inconclusive: bool = True,
    run_id: str | None = None,
) -> tuple[TestExecutionReport, EvidenceManifest]:
    workspace = Path(workspace).resolve()
    if run_tests and not dry_run:
        report = execute_test_run(
            TestRunRequest(
                workspace=workspace,
                executable=Path(executable) if executable is not None else None,
                timeout_seconds=timeout_seconds,
                allow_placeholder_tests=allow_placeholder_tests,
                run_id=run_id,
            )
        )
        if report.run_paths is None:
            raise ValueError("Execution run paths were not preserved.")
        evidence_paths, loaded_report, manifest = prepare_evidence_from_existing_run(
            workspace,
            run_id=report.run_paths.run_id,
        )
        loaded_report.run_paths = report.run_paths
        manifest.evidence_paths = evidence_paths
        return loaded_report, manifest
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
            test_case_ids = [case.test_case_id for case in design_case_results if case.test_case_id]
            if test_case_ids:
                command_result, parsed_summary, runner_case_results, status = run_test_executable_cases(workspace, executable_info, test_case_ids, timeout_seconds)
            else:
                command_result, parsed_summary, runner_case_results, status = run_test_executable(workspace, executable_info, timeout_seconds)
            if parsed_summary.total == 0 and design_case_results:
                warnings.append(
                    TestExecutionWarning(
                        "runner_output_missing",
                        "runner出力からテストケース結果を取得できなかったため、テストケース設計から生成済みケースを表示します。logs/test_execution.log を確認してください。",
                    )
                )
                case_results = _case_results_without_runner_output(design_case_results, status)
                parsed_summary = _summary_from_case_results(case_results, parser_confidence="low")
            else:
                case_results = _merge_runner_case_results_with_design(design_case_results, runner_case_results, status)
                parsed_summary = _summary_from_case_results(case_results, assertion_failures=parsed_summary.assertion_failures, parser_confidence=parsed_summary.parser_confidence)
                if parsed_summary.not_run > 0:
                    warnings.append(
                        TestExecutionWarning(
                            "runner_cases_not_reached",
                            f"テストケース設計は {len(design_case_results)} 件ですが、runner出力で開始されたケースは {parsed_summary.started} 件です。未到達ケースを not_run として記録しました。",
                        )
                    )
                status = _status_from_summary(parsed_summary, status)
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
        parsed_summary = _summary_from_case_results(case_results, assertion_failures=parsed_summary.assertion_failures, parser_confidence=parsed_summary.parser_confidence)
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


def _merge_runner_case_results_with_design(
    design_case_results: list[TestCaseExecutionResult],
    runner_case_results: list[TestCaseExecutionResult],
    execution_status: str,
) -> list[TestCaseExecutionResult]:
    runner_by_id = {case.test_case_id: case for case in runner_case_results if case.test_case_id}
    merged: list[TestCaseExecutionResult] = []
    for design_case in design_case_results:
        if design_case.test_case_id in runner_by_id:
            observed = runner_by_id[design_case.test_case_id]
            observed.related_coverage_ids = observed.related_coverage_ids or list(design_case.related_coverage_ids)
            observed.review_required = observed.review_required or design_case.review_required
            merged.append(observed)
            continue
        evidence = "runner出力にこのテストケースの開始行がないため、未実行として記録しました。"
        warnings = [TestExecutionWarning("runner_case_not_reached", evidence, related_test_case_id=design_case.test_case_id)]
        if execution_status in {"failed", "timeout"} and runner_case_results:
            evidence = "先行ケースの異常終了または実行中断により、このテストケースへ到達していません。logs/test_execution.log を確認してください。"
            warnings = [TestExecutionWarning("runner_case_not_reached_after_failure", evidence, related_test_case_id=design_case.test_case_id)]
        merged.append(
            TestCaseExecutionResult(
                test_case_id=design_case.test_case_id,
                generated_function_name=design_case.generated_function_name,
                status="not_run",
                exit_related=False,
                related_coverage_ids=list(design_case.related_coverage_ids),
                review_required=design_case.review_required,
                evidence=evidence,
                warnings=warnings,
            )
        )
    design_ids = {case.test_case_id for case in design_case_results}
    for runner_case in runner_case_results:
        if runner_case.test_case_id not in design_ids:
            merged.append(runner_case)
    return merged


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


def _summary_from_case_results(
    case_results: list[TestCaseExecutionResult],
    assertion_failures: int = 0,
    parser_confidence: str = "medium",
) -> TestResultSummary:
    passed = len([case for case in case_results if case.status == "passed"])
    failed = len([case for case in case_results if case.status == "failed"])
    skipped = len([case for case in case_results if case.status == "skipped"])
    inconclusive = len([case for case in case_results if case.status in {"inconclusive", "not_found_in_output"}])
    crashed = len([case for case in case_results if case.status in {"crashed", "timeout"}])
    not_run = len([case for case in case_results if case.status == "not_run"])
    started = len([case for case in case_results if case.status not in {"not_run", "not_found_in_output"}])
    completed = passed + failed + skipped + inconclusive
    if crashed or not_run:
        parser_confidence = "low"
    return TestResultSummary(len(case_results), passed, failed, skipped, inconclusive, assertion_failures, parser_confidence, crashed, not_run, started, completed)


def _status_from_summary(summary: TestResultSummary, current_status: str) -> str:
    if current_status in {"timeout", "timed_out"}:
        return current_status
    if summary.crashed > 0 or summary.failed > 0 or current_status == "failed":
        return "failed"
    if summary.not_run > 0 or summary.inconclusive > 0:
        return "inconclusive"
    if summary.total > 0 and summary.passed == summary.total:
        return "passed"
    return current_status


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
