from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _path_text(path: Path | None) -> str | None:
    return path.as_posix() if path is not None else None


@dataclass
class DependencyEvidence:
    kind: str
    detail: str
    source: str
    weight: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail, "source": self.source, "weight": self.weight}


@dataclass
class DependencyRewriteSite:
    call_id: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "start": {"line": self.start_line, "column": self.start_column},
            "end": {"line": self.end_line, "column": self.end_column},
        }


@dataclass
class ResolvedParameter:
    index: int
    name: str | None
    type_raw: str
    pointer_level: int = 0
    qualifiers: list[str] = field(default_factory=list)
    is_variadic: bool = False
    canonical_type: str | None = None
    type_category: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "type_raw": self.type_raw,
            "pointer_level": self.pointer_level,
            "qualifiers": self.qualifiers,
            "is_variadic": self.is_variadic,
            "canonical_type": self.canonical_type,
            "type_category": self.type_category,
        }


@dataclass
class ResolvedSignature:
    resolution: str
    return_type_raw: str | None = None
    return_type_canonical: str | None = None
    return_type_category: str = "unknown"
    calling_convention: str | None = None
    parameters: list[ResolvedParameter] = field(default_factory=list)
    prototype: str | None = None
    declaration_source: Path | None = None
    definition_source: Path | None = None
    conflicts: list[str] = field(default_factory=list)
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution": self.resolution,
            "return_type_raw": self.return_type_raw,
            "return_type_canonical": self.return_type_canonical,
            "return_type_category": self.return_type_category,
            "calling_convention": self.calling_convention,
            "parameters": [item.to_dict() for item in self.parameters],
            "prototype": self.prototype,
            "declaration_source": _path_text(self.declaration_source),
            "definition_source": _path_text(self.definition_source),
            "conflicts": self.conflicts,
            "confidence": self.confidence,
        }


@dataclass
class DependencyPolicyEntry:
    callee: str
    target_kind: str
    configured_mode: str
    resolved_mode: str
    review_status: str
    signature: ResolvedSignature
    implementation_source: Path | None = None
    related_call_ids: list[str] = field(default_factory=list)
    rewrite_sites: list[DependencyRewriteSite] = field(default_factory=list)
    evidence: list[DependencyEvidence] = field(default_factory=list)
    shared_globals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "callee": self.callee,
            "target_kind": self.target_kind,
            "configured_mode": self.configured_mode,
            "resolved_mode": self.resolved_mode,
            "review_status": self.review_status,
            "signature": self.signature.to_dict(),
            "implementation_source": _path_text(self.implementation_source),
            "related_call_ids": self.related_call_ids,
            "rewrite_sites": [item.to_dict() for item in self.rewrite_sites],
            "evidence": [item.to_dict() for item in self.evidence],
            "shared_globals": self.shared_globals,
            "warnings": self.warnings,
        }


@dataclass
class ExternalObjectPolicyEntry:
    symbol: str
    type_raw: str
    configured_mode: str
    resolved_mode: str
    review_status: str
    declaration_header: Path | None = None
    definition_source: Path | None = None
    definition_candidates: list[Path] = field(default_factory=list)
    evidence: list[DependencyEvidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "type_raw": self.type_raw,
            "configured_mode": self.configured_mode,
            "resolved_mode": self.resolved_mode,
            "review_status": self.review_status,
            "declaration_header": _path_text(self.declaration_header),
            "definition_source": _path_text(self.definition_source),
            "definition_candidates": [item.as_posix() for item in self.definition_candidates],
            "evidence": [item.to_dict() for item in self.evidence],
            "warnings": self.warnings,
        }


@dataclass
class DependencyPolicyReport:
    source_path: Path
    target_function: str
    status: str
    dependencies: list[DependencyPolicyEntry] = field(default_factory=list)
    external_objects: list[ExternalObjectPolicyEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {"path": self.source_path.as_posix()},
            "function": {"name": self.target_function, "status": self.status},
            "dependencies": [item.to_dict() for item in self.dependencies],
            "external_objects": [item.to_dict() for item in self.external_objects],
            "warnings": self.warnings,
        }
