from __future__ import annotations

from .finalizer import finalize_function_dossier, prepare_review_from_dossier
from .link_context_compat import apply_link_context_compat

apply_link_context_compat()

from .quick_summary_compat import analyze_function_workflow
from .workflow import (
    generate_build_workspace_from_reports,
    generate_build_workspace_from_workspace,
    generate_harness_skeleton_from_reports,
    generate_test_design_from_dossier,
    generate_test_design_from_dossier_result,
    generate_test_design_from_reports,
    generate_test_design_from_reports_result,
    write_test_case_design,
)

__all__ = [
    "analyze_function_workflow",
    "finalize_function_dossier",
    "generate_build_workspace_from_reports",
    "generate_build_workspace_from_workspace",
    "generate_harness_skeleton_from_reports",
    "generate_test_design_from_dossier",
    "generate_test_design_from_dossier_result",
    "generate_test_design_from_reports",
    "generate_test_design_from_reports_result",
    "prepare_review_from_dossier",
    "write_test_case_design",
]
