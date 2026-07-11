from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .analysis_common import path_text
from .function_models import SourcePosition, SourceRange
from .global_access_models import IdentifierUse


@dataclass
class CallAnalyzerWarning:
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


@dataclass(frozen=True)
class LinkProvider:
    library: Path
    symbol: str
    provider_kind: str
    source: str
    link_order: int
    project_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "library": path_text(self.library),
            "symbol": self.symbol,
            "provider_kind": self.provider_kind,
            "source": self.source,
            "link_order": self.link_order,
            "project_name": self.project_name,
        }


@dataclass
class ReturnUsage:
    usage_kind: str
    consumer_range: SourceRange | None = None
    assigned_to: str | None = None
    compared_with: str | None = None
    evidence: str = ""
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "usage_kind": self.usage_kind,
            "consumer_range": self.consumer_range.to_dict() if self.consumer_range else None,
            "assigned_to": self.assigned_to,
            "compared_with": self.compared_with,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }


@dataclass
class CallArgument:
    index: int
    raw: str
    expression_range: SourceRange
    identifiers: list[IdentifierUse] = field(default_factory=list)
    argument_kind: str = "unknown"
    passing_mode_hint: str = "unknown"
    confidence: str = "medium"
    warnings: list[CallAnalyzerWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "raw": self.raw,
            "expression_range": self.expression_range.to_dict(),
            "identifiers": [identifier.to_dict() for identifier in self.identifiers],
            "argument_kind": self.argument_kind,
            "passing_mode_hint": self.passing_mode_hint,
            "confidence": self.confidence,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass
class FunctionCall:
    call_id: str
    name: str
    target_kind: str
    call_range: SourceRange
    name_position: SourcePosition
    arguments: list[CallArgument]
    return_usage: ReturnUsage
    nesting_level: int
    conditional_context: Any = None
    confidence: str = "medium"
    evidence: str = ""
    warnings: list[CallAnalyzerWarning] = field(default_factory=list)
    link_provider: LinkProvider | None = None
    link_providers: list[LinkProvider] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "name": self.name,
            "target_kind": self.target_kind,
            "call_range": self.call_range.to_dict(),
            "name_position": self.name_position.to_dict(),
            "arguments": [argument.to_dict() for argument in self.arguments],
            "return_usage": self.return_usage.to_dict(),
            "nesting_level": self.nesting_level,
            "conditional_context": self.conditional_context,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "warnings": [warning.to_dict() for warning in self.warnings],
            "link_provider": self.link_provider.to_dict() if self.link_provider else None,
            "link_providers": [provider.to_dict() for provider in self.link_providers],
        }


@dataclass
class StubCandidate:
    name: str
    reason: str
    target_kind: str
    call_count: int
    return_value_control_needed: bool
    argument_capture_needed: bool
    side_effect_control_needed: bool
    related_calls: list[str]
    confidence: str
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "reason": self.reason,
            "target_kind": self.target_kind,
            "call_count": self.call_count,
            "return_value_control_needed": self.return_value_control_needed,
            "argument_capture_needed": self.argument_capture_needed,
            "side_effect_control_needed": self.side_effect_control_needed,
            "related_calls": self.related_calls,
            "confidence": self.confidence,
            "tags": self.tags,
        }


@dataclass
class CallSideEffectCandidate:
    call_id: str
    call_name: str
    kind: str
    argument_index: int | None
    related_identifier: str | None
    reason: str
    confidence: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "call_name": self.call_name,
            "kind": self.kind,
            "argument_index": self.argument_index,
            "related_identifier": self.related_identifier,
            "reason": self.reason,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class CallAnalysisRequest:
    source_path: Path
    source_text: str
    masked_text: str
    tokens: list[Any]
    function_location: Any
    function_signature: Any
    global_access: Any


@dataclass
class CallReport:
    source_path: Path
    source_sha256: str
    function_name: str
    status: str
    calls: list[FunctionCall] = field(default_factory=list)
    stub_candidates: list[StubCandidate] = field(default_factory=list)
    side_effect_candidates: list[CallSideEffectCandidate] = field(default_factory=list)
    unresolved_calls: list[FunctionCall] = field(default_factory=list)
    warnings: list[CallAnalyzerWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {"path": path_text(self.source_path), "sha256": self.source_sha256},
            "function": {"name": self.function_name, "status": self.status},
            "calls": [call.to_dict() for call in self.calls],
            "stub_candidates": [candidate.to_dict() for candidate in self.stub_candidates],
            "side_effect_candidates": [candidate.to_dict() for candidate in self.side_effect_candidates],
            "unresolved_calls": [call.to_dict() for call in self.unresolved_calls],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
