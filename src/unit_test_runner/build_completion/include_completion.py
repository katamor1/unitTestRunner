from __future__ import annotations

from pathlib import Path
from typing import Any

from .completion_models import (
    BuildCompletionPolicy,
    BuildCompletionWarning,
    CompletionAction,
    IncludeCompletionCandidate,
    ManualActionItem,
)


def plan_include_completions(
    build_probe_report: dict[str, Any],
    source_root: Path | str,
    policy: BuildCompletionPolicy | None = None,
) -> tuple[list[IncludeCompletionCandidate], list[CompletionAction], list[BuildCompletionWarning], list[ManualActionItem]]:
    actions: list[CompletionAction] = []
    warnings: list[BuildCompletionWarning] = []
    manual_items: list[ManualActionItem] = []
    candidates = _include_candidates(build_probe_report, Path(source_root).resolve(), actions, warnings, manual_items, policy or BuildCompletionPolicy())
    return candidates, actions, warnings, manual_items


def find_include_candidates(root: Path | str, include_name: str, max_results: int) -> list[Path]:
    return _find_include_candidates(Path(root), include_name, max_results)


def _include_candidates(
    build_probe_report: dict[str, Any],
    source_root: Path,
    actions: list[CompletionAction],
    warnings: list[BuildCompletionWarning],
    manual_items: list[ManualActionItem],
    policy: BuildCompletionPolicy,
) -> list[IncludeCompletionCandidate]:
    candidates: list[IncludeCompletionCandidate] = []
    for index, missing in enumerate(build_probe_report.get("missing_includes", []), start=1):
        include_name = missing.get("include_name", "")
        found = _find_include_candidates(source_root, include_name, policy.include_search_max_results) if policy.search_include_candidates else []
        dirs = sorted({path.parent for path in found})
        action_id = None
        if len(dirs) == 1:
            action_id = f"ACT_INCLUDE_{index:03d}"
            actions.append(
                CompletionAction(
                    action_id=action_id,
                    action_kind="add_include_dir",
                    source_diagnostic_code="C1083",
                    source_diagnostic_raw=missing.get("diagnostic_raw", ""),
                    description=f"Add include directory candidate for {include_name}",
                    apply_mode="manual_review",
                    safety_level="moderate",
                    target_files=[dirs[0]],
                    expected_effect=f"Resolve missing include {include_name}",
                    review_required=True,
                )
            )
        elif len(dirs) > 1:
            warnings.append(BuildCompletionWarning("include_candidate_not_unique", f"Multiple include candidates found for {include_name}.", related_symbol=include_name))
        else:
            warnings.append(BuildCompletionWarning("include_candidate_not_found", f"No include candidate found for {include_name}.", related_symbol=include_name))
            manual_items.append(
                ManualActionItem(
                    item_id=f"MANUAL_INCLUDE_{index:03d}",
                    item_kind="include_path_review",
                    description=f"Resolve missing include {include_name}.",
                    reason="No unique include candidate was found.",
                    suggested_action="Add the correct include directory or copy the required header into the build workspace.",
                    related_diagnostic_raw=missing.get("diagnostic_raw"),
                )
            )
        candidates.append(
            IncludeCompletionCandidate(
                include_name=include_name,
                missing_from=Path(missing["included_from"]) if missing.get("included_from") else None,
                candidate_paths=found,
                candidate_include_dirs=dirs,
                selected_action_id=action_id,
                confidence="high" if len(dirs) == 1 else "low",
                review_required=True,
            )
        )
    return candidates


def _find_include_candidates(root: Path, include_name: str, max_results: int) -> list[Path]:
    if not root.exists():
        return []
    found: list[Path] = []
    for path in root.rglob(Path(include_name).name):
        if path.is_file() and path.name.lower() == Path(include_name).name.lower():
            found.append(path.resolve())
            if len(found) >= max_results:
                break
    return found
