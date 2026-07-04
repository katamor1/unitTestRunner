from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from unit_test_runner.c_analyzer.analysis_common import path_text


@dataclass
class TestCaseGenerationPolicy:
    max_cases_per_coverage_item: int = 2
    include_additional_candidates: bool = True
    include_review_required_candidates: bool = True
    merge_compatible_coverage_items: bool = False
    prefer_high_confidence: bool = True
    emit_csv: bool = True
    emit_markdown: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cases_per_coverage_item": self.max_cases_per_coverage_item,
            "include_additional_candidates": self.include_additional_candidates,
            "include_review_required_candidates": self.include_review_required_candidates,
            "merge_compatible_coverage_items": self.merge_compatible_coverage_items,
            "prefer_high_confidence": self.prefer_high_confidence,
            "emit_csv": self.emit_csv,
            "emit_markdown": self.emit_markdown,
        }


@dataclass
class TestCaseDraftWarning:
    code: str
    message: str
    related_test_case_id: str | None = None
    related_coverage_id: str | None = None
    text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.related_test_case_id is not None:
            value["related_test_case_id"] = self.related_test_case_id
        if self.related_coverage_id is not None:
            value["related_coverage_id"] = self.related_coverage_id
        if self.text is not None:
            value["text"] = self.text
        return value


@dataclass
class TestPrecondition:
    description: str
    source: str
    review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"description": self.description, "source": self.source, "review_required": self.review_required}


@dataclass
class TestInputAssignment:
    target_name: str
    target_kind: str
    value_expression: str
    value_kind: str
    source_candidate_id: str | None
    rationale: str
    review_required: bool
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_name": self.target_name,
            "target_kind": self.target_kind,
            "value_expression": self.value_expression,
            "value_kind": self.value_kind,
            "source_candidate_id": self.source_candidate_id,
            "rationale": self.rationale,
            "review_required": self.review_required,
            "confidence": self.confidence,
        }


@dataclass
class TestStateSetup:
    variable_name: str
    scope: str
    value_expression: str
    setup_method_hint: str
    source_candidate_id: str | None
    review_required: bool
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable_name": self.variable_name,
            "scope": self.scope,
            "value_expression": self.value_expression,
            "setup_method_hint": self.setup_method_hint,
            "source_candidate_id": self.source_candidate_id,
            "review_required": self.review_required,
            "confidence": self.confidence,
        }


@dataclass
class TestStubSetup:
    stub_name: str
    setup_kind: str
    value_expression: str | None
    call_behavior: str | None
    source_candidate_id: str | None
    related_call_id: str | None
    review_required: bool
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stub_name": self.stub_name,
            "setup_kind": self.setup_kind,
            "value_expression": self.value_expression,
            "call_behavior": self.call_behavior,
            "source_candidate_id": self.source_candidate_id,
            "related_call_id": self.related_call_id,
            "review_required": self.review_required,
            "confidence": self.confidence,
        }


@dataclass
class TestExecutionStep:
    order: int
    action: str
    detail: str
    review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"order": self.order, "action": self.action, "detail": self.detail, "review_required": self.review_required}


@dataclass
class ExpectedObservation:
    observation_kind: str
    target_name: str | None
    expected_expression: str | None
    source: str
    review_required: bool
    confidence: str
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_kind": self.observation_kind,
            "target_name": self.target_name,
            "expected_expression": self.expected_expression,
            "source": self.source,
            "review_required": self.review_required,
            "confidence": self.confidence,
            "note": self.note,
        }


@dataclass
class TestCoverageLink:
    coverage_id: str
    coverage_type: str
    target_id: str
    intended_value: str | None
    link_reason: str
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_id": self.coverage_id,
            "coverage_type": self.coverage_type,
            "target_id": self.target_id,
            "intended_value": self.intended_value,
            "link_reason": self.link_reason,
            "confidence": self.confidence,
        }


@dataclass
class TestCaseDraft:
    test_case_id: str
    title: str
    target_function: str
    purpose: str
    priority: str
    case_kind: str
    preconditions: list[TestPrecondition] = field(default_factory=list)
    input_assignments: list[TestInputAssignment] = field(default_factory=list)
    state_setups: list[TestStateSetup] = field(default_factory=list)
    stub_setups: list[TestStubSetup] = field(default_factory=list)
    execution_steps: list[TestExecutionStep] = field(default_factory=list)
    expected_observations: list[ExpectedObservation] = field(default_factory=list)
    coverage_links: list[TestCoverageLink] = field(default_factory=list)
    candidate_links: list[str] = field(default_factory=list)
    review_status: str = "review_required"
    confidence: str = "medium"
    warnings: list[TestCaseDraftWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_case_id": self.test_case_id,
            "title": self.title,
            "target_function": self.target_function,
            "purpose": self.purpose,
            "priority": self.priority,
            "case_kind": self.case_kind,
            "preconditions": [item.to_dict() for item in self.preconditions],
            "input_assignments": [item.to_dict() for item in self.input_assignments],
            "state_setups": [item.to_dict() for item in self.state_setups],
            "stub_setups": [item.to_dict() for item in self.stub_setups],
            "execution_steps": [item.to_dict() for item in self.execution_steps],
            "expected_observations": [item.to_dict() for item in self.expected_observations],
            "coverage_links": [item.to_dict() for item in self.coverage_links],
            "candidate_links": self.candidate_links,
            "review_status": self.review_status,
            "confidence": self.confidence,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass
class CoverageDraftSummary:
    total_coverage_items: int
    covered_by_draft_count: int
    uncovered_coverage_ids: list[str]
    coverage_to_test_cases: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_coverage_items": self.total_coverage_items,
            "covered_by_draft_count": self.covered_by_draft_count,
            "uncovered_coverage_ids": self.uncovered_coverage_ids,
            "coverage_to_test_cases": self.coverage_to_test_cases,
        }


@dataclass
class UnresolvedTestDesignItem:
    item_id: str
    item_kind: str
    description: str
    related_test_case_ids: list[str]
    reason: str
    suggested_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_kind": self.item_kind,
            "description": self.description,
            "related_test_case_ids": self.related_test_case_ids,
            "reason": self.reason,
            "suggested_action": self.suggested_action,
        }


@dataclass
class TestCaseDraftRequest:
    source_path: Path
    function_signature: Any
    global_access: Any
    call_report: Any
    coverage_design: Any
    boundary_candidates: Any
    generation_policy: TestCaseGenerationPolicy


@dataclass
class TestCaseDraftReport:
    source_path: Path
    source_sha256: str
    function_name: str
    status: str
    generation_policy: TestCaseGenerationPolicy
    test_cases: list[TestCaseDraft]
    additional_case_candidates: list[TestCaseDraft]
    coverage_summary: CoverageDraftSummary
    unresolved_items: list[UnresolvedTestDesignItem] = field(default_factory=list)
    warnings: list[TestCaseDraftWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {"path": path_text(self.source_path), "sha256": self.source_sha256},
            "function": {"name": self.function_name, "status": self.status},
            "generation_policy": self.generation_policy.to_dict(),
            "test_cases": [case.to_dict() for case in self.test_cases],
            "additional_case_candidates": [case.to_dict() for case in self.additional_case_candidates],
            "coverage_summary": self.coverage_summary.to_dict(),
            "unresolved_items": [item.to_dict() for item in self.unresolved_items],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
