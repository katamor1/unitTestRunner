from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .analysis_common import path_text
from .function_models import SourcePosition, SourceRange


@dataclass
class BranchAnalyzerWarning:
    code: str
    message: str
    line_number: int | None = None
    column: int | None = None
    text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.line_number is not None:
            value["line_number"] = self.line_number
        if self.column is not None:
            value["column"] = self.column
        if self.text is not None:
            value["text"] = self.text
        return value


@dataclass
class ConditionOperand:
    raw: str
    operand_kind: str
    resolved_as: str
    name: str | None
    literal_value: str | None
    position: SourcePosition
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "operand_kind": self.operand_kind,
            "resolved_as": self.resolved_as,
            "name": self.name,
            "literal_value": self.literal_value,
            "position": self.position.to_dict(),
            "confidence": self.confidence,
        }


@dataclass
class ConditionExpression:
    condition_id: str
    raw: str
    expression_range: SourceRange
    condition_kind: str
    operands: list[ConditionOperand] = field(default_factory=list)
    operators: list[str] = field(default_factory=list)
    related_variables: list[str] = field(default_factory=list)
    related_calls: list[str] = field(default_factory=list)
    complexity: str = "simple"
    active_state: str = "active"
    confidence: str = "medium"
    warnings: list[BranchAnalyzerWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "raw": self.raw,
            "expression_range": self.expression_range.to_dict(),
            "condition_kind": self.condition_kind,
            "operands": [operand.to_dict() for operand in self.operands],
            "operators": self.operators,
            "related_variables": self.related_variables,
            "related_calls": self.related_calls,
            "complexity": self.complexity,
            "active_state": self.active_state,
            "confidence": self.confidence,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass
class BranchNode:
    branch_id: str
    kind: str
    condition: ConditionExpression | None
    branch_range: SourceRange
    body_range: SourceRange | None = None
    parent_branch_id: str | None = None
    nesting_level: int = 0
    has_else: bool = False
    else_branch_id: str | None = None
    active_state: str = "active"
    confidence: str = "medium"
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "kind": self.kind,
            "condition": self.condition.to_dict() if self.condition else None,
            "branch_range": self.branch_range.to_dict(),
            "body_range": self.body_range.to_dict() if self.body_range else None,
            "parent_branch_id": self.parent_branch_id,
            "nesting_level": self.nesting_level,
            "has_else": self.has_else,
            "else_branch_id": self.else_branch_id,
            "active_state": self.active_state,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class CaseNode:
    case_id: str
    label_raw: str
    label_kind: str
    label_value: str | None
    case_range: SourceRange
    body_range: SourceRange | None = None
    fallthrough_candidate: bool = False
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "label_raw": self.label_raw,
            "label_kind": self.label_kind,
            "label_value": self.label_value,
            "case_range": self.case_range.to_dict(),
            "body_range": self.body_range.to_dict() if self.body_range else None,
            "fallthrough_candidate": self.fallthrough_candidate,
            "confidence": self.confidence,
        }


@dataclass
class SwitchNode:
    switch_id: str
    expression: ConditionExpression
    switch_range: SourceRange
    cases: list[CaseNode] = field(default_factory=list)
    has_default: bool = False
    active_state: str = "active"
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "switch_id": self.switch_id,
            "expression": self.expression.to_dict(),
            "switch_range": self.switch_range.to_dict(),
            "cases": [case.to_dict() for case in self.cases],
            "has_default": self.has_default,
            "active_state": self.active_state,
            "confidence": self.confidence,
        }


@dataclass
class LoopNode:
    loop_id: str
    kind: str
    condition: ConditionExpression | None
    initializer_raw: str | None
    increment_raw: str | None
    loop_range: SourceRange
    body_range: SourceRange | None = None
    coverage_hints: list[str] = field(default_factory=list)
    active_state: str = "active"
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "kind": self.kind,
            "condition": self.condition.to_dict() if self.condition else None,
            "initializer_raw": self.initializer_raw,
            "increment_raw": self.increment_raw,
            "loop_range": self.loop_range.to_dict(),
            "body_range": self.body_range.to_dict() if self.body_range else None,
            "coverage_hints": self.coverage_hints,
            "active_state": self.active_state,
            "confidence": self.confidence,
        }


@dataclass
class TernaryNode:
    ternary_id: str
    condition: ConditionExpression
    true_expression_raw: str
    false_expression_raw: str
    expression_range: SourceRange
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ternary_id": self.ternary_id,
            "condition": self.condition.to_dict(),
            "true_expression_raw": self.true_expression_raw,
            "false_expression_raw": self.false_expression_raw,
            "expression_range": self.expression_range.to_dict(),
            "confidence": self.confidence,
        }


@dataclass
class ReturnPath:
    return_id: str
    return_range: SourceRange
    expression_raw: str | None
    return_kind: str
    related_variables: list[str] = field(default_factory=list)
    related_calls: list[str] = field(default_factory=list)
    active_state: str = "active"
    confidence: str = "medium"
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "return_id": self.return_id,
            "return_range": self.return_range.to_dict(),
            "expression_raw": self.expression_raw,
            "return_kind": self.return_kind,
            "related_variables": self.related_variables,
            "related_calls": self.related_calls,
            "active_state": self.active_state,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class CoverageItem:
    coverage_id: str
    coverage_type: str
    target_id: str
    purpose: str
    condition_value: str | None = None
    required_state: str | None = None
    related_variables: list[str] = field(default_factory=list)
    related_calls: list[str] = field(default_factory=list)
    review_required: bool = True
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_id": self.coverage_id,
            "coverage_type": self.coverage_type,
            "target_id": self.target_id,
            "purpose": self.purpose,
            "condition_value": self.condition_value,
            "required_state": self.required_state,
            "related_variables": self.related_variables,
            "related_calls": self.related_calls,
            "review_required": self.review_required,
            "confidence": self.confidence,
        }


@dataclass
class CoverageDesignReport:
    source_path: Path
    source_sha256: str
    function_name: str
    status: str
    branches: list[BranchNode] = field(default_factory=list)
    switches: list[SwitchNode] = field(default_factory=list)
    loops: list[LoopNode] = field(default_factory=list)
    ternaries: list[TernaryNode] = field(default_factory=list)
    return_paths: list[ReturnPath] = field(default_factory=list)
    condition_expressions: list[ConditionExpression] = field(default_factory=list)
    coverage_items: list[CoverageItem] = field(default_factory=list)
    warnings: list[BranchAnalyzerWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {"path": path_text(self.source_path), "sha256": self.source_sha256},
            "function": {"name": self.function_name, "status": self.status},
            "branches": [branch.to_dict() for branch in self.branches],
            "switches": [switch.to_dict() for switch in self.switches],
            "loops": [loop.to_dict() for loop in self.loops],
            "ternaries": [ternary.to_dict() for ternary in self.ternaries],
            "return_paths": [path.to_dict() for path in self.return_paths],
            "condition_expressions": [condition.to_dict() for condition in self.condition_expressions],
            "coverage_items": [item.to_dict() for item in self.coverage_items],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
