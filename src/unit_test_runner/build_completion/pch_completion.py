from __future__ import annotations

from pathlib import Path
from typing import Any

from .completion_models import CompletionAction, ManualActionItem, PchCompletionCandidate


def plan_pch_completions(build_probe_report: dict[str, Any]) -> tuple[list[PchCompletionCandidate], list[CompletionAction], list[ManualActionItem]]:
    actions: list[CompletionAction] = []
    manual_items: list[ManualActionItem] = []
    candidates = _pch_candidates(build_probe_report, actions, manual_items)
    return candidates, actions, manual_items


def _pch_candidates(
    build_probe_report: dict[str, Any],
    actions: list[CompletionAction],
    manual_items: list[ManualActionItem],
) -> list[PchCompletionCandidate]:
    candidates: list[PchCompletionCandidate] = []
    for index, issue in enumerate(build_probe_report.get("pch_issues", []), start=1):
        action_id = f"ACT_PCH_{index:03d}"
        actions.append(
            CompletionAction(
                action_id=action_id,
                action_kind="adjust_pch_option",
                source_diagnostic_code="PCH",
                source_diagnostic_raw=issue.get("diagnostic_raw", ""),
                description="Review PCH options for build workspace.",
                apply_mode="manual_review",
                safety_level="moderate",
                target_files=[Path("build/Makefile")],
                expected_effect="Resolve PCH mismatch or missing stdafx.h issue.",
                review_required=True,
            )
        )
        candidates.append(
            PchCompletionCandidate(
                issue_kind=issue.get("issue_kind", "pch_issue"),
                header=issue.get("header"),
                suggested_action=issue.get("suggested_action", "Review PCH settings."),
                action_id=action_id,
                safety_level="moderate",
                review_required=True,
            )
        )
        manual_items.append(
            ManualActionItem(
                item_id=f"MANUAL_PCH_{index:03d}",
                item_kind="pch_review",
                description="PCH configuration requires review.",
                reason="PCH behavior is project-specific and is not auto-applied.",
                suggested_action=issue.get("suggested_action", "Review /Yu, /Yc, forced include, and stdafx.h handling."),
                related_diagnostic_raw=issue.get("diagnostic_raw"),
            )
        )
    return candidates
