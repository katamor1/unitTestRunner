from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from unit_test_runner.contracts import ArtifactKind, RunOutcome
from unit_test_runner.workspace_artifacts import (
    artifact_sha256,
    is_current_review_approved,
    load_public_artifact,
    write_test_run_report,
)

from .execution_models import (
    ExecutionCommandResult,
    ExecutionReviewItem,
    TestCaseExecutionResult,
    TestExecutionPolicy,
    TestExecutionReport,
    TestExecutionWarning,
    TestRunRequest,
    TestResultSummary,
)
from .executable_resolver import resolve_executable
from .execution_runner import build_execution_command, run_test_executable_cases
from .precondition_validator import validate_execution_preconditions
from .run_paths import create_run_paths


def execute_test_run(request: TestRunRequest) -> TestExecutionReport:
    workspace = Path(request.workspace).resolve()
    if not is_current_review_approved(workspace, ArtifactKind.TEST_SPEC):
        raise PermissionError(
            "Current test_spec is not covered by an approved review_record."
        )
    reports = workspace / "reports"
    test_spec_payload = load_public_artifact(
        reports / "test_spec.json",
        ArtifactKind.TEST_SPEC,
    )
    test_case_design = dict(test_spec_payload["data"])
    requested_case_ids = select_test_case_ids(
        test_case_design,
        request.selector_kind,
        list(request.selector_values),
    )
    paths = create_run_paths(workspace, request.run_id)
    harness_report = _read_json(reports / "harness_skeleton_report.json")
    build_probe = load_public_artifact(
        reports / "build_probe_report.json",
        ArtifactKind.BUILD_PROBE_REPORT,
    )
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
    design_results_by_id = {
        item.test_case_id: item
        for item in _case_results_from_design(test_case_design)
        if item.test_case_id
    }
    design_case_results = [
        design_results_by_id[case_id] for case_id in requested_case_ids
    ]
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
    if not design_case_results and precondition_status == "ready":
        warnings.append(
            TestExecutionWarning(
                "no_executable_test_cases",
                "実行可能なテストケースがないため、runnerは起動しません。追加候補と未解決項目を解消してください。",
            )
        )
    elif review_items and not request.allow_placeholder_tests and precondition_status == "ready":
        warnings.append(
            TestExecutionWarning(
                "placeholder_tests_not_allowed",
                "未確定の期待値を含むため、テスト実行をブロックしました。",
            )
        )
    elif precondition_status == "ready":
        executed = True
        command_result, parsed_summary, runner_case_results, raw_status = run_test_executable_cases(
            workspace,
            executable_info,
            requested_case_ids,
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
            status = RunOutcome.BLOCKED.value
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
        warnings=warnings,
        policy=policy,
        schema_version="1.0.0",
        run_paths=paths,
    )
    started_case_ids, completed_case_ids, not_run_case_ids = _case_progress_ids(
        requested_case_ids,
        case_results,
    )
    write_test_run_report(
        workspace,
        paths.run_id,
        test_spec_payload["subject"],
        {
            "run_id": paths.run_id,
            "outcome": _canonical_run_outcome(status),
            "executed": executed,
            "test_spec_sha256": artifact_sha256(reports / "test_spec.json"),
            "requested_case_ids": requested_case_ids,
            "started_case_ids": started_case_ids,
            "completed_case_ids": completed_case_ids,
            "not_run_case_ids": not_run_case_ids,
            "summary": parsed_summary.to_dict(),
            "case_results": [item.to_dict() for item in case_results],
            "warnings": [item.to_dict() for item in warnings],
        },
    )
    return report


def _case_progress_ids(
    requested_case_ids: list[str],
    case_results: list[TestCaseExecutionResult],
) -> tuple[list[str], list[str], list[str]]:
    status_by_id = {
        str(item.test_case_id): str(item.status)
        for item in case_results
        if item.test_case_id
    }
    not_run = [
        case_id
        for case_id in requested_case_ids
        if status_by_id.get(case_id) in {None, "not_run", "not_found_in_output"}
    ]
    started = [case_id for case_id in requested_case_ids if case_id not in not_run]
    completed_statuses = {"passed", "failed", "skipped"}
    completed = [
        case_id
        for case_id in requested_case_ids
        if status_by_id.get(case_id) in completed_statuses
    ]
    return started, completed, not_run


def select_test_case_ids(
    test_spec_data: dict[str, Any],
    selector_kind: str,
    selector_values: list[str],
) -> list[str]:
    cases = test_spec_data.get("test_cases")
    if not isinstance(cases, list):
        raise ValueError("Current test_spec has no test_cases array.")
    ordered_ids: list[str] = []
    cases_by_id: dict[str, dict[str, Any]] = {}
    for raw_case in cases:
        if not isinstance(raw_case, dict):
            raise ValueError("Current test_spec contains an invalid test case.")
        case_id = raw_case.get("test_case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("Every test case must have a non-empty test_case_id.")
        if case_id in cases_by_id:
            raise ValueError(f"Duplicate test_case_id in test_spec: {case_id}")
        cases_by_id[case_id] = raw_case
        ordered_ids.append(case_id)

    def enabled(case: dict[str, Any]) -> bool:
        return case.get("enabled", True) is not False and case.get("disabled") is not True

    if selector_kind == "all":
        if selector_values:
            raise ValueError("The all selector does not accept values.")
        selected = [case_id for case_id in ordered_ids if enabled(cases_by_id[case_id])]
    elif selector_kind == "case_id":
        if not selector_values or any(not value for value in selector_values):
            raise ValueError("At least one non-empty case ID is required.")
        if len(set(selector_values)) != len(selector_values):
            raise ValueError("Duplicate case IDs are not allowed.")
        missing = [value for value in selector_values if value not in cases_by_id]
        disabled = [
            value
            for value in selector_values
            if value in cases_by_id and not enabled(cases_by_id[value])
        ]
        if missing:
            raise ValueError("Unknown test case IDs: " + ", ".join(missing))
        if disabled:
            raise ValueError("Disabled test case IDs: " + ", ".join(disabled))
        selected = list(selector_values)
    elif selector_kind == "tag":
        if len(selector_values) != 1 or not selector_values[0]:
            raise ValueError("A single non-empty tag is required.")
        tag = selector_values[0]
        matching = [
            case_id
            for case_id in ordered_ids
            if tag in list(cases_by_id[case_id].get("tags") or [])
        ]
        selected = [case_id for case_id in matching if enabled(cases_by_id[case_id])]
        if matching and not selected:
            raise ValueError(f"All test cases for tag {tag!r} are disabled.")
    else:
        raise ValueError(f"Unknown test selector: {selector_kind}")
    if not selected:
        raise ValueError("The test selector matched no enabled cases.")
    return selected


def validate_test_run_preflight(
    workspace: Path | str,
    executable: Path | str | None = None,
    *,
    allow_placeholder_tests: bool = True,
) -> tuple[list[TestExecutionWarning], list[ExecutionReviewItem]]:
    workspace = Path(workspace).resolve()
    reports = workspace / "reports"
    test_case_design = _read_canonical_test_spec(reports)
    harness_report = _read_json(reports / "harness_skeleton_report.json")
    build_probe = load_public_artifact(
        reports / "build_probe_report.json",
        ArtifactKind.BUILD_PROBE_REPORT,
    )
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
    review_items.extend(placeholder_items)
    if placeholder_items and not allow_placeholder_tests:
        warnings.append(
            TestExecutionWarning(
                "placeholder_tests_not_allowed",
                "未確定の期待値を含むため、テスト実行はブロックされます。",
            )
        )
    return warnings, review_items


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


def _canonical_run_outcome(status: str) -> str:
    if status == "timeout":
        return RunOutcome.TIMED_OUT.value
    if status == "not_run":
        return RunOutcome.BLOCKED.value
    if status == "inconclusive":
        return RunOutcome.BLOCKED.value
    try:
        return RunOutcome(status).value
    except ValueError:
        return RunOutcome.ERROR.value


def _case_results_from_design(test_case_design: dict[str, Any]) -> list[TestCaseExecutionResult]:
    results = []
    for case in test_case_design.get("test_cases", []):
        coverage = [link.get("coverage_id", "") for link in case.get("coverage_links", []) if link.get("coverage_id")]
        review = any(
            _has_active_review(case.get(field) or [])
            for field in (
                "input_assignments",
                "state_setups",
                "stub_setups",
                "dependency_overrides",
                "expected_observations",
            )
        )
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
    items.extend(_canonical_test_spec_review_items(test_case_design))
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
    return _unique_review_items(items)


def _canonical_test_spec_review_items(
    test_spec: dict[str, Any],
) -> list[ExecutionReviewItem]:
    items: list[ExecutionReviewItem] = []
    represented_ids: set[str] = set()
    represented_cases: set[str] = set()
    executable_case_ids = {
        str(case.get("test_case_id") or "")
        for case in test_spec.get("test_cases") or []
        if isinstance(case, dict) and str(case.get("test_case_id") or "").strip()
    }
    for index, unresolved in enumerate(test_spec.get("unresolved_items") or [], start=1):
        if not isinstance(unresolved, dict):
            continue
        if unresolved.get("blocking") is False:
            continue
        item_id = str(unresolved.get("item_id") or f"REVIEW_UNRESOLVED_{index:03d}")
        related_ids = [
            str(value)
            for value in unresolved.get("related_test_case_ids") or []
            if str(value)
        ]
        if related_ids and not (set(related_ids) & executable_case_ids):
            continue
        represented_ids.add(item_id)
        represented_cases.update(related_ids)
        items.append(
            ExecutionReviewItem(
                item_id,
                str(unresolved.get("item_kind") or "test_spec_unresolved_item"),
                related_ids[0] if related_ids else None,
                str(
                    unresolved.get("description")
                    or unresolved.get("message")
                    or "テスト仕様に未解決項目が残っています。"
                ),
                str(
                    unresolved.get("suggested_action")
                    or "未解決項目を解消し、正本のテスト仕様を更新してください。"
                ),
                "warning",
            )
        )

    for case in test_spec.get("test_cases") or []:
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("test_case_id") or "") or None
        execution_values = [
            case.get(field) or []
            for field in (
                "input_assignments",
                "state_setups",
                "stub_setups",
                "dependency_overrides",
                "expected_observations",
            )
        ]
        if not any(_has_active_review(value) for value in execution_values):
            continue
        references: list[str] = []
        for value in execution_values:
            references.extend(_active_review_references(value))
        references = list(dict.fromkeys(references)) or [
            f"REVIEW_CASE_{len(items) + 1:03d}"
        ]
        for reference in references:
            if reference in represented_ids:
                continue
            represented_ids.add(reference)
            if case_id:
                represented_cases.add(case_id)
            items.append(
                ExecutionReviewItem(
                    reference,
                    "review_decision_required",
                    case_id,
                    "実行ケースに未確認の入力または期待値が残っています。",
                    "TestSpec入力を確定し、現在のSHAをreview-setで承認してください。",
                    "warning",
                )
            )

    if not test_spec.get("test_cases") and not items:
        items.append(
            ExecutionReviewItem(
                "REVIEW_NO_EXECUTABLE_CASES_001",
                "no_executable_test_cases",
                None,
                "実行可能なテストケースがありません。",
                "値と期待結果が確定したテストケースを正本へ追加してください。",
                "warning",
            )
        )
    return items


def _active_review_references(value: Any) -> list[str]:
    references: list[str] = []
    if isinstance(value, dict):
        if value.get("review_required") is True:
            for key in ("review_item_id", "review_item_ids"):
                child = value.get(key)
                values = child if isinstance(child, list) else ([] if child is None else [child])
                references.extend(str(item) for item in values if str(item))
        for child in value.values():
            references.extend(_active_review_references(child))
    elif isinstance(value, list):
        for child in value:
            references.extend(_active_review_references(child))
    return list(dict.fromkeys(references))


def _has_active_review(value: Any) -> bool:
    if isinstance(value, dict):
        return value.get("review_required") is True or any(
            _has_active_review(child) for child in value.values()
        )
    if isinstance(value, list):
        return any(_has_active_review(child) for child in value)
    return False


def _unique_review_items(items: list[ExecutionReviewItem]) -> list[ExecutionReviewItem]:
    unique: list[ExecutionReviewItem] = []
    seen: set[str] = set()
    for item in items:
        if item.item_id in seen:
            continue
        seen.add(item.item_id)
        unique.append(item)
    return unique


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_canonical_test_spec(reports: Path) -> dict[str, Any]:
    from unit_test_runner.test_spec import (
        build_current_artifact_context,
        load_test_spec,
        test_spec_consumer_payload,
        validate_test_spec,
    )

    path = reports / "test_spec.json"
    spec = load_test_spec(path)
    context = build_current_artifact_context(reports.parent, spec)
    violations = validate_test_spec(spec, current_context=context)
    if violations:
        detail = "; ".join(
            f"{item.code} at {item.json_path}: {item.message}"
            for item in violations
        )
        raise ValueError(f"Stale canonical test_spec: {detail}")
    return test_spec_consumer_payload(spec)


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)
