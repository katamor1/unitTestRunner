from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .completion_models import (
    BuildCompletionIterationReport,
    BuildCompletionPlan,
    BuildCompletionPolicy,
    BuildCompletionWarning,
    CompatibilityFeedbackItem,
    CompletionAction,
    CompletionIteration,
    DiagnosticsSummary,
    IncludeCompletionCandidate,
    ManualActionItem,
    PchCompletionCandidate,
    StubCompletionCandidate,
)
from .completion_report_writer import write_completion_reports
from .symbol_normalizer import normalize_link_symbol


def analyze_build_errors_from_workspace(
    workspace: Path | str,
    source_root: Path | str | None = None,
    policy: BuildCompletionPolicy | None = None,
) -> tuple[BuildCompletionPlan, BuildCompletionIterationReport]:
    workspace = Path(workspace).resolve()
    reports = workspace / "reports"
    plan, iteration = analyze_build_errors(
        _read_json(reports / "build_workspace_report.json"),
        _read_json(reports / "build_probe_report.json"),
        _read_json(reports / "call_report.json"),
        _read_json(reports / "harness_skeleton_report.json"),
        workspace,
        Path(source_root).resolve() if source_root else _source_root_from_context(reports / "build_context.json"),
        policy=policy,
    )
    write_completion_reports(workspace, plan, iteration)
    return plan, iteration


def analyze_build_errors(
    build_workspace_report: dict[str, Any],
    build_probe_report: dict[str, Any],
    call_report: dict[str, Any],
    harness_report: dict[str, Any],
    workspace: Path | str,
    source_root: Path | str | None = None,
    policy: BuildCompletionPolicy | None = None,
) -> tuple[BuildCompletionPlan, BuildCompletionIterationReport]:
    workspace = Path(workspace).resolve()
    source_root = Path(source_root).resolve() if source_root else workspace
    policy = policy or BuildCompletionPolicy()
    source_path = Path(build_workspace_report.get("source", {}).get("path") or build_probe_report.get("source", {}).get("path") or "")
    function_name = build_workspace_report.get("function", {}).get("name") or build_probe_report.get("function", {}).get("name") or "unknown_function"
    actions: list[CompletionAction] = []
    warnings: list[BuildCompletionWarning] = []
    manual_items: list[ManualActionItem] = []
    include_candidates = _include_candidates(build_probe_report, source_root, actions, warnings, manual_items, policy)
    stub_candidates = _stub_candidates(build_probe_report, call_report, actions, warnings, policy)
    pch_candidates = _pch_candidates(build_probe_report, actions, manual_items)
    compatibility = _compatibility_feedback(build_probe_report, manual_items)
    status = _plan_status(actions, manual_items, build_probe_report)
    plan = BuildCompletionPlan(
        source_path=source_path,
        function_name=function_name,
        status=status,
        policy=policy,
        completion_actions=actions,
        include_completion_candidates=include_candidates,
        stub_completion_candidates=stub_candidates,
        pch_completion_candidates=pch_candidates,
        compatibility_feedback_items=compatibility,
        manual_action_items=manual_items,
        warnings=warnings,
    )
    summary = diagnostics_summary(build_probe_report)
    iteration = BuildCompletionIterationReport(
        source_path=source_path,
        function_name=function_name,
        status=status,
        iterations=[
            CompletionIteration(
                iteration_index=1,
                input_probe_report=Path("reports/build_probe_report.json"),
                completion_plan=Path("reports/build_completion_plan.json"),
                applied_actions=[],
                skipped_actions=[action.action_id for action in actions],
                generated_files=[],
                probe_executed=False,
                probe_report=Path("reports/build_probe_report.json"),
                diagnostics_before=summary,
                diagnostics_after=None,
                progress="not_run",
            )
        ],
        final_build_probe_status=build_probe_report.get("function", {}).get("status", "not_run"),
        final_diagnostics_summary=summary,
        stop_reason="completion plan generated; safe completions are not applied unless explicitly requested",
        next_recommended_action="Review build_completion_plan and run complete-build with --apply-safe-completions if appropriate.",
        warnings=[],
    )
    return plan, iteration


def diagnostics_summary(build_probe_report: dict[str, Any]) -> DiagnosticsSummary:
    diagnostics = build_probe_report.get("diagnostics", [])
    return DiagnosticsSummary(
        missing_include_count=len(build_probe_report.get("missing_includes", [])),
        unresolved_symbol_count=len(build_probe_report.get("unresolved_symbols", [])),
        pch_issue_count=len(build_probe_report.get("pch_issues", [])),
        vc6_compatibility_issue_count=len(build_probe_report.get("vc6_compatibility_issues", [])),
        compiler_error_count=len([item for item in diagnostics if item.get("severity") == "error"]),
        compiler_warning_count=len([item for item in diagnostics if item.get("severity") == "warning"]),
    )


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


def _stub_candidates(
    build_probe_report: dict[str, Any],
    call_report: dict[str, Any],
    actions: list[CompletionAction],
    warnings: list[BuildCompletionWarning],
    policy: BuildCompletionPolicy,
) -> list[StubCompletionCandidate]:
    calls = {call.get("name"): call for call in call_report.get("calls", [])}
    candidates: list[StubCompletionCandidate] = []
    for index, unresolved in enumerate(build_probe_report.get("unresolved_symbols", []), start=1):
        normalized = normalize_link_symbol(unresolved.get("symbol_name", ""))
        function_name = normalized.function_name_candidate
        call = calls.get(function_name)
        if call:
            strategy = "from_call_report"
            parameter_strategy = "from_call_arguments"
            confidence = "high"
            related_call_id = call.get("call_id")
            related_call_name = call.get("name")
        else:
            strategy = "default_int"
            parameter_strategy = "empty_parameter_list"
            confidence = "low"
            related_call_id = None
            related_call_name = None
            warnings.append(BuildCompletionWarning("unknown_symbol_stub_generated", f"Unknown symbol stub candidate requires review: {function_name}.", related_symbol=function_name))
        source = Path("generated/stubs") / f"stub_{function_name}.c"
        header = Path("generated/stubs") / f"stub_{function_name}.h"
        action_id = f"ACT_STUB_{index:03d}"
        if call or policy.generate_unknown_symbol_stubs:
            actions.append(
                CompletionAction(
                    action_id=action_id,
                    action_kind="generate_stub",
                    source_diagnostic_code=unresolved.get("diagnostic_code", "LNK"),
                    source_diagnostic_raw=unresolved.get("diagnostic_raw", ""),
                    description=f"Generate additional stub for {function_name}",
                    apply_mode="auto_safe",
                    safety_level="safe" if call else "moderate",
                    target_files=[source, header],
                    expected_effect=f"Resolve unresolved external symbol {function_name}",
                    review_required=True,
                )
            )
        candidates.append(
            StubCompletionCandidate(
                symbol_name=unresolved.get("symbol_name", ""),
                function_name_candidate=function_name,
                related_call_name=related_call_name,
                related_call_id=related_call_id,
                return_type_strategy=strategy,
                parameter_strategy=parameter_strategy,
                stub_source_path=source,
                stub_header_path=header,
                makefile_registration_required=True,
                confidence=confidence,
                review_required=True,
            )
        )
    return candidates


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
                feedback_target_step="Step 13" if generated else "Step 14",
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


def _plan_status(actions: list[CompletionAction], manual_items: list[ManualActionItem], build_probe_report: dict[str, Any]) -> str:
    if build_probe_report.get("function", {}).get("status") == "succeeded":
        return "no_action_needed"
    if actions:
        return "planned"
    if manual_items:
        return "manual_action_required"
    return "no_action_needed"


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


def _source_root_from_context(path: Path) -> Path | None:
    if not path.exists():
        return None
    try:
        payload = _read_json(path)
    except OSError:
        return None
    root = payload.get("workspace_root")
    return Path(root).resolve() if root else None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
