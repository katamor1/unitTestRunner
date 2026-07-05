from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _path_text(path: Path | None) -> str | None:
    if path is None:
        return None
    return path.as_posix()


@dataclass
class BuildCompletionPolicy:
    apply_safe_completions: bool = False
    run_probe_after_apply: bool = False
    max_iterations: int = 3
    search_include_candidates: bool = True
    include_search_max_results: int = 20
    generate_unknown_symbol_stubs: bool = True
    overwrite_existing_generated_stubs: bool = False
    stop_on_no_progress: bool = True
    stop_on_new_error_growth: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "apply_safe_completions": self.apply_safe_completions,
            "run_probe_after_apply": self.run_probe_after_apply,
            "max_iterations": self.max_iterations,
            "search_include_candidates": self.search_include_candidates,
            "include_search_max_results": self.include_search_max_results,
            "generate_unknown_symbol_stubs": self.generate_unknown_symbol_stubs,
            "overwrite_existing_generated_stubs": self.overwrite_existing_generated_stubs,
            "stop_on_no_progress": self.stop_on_no_progress,
            "stop_on_new_error_growth": self.stop_on_new_error_growth,
        }


@dataclass
class BuildCompletionWarning:
    code: str
    message: str
    related_action_id: str | None = None
    related_symbol: str | None = None
    related_file: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "related_action_id": self.related_action_id,
            "related_symbol": self.related_symbol,
            "related_file": _path_text(self.related_file),
        }


@dataclass
class CompletionAction:
    action_id: str
    action_kind: str
    source_diagnostic_code: str
    source_diagnostic_raw: str
    description: str
    apply_mode: str
    safety_level: str
    target_files: list[Path]
    expected_effect: str
    applied: bool = False
    result: str | None = None
    review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_kind": self.action_kind,
            "source_diagnostic_code": self.source_diagnostic_code,
            "source_diagnostic_raw": self.source_diagnostic_raw,
            "description": self.description,
            "apply_mode": self.apply_mode,
            "safety_level": self.safety_level,
            "target_files": [_path_text(item) for item in self.target_files],
            "expected_effect": self.expected_effect,
            "applied": self.applied,
            "result": self.result,
            "review_required": self.review_required,
        }


@dataclass
class IncludeCompletionCandidate:
    include_name: str
    missing_from: Path | None
    candidate_paths: list[Path]
    candidate_include_dirs: list[Path]
    selected_action_id: str | None
    confidence: str
    review_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "include_name": self.include_name,
            "missing_from": _path_text(self.missing_from),
            "candidate_paths": [_path_text(item) for item in self.candidate_paths],
            "candidate_include_dirs": [_path_text(item) for item in self.candidate_include_dirs],
            "selected_action_id": self.selected_action_id,
            "confidence": self.confidence,
            "review_required": self.review_required,
        }


@dataclass
class StubCompletionCandidate:
    symbol_name: str
    function_name_candidate: str
    related_call_name: str | None
    related_call_id: str | None
    return_type_strategy: str
    parameter_strategy: str
    stub_source_path: Path
    stub_header_path: Path
    makefile_registration_required: bool
    confidence: str
    review_required: bool
    parameter_count: int = 0
    warnings: list[BuildCompletionWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol_name": self.symbol_name,
            "function_name_candidate": self.function_name_candidate,
            "related_call_name": self.related_call_name,
            "related_call_id": self.related_call_id,
            "return_type_strategy": self.return_type_strategy,
            "parameter_strategy": self.parameter_strategy,
            "stub_source_path": _path_text(self.stub_source_path),
            "stub_header_path": _path_text(self.stub_header_path),
            "makefile_registration_required": self.makefile_registration_required,
            "confidence": self.confidence,
            "review_required": self.review_required,
            "parameter_count": self.parameter_count,
            "warnings": [item.to_dict() for item in self.warnings],
        }


@dataclass
class PchCompletionCandidate:
    issue_kind: str
    header: str | None
    suggested_action: str
    action_id: str | None
    safety_level: str
    review_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_kind": self.issue_kind,
            "header": self.header,
            "suggested_action": self.suggested_action,
            "action_id": self.action_id,
            "safety_level": self.safety_level,
            "review_required": self.review_required,
        }


@dataclass
class CompatibilityFeedbackItem:
    issue_kind: str
    file: Path | None
    line_number: int | None
    suspected_generator: str | None
    suggested_fix: str
    feedback_target_item: str
    review_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_kind": self.issue_kind,
            "file": _path_text(self.file),
            "line_number": self.line_number,
            "suspected_generator": self.suspected_generator,
            "suggested_fix": self.suggested_fix,
            "feedback_target_item": self.feedback_target_item,
            "review_required": self.review_required,
        }


@dataclass
class ManualActionItem:
    item_id: str
    item_kind: str
    description: str
    reason: str
    suggested_action: str
    related_diagnostic_raw: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_kind": self.item_kind,
            "description": self.description,
            "reason": self.reason,
            "suggested_action": self.suggested_action,
            "related_diagnostic_raw": self.related_diagnostic_raw,
        }


@dataclass
class DiagnosticsSummary:
    missing_include_count: int = 0
    unresolved_symbol_count: int = 0
    pch_issue_count: int = 0
    vc6_compatibility_issue_count: int = 0
    compiler_error_count: int = 0
    compiler_warning_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "missing_include_count": self.missing_include_count,
            "unresolved_symbol_count": self.unresolved_symbol_count,
            "pch_issue_count": self.pch_issue_count,
            "vc6_compatibility_issue_count": self.vc6_compatibility_issue_count,
            "compiler_error_count": self.compiler_error_count,
            "compiler_warning_count": self.compiler_warning_count,
        }


@dataclass
class BuildCompletionPlan:
    source_path: Path
    function_name: str
    status: str
    policy: BuildCompletionPolicy
    completion_actions: list[CompletionAction] = field(default_factory=list)
    include_completion_candidates: list[IncludeCompletionCandidate] = field(default_factory=list)
    stub_completion_candidates: list[StubCompletionCandidate] = field(default_factory=list)
    pch_completion_candidates: list[PchCompletionCandidate] = field(default_factory=list)
    compatibility_feedback_items: list[CompatibilityFeedbackItem] = field(default_factory=list)
    manual_action_items: list[ManualActionItem] = field(default_factory=list)
    warnings: list[BuildCompletionWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {"path": _path_text(self.source_path)},
            "function": {"name": self.function_name, "status": self.status},
            "policy": self.policy.to_dict(),
            "completion_actions": [item.to_dict() for item in self.completion_actions],
            "include_completion_candidates": [item.to_dict() for item in self.include_completion_candidates],
            "stub_completion_candidates": [item.to_dict() for item in self.stub_completion_candidates],
            "pch_completion_candidates": [item.to_dict() for item in self.pch_completion_candidates],
            "compatibility_feedback_items": [item.to_dict() for item in self.compatibility_feedback_items],
            "manual_action_items": [item.to_dict() for item in self.manual_action_items],
            "warnings": [item.to_dict() for item in self.warnings],
        }


@dataclass
class CompletionIteration:
    iteration_index: int
    input_probe_report: Path
    completion_plan: Path
    applied_actions: list[str]
    skipped_actions: list[str]
    generated_files: list[Path]
    probe_executed: bool
    probe_report: Path | None
    diagnostics_before: DiagnosticsSummary
    diagnostics_after: DiagnosticsSummary | None
    progress: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration_index": self.iteration_index,
            "input_probe_report": _path_text(self.input_probe_report),
            "completion_plan": _path_text(self.completion_plan),
            "applied_actions": self.applied_actions,
            "skipped_actions": self.skipped_actions,
            "generated_files": [_path_text(item) for item in self.generated_files],
            "probe_executed": self.probe_executed,
            "probe_report": _path_text(self.probe_report),
            "diagnostics_before": self.diagnostics_before.to_dict(),
            "diagnostics_after": self.diagnostics_after.to_dict() if self.diagnostics_after else None,
            "progress": self.progress,
        }


@dataclass
class BuildCompletionIterationReport:
    source_path: Path
    function_name: str
    status: str
    iterations: list[CompletionIteration]
    final_build_probe_status: str
    final_diagnostics_summary: DiagnosticsSummary
    stop_reason: str
    next_recommended_action: str
    warnings: list[BuildCompletionWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {"path": _path_text(self.source_path)},
            "function": {"name": self.function_name, "status": self.status},
            "iterations": [item.to_dict() for item in self.iterations],
            "final_build_probe_status": self.final_build_probe_status,
            "final_diagnostics_summary": self.final_diagnostics_summary.to_dict(),
            "stop_reason": self.stop_reason,
            "next_recommended_action": self.next_recommended_action,
            "warnings": [item.to_dict() for item in self.warnings],
        }
