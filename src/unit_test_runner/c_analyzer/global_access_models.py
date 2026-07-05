from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .analysis_common import path_text
from .function_models import SourcePosition, SourceRange


@dataclass
class GlobalAccessWarning:
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
class VariableDeclaration:
    name: str
    scope: str
    storage_class: str | None
    type_raw: str
    declaration_range: SourceRange
    initializer_range: SourceRange | None = None
    is_array: bool = False
    is_pointer: bool = False
    is_struct_like: bool = False
    confidence: str = "medium"
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "scope": self.scope,
            "storage_class": self.storage_class,
            "type_raw": self.type_raw,
            "declaration_range": self.declaration_range.to_dict(),
            "initializer_range": self.initializer_range.to_dict() if self.initializer_range else None,
            "is_array": self.is_array,
            "is_pointer": self.is_pointer,
            "is_struct_like": self.is_struct_like,
            "confidence": self.confidence,
            "raw": self.raw,
        }


@dataclass
class IdentifierUse:
    name: str
    position: SourcePosition
    context: str
    token_index: int
    resolved_as: str
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "position": self.position.to_dict(),
            "context": self.context,
            "token_index": self.token_index,
            "resolved_as": self.resolved_as,
            "confidence": self.confidence,
        }


@dataclass
class VariableAccess:
    name: str
    access_kind: str
    scope: str
    position: SourcePosition
    expression_range: SourceRange
    access_path: str | None
    operator: str | None
    confidence: str
    evidence: str
    related_declaration: VariableDeclaration | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "access_kind": self.access_kind,
            "scope": self.scope,
            "position": self.position.to_dict(),
            "expression_range": self.expression_range.to_dict(),
            "access_path": self.access_path,
            "operator": self.operator,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "related_declaration": self.related_declaration.to_dict() if self.related_declaration else None,
        }


@dataclass
class ParameterAccess:
    parameter_name: str
    access_kind: str
    position: SourcePosition
    expression_range: SourceRange
    access_path: str | None
    direction_hint_before_body: str
    body_access_hint: str
    confidence: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "access_kind": self.access_kind,
            "position": self.position.to_dict(),
            "expression_range": self.expression_range.to_dict(),
            "access_path": self.access_path,
            "direction_hint_before_body": self.direction_hint_before_body,
            "body_access_hint": self.body_access_hint,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class SideEffectCandidate:
    kind: str
    name: str | None
    position: SourcePosition
    expression_range: SourceRange
    reason: str
    confidence: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "position": self.position.to_dict(),
            "expression_range": self.expression_range.to_dict(),
            "reason": self.reason,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class GlobalAccessRequest:
    source_path: Path
    source_text: str
    masked_text: str
    tokens: list[Any]
    function_location: Any
    function_signature: Any


@dataclass
class GlobalAccessReport:
    source_path: Path
    source_sha256: str
    function_name: str
    status: str
    file_scope_declarations: list[VariableDeclaration] = field(default_factory=list)
    local_declarations: list[VariableDeclaration] = field(default_factory=list)
    parameter_accesses: list[ParameterAccess] = field(default_factory=list)
    global_accesses: list[VariableAccess] = field(default_factory=list)
    unresolved_identifiers: list[IdentifierUse] = field(default_factory=list)
    side_effect_candidates: list[SideEffectCandidate] = field(default_factory=list)
    warnings: list[GlobalAccessWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {"path": path_text(self.source_path), "sha256": self.source_sha256},
            "function": {"name": self.function_name, "status": self.status},
            "file_scope_declarations": [item.to_dict() for item in self.file_scope_declarations],
            "local_declarations": [item.to_dict() for item in self.local_declarations],
            "parameter_accesses": [item.to_dict() for item in self.parameter_accesses],
            "global_accesses": [item.to_dict() for item in self.global_accesses],
            "unresolved_identifiers": [item.to_dict() for item in self.unresolved_identifiers],
            "side_effect_candidates": [item.to_dict() for item in self.side_effect_candidates],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
