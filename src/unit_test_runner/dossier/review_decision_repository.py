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
from typing import Callable, TypeVar
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


_T = TypeVar("_T")
_WINDOWS_SHARING_RETRY_SECONDS = 1.0
_WINDOWS_SHARING_RETRY_DELAY_SECONDS = 0.01
_WINDOWS_TRANSIENT_PERMISSION_WINERRORS = frozenset({32, 33})


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
                _replace_with_windows_retry(temporary, self._path)
                _fsync_directory(self._path.parent)
            finally:
                try:
                    _unlink_with_windows_retry(temporary)
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
        # Ledger, lock, and temporary leaf files are intentionally volatile. A
        # concurrent writer may create or remove one between the component check
        # above and Path.resolve(), so resolve only the stable parent directory.
        resolved_parent = lexical.parent.resolve(strict=False)
        expected_parent = resolved_root / relative.parent
        if resolved_parent != expected_parent:
            raise ValueError(
                "Review repository path escapes through a symlink or reparse point."
            )


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


def _running_on_windows() -> bool:
    return os.name == "nt"


def _is_transient_windows_permission_error(error: PermissionError) -> bool:
    return (
        _running_on_windows()
        and getattr(error, "winerror", None)
        in _WINDOWS_TRANSIENT_PERMISSION_WINERRORS
    )


def _retry_windows_permission_error(
    operation: Callable[[], _T],
    *,
    timeout_seconds: float = _WINDOWS_SHARING_RETRY_SECONDS,
    deadline: float | None = None,
) -> _T:
    if deadline is None:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
    last_permission_error: PermissionError | None = None
    while True:
        if last_permission_error is not None and time.monotonic() >= deadline:
            raise last_permission_error
        try:
            return operation()
        except PermissionError as error:
            if not _is_transient_windows_permission_error(error):
                raise
            last_permission_error = error
            now = time.monotonic()
            if now >= deadline:
                raise
            time.sleep(min(_WINDOWS_SHARING_RETRY_DELAY_SECONDS, deadline - now))


def _replace_with_windows_retry(source: Path, destination: Path) -> None:
    _retry_windows_permission_error(lambda: os.replace(source, destination))


def _unlink_with_windows_retry(path: Path) -> None:
    _retry_windows_permission_error(path.unlink)


def _lock_file_identity(metadata: os.stat_result) -> tuple[int, int]:
    return (int(metadata.st_dev), int(metadata.st_ino))


def _assert_owned_lock(
    path: Path,
    *,
    expected_identity: tuple[int, int],
    expected_token: bytes,
) -> None:
    if _is_symlink_or_reparse(path):
        raise ValueError("Review ledger lock must not be a symlink or reparse point.")
    current_identity = _lock_file_identity(os.stat(path, follow_symlinks=False))
    if current_identity != expected_identity or path.read_bytes() != expected_token:
        raise RuntimeError(
            "Review ledger lock ownership changed before cleanup; refusing to unlink."
        )


@contextmanager
def _exclusive_lock(path: Path, *, timeout_seconds: float = 10.0):
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    flags = (
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_BINARY", 0)
    )
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    def open_lock() -> int:
        if _is_symlink_or_reparse(path):
            raise ValueError("Review ledger lock must not be a symlink or reparse point.")
        return os.open(path, flags, 0o600)

    while descriptor is None:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out acquiring review ledger lock: {path}")
        try:
            descriptor = _retry_windows_permission_error(
                open_lock,
                deadline=deadline,
            )
        except FileExistsError:
            if _is_symlink_or_reparse(path):
                raise ValueError(
                    "Review ledger lock must not be a symlink or reparse point."
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out acquiring review ledger lock: {path}")
            time.sleep(0.01)
    ownership_token = f"{os.getpid()}:{uuid4().hex}\n".encode("ascii")
    ownership_identity: tuple[int, int] | None = None
    try:
        unwritten = memoryview(ownership_token)
        while unwritten:
            written = os.write(descriptor, unwritten)
            if written <= 0:
                raise OSError("Failed to write review ledger lock ownership token.")
            unwritten = unwritten[written:]
        os.fsync(descriptor)
        ownership_identity = _lock_file_identity(os.fstat(descriptor))
        yield
    finally:
        os.close(descriptor)

        if ownership_identity is not None:
            def unlink_owned_lock() -> None:
                _assert_owned_lock(
                    path,
                    expected_identity=ownership_identity,
                    expected_token=ownership_token,
                )
                path.unlink()

            try:
                _retry_windows_permission_error(unlink_owned_lock)
            except FileNotFoundError:
                pass


def _write_exclusive_fsync(path: Path, data: bytes) -> None:
    # Windows CRT text mode translates LF to CRLF even for os.write().
    # Contract artifacts must preserve the exact validated byte sequence.
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
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
