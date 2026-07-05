from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .analysis_common import path_text


@dataclass
class BoundaryCandidateWarning:
    code: str
    message: str
    related_condition_id: str | None = None
    text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.related_condition_id is not None:
            value["related_condition_id"] = self.related_condition_id
        if self.text is not None:
            value["text"] = self.text
        return value


@dataclass
class InputValueCandidate:
    candidate_id: str
    target_name: str
    target_kind: str
    value_expression: str
    value_kind: str
    source: str
    related_condition_id: str | None
    related_coverage_ids: list[str]
    purpose: str
    confidence: str
    review_required: bool
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "target_name": self.target_name,
            "target_kind": self.target_kind,
            "value_expression": self.value_expression,
            "value_kind": self.value_kind,
            "source": self.source,
            "related_condition_id": self.related_condition_id,
            "related_coverage_ids": self.related_coverage_ids,
            "purpose": self.purpose,
            "confidence": self.confidence,
            "review_required": self.review_required,
            "evidence": self.evidence,
        }


@dataclass
class StateValueCandidate:
    candidate_id: str
    variable_name: str
    scope: str
    value_expression: str
    value_kind: str
    related_condition_id: str | None
    related_coverage_ids: list[str]
    setup_hint: str
    confidence: str
    review_required: bool
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "variable_name": self.variable_name,
            "scope": self.scope,
            "value_expression": self.value_expression,
            "value_kind": self.value_kind,
            "related_condition_id": self.related_condition_id,
            "related_coverage_ids": self.related_coverage_ids,
            "setup_hint": self.setup_hint,
            "confidence": self.confidence,
            "review_required": self.review_required,
            "evidence": self.evidence,
        }


@dataclass
class StubReturnCandidate:
    candidate_id: str
    call_name: str
    value_expression: str
    value_kind: str
    related_call_id: str | None
    related_condition_id: str | None
    related_coverage_ids: list[str]
    purpose: str
    confidence: str
    review_required: bool
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "call_name": self.call_name,
            "value_expression": self.value_expression,
            "value_kind": self.value_kind,
            "related_call_id": self.related_call_id,
            "related_condition_id": self.related_condition_id,
            "related_coverage_ids": self.related_coverage_ids,
            "purpose": self.purpose,
            "confidence": self.confidence,
            "review_required": self.review_required,
            "evidence": self.evidence,
        }


@dataclass
class EquivalenceClass:
    class_id: str
    target_name: str
    target_kind: str
    class_name: str
    representative_values: list[str]
    description: str
    related_conditions: list[str]
    related_coverage_ids: list[str]
    confidence: str
    review_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_id": self.class_id,
            "target_name": self.target_name,
            "target_kind": self.target_kind,
            "class_name": self.class_name,
            "representative_values": self.representative_values,
            "description": self.description,
            "related_conditions": self.related_conditions,
            "related_coverage_ids": self.related_coverage_ids,
            "confidence": self.confidence,
            "review_required": self.review_required,
        }


@dataclass
class BoundaryGroup:
    group_id: str
    target_name: str
    boundary_expression: str
    operator: str
    candidates: list[str]
    related_condition_id: str
    confidence: str
    review_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "target_name": self.target_name,
            "boundary_expression": self.boundary_expression,
            "operator": self.operator,
            "candidates": self.candidates,
            "related_condition_id": self.related_condition_id,
            "confidence": self.confidence,
            "review_required": self.review_required,
        }


@dataclass
class CandidateCoverageLink:
    coverage_id: str
    candidate_ids: list[str]
    link_reason: str
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_id": self.coverage_id,
            "candidate_ids": self.candidate_ids,
            "link_reason": self.link_reason,
            "confidence": self.confidence,
        }


@dataclass
class BoundaryCandidateRequest:
    source_path: Path
    function_signature: Any
    global_access: Any
    call_report: Any
    coverage_design: Any


@dataclass
class BoundaryEquivalenceReport:
    source_path: Path
    source_sha256: str
    function_name: str
    status: str
    input_candidates: list[InputValueCandidate] = field(default_factory=list)
    state_candidates: list[StateValueCandidate] = field(default_factory=list)
    stub_return_candidates: list[StubReturnCandidate] = field(default_factory=list)
    equivalence_classes: list[EquivalenceClass] = field(default_factory=list)
    boundary_groups: list[BoundaryGroup] = field(default_factory=list)
    coverage_links: list[CandidateCoverageLink] = field(default_factory=list)
    warnings: list[BoundaryCandidateWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {"path": path_text(self.source_path), "sha256": self.source_sha256},
            "function": {"name": self.function_name, "status": self.status},
            "input_candidates": [candidate.to_dict() for candidate in self.input_candidates],
            "state_candidates": [candidate.to_dict() for candidate in self.state_candidates],
            "stub_return_candidates": [candidate.to_dict() for candidate in self.stub_return_candidates],
            "equivalence_classes": [item.to_dict() for item in self.equivalence_classes],
            "boundary_groups": [item.to_dict() for item in self.boundary_groups],
            "coverage_links": [link.to_dict() for link in self.coverage_links],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
