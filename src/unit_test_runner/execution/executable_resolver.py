from __future__ import annotations

from pathlib import Path
from typing import Any

from unit_test_runner.harness.c90_writer import sha256_file
from unit_test_runner.path_utils import resolved_relative_to

from .execution_models import ExecutableInfo, TestExecutionWarning


def resolve_executable(
    workspace: Path | str,
    executable: Path | str | None = None,
    build_probe_report: dict[str, Any] | None = None,
) -> ExecutableInfo:
    workspace = Path(workspace).resolve()
    build_probe_report = build_probe_report or {}
    path = Path(executable) if executable else Path("bin") / "utr_probe.exe"
    if path.is_absolute():
        absolute = path.resolve(strict=False)
        try:
            relative = resolved_relative_to(absolute, workspace)
        except ValueError:
            relative = path
    else:
        absolute = workspace / path
        relative = path
    warnings: list[TestExecutionWarning] = []
    if not absolute.exists():
        warnings.append(TestExecutionWarning("executable_not_found", f"実行ファイルが見つかりません: {relative}", related_file=relative))
    return ExecutableInfo(
        path=relative,
        exists=absolute.exists(),
        sha256=sha256_file(absolute),
        generated_from="build_probe",
        build_probe_status=build_probe_report.get("function", {}).get("status", "unknown"),
        warnings=warnings,
    )
