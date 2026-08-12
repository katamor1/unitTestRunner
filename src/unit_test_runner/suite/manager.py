from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping
from uuid import uuid4

from unit_test_runner.contracts import ArtifactKind, RunOutcome, validate_artifact
from unit_test_runner.execution import execute_test_run, validate_test_run_preflight
from unit_test_runner.execution.execution_models import TestRunRequest
from unit_test_runner.vc6.debug_workspace_writer import write_vc6_debug_suite
from unit_test_runner.workspace_artifacts import load_public_artifact

from .models import (
    SuiteEntry,
    SuiteManifest,
    SuiteRunEntryResult,
    SuiteRunPolicy,
    SuiteRunReport,
    normalize_subject,
)
from .report_writer import write_suite_run_report


_FINGERPRINT_FIELDS = ("source_sha256", "test_spec_sha256", "harness_sha256")


def default_suite_manifest_path(output_root: Path | str) -> Path:
    return Path(output_root) / "suites" / "default" / "suite_manifest.json"


def load_suite_manifest(suite_path: Path | str) -> SuiteManifest:
    suite_path = Path(suite_path).resolve()
    if not suite_path.exists():
        return SuiteManifest(suite_id=_suite_id_from_path(suite_path))
    payload = _read_json(suite_path)
    _raise_schema_errors(ArtifactKind.SUITE_MANIFEST, payload)
    return SuiteManifest.from_dict(
        payload,
        suite_root=_suite_root(suite_path),
        suite_id=_suite_id_from_path(suite_path),
    )


def save_suite_manifest(
    suite_path: Path | str,
    manifest: SuiteManifest,
    *,
    expected_revision: int,
) -> None:
    suite_path = Path(suite_path).resolve()
    with _manifest_write_lock(suite_path):
        current = _current_revision(suite_path)
        if current != expected_revision:
            raise ValueError(
                f"Suite manifest revision mismatch: expected {expected_revision}, current {current}."
            )
        if manifest.subject is None:
            raise ValueError("The first suite registration must establish an anchor subject.")
        if suite_path.exists():
            persisted = _read_json(suite_path)
            if persisted.get("subject") != manifest.subject:
                raise ValueError("The suite anchor subject is immutable after first registration.")
        entry_ids = [entry.entry_id for entry in manifest.entries]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("Suite manifest contains duplicate entry_id values.")
        previous_revision = manifest.revision
        manifest.revision = expected_revision + 1
        try:
            payload = manifest.to_dict()
            _raise_schema_errors(ArtifactKind.SUITE_MANIFEST, payload)
            _atomic_revision_write(
                suite_path,
                payload,
                expected_revision=expected_revision,
            )
        except Exception:
            manifest.revision = previous_revision
            raise


def register_workspace(
    suite_path: Path | str,
    workspace: Path | str,
    tags: list[str] | tuple[str, ...] | None = None,
    *,
    enabled: bool | None = None,
    expected_revision: int,
) -> SuiteManifest:
    suite_path = Path(suite_path).resolve()
    workspace = _existing_dir(workspace, "workspace")
    manifest = load_suite_manifest(suite_path)
    if expected_revision != manifest.revision:
        raise ValueError(
            f"Suite manifest revision mismatch: expected {expected_revision}, current {manifest.revision}."
        )
    subject = _workspace_subject(workspace)
    entry_id = _entry_id(subject)
    existing = next((item for item in manifest.entries if item.entry_id == entry_id), None)
    entry = _entry_from_workspace(
        suite_path,
        workspace,
        subject=subject,
        enabled=(
            existing.enabled
            if existing is not None and enabled is None
            else (True if enabled is None else enabled)
        ),
        tags=(
            list(existing.tags)
            if existing is not None and tags is None
            else _normalize_tags(tags)
        ),
    )
    manifest.entries = [item for item in manifest.entries if item.entry_id != entry.entry_id]
    manifest.entries.append(entry)
    if manifest.subject is None:
        manifest.subject = dict(subject)
    save_suite_manifest(
        suite_path,
        manifest,
        expected_revision=expected_revision,
    )
    _refresh_vc6_debug_suite(suite_path, manifest)
    return manifest


def remove_entry(
    suite_path: Path | str,
    entry_id: str,
    *,
    expected_revision: int,
) -> SuiteManifest:
    suite_path = Path(suite_path).resolve()
    manifest = load_suite_manifest(suite_path)
    if expected_revision != manifest.revision:
        raise ValueError(
            f"Suite manifest revision mismatch: expected {expected_revision}, current {manifest.revision}."
        )
    if not any(entry.entry_id == entry_id for entry in manifest.entries):
        raise ValueError(f"Unknown suite entry: {entry_id}")
    manifest.entries = [entry for entry in manifest.entries if entry.entry_id != entry_id]
    save_suite_manifest(
        suite_path,
        manifest,
        expected_revision=expected_revision,
    )
    _refresh_vc6_debug_suite(suite_path, manifest)
    return manifest


def update_entry(
    suite_path: Path | str,
    entry_id: str,
    *,
    expected_revision: int,
    workspace: Path | str | None = None,
    tags: list[str] | tuple[str, ...] | None = None,
    enabled: bool | None = None,
) -> SuiteManifest:
    suite_path = Path(suite_path).resolve()
    manifest = load_suite_manifest(suite_path)
    if expected_revision != manifest.revision:
        raise ValueError(
            f"Suite manifest revision mismatch: expected {expected_revision}, current {manifest.revision}."
        )
    index = next(
        (position for position, item in enumerate(manifest.entries) if item.entry_id == entry_id),
        None,
    )
    if index is None:
        raise ValueError(f"Unknown suite entry: {entry_id}")
    current = manifest.entries[index]
    resolved_workspace = (
        current.workspace
        if workspace is None
        else _existing_dir(workspace, "workspace")
    )
    subject = _workspace_subject(resolved_workspace)
    if _entry_id(subject) != entry_id:
        raise ValueError("Suite update cannot change an entry identity.")
    manifest.entries[index] = _entry_from_workspace(
        suite_path,
        resolved_workspace,
        subject=subject,
        enabled=current.enabled if enabled is None else enabled,
        tags=list(current.tags) if tags is None else _normalize_tags(tags),
    )
    save_suite_manifest(
        suite_path,
        manifest,
        expected_revision=expected_revision,
    )
    _refresh_vc6_debug_suite(suite_path, manifest)
    return manifest


def list_entries(suite_path: Path | str, tag: str | None = None) -> list[SuiteEntry]:
    entries = load_suite_manifest(suite_path).entries
    if tag:
        return [entry for entry in entries if tag in entry.tags]
    return entries


def validate_suite_selection(
    suite_path: Path | str,
    *,
    entry_ids: list[str] | None = None,
    tag: str | None = None,
    all_entries: bool = False,
) -> list[SuiteEntry]:
    manifest = load_suite_manifest(suite_path)
    selected = _select_entries(
        manifest.entries,
        entry_ids=entry_ids,
        tag=tag,
        all_entries=all_entries,
    )
    if not selected:
        raise ValueError("Suite selection must resolve to at least one enabled entry.")
    return selected


def validate_suite_plan(
    suite_path: Path | str,
    *,
    entry_ids: list[str] | None = None,
    tag: str | None = None,
    all_entries: bool = False,
) -> tuple[list[SuiteEntry], list[dict[str, str]]]:
    selected = validate_suite_selection(
        suite_path,
        entry_ids=entry_ids,
        tag=tag,
        all_entries=all_entries,
    )
    diagnostics: list[dict[str, str]] = []
    for entry in selected:
        warnings, review_items = _validate_entry_preconditions(entry)
        diagnostics.extend(
            {
                "code": f"suite_entry_{warning.code}",
                "severity": "warning",
                "message": f"[{entry.entry_id}] {warning.message}",
            }
            for warning in warnings
        )
        diagnostics.extend(
            {
                "code": f"suite_entry_{item.item_kind}",
                "severity": item.severity if item.severity in {"info", "warning", "error"} else "warning",
                "message": f"[{entry.entry_id}] {item.description}",
            }
            for item in review_items
        )
    return selected, diagnostics


def _validate_entry_preconditions(entry: SuiteEntry) -> tuple[list[Any], list[Any]]:
    changed, _ = _entry_fingerprints(entry)
    if changed:
        raise ValueError(
            f"Suite entry {entry.entry_id} is stale: {', '.join(changed)}"
        )
    return validate_test_run_preflight(_existing_dir(entry.workspace, f"suite entry {entry.entry_id} workspace"))


def run_suite(
    suite_path: Path | str,
    *,
    entry_ids: list[str] | None = None,
    tag: str | None = None,
    all_entries: bool = False,
    policy: SuiteRunPolicy | None = None,
) -> tuple[SuiteRunReport, dict[str, Path]]:
    suite_path = Path(suite_path).resolve()
    policy = policy or SuiteRunPolicy()
    manifest = load_suite_manifest(suite_path)
    selected = _select_entries(
        manifest.entries,
        entry_ids=entry_ids,
        tag=tag,
        all_entries=all_entries,
    )
    if not selected:
        raise ValueError("Suite selection must resolve to at least one enabled entry.")
    _refresh_vc6_debug_suite(suite_path, manifest)
    results = [_run_entry(entry, policy) for entry in selected]
    summary = _summary(results)
    status = _suite_outcome(results, policy).value
    report = SuiteRunReport(
        suite_id=manifest.suite_id,
        status=status,
        selector=_selector_payload(entry_ids=entry_ids, tag=tag, all_entries=all_entries),
        policy=policy,
        results=results,
        summary=summary,
        subject=dict(manifest.subject or {}),
        manifest_revision=manifest.revision,
    )
    return report, write_suite_run_report(suite_path, report)


def _run_entry(entry: SuiteEntry, policy: SuiteRunPolicy) -> SuiteRunEntryResult:
    changed, fingerprints = _entry_fingerprints(entry)
    if changed:
        return SuiteRunEntryResult(
            entry_id=entry.entry_id,
            function_name=entry.subject["function"],
            workspace=entry.workspace,
            execution_status=RunOutcome.BLOCKED.value,
            green_status="not_green",
            executed=False,
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            inconclusive_tests=0,
            unresolved_review_count=0,
            report_path=None,
            error="stale suite input",
            subject=dict(entry.subject),
            workspace_path=entry.workspace_path,
            changed_fields=changed,
            fingerprints=fingerprints,
        )
    try:
        if not policy.run_tests or policy.dry_run:
            warnings, review_items = validate_test_run_preflight(entry.workspace)
            return SuiteRunEntryResult(
                entry_id=entry.entry_id,
                function_name=entry.subject["function"],
                workspace=entry.workspace,
                execution_status=RunOutcome.PLANNED.value,
                green_status="not_green",
                executed=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                inconclusive_tests=0,
                unresolved_review_count=len(review_items),
                report_path=None,
                error=(warnings[0].message if warnings else None),
                subject=dict(entry.subject),
                workspace_path=entry.workspace_path,
                fingerprints=fingerprints,
            )
        report = execute_test_run(
            TestRunRequest(
                workspace=entry.workspace,
                executable=None,
                timeout_seconds=policy.timeout_seconds,
                allow_placeholder_tests=False,
                selector_kind="all",
            )
        )
        parsed = report.parsed_result
        total = parsed.total if parsed else len(report.case_results)
        passed = parsed.passed if parsed else 0
        failed = parsed.failed if parsed else 0
        inconclusive = parsed.inconclusive if parsed else 0
        unresolved = len(report.unresolved_review_items)
        green = _is_green(report.status, report.executed, total, failed, inconclusive, unresolved)
        run_paths = getattr(report, "run_paths", None)
        report_path = (
            _portable_report_path(entry, run_paths.public_report)
            if run_paths is not None
            else None
        )
        return SuiteRunEntryResult(
            entry_id=entry.entry_id,
            function_name=entry.subject["function"],
            workspace=entry.workspace,
            execution_status=_canonical_entry_outcome(report.status, policy).value,
            green_status="green" if green else "not_green",
            executed=report.executed,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            inconclusive_tests=inconclusive,
            unresolved_review_count=unresolved,
            report_path=report_path,
            subject=dict(entry.subject),
            workspace_path=entry.workspace_path,
            fingerprints=fingerprints,
        )
    except Exception as exc:
        return SuiteRunEntryResult(
            entry_id=entry.entry_id,
            function_name=entry.subject["function"],
            workspace=entry.workspace,
            execution_status=RunOutcome.ERROR.value,
            green_status="not_green",
            executed=False,
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            inconclusive_tests=0,
            unresolved_review_count=0,
            report_path=None,
            error=str(exc),
            subject=dict(entry.subject),
            workspace_path=entry.workspace_path,
            fingerprints=fingerprints,
        )


def _portable_report_path(entry: SuiteEntry, report_path: Path) -> Path:
    try:
        relative = report_path.resolve().relative_to(entry.workspace.resolve())
    except ValueError as error:
        raise ValueError("Suite test_run_report must stay inside its registered workspace.") from error
    return Path(
        PurePosixPath(entry.workspace_path) / PurePosixPath(relative.as_posix())
    )


def _entry_fingerprints(
    entry: SuiteEntry,
) -> tuple[list[str], dict[str, dict[str, str | None]]]:
    source = _workspace_source_path(entry.workspace, entry.subject)
    paths = {
        "source_sha256": source,
        "test_spec_sha256": entry.workspace / "reports" / "test_spec.json",
        "harness_sha256": entry.workspace / "reports" / "harness_skeleton_report.json",
    }
    expected = {
        "source_sha256": entry.subject["source_sha256"],
        "test_spec_sha256": entry.test_spec_sha256,
        "harness_sha256": entry.harness_sha256,
    }
    fingerprints: dict[str, dict[str, str | None]] = {}
    changed: list[str] = []
    for field in _FINGERPRINT_FIELDS:
        path = paths[field]
        try:
            actual = _sha256_file(path) if path.is_file() else None
        except OSError:
            actual = None
        fingerprints[field] = {"expected": expected[field], "actual": actual}
        if actual != expected[field]:
            changed.append(field)
    return changed, fingerprints


def _is_green(status: str, executed: bool, total: int, failed: int, inconclusive: int, unresolved: int) -> bool:
    return executed and status == "passed" and total > 0 and failed == 0 and inconclusive == 0 and unresolved == 0


def _suite_outcome(results: list[SuiteRunEntryResult], policy: SuiteRunPolicy) -> RunOutcome:
    if not policy.run_tests or policy.dry_run:
        return RunOutcome.PLANNED
    states = {_canonical_entry_outcome(result.execution_status, policy) for result in results}
    for state in (
        RunOutcome.ERROR,
        RunOutcome.CANCELLED,
        RunOutcome.TIMED_OUT,
        RunOutcome.BLOCKED,
        RunOutcome.FAILED,
    ):
        if state in states:
            return state
    if any(result.green_status != "green" for result in results):
        return RunOutcome.FAILED
    if states == {RunOutcome.PASSED} and results:
        return RunOutcome.PASSED
    return RunOutcome.ERROR


def _canonical_entry_outcome(value: str, policy: SuiteRunPolicy) -> RunOutcome:
    if not policy.run_tests or policy.dry_run:
        return RunOutcome.PLANNED
    try:
        return RunOutcome(value)
    except ValueError:
        return RunOutcome.ERROR


def _select_entries(
    entries: list[SuiteEntry],
    *,
    entry_ids: list[str] | None,
    tag: str | None,
    all_entries: bool,
) -> list[SuiteEntry]:
    modes = int(bool(entry_ids)) + int(bool(tag)) + int(all_entries)
    if modes != 1:
        raise ValueError("suite-run requires exactly one non-empty selector.")
    enabled = [entry for entry in entries if entry.enabled]
    if all_entries:
        return enabled
    if tag:
        return [entry for entry in enabled if tag in entry.tags]
    assert entry_ids is not None
    if len(entry_ids) != len(set(entry_ids)):
        raise ValueError("Suite entry selector contains duplicate entry IDs.")
    by_id = {entry.entry_id: entry for entry in enabled}
    missing = [entry_id for entry_id in entry_ids if entry_id not in by_id]
    if missing:
        raise ValueError("Unknown or disabled suite entries: " + ", ".join(missing))
    return [by_id[entry_id] for entry_id in entry_ids]


def _summary(results: list[SuiteRunEntryResult]) -> dict[str, int]:
    counts = {state.value: 0 for state in RunOutcome}
    for result in results:
        try:
            state = RunOutcome(result.execution_status)
        except ValueError:
            state = RunOutcome.ERROR
        counts[state.value] += 1
    green = sum(result.green_status == "green" for result in results)
    return {
        "total": len(results),
        "green": green,
        "not_green": len(results) - green,
        "executed": sum(result.executed for result in results),
        **counts,
    }


def _selector_payload(*, entry_ids: list[str] | None, tag: str | None, all_entries: bool) -> dict[str, Any]:
    if all_entries:
        return {"kind": "all"}
    if tag:
        return {"kind": "tag", "tag": tag}
    return {"kind": "entry_id", "entry_ids": list(entry_ids or [])}


def _workspace_subject(workspace: Path) -> dict[str, str]:
    dossier = _public_subject(workspace / "reports" / "function_dossier.json", "function_dossier")
    test_spec = _public_subject(workspace / "reports" / "test_spec.json", "test_spec")
    if dossier != test_spec:
        raise ValueError("Function dossier and TestSpec subjects do not match.")
    source_path = PurePosixPath(dossier["source_path"])
    if (
        "\\" in dossier["source_path"]
        or source_path.is_absolute()
        or (source_path.parts and ":" in source_path.parts[0])
        or any(part in {"", ".", ".."} for part in source_path.parts)
    ):
        raise ValueError("Suite source_path must be workspace-relative and traversal-free.")
    source = _workspace_source_path(workspace, dossier)
    actual = _sha256_file(_existing_file(source, "suite source"))
    if actual != dossier["source_sha256"]:
        raise ValueError("Suite source SHA-256 does not match the registered subject.")
    return dossier


def _workspace_source_path(
    workspace: Path,
    subject: Mapping[str, str],
) -> Path:
    request_path = workspace / "input" / "request.json"
    if not request_path.is_file():
        return (
            workspace
            / Path(*PurePosixPath(subject["source_path"]).parts)
        ).resolve()
    request = _read_json(request_path)
    source_root_value = request.get("workspace")
    source_value = request.get("source")
    if not isinstance(source_root_value, str) or not source_root_value:
        raise ValueError("Suite input request has no source workspace.")
    if source_value != subject["source_path"]:
        raise ValueError("Suite input request source does not match the public subject.")
    source_root = _existing_dir(source_root_value, "suite source workspace")
    source = (source_root / Path(*PurePosixPath(subject["source_path"]).parts)).resolve()
    try:
        source.relative_to(source_root)
    except ValueError as error:
        raise ValueError("Suite source_path escapes its source workspace.") from error
    return source


def _entry_from_workspace(
    suite_path: Path,
    workspace: Path,
    *,
    subject: Mapping[str, str],
    enabled: bool,
    tags: list[str],
) -> SuiteEntry:
    return SuiteEntry(
        entry_id=_entry_id(subject),
        enabled=enabled,
        tags=tags,
        subject=dict(subject),
        workspace=workspace,
        workspace_path=_relative_workspace(suite_path, workspace),
        test_spec_sha256=_sha256_file(
            _existing_file(
                workspace / "reports" / "test_spec.json",
                "test_spec",
            )
        ),
        harness_sha256=_sha256_file(
            _existing_file(
                workspace / "reports" / "harness_skeleton_report.json",
                "harness_skeleton_report",
            )
        ),
    )


def _public_subject(path: Path, expected_kind: str) -> dict[str, str]:
    kind = ArtifactKind(expected_kind)
    payload = load_public_artifact(_existing_file(path, expected_kind), kind)
    subject = payload.get("subject")
    if not isinstance(subject, Mapping):
        raise ValueError(f"{path.name} must contain a function subject.")
    return normalize_subject(subject)


def _entry_id(subject: Mapping[str, str]) -> str:
    seed = "|".join(
        subject[field]
        for field in ("function", "source_path", "project", "configuration")
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"{_safe_id(subject['function'])}-{digest}"


def _relative_workspace(suite_path: Path, workspace: Path) -> str:
    root = _suite_root(suite_path)
    try:
        relative = workspace.resolve().relative_to(root)
    except ValueError as error:
        raise ValueError("Suite workspace must be contained by the suite output root.") from error
    text = relative.as_posix()
    if text in {"", "."} or "\\" in text or ".." in PurePosixPath(text).parts:
        raise ValueError("Suite workspace must be a non-empty manifest-relative POSIX path.")
    return text


def _suite_root(suite_path: Path) -> Path:
    try:
        return suite_path.resolve().parents[2]
    except IndexError as error:
        raise ValueError("Suite manifest path must be nested under suites/<suite-id>.") from error


def _normalize_tags(tags: list[str] | tuple[str, ...] | None) -> list[str]:
    result: list[str] = []
    for tag in tags or []:
        text = str(tag).strip()
        if text and text not in result:
            result.append(text)
    return result


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _current_revision(path: Path) -> int:
    if not path.exists():
        return 0
    payload = _read_json(path)
    data = payload.get("data")
    if not isinstance(data, Mapping) or not isinstance(data.get("revision"), int):
        raise ValueError("Existing suite manifest has no valid revision.")
    return int(data["revision"])


def _atomic_revision_write(path: Path, payload: Mapping[str, Any], *, expected_revision: int) -> None:
    final_bytes = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(final_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        if _current_revision(path) != expected_revision:
            raise ValueError("Suite manifest revision changed before atomic publication.")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _manifest_write_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    with lock_path.open("a+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        try:
            _lock_file_nonblocking(handle.fileno())
        except OSError as error:
            raise ValueError("Suite manifest is being updated by another writer.") from error
        try:
            yield
        finally:
            handle.seek(0)
            _unlock_file(handle.fileno())


def _lock_file_nonblocking(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_UN)


def _raise_schema_errors(kind: ArtifactKind, payload: Mapping[str, Any]) -> None:
    violations = validate_artifact(kind, payload)
    if violations:
        detail = "; ".join(f"{item.code} at {item.json_path}: {item.message}" for item in violations)
        raise ValueError(f"Invalid {kind.value}: {detail}")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _existing_dir(path: Path | str, label: str) -> Path:
    value = Path(path).expanduser().resolve()
    if not value.is_dir():
        raise ValueError(f"{label} directory not found: {value}")
    return value


def _existing_file(path: Path | str, label: str) -> Path:
    value = Path(path).expanduser().resolve()
    if not value.is_file():
        raise ValueError(f"{label} file not found: {value}")
    return value


def _suite_id_from_path(suite_path: Path) -> str:
    return suite_path.parent.name or "default"


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value) or "function"


def _refresh_vc6_debug_suite(suite_path: Path, manifest: SuiteManifest) -> None:
    try:
        write_vc6_debug_suite(suite_path, manifest)
    except Exception:
        # The portable public manifest remains valid before build views exist.
        return
