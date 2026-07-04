from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _path_text(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


@dataclass
class SourceWarning:
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
class SourceReadResult:
    path: Path
    encoding: str
    text: str
    newline: str | None
    sha256: str
    line_count: int
    warnings: list[SourceWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": _path_text(self.path),
            "encoding": self.encoding,
            "newline": self.newline,
            "sha256": self.sha256,
            "line_count": self.line_count,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass
class MaskedRange:
    kind: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    preview: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start_line": self.start_line,
            "start_column": self.start_column,
            "end_line": self.end_line,
            "end_column": self.end_column,
            "preview": self.preview,
        }


@dataclass
class LineMapEntry:
    original_line: int
    masked_line: int
    original_start_offset: int
    masked_start_offset: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_line": self.original_line,
            "masked_line": self.masked_line,
            "original_start_offset": self.original_start_offset,
            "masked_start_offset": self.masked_start_offset,
        }


@dataclass
class MaskedSource:
    original_path: Path
    original_text: str
    masked_text: str
    line_map: list[LineMapEntry]
    masked_ranges: list[MaskedRange]
    warnings: list[SourceWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_path": _path_text(self.original_path),
            "line_map": [item.to_dict() for item in self.line_map],
            "masked_ranges": [item.to_dict() for item in self.masked_ranges],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass
class PreprocessorDirective:
    kind: str
    line_number: int
    column: int
    raw: str
    argument: str
    active_state: str
    nesting_level: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "line_number": self.line_number,
            "column": self.column,
            "raw": self.raw,
            "argument": self.argument,
            "active_state": self.active_state,
            "nesting_level": self.nesting_level,
        }


@dataclass
class MacroDefinition:
    name: str
    value: str | None
    parameters: list[str] | None
    line_number: int
    is_function_like: bool
    active_state: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "parameters": self.parameters,
            "line_number": self.line_number,
            "is_function_like": self.is_function_like,
            "active_state": self.active_state,
        }


@dataclass
class IncludeDirective:
    target: str
    style: str
    line_number: int
    resolved_candidates: list[Path]
    exists: bool | None
    active_state: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "style": self.style,
            "line_number": self.line_number,
            "resolved_candidates": [_path_text(path) for path in self.resolved_candidates],
            "exists": self.exists,
            "active_state": self.active_state,
        }


@dataclass
class LexToken:
    kind: str
    value: str
    line_number: int
    column: int
    start_offset: int
    end_offset: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "line_number": self.line_number,
            "column": self.column,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
        }


@dataclass
class SourceDigest:
    source: SourceReadResult
    masked_source: MaskedSource
    directives: list[PreprocessorDirective]
    includes: list[IncludeDirective]
    macros: list[MacroDefinition]
    tokens: list[LexToken]
    warnings: list[SourceWarning] = field(default_factory=list)
    masked_source_path: Path | None = None
    schema_version: str = "0.1"

    def to_dict(self, include_tokens: bool = True) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": self.schema_version,
            "source": self.source.to_dict(),
            "masking": {
                "masked_source_path": _path_text(self.masked_source_path),
                "masked_ranges": [item.to_dict() for item in self.masked_source.masked_ranges],
            },
            "preprocessor": {
                "includes": [item.to_dict() for item in self.includes],
                "macros": [item.to_dict() for item in self.macros],
                "directives": [item.to_dict() for item in self.directives],
            },
            "token_summary": _token_summary(self.tokens),
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
        if include_tokens:
            value["tokens"] = [token.to_dict() for token in self.tokens]
        return value


def _token_summary(tokens: list[LexToken]) -> dict[str, int]:
    summary = {
        "identifier_count": 0,
        "keyword_count": 0,
        "number_count": 0,
        "operator_count": 0,
        "punctuation_count": 0,
        "unknown_count": 0,
    }
    for token in tokens:
        key = f"{token.kind}_count"
        if key in summary:
            summary[key] += 1
    return summary
