from __future__ import annotations

from pathlib import Path
from typing import Any

from .completion_models import CompatibilityFeedbackItem, ManualActionItem


def plan_compatibility_feedback(build_probe_report: dict[str, Any]) -> tuple[list[CompatibilityFeedbackItem], list[ManualActionItem]]:
    manual_items: list[ManualActionItem] = []
    feedback = _compatibility_feedback(build_probe_report, manual_items)
    return feedback, manual_items


def _compatibility_feedback(build_probe_report: dict[str, Any], manual_items: list[ManualActionItem]) -> list[CompatibilityFeedbackItem]:
    feedback: list[CompatibilityFeedbackItem] = []
    for index, issue in enumerate(build_probe_report.get("vc6_compatibility_issues", []), start=1):
        file_value = Path(issue["file"]) if issue.get("file") else None
        generated = file_value is not None and "generated" in file_value.as_posix().replace("\\", "/")
        feedback.append(
            CompatibilityFeedbackItem(
                issue_kind=issue.get("issue_kind", "vc6_compatibility_issue"),
                file=file_value,
                line_number=issue.get("line_number"),
                suspected_generator="harness_skeleton_generator" if generated else None,
                suggested_fix=issue.get("suggested_action", "Review generated code for VC6/C90 compatibility."),
                feedback_target_item="harness_skeleton_generation" if generated else "build_workspace_generation",
                review_required=True,
            )
        )
        manual_items.append(
            ManualActionItem(
                item_id=f"MANUAL_COMPAT_{index:03d}",
                item_kind="generated_code_fix" if generated else "target_source_issue",
                description="VC6 compatibility issue requires review.",
                reason="Syntax compatibility cannot be safely corrected from build log alone.",
                suggested_action=issue.get("suggested_action", "Inspect the related file and adjust generator or build context."),
                related_diagnostic_raw=issue.get("diagnostic_raw"),
            )
        )
    return feedback
