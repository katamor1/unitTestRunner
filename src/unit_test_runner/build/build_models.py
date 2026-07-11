from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _path_text(path: Path | None) -> str | None:
    if path is None:
        return None
    return path.as_posix()


@dataclass
class BuildDiagnostic:
    code: str
    severity: str
    message: str
    file: Path | None = None
    line_number: int | None = None
    raw: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "file": _path_text(self.file),
            "line_number": self.line_number,
            "raw": self.raw,
        }


@dataclass
class MissingInclude:
    include_name: str
    included_from: Path | None
    line_number: int | None
    diagnostic_raw: str
    candidate_dirs: list[Path] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "include_name": self.include_name,
            "included_from": _path_text(self.included_from),
            "line_number": self.line_number,
            "diagnostic_raw": self.diagnostic_raw,
            "candidate_dirs": [_path_text(item) for item in self.candidate_dirs],
        }


@dataclass
class UnresolvedSymbol:
    symbol_name: str
    referenced_from: str | None
    diagnostic_code: str
    diagnostic_raw: str
    stub_candidate: bool = False
    related_call_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol_name": self.symbol_name,
            "referenced_from": self.referenced_from,
            "diagnostic_code": self.diagnostic_code,
            "diagnostic_raw": self.diagnostic_raw,
            "stub_candidate": self.stub_candidate,
            "related_call_name": self.related_call_name,
        }


@dataclass
class PchIssue:
    issue_kind: str
    header: str | None
    diagnostic_raw: str
    suggested_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_kind": self.issue_kind,
            "header": self.header,
            "diagnostic_raw": self.diagnostic_raw,
            "suggested_action": self.suggested_action,
        }


@dataclass
class VC6CompatibilityIssue:
    issue_kind: str
    file: Path | None
    line_number: int | None
    diagnostic_raw: str
    suggested_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_kind": self.issue_kind,
            "file": _path_text(self.file),
            "line_number": self.line_number,
            "diagnostic_raw": self.diagnostic_raw,
            "suggested_action": self.suggested_action,
        }


@dataclass
class BuildPathEntry:
    raw: str
    workspace_path: Path | None
    original_path: Path | None
    exists: bool
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "workspace_path": _path_text(self.workspace_path),
            "original_path": _path_text(self.original_path),
            "exists": self.exists,
            "source": self.source,
        }


@dataclass(frozen=True)
class LinkLibraryEntry:
    path: Path
    source: str
    link_order: int
    project_name: str | None = None
    configuration: str | None = None
    exists: bool = True
    scan_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": _path_text(self.path),
            "source": self.source,
            "link_order": self.link_order,
            "project_name": self.project_name,
            "configuration": self.configuration,
            "exists": self.exists,
            "scan_status": self.scan_status,
        }


@dataclass
class WorkspaceFile:
    workspace_path: Path
    file_kind: str
    source_path: Path | None = None
    sha256: str | None = None
    copied: bool = False
    generated: bool = False
    required: bool = True
    exists: bool = True
    warnings: list[BuildDiagnostic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": _path_text(self.source_path),
            "workspace_path": _path_text(self.workspace_path),
            "file_kind": self.file_kind,
            "sha256": self.sha256,
            "copied": self.copied,
            "generated": self.generated,
            "required": self.required,
            "exists": self.exists,
            "warnings": [item.to_dict() for item in self.warnings],
        }


@dataclass
class CompileUnit:
    source_file: Path
    object_file: Path
    include_dirs: list[BuildPathEntry]
    defines: list[str]
    compiler_options: list[str]
    command: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": _path_text(self.source_file),
            "object_file": _path_text(self.object_file),
            "include_dirs": [item.to_dict() for item in self.include_dirs],
            "defines": self.defines,
            "compiler_options": self.compiler_options,
            "command": self.command,
            "required": self.required,
        }


@dataclass
class BuildCommand:
    command_id: str
    command_kind: str
    working_directory: Path
    command_line: str
    log_file: Path | None = None
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_kind": self.command_kind,
            "working_directory": _path_text(self.working_directory),
            "command_line": self.command_line,
            "log_file": _path_text(self.log_file),
            "dry_run": self.dry_run,
        }


@dataclass
class BuildCommandResult:
    command_id: str
    command_kind: str
    command_line: str
    exit_code: int
    stdout_log: Path | None
    stderr_log: Path | None
    combined_log: Path | None
    diagnostics: list[BuildDiagnostic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_kind": self.command_kind,
            "command_line": self.command_line,
            "exit_code": self.exit_code,
            "stdout_log": _path_text(self.stdout_log),
            "stderr_log": _path_text(self.stderr_log),
            "combined_log": _path_text(self.combined_log),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass
class BuildWorkspaceReport:
    source_path: Path
    function_name: str
    status: str
    output_root: Path
    copied_files: list[WorkspaceFile]
    referenced_files: list[WorkspaceFile]
    generated_build_files: list[WorkspaceFile]
    compile_units: list[CompileUnit]
    link_units: list[Path]
    include_dirs: list[BuildPathEntry]
    defines: list[str]
    compiler_options: list[str]
    build_commands: list[BuildCommand]
    diagnostics: list[BuildDiagnostic]
    link_libraries: list[LinkLibraryEntry] = field(default_factory=list)
    library_dirs: list[Path] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {"path": _path_text(self.source_path)},
            "function": {"name": self.function_name, "status": self.status},
            "output_root": _path_text(self.output_root),
            "copied_files": [item.to_dict() for item in self.copied_files],
            "referenced_files": [item.to_dict() for item in self.referenced_files],
            "generated_build_files": [item.to_dict() for item in self.generated_build_files],
            "compile_units": [item.to_dict() for item in self.compile_units],
            "link_units": [_path_text(item) for item in self.link_units],
            "include_dirs": [item.to_dict() for item in self.include_dirs],
            "defines": self.defines,
            "compiler_options": self.compiler_options,
            "build_commands": [item.to_dict() for item in self.build_commands],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "link_libraries": [item.to_dict() for item in self.link_libraries],
            "library_dirs": [_path_text(item) for item in self.library_dirs],
        }


@dataclass
class BuildProbeReport:
    source_path: Path
    function_name: str
    status: str
    executed: bool
    exit_code: int | None
    commands: list[BuildCommandResult]
    diagnostics: list[BuildDiagnostic]
    missing_includes: list[MissingInclude]
    unresolved_symbols: list[UnresolvedSymbol]
    pch_issues: list[PchIssue]
    vc6_compatibility_issues: list[VC6CompatibilityIssue]
    log_files: list[Path]
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {"path": _path_text(self.source_path)},
            "function": {"name": self.function_name, "status": self.status},
            "executed": self.executed,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "commands": [item.to_dict() for item in self.commands],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "missing_includes": [item.to_dict() for item in self.missing_includes],
            "unresolved_symbols": [item.to_dict() for item in self.unresolved_symbols],
            "pch_issues": [item.to_dict() for item in self.pch_issues],
            "vc6_compatibility_issues": [item.to_dict() for item in self.vc6_compatibility_issues],
            "log_files": [_path_text(item) for item in self.log_files],
        }
