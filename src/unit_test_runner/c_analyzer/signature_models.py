from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .analysis_common import path_text
from .function_models import SourceRange


@dataclass
class SignatureWarning:
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
class TypeInfo:
    raw: str
    normalized: str
    base_type: str | None
    qualifiers: list[str] = field(default_factory=list)
    storage_class: str | None = None
    pointer_level: int = 0
    is_const_pointer: bool | None = None
    is_struct: bool = False
    is_union: bool = False
    is_enum: bool = False
    is_typedef_like: bool = False
    is_function_pointer: bool = False
    is_array: bool = False
    array_dimensions: list[str] = field(default_factory=list)
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "normalized": self.normalized,
            "base_type": self.base_type,
            "qualifiers": self.qualifiers,
            "storage_class": self.storage_class,
            "pointer_level": self.pointer_level,
            "is_const_pointer": self.is_const_pointer,
            "is_struct": self.is_struct,
            "is_union": self.is_union,
            "is_enum": self.is_enum,
            "is_typedef_like": self.is_typedef_like,
            "is_function_pointer": self.is_function_pointer,
            "is_array": self.is_array,
            "array_dimensions": self.array_dimensions,
            "confidence": self.confidence,
        }


@dataclass
class ParameterInfo:
    index: int
    name: str | None
    type_info: TypeInfo
    raw: str
    direction_hint: str = "unknown"
    is_variadic: bool = False
    is_void: bool = False
    default_value: str | None = None
    confidence: str = "medium"
    warnings: list[SignatureWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "type": self.type_info.to_dict(),
            "raw": self.raw,
            "direction_hint": self.direction_hint,
            "is_variadic": self.is_variadic,
            "is_void": self.is_void,
            "default_value": self.default_value,
            "confidence": self.confidence,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass
class FunctionSignatureRequest:
    source_path: Path
    function_name: str
    source_text: str
    masked_text: str
    function_location: Any
    tokens: list[Any]


@dataclass
class FunctionSignature:
    function_name: str
    source_path: Path
    source_sha256: str
    status: str
    style: str
    confidence: str
    signature_range: SourceRange
    header_text_raw: str
    header_text_normalized: str
    storage_class: str | None
    calling_convention: str | None
    return_type: TypeInfo
    parameters: list[ParameterInfo]
    warnings: list[SignatureWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {
                "path": path_text(self.source_path),
                "sha256": self.source_sha256,
            },
            "function": {
                "name": self.function_name,
                "status": self.status,
                "style": self.style,
                "confidence": self.confidence,
                "signature_range": self.signature_range.to_dict(),
                "header_text_raw": self.header_text_raw,
                "header_text_normalized": self.header_text_normalized,
                "storage_class": self.storage_class,
                "calling_convention": self.calling_convention,
                "return_type": self.return_type.to_dict(),
                "parameters": [parameter.to_dict() for parameter in self.parameters],
                "takes_no_parameters": len(self.parameters) == 0,
            },
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
