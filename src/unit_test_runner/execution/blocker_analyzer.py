from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping

from .blocker_models import BlockerAction, ExecutionBlocker, TestExecutionBlockerReport
from .execution_models import ExecutableInfo, TestExecutionReport


_DIAGNOSTIC_LIMIT = 4096
_CURRENT_VALUE_LIMIT = 2048
_RUNNER_EXCERPT_LIMIT = 8192
_CATEGORY_PRIORITY = {
    "build": 0,
    "executable": 1,
    "harness": 2,
    "test_case": 3,
    "test_input": 4,
    "runner": 5,
    "unknown": 6,
}

_BUILD_ACTION = BlockerAction("open_build_probe_report", "ビルド結果を開く")
_EXECUTABLE_ACTION = BlockerAction(
    "choose_or_build_executable",
    "実行ファイルを選択またはビルド",
)
_EXECUTION_REPORT_ACTION = BlockerAction(
    "open_execution_report",
    "テスト実行レポートを開く",
)
_TEST_INPUT_ACTION = BlockerAction(
    "open_test_input_editor",
    "未確定項目を入力",
)
_HARNESS_ACTION = BlockerAction(
    "generate_harness",
    "テストハーネスを生成",
)
_EXECUTION_LOG_ACTION = BlockerAction(
    "open_execution_log",
    "テスト実行ログを開く",
)
_TEST_INPUT_NEXT_STEPS = (
    "値を入力する",
    "項目を確認済みにする",
    "テストハーネスを再生成する",
    "ビルドを実行する",
    "テストを再実行する",
)


@dataclass(frozen=True)
class BlockerAnalysisInput:
    workspace: Path
    run_id: str
    execution_report_path: Path
    execution_report_sha256: str
    report: TestExecutionReport
    test_spec: Mapping[str, Any]
    harness_report: Mapping[str, Any]
    build_probe_report: Mapping[str, Any]
    build_workspace_report: Mapping[str, Any]


def analyze_test_execution_blockers(
    value: BlockerAnalysisInput,
) -> TestExecutionBlockerReport:
    candidates: list[ExecutionBlocker] = []
    build_status = str(
        value.build_probe_report.get("function", {}).get("status") or "unknown"
    )
    if build_status != "succeeded":
        candidates.extend(_build_probe_blockers(value))
    elif value.report.executable is not None and not value.report.executable.exists:
        candidates.append(_missing_executable_blocker(value))
    else:
        candidates.extend(_non_prerequisite_blockers(value))
    if not candidates:
        candidates.append(_unknown_blocker(value))
    blockers = _deduplicate_sort_and_number(candidates)
    primary = _primary_action(blockers)
    return TestExecutionBlockerReport(
        run_id=value.run_id,
        execution_report_path=value.execution_report_path.as_posix(),
        execution_report_sha256=value.execution_report_sha256,
        primary_action=primary,
        blockers=blockers,
    )


def _build_probe_blockers(value: BlockerAnalysisInput) -> list[ExecutionBlocker]:
    result: list[ExecutionBlocker] = []
    diagnostics = value.build_probe_report.get("diagnostics")
    if isinstance(diagnostics, list):
        for index, raw in enumerate(diagnostics):
            if not isinstance(raw, Mapping):
                continue
            if str(raw.get("severity") or "").lower() != "error":
                continue
            summary, truncated = _bounded_text(
                raw.get("message") or "ビルドプローブでエラーが発生しました。",
                _DIAGNOSTIC_LIMIT,
            )
            line_number = raw.get("line_number")
            if not isinstance(line_number, int) or isinstance(line_number, bool) or line_number < 1:
                line_number = None
            result.append(
                ExecutionBlocker(
                    blocker_id="",
                    code=str(raw.get("code") or "build_probe_error"),
                    category="build",
                    severity="error",
                    summary=summary,
                    source_artifact="reports/build_probe_report.json",
                    source_pointer=f"/diagnostics/{index}",
                    related_file=_workspace_relative_path(
                        value.workspace,
                        raw.get("file") or raw.get("related_file"),
                    ),
                    line_number=line_number,
                    recommended_action=_BUILD_ACTION,
                    next_steps=(
                        "ビルドプローブのエラー診断を確認する",
                        "原因を修正してビルドを再実行する",
                        "テストを再実行する",
                    ),
                    truncated=truncated,
                )
            )
    if result:
        return result
    status = str(
        value.build_probe_report.get("function", {}).get("status") or "unknown"
    )
    summary, truncated = _bounded_text(
        f"ビルドプローブが成功していません（status={status}）。",
        _DIAGNOSTIC_LIMIT,
    )
    return [
        ExecutionBlocker(
            blocker_id="",
            code="build_probe_not_successful",
            category="build",
            severity="error",
            summary=summary,
            source_artifact="reports/build_probe_report.json",
            source_pointer="/function/status",
            recommended_action=_BUILD_ACTION,
            next_steps=(
                "ビルド結果を確認する",
                "ビルドプローブを成功させる",
                "テストを再実行する",
            ),
            truncated=truncated,
        )
    ]


def _missing_executable_blocker(value: BlockerAnalysisInput) -> ExecutionBlocker:
    executable = value.report.executable
    if executable is None:
        raise ValueError("Missing executable blocker requires executable metadata.")
    messages = [warning.message for warning in executable.warnings if warning.message]
    summary, summary_truncated = _bounded_text(
        messages[0] if messages else "テスト実行ファイルが見つかりません。",
        _DIAGNOSTIC_LIMIT,
    )
    path_text = _workspace_relative_path(value.workspace, executable.path)
    current_value = path_text
    value_truncated = False
    if current_value is not None:
        current_value, value_truncated = _bounded_text(
            current_value,
            _CURRENT_VALUE_LIMIT,
        )
    return ExecutionBlocker(
        blocker_id="",
        code="executable_not_found",
        category="executable",
        severity="error",
        summary=summary,
        current_value=current_value,
        source_artifact=value.execution_report_path.as_posix(),
        source_pointer="/data/executable/path",
        recommended_action=_EXECUTABLE_ACTION,
        next_steps=(
            "ビルドを成功させるか実行ファイルを指定する",
            "実行ファイルの存在を確認する",
            "テストを再実行する",
        ),
        truncated=summary_truncated or value_truncated,
    )


def _non_prerequisite_blockers(
    value: BlockerAnalysisInput,
) -> list[ExecutionBlocker]:
    if value.report.executed:
        return _runner_blockers(value)
    harness = _harness_blockers(value)
    if harness:
        return harness
    test_input = _test_input_blockers(value)
    if test_input:
        return test_input
    placeholders = _unmapped_placeholder_blockers(value)
    if placeholders and not value.report.policy.allow_placeholder_tests:
        return placeholders
    if not _test_cases(value.test_spec):
        return [_no_executable_cases_blocker()]
    return []


def _test_input_blockers(value: BlockerAnalysisInput) -> list[ExecutionBlocker]:
    # Import lazily: test_spec models import execution.test_result_writer while
    # the execution package is initializing, and test_input_form.service imports
    # test_spec. Keeping this dependency out of module initialization avoids a
    # package-level cycle without duplicating the canonical field rules.
    from unit_test_runner.test_input_form import describe_test_spec_fields
    from unit_test_runner.test_input_form.validation import is_unresolved

    blockers: list[ExecutionBlocker] = []
    has_executable_cases = bool(_test_cases(value.test_spec))
    for field in describe_test_spec_fields(value.test_spec):
        if not field.execution_blocking:
            continue
        if field.case_location == "additional_case_candidates":
            if has_executable_cases:
                continue
        elif field.case_location == "test_cases":
            if value.report.policy.allow_placeholder_tests:
                continue
        else:
            continue
        unresolved_controls = [
            control
            for control in field.controls
            if control.required_for_confirmation and is_unresolved(control.value)
        ]
        if unresolved_controls:
            for control in unresolved_controls:
                current, truncated = _bounded_text(
                    control.value,
                    _CURRENT_VALUE_LIMIT,
                )
                summary, summary_truncated = _bounded_text(
                    f"{field.label} の実行値が未確定です。",
                    _DIAGNOSTIC_LIMIT,
                )
                blockers.append(
                    ExecutionBlocker(
                        blocker_id="",
                        code="unresolved_test_input",
                        category="test_input",
                        severity="error",
                        case_id=field.case_id,
                        item_id=field.item_id,
                        control_name=control.name,
                        summary=summary,
                        current_value=current,
                        source_artifact="reports/test_spec.json",
                        source_pointer=control.json_pointer,
                        recommended_action=_TEST_INPUT_ACTION,
                        next_steps=_TEST_INPUT_NEXT_STEPS,
                        truncated=truncated or summary_truncated,
                    )
                )
            continue
        if field.confirmed:
            continue
        summary_value, truncated = _bounded_text(
            ", ".join(
                f"{control.name}={control.value}"
                for control in field.controls
                if control.required_for_confirmation
            ),
            _CURRENT_VALUE_LIMIT,
        )
        summary, summary_truncated = _bounded_text(
            f"{field.label} は具体値ですが確認済みではありません。",
            _DIAGNOSTIC_LIMIT,
        )
        blockers.append(
            ExecutionBlocker(
                blocker_id="",
                code="unconfirmed_test_input",
                category="test_input",
                severity="error",
                case_id=field.case_id,
                item_id=field.item_id,
                summary=summary,
                current_value=summary_value,
                source_artifact="reports/test_spec.json",
                source_pointer=field.parent_pointer,
                recommended_action=_TEST_INPUT_ACTION,
                next_steps=_TEST_INPUT_NEXT_STEPS,
                truncated=truncated or summary_truncated,
            )
        )
    return blockers


def _harness_blockers(value: BlockerAnalysisInput) -> list[ExecutionBlocker]:
    function = value.harness_report.get("function")
    status = (
        str(function.get("status") or "")
        if isinstance(function, Mapping)
        else ""
    )
    if status and status not in {"generated", "partial"}:
        return [
            ExecutionBlocker(
                blocker_id="",
                code="harness_missing_or_stale",
                category="harness",
                severity="error",
                summary=f"テストハーネスが実行可能な状態ではありません（status={status}）。",
                current_value=status,
                source_artifact="reports/harness_skeleton_report.json",
                source_pointer="/function/status",
                recommended_action=_HARNESS_ACTION,
                next_steps=(
                    "現在のテスト仕様からハーネスを再生成する",
                    "ビルドを実行する",
                    "テストを再実行する",
                ),
            )
        ]
    generated = value.harness_report.get("generated_files")
    if not isinstance(generated, list):
        return []
    for index, item in enumerate(generated):
        if not isinstance(item, Mapping) or item.get("file_kind") != "test_source":
            continue
        relative = _workspace_relative_path(value.workspace, item.get("path"))
        if relative is None:
            continue
        if (value.workspace / relative).is_file():
            continue
        return [
            ExecutionBlocker(
                blocker_id="",
                code="harness_missing_or_stale",
                category="harness",
                severity="error",
                summary="生成済みテストソースが見つかりません。",
                current_value=relative,
                source_artifact="reports/harness_skeleton_report.json",
                source_pointer=f"/generated_files/{index}/path",
                related_file=relative,
                recommended_action=_HARNESS_ACTION,
                next_steps=(
                    "テストハーネスを再生成する",
                    "ビルドを実行する",
                    "テストを再実行する",
                ),
            )
        ]
    return []


def _unmapped_placeholder_blockers(
    value: BlockerAnalysisInput,
) -> list[ExecutionBlocker]:
    placeholders = value.harness_report.get("unresolved_placeholders")
    if not isinstance(placeholders, list):
        return []
    blockers: list[ExecutionBlocker] = []
    for index, placeholder in enumerate(placeholders):
        if not isinstance(placeholder, Mapping):
            continue
        summary, summary_truncated = _bounded_text(
            placeholder.get("reason")
            or f"未確定プレースホルダーが残っています: {placeholder.get('name') or 'unknown'}",
            _DIAGNOSTIC_LIMIT,
        )
        current, value_truncated = _bounded_text(
            placeholder.get("name") or "",
            _CURRENT_VALUE_LIMIT,
        )
        blockers.append(
            ExecutionBlocker(
                blocker_id="",
                code="placeholder_tests_not_allowed",
                category="test_input",
                severity="error",
                case_id=(
                    str(placeholder.get("related_test_case_id"))
                    if placeholder.get("related_test_case_id")
                    else None
                ),
                summary=summary,
                current_value=current,
                source_artifact="reports/harness_skeleton_report.json",
                source_pointer=f"/unresolved_placeholders/{index}",
                recommended_action=_TEST_INPUT_ACTION,
                next_steps=_TEST_INPUT_NEXT_STEPS,
                truncated=summary_truncated or value_truncated,
            )
        )
    return blockers


def _runner_blockers(value: BlockerAnalysisInput) -> list[ExecutionBlocker]:
    source_artifact = _runner_source_artifact(value)
    blockers: list[ExecutionBlocker] = []
    for case in value.report.case_results:
        if case.status != "blocked":
            continue
        summary, truncated = _bounded_text(
            case.evidence or "Runner reported a blocked test case.",
            _DIAGNOSTIC_LIMIT,
        )
        blockers.append(
            ExecutionBlocker(
                blocker_id="",
                code="runner_reported_blocked",
                category="runner",
                severity="error",
                case_id=case.test_case_id,
                summary=summary,
                source_artifact=source_artifact,
                recommended_action=_EXECUTION_LOG_ACTION,
                next_steps=(
                    "実行ログを確認する",
                    "ブロック条件を解消する",
                    "テストを再実行する",
                ),
                truncated=truncated,
            )
        )
    if blockers:
        return blockers
    excerpt, truncated = _runner_log_excerpt(value)
    return [
        ExecutionBlocker(
            blocker_id="",
            code="runner_reported_blocked",
            category="runner",
            severity="error",
            summary="Runnerがテスト実行をブロックしました。",
            log_excerpt=excerpt,
            source_artifact=source_artifact,
            recommended_action=_EXECUTION_LOG_ACTION,
            next_steps=(
                "実行ログを確認する",
                "ブロック条件を解消する",
                "テストを再実行する",
            ),
            truncated=truncated,
        )
    ]


def _runner_source_artifact(value: BlockerAnalysisInput) -> str:
    run_paths = value.report.run_paths
    if run_paths is not None and run_paths.combined_log.is_file():
        relative = _workspace_relative_path(value.workspace, run_paths.combined_log)
        if relative is not None:
            return relative
    return value.execution_report_path.as_posix()


def _runner_log_excerpt(value: BlockerAnalysisInput) -> tuple[str | None, bool]:
    run_paths = value.report.run_paths
    if run_paths is None:
        return None, False
    relative = _workspace_relative_path(value.workspace, run_paths.combined_log)
    if relative is None:
        return None, False
    log_path = (value.workspace / relative).resolve(strict=False)
    if not log_path.is_file():
        return None, False
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as stream:
            text = stream.read(_RUNNER_EXCERPT_LIMIT + 1)
    except OSError:
        return None, False
    truncated = len(text) > _RUNNER_EXCERPT_LIMIT
    excerpt = text[:_RUNNER_EXCERPT_LIMIT]
    return excerpt or None, truncated


def _no_executable_cases_blocker() -> ExecutionBlocker:
    return ExecutionBlocker(
        blocker_id="",
        code="no_executable_test_cases",
        category="test_case",
        severity="error",
        summary="実行可能なテストケースがありません。",
        source_artifact="reports/test_spec.json",
        source_pointer="/test_cases",
        recommended_action=_TEST_INPUT_ACTION,
        next_steps=_TEST_INPUT_NEXT_STEPS,
    )


def _test_cases(test_spec: Mapping[str, Any]) -> list[Any]:
    data = test_spec.get("data")
    source = data if isinstance(data, Mapping) else test_spec
    value = source.get("test_cases") if isinstance(source, Mapping) else None
    return value if isinstance(value, list) else []


def _unknown_blocker(value: BlockerAnalysisInput) -> ExecutionBlocker:
    return ExecutionBlocker(
        blocker_id="",
        code="execution_blocked_unknown",
        category="unknown",
        severity="error",
        summary="テスト実行はブロックされましたが、具体的な直接原因を特定できませんでした。",
        source_artifact=value.execution_report_path.as_posix(),
        recommended_action=_EXECUTION_REPORT_ACTION,
        next_steps=(
            "テスト実行レポートを確認する",
            "関連する警告とログを確認する",
            "原因を解消してテストを再実行する",
        ),
    )


def _bounded_text(value: Any, limit: int) -> tuple[str, bool]:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _workspace_relative_path(workspace: Path, raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    normalized = text.replace("\\", "/")
    windows = PureWindowsPath(text)
    posix = PurePosixPath(normalized)
    path = Path(text)
    if path.is_absolute():
        try:
            return path.resolve(strict=False).relative_to(
                workspace.resolve(strict=False)
            ).as_posix()
        except (OSError, ValueError):
            return None
    if windows.drive or windows.root:
        return None
    if posix.is_absolute() or ".." in posix.parts or not posix.parts:
        return None
    return posix.as_posix()


def _deduplicate_sort_and_number(
    candidates: list[ExecutionBlocker],
) -> tuple[ExecutionBlocker, ...]:
    unique: dict[tuple[str, str, str, str, str, str], ExecutionBlocker] = {}
    for item in candidates:
        key = (
            item.code,
            item.case_id or "",
            item.item_id or "",
            item.control_name or "",
            item.source_artifact,
            item.source_pointer or "",
        )
        unique.setdefault(key, item)
    ordered = sorted(
        unique.values(),
        key=lambda item: (
            _CATEGORY_PRIORITY.get(item.category, 99),
            item.case_id or "",
            item.item_id or "",
            item.control_name or "",
            item.source_pointer or "",
            item.code,
        ),
    )
    return tuple(
        replace(item, blocker_id=f"BLK-{index:03d}")
        for index, item in enumerate(ordered, start=1)
    )


def _primary_action(
    blockers: tuple[ExecutionBlocker, ...],
) -> BlockerAction:
    if not blockers:
        raise ValueError("A blocked report must contain at least one blocker.")
    first = blockers[0].recommended_action
    affected_count = sum(
        1
        for item in blockers
        if item.recommended_action.code == first.code
    )
    return replace(first, affected_count=affected_count)
