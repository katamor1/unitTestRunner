from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from unit_test_runner.contracts import ArtifactKind, validate_artifact


class WorkspaceRegenerationRequired(ValueError):
    """The workspace predates the v0.1 contract and must be regenerated."""


_CANONICAL_RELATIVE_PATHS = {
    ArtifactKind.FUNCTION_DOSSIER: Path("reports/function_dossier.json"),
    ArtifactKind.TEST_SPEC: Path("reports/test_spec.json"),
    ArtifactKind.REVIEW_RECORD: Path("reports/review_record.json"),
    ArtifactKind.BUILD_PROBE_REPORT: Path("reports/build_probe_report.json"),
    ArtifactKind.REANALYSIS_REPORT: Path("reports/reanalysis_report.json"),
}

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def canonical_artifact_path(
    workspace: Path | str,
    kind: ArtifactKind,
) -> Path:
    try:
        relative = _CANONICAL_RELATIVE_PATHS[kind]
    except KeyError as error:
        raise ValueError(f"{kind.value} has no single canonical workspace path.") from error
    return Path(workspace).resolve() / relative


def write_canonical_artifact(
    workspace: Path | str,
    kind: ArtifactKind,
    subject: Mapping[str, str],
    data: Mapping[str, Any],
) -> Path:
    return _write_public_artifact(
        canonical_artifact_path(workspace, kind),
        kind,
        subject,
        data,
    )


def load_public_artifact(
    path: Path | str,
    expected_kind: ArtifactKind,
) -> dict[str, Any]:
    resolved = Path(path)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read {expected_kind.value}: {resolved}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{expected_kind.value} root must be an object.")
    version = payload.get("schema_version")
    if version != "1.0.0":
        raise WorkspaceRegenerationRequired(
            f"Workspace artifact {resolved} uses schema {version!r}; regenerate the workspace for v0.1."
        )
    if payload.get("artifact_kind") != expected_kind.value:
        raise ValueError(
            f"Expected {expected_kind.value}; received {payload.get('artifact_kind')!r}."
        )
    violations = validate_artifact(expected_kind, payload)
    if violations:
        detail = "; ".join(
            f"{item.code} at {item.json_path}: {item.message}" for item in violations
        )
        raise ValueError(f"Invalid {expected_kind.value}: {detail}")
    return payload


def artifact_sha256(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def set_review_record(
    workspace: Path | str,
    *,
    artifact_kind: ArtifactKind,
    artifact_sha256_value: str,
    decision: str,
    reviewer: str,
    reviewed_at: str,
    comment: str,
) -> Path:
    if artifact_kind is ArtifactKind.REVIEW_RECORD:
        raise ValueError("A review_record cannot review itself.")
    if decision not in {"approved", "changes_requested"}:
        raise ValueError("decision must be approved or changes_requested.")
    target = canonical_artifact_path(workspace, artifact_kind)
    payload = load_public_artifact(target, artifact_kind)
    current_sha256 = artifact_sha256(target)
    if artifact_sha256_value != current_sha256:
        raise ValueError(
            "artifact_sha256 does not match the current canonical artifact."
        )
    return write_canonical_artifact(
        workspace,
        ArtifactKind.REVIEW_RECORD,
        payload["subject"],
        {
            "artifact_kind": artifact_kind.value,
            "artifact_sha256": current_sha256,
            "decision": decision,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "comment": comment,
        },
    )


def is_current_review_approved(
    workspace: Path | str,
    artifact_kind: ArtifactKind,
) -> bool:
    target = canonical_artifact_path(workspace, artifact_kind)
    review_path = canonical_artifact_path(workspace, ArtifactKind.REVIEW_RECORD)
    if not target.is_file() or not review_path.is_file():
        return False
    try:
        review = load_public_artifact(review_path, ArtifactKind.REVIEW_RECORD)
        target_payload = load_public_artifact(target, artifact_kind)
    except (ValueError, WorkspaceRegenerationRequired):
        return False
    data = review["data"]
    return (
        review["subject"] == target_payload["subject"]
        and data.get("artifact_kind") == artifact_kind.value
        and data.get("artifact_sha256") == artifact_sha256(target)
        and data.get("decision") == "approved"
    )


def write_test_run_report(
    workspace: Path | str,
    run_id: str,
    subject: Mapping[str, str],
    data: Mapping[str, Any],
) -> Path:
    if not _RUN_ID.fullmatch(run_id) or run_id in {".", ".."}:
        raise ValueError("run_id must be a simple portable identifier.")
    path = Path(workspace).resolve() / "runs" / run_id / "test_run_report.json"
    if path.exists():
        raise FileExistsError(f"test run already exists: {run_id}")
    return _write_public_artifact(
        path,
        ArtifactKind.TEST_RUN_REPORT,
        subject,
        data,
        replace=False,
    )


def apply_reanalysis_candidate(
    workspace: Path | str,
    candidate_path: Path | str,
    *,
    candidate_sha256: str,
    expected_revision: int,
) -> tuple[Path, int]:
    root = Path(workspace).resolve()
    candidate = Path(candidate_path).resolve()
    canonical = canonical_artifact_path(root, ArtifactKind.TEST_SPEC)
    if candidate == canonical:
        raise ValueError("Reanalysis candidate must be separate from canonical test_spec.")
    try:
        raw_candidate = candidate.read_bytes()
    except OSError as error:
        raise ValueError(f"Cannot read reanalysis candidate: {candidate}") from error
    actual_sha256 = hashlib.sha256(raw_candidate).hexdigest()
    if actual_sha256 != candidate_sha256:
        raise ValueError("Reanalysis candidate SHA-256 does not match the supplied value.")
    try:
        candidate_payload = json.loads(raw_candidate.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Reanalysis candidate is not valid UTF-8 JSON.") from error
    if not isinstance(candidate_payload, dict):
        raise ValueError("Reanalysis candidate root must be an object.")
    if candidate_payload.get("schema_version") != "1.0.0":
        raise WorkspaceRegenerationRequired(
            "Reanalysis candidate is not schema 1.0.0; regenerate it for v0.1."
        )
    if candidate_payload.get("artifact_kind") != ArtifactKind.TEST_SPEC.value:
        raise ValueError("Reanalysis candidate must be a test_spec artifact.")
    violations = validate_artifact(ArtifactKind.TEST_SPEC, candidate_payload)
    if violations:
        detail = "; ".join(
            f"{item.code} at {item.json_path}: {item.message}" for item in violations
        )
        raise ValueError(f"Invalid reanalysis candidate: {detail}")
    candidate_data = candidate_payload.get("data")
    if not isinstance(candidate_data, dict):
        raise ValueError("Reanalysis candidate data must be an object.")
    candidate_revision = candidate_data.get("revision")
    if type(candidate_revision) is not int or candidate_revision != expected_revision:
        raise ValueError(
            "Reanalysis candidate revision does not match expected revision."
        )
    unresolved = candidate_data.get("unresolved_items")
    conflicts = [
        item
        for item in unresolved
        if isinstance(item, Mapping)
        and item.get("item_kind") == "reanalysis_merge_conflict"
    ] if isinstance(unresolved, list) else []
    if conflicts or candidate_data.get("reanalysis_conflicts"):
        raise ValueError("Reanalysis candidate has unresolved merge conflicts.")

    lock_path = canonical.with_name(f".{canonical.name}.apply.lock")
    with _exclusive_workspace_lock(lock_path):
        current = load_public_artifact(canonical, ArtifactKind.TEST_SPEC)
        current_data = current.get("data")
        current_revision = (
            current_data.get("revision") if isinstance(current_data, dict) else None
        )
        if type(current_revision) is not int or current_revision != expected_revision:
            raise ValueError(
                f"Expected test_spec revision {expected_revision}; current revision is {current_revision!r}."
            )
        candidate_subject = candidate_payload.get("subject")
        current_subject = current.get("subject")
        if not isinstance(candidate_subject, Mapping) or not isinstance(current_subject, Mapping):
            raise ValueError("Reanalysis candidate subject is invalid.")
        stable_subject_fields = ("source_path", "function", "project", "configuration")
        if any(
            candidate_subject.get(field) != current_subject.get(field)
            for field in stable_subject_fields
        ):
            raise ValueError("Reanalysis candidate subject is stale.")
        next_revision = expected_revision + 1
        next_data = dict(candidate_data)
        next_data["revision"] = next_revision
        for stale_kind in (
            ArtifactKind.REVIEW_RECORD,
            ArtifactKind.BUILD_PROBE_REPORT,
        ):
            canonical_artifact_path(root, stale_kind).unlink(missing_ok=True)
        applied = write_canonical_artifact(
            root,
            ArtifactKind.TEST_SPEC,
            candidate_subject,
            next_data,
        )
    return applied, next_revision


@contextmanager
def _exclusive_workspace_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RuntimeError(f"Workspace update is already in progress: {path}") from error
    os.close(descriptor)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def _write_public_artifact(
    path: Path,
    kind: ArtifactKind,
    subject: Mapping[str, str],
    data: Mapping[str, Any],
    *,
    replace: bool = True,
) -> Path:
    payload = {
        "schema_version": "1.0.0",
        "artifact_kind": kind.value,
        "subject": dict(subject),
        "data": dict(data),
    }
    violations = validate_artifact(kind, payload)
    if violations:
        detail = "; ".join(
            f"{item.code} at {item.json_path}: {item.message}" for item in violations
        )
        raise ValueError(f"Invalid {kind.value}: {detail}")
    final_bytes = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(final_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                raise FileExistsError(f"Artifact already exists: {path}") from None
            temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)
    return path
