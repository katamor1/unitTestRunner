from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class RunPaths:
    run_id: str
    root: Path
    execution_report: Path
    result_json: Path
    result_csv: Path
    stdout_log: Path
    stderr_log: Path
    combined_log: Path


def create_run_paths(workspace: Path, run_id: str | None = None) -> RunPaths:
    workspace = Path(workspace).resolve()
    selected_id = run_id or _new_run_id()
    _validate_id(selected_id)
    runs_root = workspace / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    root = runs_root / selected_id
    root.mkdir(exist_ok=False)
    logs = root / "logs"
    logs.mkdir()
    return RunPaths(
        run_id=selected_id,
        root=root,
        execution_report=root / "test_execution_report.json",
        result_json=root / "test_result.json",
        result_csv=root / "test_result.csv",
        stdout_log=logs / "stdout.log",
        stderr_log=logs / "stderr.log",
        combined_log=logs / "test_execution.log",
    )


def _new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"run-{timestamp}-{uuid4().hex[:8]}"


def _validate_id(value: str) -> None:
    if not value or value in {".", ".."} or Path(value).name != value or "/" in value or "\\" in value:
        raise ValueError(f"Invalid run ID: {value!r}")
