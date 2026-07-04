from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .source_models import PreprocessorDirective


def _path_text(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


@dataclass
class SourcePosition:
    line: int
    column: int
    offset: int

    def to_dict(self) -> dict[str, int]:
        return {"line": self.line, "column": self.column, "offset": self.offset}


@dataclass
class SourceRange:
    start: SourcePosition
    end: SourcePosition

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}


@dataclass
class ConditionalContext:
    active_state: str
    nesting_level: int
    directives: list[PreprocessorDirective] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_state": self.active_state,
            "nesting_level": self.nesting_level,
            "directives": [directive.to_dict() for directive in self.directives],
        }


@dataclass
class FunctionLocatorWarning:
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
class FunctionCandidate:
    name: str
    kind: str
    confidence: str
    header_range: SourceRange
    body_range: SourceRange | None
    full_range: SourceRange
    opening_brace: SourcePosition | None
    closing_brace: SourcePosition | None
    storage_class_hint: str | None
    conditional_context: ConditionalContext | None
    signature_preview: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "confidence": self.confidence,
            "header_range": self.header_range.to_dict(),
            "body_range": self.body_range.to_dict() if self.body_range else None,
            "full_range": self.full_range.to_dict(),
            "opening_brace": self.opening_brace.to_dict() if self.opening_brace else None,
            "closing_brace": self.closing_brace.to_dict() if self.closing_brace else None,
            "storage_class_hint": self.storage_class_hint,
            "conditional_context": self.conditional_context.to_dict() if self.conditional_context else None,
            "signature_preview": self.signature_preview,
            "reason": self.reason,
        }


@dataclass
class FunctionLocation:
    function_name: str
    source_path: Path
    status: str
    selected_candidate: FunctionCandidate | None
    candidates: list[FunctionCandidate]
    warnings: list[FunctionLocatorWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {
                "path": _path_text(self.source_path),
            },
            "function": {
                "name": self.function_name,
                "status": self.status,
                "selected_candidate": self.selected_candidate.to_dict() if self.selected_candidate else None,
                "candidates": [candidate.to_dict() for candidate in self.candidates],
                "candidate_count": len(self.candidates),
            },
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
