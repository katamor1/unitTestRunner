from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .execution_models import ExecutableInfo, ExecutionCommand, ExecutionCommandResult, TestResultSummary
from .runner_output_parser import parse_runner_output


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


def run_test_executable(workspace: Path | str, executable: ExecutableInfo | Path | str, timeout_seconds: int = 60):
    workspace = Path(workspace).resolve()
    executable_path = executable.path if isinstance(executable, ExecutableInfo) else Path(executable)
    started = datetime.now(timezone.utc)
    start = time.monotonic()
    stdout_log = workspace / "logs" / "test_stdout.log"
    stderr_log = workspace / "logs" / "test_stderr.log"
    combined_log = workspace / "logs" / "test_execution.log"
    command_path = executable_path if executable_path.is_absolute() else workspace / executable_path
    try:
        completed = subprocess.run([str(command_path)], cwd=workspace, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_seconds, check=False)
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


def environment_summary() -> dict[str, str]:
    return {"cwd": str(Path.cwd()), "path_set": "yes" if os.environ.get("PATH") else "no"}
