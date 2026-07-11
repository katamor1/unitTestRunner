from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Mapping, Sequence

_PROCESS_GROUP_GRACE_SECONDS = 0.25
_TERMINATION_WAIT_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class ProcessTreeRunResult:
    returncode: int | None
    stdout: str | bytes
    stderr: str | bytes | None
    timed_out: bool


def run_process_tree(
    command: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path | str | None = None,
    timeout_seconds: float | None = None,
    text: bool = False,
    stdout: int | IO[bytes] | IO[str] | None = subprocess.PIPE,
    stderr: int | IO[bytes] | IO[str] | None = subprocess.PIPE,
    env: Mapping[str, str] | None = None,
) -> ProcessTreeRunResult:
    """Run a command and terminate its complete process tree on timeout."""

    popen_kwargs: dict[str, object] = {
        "cwd": cwd,
        "text": text,
        "stdout": stdout,
        "stderr": stderr,
        "env": dict(env) if env is not None else None,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen([str(item) for item in command], **popen_kwargs)
    try:
        captured_stdout, captured_stderr = process.communicate(timeout=timeout_seconds)
        return ProcessTreeRunResult(process.returncode, _empty_output(captured_stdout, text), captured_stderr, False)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        captured_stdout, captured_stderr = _collect_after_termination(process, text)
        return ProcessTreeRunResult(process.returncode, captured_stdout, captured_stderr, True)


def _terminate_process_tree(process: subprocess.Popen[object]) -> None:
    if os.name == "nt":
        if not _taskkill_process_tree(process.pid):
            _kill_direct_process(process)
        return

    _signal_process_group(process.pid, signal.SIGTERM)
    time.sleep(_PROCESS_GROUP_GRACE_SECONDS)
    _signal_process_group(process.pid, signal.SIGKILL)


def _taskkill_process_tree(pid: int) -> bool:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        killer = subprocess.Popen(
            ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except OSError:
        return False
    try:
        return killer.wait(timeout=_TERMINATION_WAIT_SECONDS) == 0
    except subprocess.TimeoutExpired:
        try:
            killer.kill()
        except OSError:
            pass
        return False


def _signal_process_group(pid: int, sig: signal.Signals) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        return


def _kill_direct_process(process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return
    try:
        process.kill()
    except OSError:
        pass


def _collect_after_termination(process: subprocess.Popen[object], text: bool) -> tuple[str | bytes, str | bytes | None]:
    try:
        captured_stdout, captured_stderr = process.communicate(timeout=_TERMINATION_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        _kill_direct_process(process)
        captured_stdout, captured_stderr = process.communicate()
    return _empty_output(captured_stdout, text), captured_stderr


def _empty_output(value: str | bytes | None, text: bool) -> str | bytes:
    if value is not None:
        return value
    return "" if text else b""
