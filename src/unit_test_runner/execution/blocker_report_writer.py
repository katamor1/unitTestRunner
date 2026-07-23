from __future__ import annotations

import html
import os
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from unit_test_runner.contracts import ArtifactKind

from .blocker_models import (
    BlockerPublicationDiagnostic,
    BlockerPublicationResult,
    TestExecutionBlockerReport,
)
from .run_paths import RunPaths
from .test_result_writer import build_artifact_payload, write_validated_artifact


_LATEST_JSON = "test_execution_blockers.json"
_LATEST_MARKDOWN = "test_execution_blockers.md"


def render_test_execution_blockers_markdown(
    report: TestExecutionBlockerReport,
) -> str:
    lines = [
        "# テスト実行ブロック項目",
        "",
        "## 状態",
        "- 実行状態: BLOCKED",
        f"- 実行ID: `{_md_code(report.run_id)}`",
        f"- ブロック項目: {report.blocker_count}件",
        "",
        "## 最初に行う操作",
        f"- {_md(report.primary_action.label)}（{report.primary_action.affected_count}件）",
    ]
    current_case: str | None = None
    for blocker in report.blockers:
        case_label = blocker.case_id or "全体"
        if case_label != current_case:
            lines.extend(["", f"## {_md(case_label)}"])
            current_case = case_label
        lines.extend(
            [
                "",
                f"### {_md(blocker.summary)}",
                f"- ブロッカーID: `{_md_code(blocker.blocker_id)}`",
                f"- 種別: `{_md_code(blocker.code)}`",
                f"- 原因元: `{_md_code(blocker.source_artifact)}`",
            ]
        )
        if blocker.current_value is not None:
            lines.append(f"- 現在値: `{_md_code(blocker.current_value)}`")
        if blocker.source_pointer is not None:
            lines.append(f"- 位置: `{_md_code(blocker.source_pointer)}`")
        if blocker.related_file is not None:
            location = _md_code(blocker.related_file)
            if blocker.line_number is not None:
                location += f":{blocker.line_number}"
            lines.append(f"- 関連ファイル: `{location}`")
        if blocker.log_excerpt is not None:
            lines.append("- ログ抜粋:")
            excerpt_lines = blocker.log_excerpt.splitlines() or [""]
            lines.extend(f"    {html.escape(line, quote=False)}" for line in excerpt_lines)
        if blocker.truncated:
            lines.append("- 注記: 表示内容の一部を上限に合わせて省略しています。")
        lines.append(f"- 推奨操作: {_md(blocker.recommended_action.label)}")
        lines.append("- その後:")
        lines.extend(
            f"  {index}. {_md(step)}"
            for index, step in enumerate(blocker.next_steps, start=1)
        )
    return "\n".join(lines) + "\n"


def publish_test_execution_blocker_report(
    workspace: Path,
    paths: RunPaths,
    report: TestExecutionBlockerReport,
    *,
    subject: dict[str, str],
    producer_commit: str,
) -> BlockerPublicationResult:
    workspace = Path(workspace).resolve()
    diagnostics: list[BlockerPublicationDiagnostic] = []
    run_json: Path | None = None
    run_markdown: Path | None = None
    latest_json: Path | None = None
    latest_markdown: Path | None = None
    try:
        _validate_history_paths(workspace, paths, report)
        payload = build_artifact_payload(
            ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT,
            report.to_data(),
            subject=subject,
            producer_commit=producer_commit,
        )
        write_validated_artifact(
            paths.blocker_report_json,
            ArtifactKind.TEST_EXECUTION_BLOCKER_REPORT,
            payload,
            atomic=True,
        )
        run_json = paths.blocker_report_json
        _atomic_write_text(
            paths.blocker_report_markdown,
            render_test_execution_blockers_markdown(report),
        )
        run_markdown = paths.blocker_report_markdown
    except Exception as error:  # explanatory evidence must not replace outcome
        diagnostics.append(_diagnostic("blocker_report_write_failed", error))
        diagnostics.extend(clear_latest_test_execution_blockers(workspace).diagnostics)
        return BlockerPublicationResult(
            report=report,
            run_json=run_json,
            run_markdown=run_markdown,
            diagnostics=tuple(diagnostics),
        )

    try:
        latest_json_path, latest_markdown_path = _safe_latest_paths(
            workspace, create=True
        )
        _atomic_copy(run_json, latest_json_path)
        _atomic_copy(run_markdown, latest_markdown_path)
        latest_json = latest_json_path
        latest_markdown = latest_markdown_path
    except Exception as error:  # history remains authoritative
        diagnostics.append(_diagnostic("blocker_latest_sync_failed", error))
        diagnostics.extend(clear_latest_test_execution_blockers(workspace).diagnostics)

    return BlockerPublicationResult(
        report=report,
        run_json=run_json,
        run_markdown=run_markdown,
        latest_json=latest_json,
        latest_markdown=latest_markdown,
        diagnostics=tuple(diagnostics),
    )


def clear_latest_test_execution_blockers(
    workspace: Path,
) -> BlockerPublicationResult:
    workspace = Path(workspace).resolve()
    reports = workspace / "reports"
    if not os.path.lexists(reports):
        return BlockerPublicationResult()
    try:
        resolved_reports = _safe_reports_directory(workspace, create=False)
    except Exception as error:
        return BlockerPublicationResult(
            diagnostics=(
                _diagnostic("blocker_latest_cleanup_failed", error),
            )
        )
    diagnostics: list[BlockerPublicationDiagnostic] = []
    for path in (
        resolved_reports / _LATEST_JSON,
        resolved_reports / _LATEST_MARKDOWN,
    ):
        try:
            _remove_if_file(path)
        except Exception as error:
            diagnostics.append(_diagnostic("blocker_latest_cleanup_failed", error))
    return BlockerPublicationResult(diagnostics=tuple(diagnostics))


def _validate_history_paths(
    workspace: Path,
    paths: RunPaths,
    report: TestExecutionBlockerReport,
) -> None:
    if paths.run_id != report.run_id:
        raise ValueError(
            f"Blocker report run ID mismatch: {report.run_id!r} != {paths.run_id!r}."
        )
    expected_root = (workspace / "runs" / paths.run_id).resolve(strict=False)
    if paths.root.resolve(strict=False) != expected_root:
        raise ValueError("Blocker history root does not match the workspace run path.")
    expected = {
        paths.blocker_report_json: expected_root / "test_execution_blockers.json",
        paths.blocker_report_markdown: expected_root / "test_execution_blockers.md",
    }
    for actual, required in expected.items():
        if actual.resolve(strict=False) != required.resolve(strict=False):
            raise ValueError(f"Blocker history path escapes its run directory: {actual}")
        if os.path.lexists(actual):
            raise FileExistsError(f"Blocker history file already exists: {actual}")
        if _is_link(actual.parent) or not actual.parent.is_dir():
            raise ValueError(f"Blocker history parent is not a safe directory: {actual.parent}")


def _safe_latest_paths(
    workspace: Path,
    *,
    create: bool,
) -> tuple[Path, Path]:
    resolved = _safe_reports_directory(workspace, create=create)
    latest_json = resolved / _LATEST_JSON
    latest_markdown = resolved / _LATEST_MARKDOWN
    for path in (latest_json, latest_markdown):
        if os.path.lexists(path) and (_is_link(path) or not path.is_file()):
            raise ValueError(f"Latest blocker view is not a regular file: {path}")
    return latest_json, latest_markdown


def _safe_reports_directory(workspace: Path, *, create: bool) -> Path:
    reports = workspace / "reports"
    if os.path.lexists(reports):
        if _is_link(reports):
            raise ValueError(
                f"Latest blocker reports directory must not be a link: {reports}"
            )
        if not reports.is_dir():
            raise NotADirectoryError(
                f"Latest blocker reports path is not a directory: {reports}"
            )
    elif create:
        reports.mkdir(parents=True, exist_ok=False)
    else:
        raise FileNotFoundError(
            f"Latest blocker reports directory does not exist: {reports}"
        )
    resolved = reports.resolve(strict=False)
    try:
        resolved.relative_to(workspace)
    except ValueError as error:
        raise ValueError(
            f"Latest blocker reports directory escapes workspace: {resolved}"
        ) from error
    return resolved


def _atomic_write_text(path: Path, value: str) -> None:
    if os.path.lexists(path):
        raise FileExistsError(f"Immutable blocker view already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            temporary.unlink()


def _atomic_copy(source: Path, destination: Path) -> None:
    if not source.is_file() or _is_link(source):
        raise ValueError(f"Blocker history source is not a safe regular file: {source}")
    if os.path.lexists(destination) and (_is_link(destination) or not destination.is_file()):
        raise ValueError(f"Latest blocker destination is not a regular file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        with source.open("rb") as input_stream, temporary.open("xb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.lexists(temporary):
            temporary.unlink()


def _remove_if_file(path: Path) -> None:
    if not os.path.lexists(path):
        return
    if _is_link(path) or path.is_file():
        path.unlink()
        return
    raise ValueError(f"Latest blocker view is not a file: {path}")


def _is_link(path: Path) -> bool:
    is_junction = getattr(os.path, "isjunction", lambda _path: False)
    return path.is_symlink() or bool(is_junction(path))


def _diagnostic(code: str, error: Exception) -> BlockerPublicationDiagnostic:
    message = str(error)
    if len(message) > 4096:
        message = message[:4096]
    return BlockerPublicationDiagnostic(code=code, severity="warning", message=message)


def _md(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    return html.escape(text, quote=False).replace("|", "\\|").replace("`", "&#96;")


def _md_code(value: Any) -> str:
    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    return html.escape(text, quote=False).replace("`", "&#96;")
