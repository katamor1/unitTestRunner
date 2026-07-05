from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_legacy_module() -> ModuleType:
    legacy_path = Path(__file__).resolve().parents[1] / "dossier.py"
    spec = importlib.util.spec_from_file_location("unit_test_runner._dossier_legacy", legacy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load legacy dossier module: {legacy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_legacy = _load_legacy_module()

analyze_function_workflow = _legacy.analyze_function_workflow
generate_build_workspace_from_reports = _legacy.generate_build_workspace_from_reports
generate_build_workspace_from_workspace = _legacy.generate_build_workspace_from_workspace
generate_harness_skeleton_from_reports = _legacy.generate_harness_skeleton_from_reports
generate_test_design_from_dossier = _legacy.generate_test_design_from_dossier
generate_test_design_from_reports = _legacy.generate_test_design_from_reports
write_test_case_design = _legacy.write_test_case_design

from .finalizer import finalize_function_dossier, prepare_review_from_dossier  # noqa: E402

__all__ = [
    "analyze_function_workflow",
    "finalize_function_dossier",
    "generate_build_workspace_from_reports",
    "generate_build_workspace_from_workspace",
    "generate_harness_skeleton_from_reports",
    "generate_test_design_from_dossier",
    "generate_test_design_from_reports",
    "prepare_review_from_dossier",
    "write_test_case_design",
]
