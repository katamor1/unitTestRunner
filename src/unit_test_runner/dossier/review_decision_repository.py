from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from unit_test_runner.cli.artifacts import ProducedArtifact
from unit_test_runner.contracts import ArtifactKind, validate_payload
from unit_test_runner.contracts.registry import get_contract

from .review_decision_models import (
    ReviewDecision,
    ReviewDecisionSet,
    ReviewItemCollection,
    ReviewItemSnapshot,
    ReviewResolution,
)


class ReviewDecisionWriteStatus(StrEnum):
    WRITTEN = "written"
    UNKNOWN_REVIEW_ID = "unknown_review_id"
    SUBJECT_FINGERPRINT_MISMATCH = "subject_fingerprint_mismatch"
    REVISION_CONFLICT = "revision_conflict"
    INVALID_LEDGER = "invalid_ledger"


@dataclass(frozen=True)
class ReviewDecisionLedgerSnapshot:
    payload: dict
    decision_set: ReviewDecisionSet
    raw_bytes: bytes
    sha256: str


@dataclass(frozen=True)
class ReviewDecisionWriteResult:
    status: ReviewDecisionWriteStatus
    current_revision: int
    snapshot: ReviewDecisionLedgerSnapshot | None = None
    artifact: ProducedArtifact | None = None
    message: str = ""


class InvalidReviewDecisionLedgerError(ValueError):
    pass


class ReviewDecisionRepository:
    def __init__(
        self,
        workspace_root: Path,
        *,
        current_items: ReviewItemCollection,
        producer_version: str,
        producer_commit: str,
    ) -> None:
        root = Path(os.path.abspath(workspace_root))
        if not str(producer_version).strip():
            raise ValueError("producer_version must not be blank")
        if not str(producer_commit).strip():
            raise ValueError("producer_commit must not be blank")
        self._root = root
        self._current_items = current_items
        self._producer_version = str(producer_version).strip()
        self._producer_commit = str(producer_commit).strip()
        self._path = root / "reports" / "review_decisions.json"
        self._lock_path = self._path.with_name(f".{self._path.name}.lock")
        _assert_safe_repository_paths(self._root, self._path, self._lock_path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> ReviewDecisionLedgerSnapshot:
        _assert_safe_repository_paths(self._root, self._path, self._lock_path)
        try:
            raw_bytes = self._path.read_bytes()
        except OSError as error:
            raise InvalidReviewDecisionLedgerError(str(error)) from error
        return _snapshot_from_bytes(raw_bytes)

    def record(
        self,
        *,
        review_id: str,
        resolution: ReviewResolution,
        reviewer: str,
        rationale: str,
        decided_at: str | None,
        expected_revision: int,
        expected_subject_fingerprint: str,
    ) -> ReviewDecisionWriteResult:
        item = self._current_items.resolve(review_id)
        if item is None:
            return ReviewDecisionWriteResult(
                ReviewDecisionWriteStatus.UNKNOWN_REVIEW_ID,
                current_revision=self._peek_revision(),
                message=f"Unknown current review ID: {review_id}",
            )
        if expected_subject_fingerprint != item.subject_fingerprint:
            return ReviewDecisionWriteResult(
                ReviewDecisionWriteStatus.SUBJECT_FINGERPRINT_MISMATCH,
                current_revision=self._peek_revision(),
                message="The supplied subject fingerprint is not current.",
            )
        decision = ReviewDecision(
            review_id=item.review_id,
            resolution=resolution,
            reviewer=reviewer,
            rationale=rationale,
            decided_at=decided_at,
            subject_artifacts=item.subject_artifacts,
        )

        _assert_safe_repository_paths(self._root, self._path, self._lock_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _assert_safe_repository_paths(self._root, self._path, self._lock_path)
        with _exclusive_lock(self._lock_path):
            current_snapshot: ReviewDecisionLedgerSnapshot | None = None
            if self._path.exists():
                try:
                    current_snapshot = self.load()
                except InvalidReviewDecisionLedgerError as error:
                    return ReviewDecisionWriteResult(
                        ReviewDecisionWriteStatus.INVALID_LEDGER,
                        current_revision=-1,
                        message=str(error),
                    )
                current_revision = current_snapshot.decision_set.revision
            else:
                current_revision = 0
            if expected_revision != current_revision:
                return ReviewDecisionWriteResult(
                    ReviewDecisionWriteStatus.REVISION_CONFLICT,
                    current_revision=current_revision,
                    snapshot=current_snapshot,
                    message=(
                        f"Expected ledger revision {expected_revision}; "
                        f"current revision is {current_revision}."
                    ),
                )

            existing = (
                current_snapshot.decision_set.decisions
                if current_snapshot is not None
                else ()
            )
            decisions = {
                existing_decision.review_id: existing_decision
                for existing_decision in existing
            }
            decisions[item.review_id] = decision
            decision_set = ReviewDecisionSet(
                revision=current_revision + 1,
                decisions=tuple(decisions[key] for key in sorted(decisions)),
            )
            payload = self._build_payload(item, decision_set)
            violations = validate_payload(ArtifactKind.REVIEW_DECISIONS, payload)
            if violations:
                detail = "; ".join(
                    f"{violation.code} at {violation.json_path}: {violation.message}"
                    for violation in violations
                )
                raise ValueError(f"Refusing to persist an invalid review ledger: {detail}")
            final_bytes = _canonical_json_bytes(payload)
            temporary = self._path.with_name(
                f".{self._path.name}.{uuid4().hex}.tmp"
            )
            _assert_safe_repository_paths(
                self._root,
                self._path,
                self._lock_path,
                temporary,
            )
            try:
                _write_exclusive_fsync(temporary, final_bytes)
                os.replace(temporary, self._path)
                _fsync_directory(self._path.parent)
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
            snapshot = self.load()
            if snapshot.raw_bytes != final_bytes:
                raise InvalidReviewDecisionLedgerError(
                    "Persisted review ledger bytes do not match the validated final bytes."
                )
            artifact = ProducedArtifact(
                kind=ArtifactKind.REVIEW_DECISIONS.value,
                path=self._path.relative_to(self._root).as_posix(),
                exists=True,
                sha256=snapshot.sha256,
                schema_version=get_contract(
                    ArtifactKind.REVIEW_DECISIONS
                ).current_version,
            )
            return ReviewDecisionWriteResult(
                ReviewDecisionWriteStatus.WRITTEN,
                current_revision=decision_set.revision,
                snapshot=snapshot,
                artifact=artifact,
            )

    def _peek_revision(self) -> int:
        if not self._path.exists():
            return 0
        try:
            return self.load().decision_set.revision
        except InvalidReviewDecisionLedgerError:
            return -1

    def _build_payload(
        self,
        item: ReviewItemSnapshot,
        decision_set: ReviewDecisionSet,
    ) -> dict:
        source_path: str | None = None
        source_sha256: str | None = None
        for subject in item.subject_artifacts:
            if subject.source_path is None or subject.source_sha256 is None:
                raise ValueError(
                    "Current review subjects require exact source path and SHA-256."
                )
            if source_path is None:
                source_path = subject.source_path
                source_sha256 = subject.source_sha256
            elif (
                source_path != subject.source_path
                or source_sha256 != subject.source_sha256
            ):
                raise ValueError(
                    "One review ledger cannot mix source identities."
                )
        assert source_path is not None
        assert source_sha256 is not None
        return {
            "artifact_kind": ArtifactKind.REVIEW_DECISIONS.value,
            "schema_version": get_contract(
                ArtifactKind.REVIEW_DECISIONS
            ).current_version,
            "producer": {
                "name": "unit-test-runner",
                "version": self._producer_version,
                "commit": self._producer_commit,
            },
            "subject": {
                "function_id": item.function_id,
                "source_path": source_path,
                "source_sha256": source_sha256,
            },
            "data": decision_set.to_data(),
            "extensions": {},
        }


def _snapshot_from_bytes(raw_bytes: bytes) -> ReviewDecisionLedgerSnapshot:
    try:
        decoded = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise InvalidReviewDecisionLedgerError(
            f"Review ledger is not valid UTF-8 JSON: {error}"
        ) from error
    if not isinstance(decoded, dict):
        raise InvalidReviewDecisionLedgerError(
            "Review ledger root must be a JSON object."
        )
    violations = validate_payload(ArtifactKind.REVIEW_DECISIONS, decoded)
    if violations:
        detail = "; ".join(
            f"{item.code} at {item.json_path}: {item.message}"
            for item in violations
        )
        raise InvalidReviewDecisionLedgerError(detail)
    try:
        decision_set = ReviewDecisionSet.from_data(decoded["data"])
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidReviewDecisionLedgerError(str(error)) from error
    return ReviewDecisionLedgerSnapshot(
        payload=decoded,
        decision_set=decision_set,
        raw_bytes=raw_bytes,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def _canonical_json_bytes(payload: dict) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _assert_safe_repository_paths(root: Path, *paths: Path) -> None:
    if _is_symlink_or_reparse(root):
        raise ValueError("Review repository root must not be a symlink or reparse point.")
    resolved_root = root.resolve(strict=False)
    for path in paths:
        lexical = Path(os.path.abspath(path))
        try:
            lexical.relative_to(root)
        except ValueError as error:
            raise ValueError("Review repository path escapes the workspace root.") from error
        current = root
        relative = lexical.relative_to(root)
        for component in relative.parts:
            current = current / component
            if current.exists() or current.is_symlink():
                if _is_symlink_or_reparse(current):
                    raise ValueError(
                        f"Review repository path contains a symlink or reparse point: {current}"
                    )
        resolved = lexical.resolve(strict=False)
        try:
            resolved.relative_to(resolved_root)
        except ValueError as error:
            raise ValueError(
                "Review repository path escapes through a symlink or reparse point."
            ) from error


def _is_symlink_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(attributes & reparse_flag)


@contextmanager
def _exclusive_lock(path: Path, *, timeout_seconds: float = 10.0):
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    while descriptor is None:
        if _is_symlink_or_reparse(path):
            raise ValueError("Review ledger lock must not be a symlink or reparse point.")
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            if _is_symlink_or_reparse(path):
                raise ValueError(
                    "Review ledger lock must not be a symlink or reparse point."
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out acquiring review ledger lock: {path}")
            time.sleep(0.01)
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _write_exclusive_fsync(path: Path, data: bytes) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "InvalidReviewDecisionLedgerError",
    "ReviewDecisionLedgerSnapshot",
    "ReviewDecisionRepository",
    "ReviewDecisionWriteResult",
    "ReviewDecisionWriteStatus",
]
