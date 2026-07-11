from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from unit_test_runner.contracts import (
    ArtifactKind,
    ContractMode,
    RunOutcome,
    load_artifact,
    migrate_payload,
)
from unit_test_runner.harness.c90_writer import sha256_file

from .execution_models import (
    AssertionResult,
    EvidenceFile,
    ExecutableInfo,
    ExecutionCommand,
    ExecutionCommandResult,
    ExecutionReviewItem,
    TestCaseExecutionResult,
    TestExecutionPolicy,
    TestExecutionReport,
    TestExecutionWarning,
    TestResultSummary,
)
from .run_paths import create_run_paths
from .test_result_writer import (
    build_artifact_payload,
    current_producer_commit,
    write_test_execution_reports,
    write_validated_artifact,
)


@dataclass(frozen=True)
class LoadedExecutionRun:
    run_id: str
    report_path: Path
    payload: dict[str, Any]
    report: TestExecutionReport


def load_test_execution_report(
    workspace: Path,
    run_id: str | None = None,
) -> TestExecutionReport:
    return load_execution_run(workspace, run_id).report


def load_execution_run(
    workspace: Path,
    run_id: str | None = None,
) -> LoadedExecutionRun:
    workspace = Path(workspace).resolve()
    selected_id = run_id
    expected_hash: str | None = None
    if selected_id is None:
        pointer_path = workspace / "reports" / "latest_run.json"
        if not pointer_path.is_file():
            legacy = workspace / "reports" / "test_execution_report.json"
            if legacy.is_file():
                return _import_legacy_execution_run(workspace, legacy)
            raise FileNotFoundError("No terminal test execution report is available.")
        pointer = load_artifact(
            pointer_path,
            expected_kind=ArtifactKind.LATEST_RUN_POINTER,
            mode=ContractMode.STRICT,
        )
        _require_valid(pointer.violations, pointer_path)
        data = pointer.payload["data"]
        selected_id = str(data["run_id"])
        reference = data["execution_report"]
        report_path = _workspace_path(workspace, reference["path"])
        expected_report_path = (
            workspace / "runs" / selected_id / "test_execution_report.json"
        ).resolve()
        if report_path != expected_report_path:
            raise ValueError(
                "Latest-run pointer run_id does not match its execution report path."
            )
        expected_hash = str(reference["sha256"])
    else:
        _validate_run_id(selected_id)
        report_path = workspace / "runs" / selected_id / "test_execution_report.json"
    if not report_path.is_file():
        raise FileNotFoundError(f"Test execution report does not exist: {report_path}")
    if expected_hash is not None and _sha256(report_path) != expected_hash:
        raise ValueError(f"Test execution report hash mismatch: {report_path}")
    loaded = load_artifact(
        report_path,
        expected_kind=ArtifactKind.TEST_EXECUTION_REPORT,
        mode=ContractMode.STRICT,
    )
    _require_valid(loaded.violations, report_path)
    report = _report_from_data(loaded.payload["data"], loaded.current_version)
    terminal = {outcome.value for outcome in RunOutcome if outcome is not RunOutcome.PLANNED}
    if report.status not in terminal:
        raise ValueError(
            f"Execution report is not terminal: status={report.status!r}"
        )
    return LoadedExecutionRun(selected_id, report_path, loaded.payload, report)


def _import_legacy_execution_run(
    workspace: Path,
    legacy_report: Path,
) -> LoadedExecutionRun:
    preflight_payload = json.loads(legacy_report.read_text(encoding="utf-8"))
    preflight_function = preflight_payload.get("function") or {}
    preflight_status = str(preflight_function.get("status") or "")
    normalized_preflight_status = (
        "timed_out" if preflight_status == "timeout" else preflight_status
    )
    terminal = {outcome.value for outcome in RunOutcome if outcome is not RunOutcome.PLANNED}
    if normalized_preflight_status not in terminal:
        raise ValueError(
            f"Legacy execution report is not terminal: status={preflight_status!r}"
        )
    run_id = (
        "imported-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + "-"
        + uuid4().hex[:8]
    )
    paths = create_run_paths(workspace, run_id)
    shutil.copy2(legacy_report, paths.execution_report)
    legacy_payload = json.loads(paths.execution_report.read_text(encoding="utf-8"))
    migrated = migrate_payload(
        ArtifactKind.TEST_EXECUTION_REPORT,
        legacy_payload,
        target_version="1.0.0",
    )
    data = migrated["data"]
    function = data.get("function") or {}
    raw_status = str(function.get("status") or "")
    status = "timed_out" if raw_status == "timeout" else raw_status
    if status not in terminal:
        raise ValueError(
            f"Legacy execution report is not terminal: status={raw_status!r}"
        )
    function["status"] = status
    source_value = str((data.get("source") or {}).get("path") or "")
    source_path = _workspace_path(workspace, source_value)
    if not source_path.is_file():
        raise ValueError(f"Legacy execution source file does not exist: {source_path}")
    relative_source = source_path.relative_to(workspace)
    data["source"] = {"path": relative_source.as_posix()}
    command = data.get("command")
    if isinstance(command, dict):
        command["working_directory"] = "."
    _copy_legacy_log(
        workspace / "logs" / "test_stdout.log",
        paths.stdout_log,
    )
    _copy_legacy_log(
        workspace / "logs" / "test_stderr.log",
        paths.stderr_log,
    )
    _copy_legacy_log(
        workspace / "logs" / "test_execution.log",
        paths.combined_log,
    )
    command_result = data.get("command_result")
    if isinstance(command_result, dict):
        command_result["stdout_log"] = paths.stdout_log.relative_to(workspace).as_posix()
        command_result["stderr_log"] = paths.stderr_log.relative_to(workspace).as_posix()
        command_result["combined_log"] = paths.combined_log.relative_to(workspace).as_posix()
    data["evidence_files"] = []
    report = _report_from_data(data, "1.0.0")
    subject = _verified_subject(
        workspace,
        relative_source,
        report.function_name,
    )
    producer_commit = current_producer_commit()
    write_test_execution_reports(
        paths,
        report,
        subject=subject,
        producer_commit=producer_commit,
        extensions=migrated.get("extensions"),
    )
    report_hash = sha256_file(paths.execution_report)
    if report_hash is None:
        raise ValueError("Imported execution report was not published.")
    pointer = build_artifact_payload(
        ArtifactKind.LATEST_RUN_POINTER,
        {
            "run_id": run_id,
            "execution_report": {
                "artifact_kind": ArtifactKind.TEST_EXECUTION_REPORT.value,
                "path": paths.execution_report.relative_to(workspace).as_posix(),
                "sha256": report_hash,
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        subject=subject,
        producer_commit=producer_commit,
    )
    write_validated_artifact(
        workspace / "reports" / "latest_run.json",
        ArtifactKind.LATEST_RUN_POINTER,
        pointer,
        atomic=True,
    )
    return load_execution_run(workspace, run_id)


def _copy_legacy_log(source: Path, destination: Path) -> None:
    if source.is_file():
        shutil.copy2(source, destination)
    else:
        destination.write_bytes(b"")


def _verified_subject(
    workspace: Path,
    source_path: Path,
    function_name: str,
) -> dict[str, str]:
    source_hash = sha256_file(workspace / source_path)
    if source_hash is None:
        raise ValueError(f"Execution source file does not exist: {source_path}")
    identity_seed = f"{source_path.as_posix()}\0{function_name}".encode("utf-8")
    suffix = hashlib.sha256(identity_seed).hexdigest()[:12]
    slug = re.sub(r"[^a-z0-9]+", "_", function_name.lower()).strip("_")
    return {
        "function_id": f"fn_{slug or 'function'}_{suffix}",
        "source_path": source_path.as_posix(),
        "source_sha256": source_hash,
    }


def _report_from_data(data: dict[str, Any], schema_version: str) -> TestExecutionReport:
    executable_data = data.get("executable")
    executable = None
    if isinstance(executable_data, dict):
        executable = ExecutableInfo(
            path=Path(executable_data["path"]),
            exists=bool(executable_data["exists"]),
            sha256=executable_data.get("sha256"),
            generated_from=executable_data.get("generated_from"),
            build_probe_status=str(executable_data["build_probe_status"]),
            warnings=[_warning(item) for item in executable_data.get("warnings", [])],
        )
    command_data = data.get("command")
    command = None
    if isinstance(command_data, dict):
        command = ExecutionCommand(
            command_line=str(command_data["command_line"]),
            working_directory=Path(command_data["working_directory"]),
            environment_summary=dict(command_data.get("environment_summary", {})),
            timeout_seconds=int(command_data["timeout_seconds"]),
            dry_run=bool(command_data["dry_run"]),
        )
    result_data = data.get("command_result")
    command_result = None
    if isinstance(result_data, dict):
        command_result = ExecutionCommandResult(
            exit_code=result_data.get("exit_code"),
            started_at=result_data.get("started_at"),
            finished_at=result_data.get("finished_at"),
            duration_ms=result_data.get("duration_ms"),
            stdout_log=_optional_path(result_data.get("stdout_log")),
            stderr_log=_optional_path(result_data.get("stderr_log")),
            combined_log=_optional_path(result_data.get("combined_log")),
            timed_out=bool(result_data.get("timed_out")),
        )
    summary_data = data.get("parsed_result")
    summary = _summary(summary_data) if isinstance(summary_data, dict) else None
    policy_data = data.get("policy") or {}
    return TestExecutionReport(
        source_path=_optional_path((data.get("source") or {}).get("path")),
        function_name=str((data.get("function") or {}).get("name") or "unknown_function"),
        status=str((data.get("function") or {}).get("status") or "error"),
        executed=bool(data.get("executed")),
        executable=executable,
        command=command,
        command_result=command_result,
        parsed_result=summary,
        case_results=[_case_result(item) for item in data.get("case_results", [])],
        unresolved_review_items=[
            _review_item(item) for item in data.get("unresolved_review_items", [])
        ],
        evidence_files=[_evidence_file(item) for item in data.get("evidence_files", [])],
        warnings=[_warning(item) for item in data.get("warnings", [])],
        policy=TestExecutionPolicy(
            run_tests=bool(policy_data.get("run_tests", False)),
            dry_run=bool(policy_data.get("dry_run", True)),
            timeout_seconds=int(policy_data.get("timeout_seconds", 60)),
            require_successful_build_probe=bool(
                policy_data.get("require_successful_build_probe", True)
            ),
            allow_placeholder_tests=bool(
                policy_data.get("allow_placeholder_tests", True)
            ),
            treat_placeholder_as_inconclusive=bool(
                policy_data.get("treat_placeholder_as_inconclusive", True)
            ),
            capture_environment=bool(policy_data.get("capture_environment", True)),
            overwrite_existing_logs=bool(
                policy_data.get("overwrite_existing_logs", False)
            ),
        ),
        schema_version=schema_version,
    )


def _warning(data: dict[str, Any]) -> TestExecutionWarning:
    return TestExecutionWarning(
        code=str(data["code"]),
        message=str(data["message"]),
        related_test_case_id=data.get("related_test_case_id"),
        related_file=_optional_path(data.get("related_file")),
    )


def _summary(data: dict[str, Any]) -> TestResultSummary:
    return TestResultSummary(
        total=int(data.get("total", 0)),
        passed=int(data.get("passed", 0)),
        failed=int(data.get("failed", 0)),
        skipped=int(data.get("skipped", 0)),
        inconclusive=int(data.get("inconclusive", 0)),
        assertion_failures=int(data.get("assertion_failures", 0)),
        parser_confidence=str(data.get("parser_confidence", "low")),
        crashed=int(data.get("crashed", 0)),
        not_run=int(data.get("not_run", 0)),
        started=int(data.get("started", 0)),
        completed=int(data.get("completed", 0)),
    )


def _case_result(data: dict[str, Any]) -> TestCaseExecutionResult:
    return TestCaseExecutionResult(
        test_case_id=data.get("test_case_id"),
        generated_function_name=data.get("generated_function_name"),
        status=str(data["status"]),
        exit_related=bool(data["exit_related"]),
        assertions=[_assertion(item) for item in data.get("assertions", [])],
        related_coverage_ids=list(data.get("related_coverage_ids", [])),
        review_required=bool(data.get("review_required")),
        evidence=str(data.get("evidence", "")),
        warnings=[_warning(item) for item in data.get("warnings", [])],
    )


def _assertion(data: dict[str, Any]) -> AssertionResult:
    return AssertionResult(
        assertion_kind=str(data["assertion_kind"]),
        status=str(data["status"]),
        file=_optional_path(data.get("file")),
        line_number=data.get("line_number"),
        expected=data.get("expected"),
        actual=data.get("actual"),
        expression=data.get("expression"),
        message=data.get("message"),
    )


def _review_item(data: dict[str, Any]) -> ExecutionReviewItem:
    return ExecutionReviewItem(
        item_id=str(data["item_id"]),
        item_kind=str(data["item_kind"]),
        related_test_case_id=data.get("related_test_case_id"),
        description=str(data["description"]),
        suggested_action=str(data["suggested_action"]),
        severity=str(data["severity"]),
    )


def _evidence_file(data: dict[str, Any]) -> EvidenceFile:
    exists = bool(data.get("exists", False))
    integrity_status = data.get("integrity_status")
    if integrity_status not in {"valid", "missing", "hash_mismatch"}:
        integrity_status = "valid" if exists and data.get("sha256") else "missing"
    return EvidenceFile(
        path=Path(data["path"]),
        file_kind=str(data["file_kind"]),
        required=bool(data["required"]),
        exists=exists,
        sha256=data.get("sha256"),
        integrity_status=integrity_status,
        description=str(data["description"]),
    )


def _optional_path(value: Any) -> Path | None:
    if value is None:
        return None
    return Path(str(value))


def _require_valid(violations: tuple[Any, ...], path: Path) -> None:
    if not violations:
        return
    detail = "; ".join(
        f"{item.code} at {item.json_path}: {item.message}" for item in violations
    )
    raise ValueError(f"Invalid artifact {path}: {detail}")


def _workspace_path(workspace: Path, value: str) -> Path:
    candidate = (workspace / value).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as error:
        raise ValueError(f"Artifact path escapes workspace: {value}") from error
    return candidate


def _validate_run_id(value: str) -> None:
    if not value or value in {".", ".."} or Path(value).name != value or "/" in value or "\\" in value:
        raise ValueError(f"Invalid run ID: {value!r}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
