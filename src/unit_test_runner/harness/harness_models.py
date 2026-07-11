from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _path_text(path: Path | None) -> str | None:
    if path is None:
        return None
    return path.as_posix()


@dataclass
class HarnessGenerationPolicy:
    c_dialect: str = "c90"
    compiler_profile: str = "vc6"
    generate_stub_headers: bool = True
    generate_argument_capture: bool = True
    generate_call_count_assertions: bool = True
    generate_placeholder_assertions: bool = True
    fail_on_unresolved_expected: bool = False
    overwrite_existing: bool = False
    c_encoding: str = "cp932"

    def to_dict(self) -> dict[str, Any]:
        return {
            "c_dialect": self.c_dialect,
            "compiler_profile": self.compiler_profile,
            "generate_stub_headers": self.generate_stub_headers,
            "generate_argument_capture": self.generate_argument_capture,
            "generate_call_count_assertions": self.generate_call_count_assertions,
            "generate_placeholder_assertions": self.generate_placeholder_assertions,
            "fail_on_unresolved_expected": self.fail_on_unresolved_expected,
            "overwrite_existing": self.overwrite_existing,
            "c_encoding": self.c_encoding,
        }


@dataclass
class HarnessGenerationWarning:
    code: str
    message: str
    related_file: Path | None = None
    related_test_case_id: str | None = None
    related_stub_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.related_file is not None:
            value["related_file"] = _path_text(self.related_file)
        if self.related_test_case_id is not None:
            value["related_test_case_id"] = self.related_test_case_id
        if self.related_stub_name is not None:
            value["related_stub_name"] = self.related_stub_name
        return value


@dataclass
class GeneratedFile:
    path: Path
    file_kind: str
    generated_from: list[str] = field(default_factory=list)
    sha256: str | None = None
    overwrite: bool = False
    review_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": _path_text(self.path),
            "file_kind": self.file_kind,
            "generated_from": self.generated_from,
            "sha256": self.sha256,
            "overwrite": self.overwrite,
            "review_required": self.review_required,
        }


@dataclass
class StubParameter:
    index: int
    name: str
    type_raw: str
    capture_strategy: str
    review_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "type_raw": self.type_raw,
            "capture_strategy": self.capture_strategy,
            "review_required": self.review_required,
        }


@dataclass
class StubSkeleton:
    stub_name: str
    original_function_name: str
    return_type_raw: str | None
    parameters: list[StubParameter]
    source_file: Path
    header_file: Path | None
    capabilities: list[str]
    related_call_ids: list[str]
    related_test_case_ids: list[str]
    warnings: list[HarnessGenerationWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stub_name": self.stub_name,
            "original_function_name": self.original_function_name,
            "return_type_raw": self.return_type_raw,
            "parameters": [item.to_dict() for item in self.parameters],
            "source_file": _path_text(self.source_file),
            "header_file": _path_text(self.header_file),
            "capabilities": self.capabilities,
            "related_call_ids": self.related_call_ids,
            "related_test_case_ids": self.related_test_case_ids,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass
class DependencyDispatch:
    callee: str
    dispatcher_name: str
    stub_invoke_name: str
    default_mode: str
    real_available: bool
    signature_resolution: str
    related_call_ids: list[str]
    rewrite_sites: list[dict[str, Any]]
    implementation_source: Path | None = None
    header_file: Path | None = None
    source_file: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "callee": self.callee,
            "dispatcher_name": self.dispatcher_name,
            "stub_invoke_name": self.stub_invoke_name,
            "default_mode": self.default_mode,
            "real_available": self.real_available,
            "signature_resolution": self.signature_resolution,
            "related_call_ids": self.related_call_ids,
            "rewrite_sites": self.rewrite_sites,
            "implementation_source": _path_text(self.implementation_source),
            "header_file": _path_text(self.header_file),
            "source_file": _path_text(self.source_file),
        }


@dataclass
class TestSkeleton:
    test_case_id: str
    function_name: str
    source_file: Path
    generated_function_name: str
    related_coverage_ids: list[str]
    related_stub_names: list[str]
    placeholder_count: int
    review_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_case_id": self.test_case_id,
            "function_name": self.function_name,
            "source_file": _path_text(self.source_file),
            "generated_function_name": self.generated_function_name,
            "related_coverage_ids": self.related_coverage_ids,
            "related_stub_names": self.related_stub_names,
            "placeholder_count": self.placeholder_count,
            "review_required": self.review_required,
        }


@dataclass
class UnresolvedPlaceholder:
    placeholder_id: str
    placeholder_kind: str
    name: str
    related_test_case_id: str | None
    related_stub_name: str | None
    reason: str
    suggested_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "placeholder_id": self.placeholder_id,
            "placeholder_kind": self.placeholder_kind,
            "name": self.name,
            "related_test_case_id": self.related_test_case_id,
            "related_stub_name": self.related_stub_name,
            "reason": self.reason,
            "suggested_action": self.suggested_action,
        }


@dataclass
class BuildHint:
    hint_id: str
    hint_kind: str
    message: str
    related_file: Path | None = None
    severity: str = "info"

    def to_dict(self) -> dict[str, Any]:
        return {
            "hint_id": self.hint_id,
            "hint_kind": self.hint_kind,
            "message": self.message,
            "related_file": _path_text(self.related_file),
            "severity": self.severity,
        }


@dataclass
class HarnessSkeletonReport:
    source_path: Path
    function_name: str
    status: str
    output_root: Path
    generation_policy: HarnessGenerationPolicy
    generated_files: list[GeneratedFile]
    stub_skeletons: list[StubSkeleton]
    test_skeletons: list[TestSkeleton]
    unresolved_placeholders: list[UnresolvedPlaceholder]
    build_hints: list[BuildHint]
    warnings: list[HarnessGenerationWarning]
    dependency_dispatches: list[DependencyDispatch] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {"path": _path_text(self.source_path)},
            "function": {"name": self.function_name, "status": self.status},
            "output_root": _path_text(self.output_root),
            "generation_policy": self.generation_policy.to_dict(),
            "generated_files": [item.to_dict() for item in self.generated_files],
            "stub_skeletons": [item.to_dict() for item in self.stub_skeletons],
            "test_skeletons": [item.to_dict() for item in self.test_skeletons],
            "unresolved_placeholders": [item.to_dict() for item in self.unresolved_placeholders],
            "build_hints": [item.to_dict() for item in self.build_hints],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "dependency_dispatches": [item.to_dict() for item in self.dependency_dispatches],
        }
