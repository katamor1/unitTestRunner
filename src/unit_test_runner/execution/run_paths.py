from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class RunPaths:
    run_id: str
    root: Path
    execution_report: Path
    blocker_report_json: Path
    blocker_report_markdown: Path
    result_json: Path
    result_csv: Path
    stdout_log: Path
    stderr_log: Path
    combined_log: Path


def create_run_paths(workspace: Path, run_id: str | None = None) -> RunPaths:
    selected_id = run_id or _new_run_id()
    paths = validate_run_paths_available(workspace, selected_id)
    paths.root.parent.mkdir(parents=True, exist_ok=True)
    paths = validate_run_paths_available(workspace, selected_id)
    try:
        paths.root.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise FileExistsError(f"Run ID already exists: {selected_id!r}") from error
    logs = paths.root / "logs"
    logs.mkdir()
    return paths


def validate_run_paths_available(workspace: Path, run_id: str) -> RunPaths:
    workspace = Path(workspace).resolve()
    _validate_id(run_id)
    runs_root = workspace / "runs"
    if os.path.lexists(runs_root):
        if _is_link(runs_root):
            raise ValueError(f"Run paths parent must not be a symlink: {runs_root}")
        if not runs_root.is_dir():
            raise NotADirectoryError(f"Run paths parent is not a directory: {runs_root}")
    resolved_runs_root = runs_root.resolve(strict=False)
    try:
        resolved_runs_root.relative_to(workspace)
    except ValueError as error:
        raise ValueError(f"Run paths parent escapes workspace: {resolved_runs_root}") from error
    root = resolved_runs_root / run_id
    if os.path.lexists(root):
        raise FileExistsError(f"Run ID already exists: {run_id!r}")
    logs = root / "logs"
    return RunPaths(
        run_id=run_id,
        root=root,
        execution_report=root / "test_execution_report.json",
        blocker_report_json=root / "test_execution_blockers.json",
        blocker_report_markdown=root / "test_execution_blockers.md",
        result_json=root / "test_result.json",
        result_csv=root / "test_result.csv",
        stdout_log=logs / "stdout.log",
        stderr_log=logs / "stderr.log",
        combined_log=logs / "test_execution.log",
    )


def _is_link(path: Path) -> bool:
    is_junction = getattr(os.path, "isjunction", lambda _path: False)
    return path.is_symlink() or bool(is_junction(path))


def _new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"run-{timestamp}-{uuid4().hex[:8]}"


def _validate_id(value: str) -> None:
    if not value or value in {".", ".."} or Path(value).name != value or "/" in value or "\\" in value:
        raise ValueError(f"Invalid run ID: {value!r}")
