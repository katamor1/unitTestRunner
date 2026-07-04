from __future__ import annotations

from pathlib import Path
from typing import Any

from .completion_applier import CompletionApplyResult
from .completion_models import BuildCompletionIterationReport, BuildCompletionPlan, BuildCompletionWarning, CompletionIteration, DiagnosticsSummary
from .diagnostic_classifier import summarize_diagnostics


def build_iteration_report(
    plan: BuildCompletionPlan,
    build_probe_report: dict[str, Any],
    apply_result: CompletionApplyResult | None = None,
    probe_executed: bool = False,
    diagnostics_after: DiagnosticsSummary | None = None,
) -> BuildCompletionIterationReport:
    before = summarize_diagnostics(build_probe_report)
    applied_actions = apply_result.applied_actions if apply_result else []
    skipped_actions = apply_result.skipped_actions if apply_result else [action.action_id for action in plan.completion_actions]
    generated_files = apply_result.generated_files if apply_result else []
    warnings: list[BuildCompletionWarning] = list(apply_result.warnings) if apply_result else []
    progress = "not_run"
    if diagnostics_after is not None:
        progress = _progress_from_summaries(before, diagnostics_after, build_probe_report)
    iteration = CompletionIteration(
        iteration_index=1,
        input_probe_report=Path("reports/build_probe_report.json"),
        completion_plan=Path("reports/build_completion_plan.json"),
        applied_actions=applied_actions,
        skipped_actions=skipped_actions,
        generated_files=generated_files,
        probe_executed=probe_executed,
        probe_report=Path("reports/build_probe_report.json"),
        diagnostics_before=before,
        diagnostics_after=diagnostics_after,
        progress=progress,
    )
    final_summary = diagnostics_after or before
    final_status = build_probe_report.get("function", {}).get("status", "not_run")
    return BuildCompletionIterationReport(
        source_path=plan.source_path,
        function_name=plan.function_name,
        status=plan.status,
        iterations=[iteration],
        final_build_probe_status=final_status,
        final_diagnostics_summary=final_summary,
        stop_reason="completion plan generated; safe completions are not applied unless explicitly requested",
        next_recommended_action="Review build_completion_plan and run complete-build with --apply-safe-completions if appropriate.",
        warnings=warnings,
    )


def _progress_from_summaries(before: DiagnosticsSummary, after: DiagnosticsSummary, build_probe_report: dict[str, Any]) -> str:
    if build_probe_report.get("function", {}).get("status") == "succeeded":
        return "succeeded"
    before_total = before.missing_include_count + before.unresolved_symbol_count + before.pch_issue_count + before.vc6_compatibility_issue_count
    after_total = after.missing_include_count + after.unresolved_symbol_count + after.pch_issue_count + after.vc6_compatibility_issue_count
    if after_total < before_total:
        return "improved"
    if after_total > before_total:
        return "regressed"
    return "unchanged"
