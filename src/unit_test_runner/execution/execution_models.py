from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .blocker_models import BlockerPublicationResult
    from .evidence_paths import EvidencePaths
    from .run_paths import RunPaths


def _path_text(path: Path | None) -> str | None:
    if path is None:
        return None
    return path.as_posix()


@dataclass(frozen=True)
class TestRunRequest:
    workspace: Path
    executable: Path | None
    timeout_seconds: int
    allow_placeholder_tests: bool
    run_id: str | None = None


@dataclass
class TestExecutionPolicy:
    run_tests: bool = False
    dry_run: bool = True
    timeout_seconds: int = 60
    require_successful_build_probe: bool = True
    allow_placeholder_tests: bool = True
    treat_placeholder_as_inconclusive: bool = True
    capture_environment: bool = True
    overwrite_existing_logs: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_tests": self.run_tests,
            "dry_run": self.dry_run,
            "timeout_seconds": self.timeout_seconds,
            "require_successful_build_probe": self.require_successful_build_probe,
            "allow_placeholder_tests": self.allow_placeholder_tests,
            "treat_placeholder_as_inconclusive": self.treat_placeholder_as_inconclusive,
            "capture_environment": self.capture_environment,
            "overwrite_existing_logs": self.overwrite_existing_logs,
        }


@dataclass
class TestExecutionWarning:
    code: str
    message: str
    related_test_case_id: str | None = None
    related_file: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "related_test_case_id": self.related_test_case_id,
            "related_file": _path_text(self.related_file),
        }


@dataclass
class ExecutableInfo:
    path: Path
    exists: bool
    sha256: str | None
    generated_from: str | None
    build_probe_status: str
    warnings: list[TestExecutionWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": _path_text(self.path),
            "exists": self.exists,
            "sha256": self.sha256,
            "generated_from": self.generated_from,
            "build_probe_status": self.build_probe_status,
            "warnings": [item.to_dict() for item in self.warnings],
        }


@dataclass
class ExecutionCommand:
    command_line: str
    working_directory: Path
    environment_summary: dict[str, str]
    timeout_seconds: int
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_line": self.command_line,
            "working_directory": _path_text(self.working_directory),
            "environment_summary": self.environment_summary,
            "timeout_seconds": self.timeout_seconds,
            "dry_run": self.dry_run,
        }


@dataclass
class ExecutionCommandResult:
    exit_code: int | None
    started_at: str | None
    finished_at: str | None
    duration_ms: int | None
    stdout_log: Path | None
    stderr_log: Path | None
    combined_log: Path | None
    timed_out: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "stdout_log": _path_text(self.stdout_log),
            "stderr_log": _path_text(self.stderr_log),
            "combined_log": _path_text(self.combined_log),
            "timed_out": self.timed_out,
        }


@dataclass
class AssertionResult:
    assertion_kind: str
    status: str
    file: Path | None
    line_number: int | None
    expected: str | None
    actual: str | None
    expression: str | None
    message: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion_kind": self.assertion_kind,
            "status": self.status,
            "file": _path_text(self.file),
            "line_number": self.line_number,
            "expected": self.expected,
            "actual": self.actual,
            "expression": self.expression,
            "message": self.message,
        }


@dataclass
class TestResultSummary:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    inconclusive: int = 0
    assertion_failures: int = 0
    parser_confidence: str = "low"
    crashed: int = 0
    not_run: int = 0
    started: int = 0
    completed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "inconclusive": self.inconclusive,
            "assertion_failures": self.assertion_failures,
            "parser_confidence": self.parser_confidence,
            "crashed": self.crashed,
            "not_run": self.not_run,
            "started": self.started,
            "completed": self.completed,
        }


@dataclass
class TestCaseExecutionResult:
    test_case_id: str | None
    generated_function_name: str | None
    status: str
    exit_related: bool
    assertions: list[AssertionResult] = field(default_factory=list)
    related_coverage_ids: list[str] = field(default_factory=list)
    review_required: bool = False
    evidence: str = ""
    warnings: list[TestExecutionWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_case_id": self.test_case_id,
            "generated_function_name": self.generated_function_name,
            "status": self.status,
            "exit_related": self.exit_related,
            "assertions": [item.to_dict() for item in self.assertions],
            "related_coverage_ids": self.related_coverage_ids,
            "review_required": self.review_required,
            "evidence": self.evidence,
            "warnings": [item.to_dict() for item in self.warnings],
        }


@dataclass
class ExecutionReviewItem:
    item_id: str
    item_kind: str
    related_test_case_id: str | None
    description: str
    suggested_action: str
    severity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_kind": self.item_kind,
            "related_test_case_id": self.related_test_case_id,
            "description": self.description,
            "suggested_action": self.suggested_action,
            "severity": self.severity,
        }


@dataclass
class EvidenceFile:
    path: Path
    file_kind: str
    required: bool
    exists: bool
    sha256: str | None
    integrity_status: Literal["valid", "missing", "hash_mismatch"]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": _path_text(self.path),
            "file_kind": self.file_kind,
            "required": self.required,
            "exists": self.exists,
            "sha256": self.sha256,
            "integrity_status": self.integrity_status,
            "description": self.description,
        }


@dataclass
class EvidenceSummary:
    build_probe_status: str
    test_execution_status: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    inconclusive_tests: int
    unresolved_review_count: int
    test_green: bool
    ready_for_review: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "build_probe_status": self.build_probe_status,
            "test_execution_status": self.test_execution_status,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "inconclusive_tests": self.inconclusive_tests,
            "unresolved_review_count": self.unresolved_review_count,
            "test_green": self.test_green,
            "ready_for_review": self.ready_for_review,
        }


@dataclass
class EvidenceManifest:
    function_name: str
    workspace_root: Path
    created_at: str
    source_files: list[EvidenceFile]
    generated_files: list[EvidenceFile]
    build_reports: list[EvidenceFile]
    test_reports: list[EvidenceFile]
    logs: list[EvidenceFile]
    unresolved_items: list[ExecutionReviewItem]
    summary: EvidenceSummary
    schema_version: str = "0.1"
    evidence_paths: EvidencePaths | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "function": self.function_name,
            "workspace_root": _path_text(self.workspace_root),
            "created_at": self.created_at,
            "source_files": [item.to_dict() for item in self.source_files],
            "generated_files": [item.to_dict() for item in self.generated_files],
            "build_reports": [item.to_dict() for item in self.build_reports],
            "test_reports": [item.to_dict() for item in self.test_reports],
            "logs": [item.to_dict() for item in self.logs],
            "unresolved_items": [item.to_dict() for item in self.unresolved_items],
            "summary": self.summary.to_dict(),
        }


@dataclass
class TestExecutionReport:
    source_path: Path | None
    function_name: str
    status: str
    executed: bool
    executable: ExecutableInfo | None
    command: ExecutionCommand | None
    command_result: ExecutionCommandResult | None
    parsed_result: TestResultSummary | None
    case_results: list[TestCaseExecutionResult]
    unresolved_review_items: list[ExecutionReviewItem]
    evidence_files: list[EvidenceFile]
    warnings: list[TestExecutionWarning]
    policy: TestExecutionPolicy
    schema_version: str = "0.1"
    run_paths: RunPaths | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    blocker_publication: BlockerPublicationResult | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": {"path": _path_text(self.source_path)},
            "function": {"name": self.function_name, "status": self.status},
            "executed": self.executed,
            "executable": self.executable.to_dict() if self.executable else None,
            "command": self.command.to_dict() if self.command else None,
            "command_result": self.command_result.to_dict() if self.command_result else None,
            "parsed_result": self.parsed_result.to_dict() if self.parsed_result else None,
            "case_results": [item.to_dict() for item in self.case_results],
            "unresolved_review_items": [item.to_dict() for item in self.unresolved_review_items],
            "evidence_files": [item.to_dict() for item in self.evidence_files],
            "warnings": [item.to_dict() for item in self.warnings],
            "policy": self.policy.to_dict(),
        }
