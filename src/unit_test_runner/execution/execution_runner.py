from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from unit_test_runner.process_control import run_process_tree

from .execution_models import ExecutableInfo, ExecutionCommand, ExecutionCommandResult, TestCaseExecutionResult, TestExecutionWarning, TestResultSummary
from .runner_output_parser import parse_runner_output

if TYPE_CHECKING:
    from .run_paths import RunPaths


def build_execution_command(
    workspace: Path | str,
    executable: ExecutableInfo | Path | str,
    timeout_seconds: int = 60,
    dry_run: bool = True,
) -> ExecutionCommand:
    workspace = Path(workspace).resolve()
    executable_path = executable.path if isinstance(executable, ExecutableInfo) else Path(executable)
    command_path = executable_path if executable_path.is_absolute() else workspace / executable_path
    return ExecutionCommand(
        command_line=f'"{command_path.as_posix()}"',
        working_directory=workspace,
        environment_summary=environment_summary(),
        timeout_seconds=timeout_seconds,
        dry_run=dry_run,
    )


def run_test_executable(
    workspace: Path | str,
    executable: ExecutableInfo | Path | str,
    timeout_seconds: int = 60,
    *,
    run_paths: RunPaths | None = None,
):
    workspace = Path(workspace).resolve()
    executable_path = executable.path if isinstance(executable, ExecutableInfo) else Path(executable)
    started = datetime.now(timezone.utc)
    start = time.monotonic()
    stdout_log = run_paths.stdout_log if run_paths else workspace / "logs" / "test_stdout.log"
    stderr_log = run_paths.stderr_log if run_paths else workspace / "logs" / "test_stderr.log"
    combined_log = run_paths.combined_log if run_paths else workspace / "logs" / "test_execution.log"
    command_path = executable_path if executable_path.is_absolute() else workspace / executable_path
    completed = run_process_tree([str(command_path)], cwd=workspace, text=True, timeout_seconds=timeout_seconds)
    duration = int((time.monotonic() - start) * 1000)
    stdout = _text_output(completed.stdout)
    stderr = _text_output(completed.stderr)
    if completed.timed_out:
        timeout_message = f"Command timed out after {timeout_seconds} seconds. Process tree terminated.\n"
        stderr += timeout_message
        stdout_log.write_text(stdout, encoding="utf-8")
        stderr_log.write_text(stderr, encoding="utf-8")
        combined_log.write_text(stdout + stderr, encoding="utf-8")
        parsed = parse_runner_output(stdout + stderr, exit_code=None, timed_out=True)
        result = ExecutionCommandResult(None, started.isoformat(), datetime.now(timezone.utc).isoformat(), duration, _reported_log_path(workspace, stdout_log), _reported_log_path(workspace, stderr_log), _reported_log_path(workspace, combined_log), True)
        return result, parsed.summary, parsed.case_results, "timeout"

    exit_code = completed.returncode if completed.returncode is not None else 1
    stdout_log.write_text(stdout, encoding="utf-8")
    stderr_log.write_text(stderr, encoding="utf-8")
    combined_log.write_text(stdout + stderr, encoding="utf-8")
    parsed = parse_runner_output(stdout + stderr, exit_code=exit_code, timed_out=False)
    status = "passed" if exit_code == 0 and parsed.summary.failed == 0 and parsed.summary.crashed == 0 else "failed"
    result = ExecutionCommandResult(exit_code, started.isoformat(), datetime.now(timezone.utc).isoformat(), duration, _reported_log_path(workspace, stdout_log), _reported_log_path(workspace, stderr_log), _reported_log_path(workspace, combined_log), False)
    return result, parsed.summary, parsed.case_results, status


def run_test_executable_cases(
    workspace: Path | str,
    executable: ExecutableInfo | Path | str,
    test_case_ids: list[str],
    timeout_seconds: int = 60,
    *,
    run_paths: RunPaths | None = None,
):
    workspace = Path(workspace).resolve()
    executable_path = executable.path if isinstance(executable, ExecutableInfo) else Path(executable)
    started = datetime.now(timezone.utc)
    start = time.monotonic()
    stdout_log = run_paths.stdout_log if run_paths else workspace / "logs" / "test_stdout.log"
    stderr_log = run_paths.stderr_log if run_paths else workspace / "logs" / "test_stderr.log"
    combined_log = run_paths.combined_log if run_paths else workspace / "logs" / "test_execution.log"
    command_path = executable_path if executable_path.is_absolute() else workspace / executable_path
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    case_results: list[TestCaseExecutionResult] = []
    exit_code: int | None = 0
    timed_out = False
    for test_case_id in test_case_ids:
        completed = run_process_tree([str(command_path), "--case", test_case_id], cwd=workspace, text=True, timeout_seconds=timeout_seconds)
        case_stdout = _text_output(completed.stdout)
        case_stderr = _text_output(completed.stderr)
        if completed.timed_out:
            timed_out = True
            exit_code = None
            case_stderr += f"Command timed out after {timeout_seconds} seconds. Process tree terminated.\n"
            parsed = parse_runner_output(case_stdout + case_stderr, exit_code=None, timed_out=True)
            if parsed.case_results:
                case_results.extend(parsed.case_results)
            else:
                case_results.append(_synthetic_case_result(test_case_id, None, True))
        else:
            case_exit_code = completed.returncode if completed.returncode is not None else 1
            if case_exit_code != 0 and exit_code == 0:
                exit_code = case_exit_code
            parsed = parse_runner_output(case_stdout + case_stderr, exit_code=case_exit_code, timed_out=False)
            if parsed.case_results:
                case_results.extend(parsed.case_results)
            else:
                case_results.append(_synthetic_case_result(test_case_id, case_exit_code, False))
        stdout_parts.extend([f"UTR CASE PROCESS {test_case_id}\n", case_stdout])
        stderr_parts.append(case_stderr)
    duration = int((time.monotonic() - start) * 1000)
    stdout_log.write_text("".join(stdout_parts), encoding="utf-8")
    stderr_log.write_text("".join(stderr_parts), encoding="utf-8")
    combined_log.write_text("".join(stdout_parts) + "".join(stderr_parts), encoding="utf-8")
    summary = _summary_from_case_results(case_results)
    status = _status_from_case_results(summary, timed_out)
    result = ExecutionCommandResult(exit_code, started.isoformat(), datetime.now(timezone.utc).isoformat(), duration, _reported_log_path(workspace, stdout_log), _reported_log_path(workspace, stderr_log), _reported_log_path(workspace, combined_log), timed_out)
    return result, summary, case_results, status


def _synthetic_case_result(test_case_id: str, exit_code: int | None, timed_out: bool) -> TestCaseExecutionResult:
    if timed_out:
        evidence = "個別ケース実行がタイムアウトしました。"
        return TestCaseExecutionResult(test_case_id, None, "timeout", True, evidence=evidence, warnings=[TestExecutionWarning("runner_case_timeout", evidence, related_test_case_id=test_case_id)])
    if exit_code not in {None, 0}:
        evidence = f"個別ケース実行が非0終了しました。exit_code={exit_code}。"
        return TestCaseExecutionResult(test_case_id, None, "crashed", True, evidence=evidence, warnings=[TestExecutionWarning("runner_case_incomplete", evidence, related_test_case_id=test_case_id)])
    evidence = "個別ケース実行は終了しましたが、runner出力からケース結果を取得できませんでした。"
    return TestCaseExecutionResult(test_case_id, None, "inconclusive", False, evidence=evidence, warnings=[TestExecutionWarning("runner_output_missing", evidence, related_test_case_id=test_case_id)])


def _summary_from_case_results(case_results: list[TestCaseExecutionResult]) -> TestResultSummary:
    passed = len([case for case in case_results if case.status == "passed"])
    failed = len([case for case in case_results if case.status == "failed"])
    skipped = len([case for case in case_results if case.status == "skipped"])
    inconclusive = len([case for case in case_results if case.status in {"inconclusive", "not_found_in_output"}])
    crashed = len([case for case in case_results if case.status in {"crashed", "timeout"}])
    not_run = len([case for case in case_results if case.status == "not_run"])
    started = len([case for case in case_results if case.status not in {"not_run", "not_found_in_output"}])
    completed = passed + failed + skipped + inconclusive
    confidence = "low" if crashed or not_run else "high"
    return TestResultSummary(len(case_results), passed, failed, skipped, inconclusive, 0, confidence, crashed, not_run, started, completed)


def _status_from_case_results(summary: TestResultSummary, timed_out: bool) -> str:
    if timed_out:
        return "timeout"
    if summary.crashed > 0 or summary.failed > 0:
        return "failed"
    if summary.inconclusive > 0 or summary.not_run > 0:
        return "inconclusive"
    if summary.total > 0 and summary.passed == summary.total:
        return "passed"
    return "not_run"


def _text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode(errors="replace")


def _reported_log_path(workspace: Path, log_path: Path) -> Path:
    try:
        return log_path.relative_to(workspace)
    except ValueError:
        return log_path


def environment_summary() -> dict[str, str]:
    return {"cwd": str(Path.cwd()), "path_set": "yes" if os.environ.get("PATH") else "no"}
