from __future__ import annotations

from pathlib import Path
from typing import Any

from unit_test_runner.reports.quick_summary import write_quick_summary

from . import workflow as _workflow


def analyze_function_workflow(
    workspace_root: Path | str,
    dsw_path: Path | str,
    source: str,
    function_name: str,
    configuration: str,
    out_dir: Path | str,
    project_name: str | None = None,
    apply_safe_completions: bool = False,
    run_tests: bool = False,
    phase: str = "execution",
) -> dict[str, Any]:
    dossier = _workflow.analyze_function_workflow(
        workspace_root,
        dsw_path,
        source,
        function_name,
        configuration,
        out_dir,
        project_name,
        apply_safe_completions=apply_safe_completions,
        run_tests=run_tests,
        phase=phase,
    )
    paths = write_quick_summary(Path(out_dir), dossier, phase, _status_for_phase(phase))
    dossier["quick_summary"] = {
        "json": str(paths["json"]),
        "markdown": str(paths["markdown"]),
        "status": _status_for_phase(phase),
    }
    return dossier


def _status_for_phase(phase: str) -> str:
    if phase == "execution":
        return "evidence_prepared"
    if phase == "build":
        return "build_workspace_generated"
    if phase == "harness":
        return "harness_skeleton_generated"
    return "analysis_completed"
