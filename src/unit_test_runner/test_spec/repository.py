from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from unit_test_runner.cli.artifacts import ProducedArtifact, build_produced_artifact
from unit_test_runner.contracts import ArtifactKind, ContractMode, ContractViolation, load_artifact

from .migration import migrate_legacy_test_case_design
from .models import (
    CurrentArtifactContext,
    TestSpec,
    TestSpecContractError,
    validate_test_spec,
)


class StaleRevisionError(ValueError):
    pass


def load_test_spec(
    path: Path,
    *,
    mode: ContractMode,
    current_context: CurrentArtifactContext | None = None,
) -> TestSpec:
    path = Path(path)
    try:
        decoded = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TestSpecContractError(
            (ContractViolation("parse_error", "$", str(error)),)
        ) from error
    if not isinstance(decoded, dict):
        raise TestSpecContractError(
            (ContractViolation("schema_error", "$", "Artifact root must be an object."),)
        )
    if decoded.get("artifact_kind") == ArtifactKind.TEST_SPEC.value:
        loaded = load_artifact(
            path,
            expected_kind=ArtifactKind.TEST_SPEC,
            mode=mode,
        )
        if loaded.violations:
            raise TestSpecContractError(loaded.violations)
        payload = loaded.payload
    else:
        if mode is ContractMode.STRICT:
            raise TestSpecContractError(
                (
                    ContractViolation(
                        "unsupported_version",
                        "$.schema_version",
                        "Strict test_spec reads require the current canonical envelope.",
                    ),
                )
            )
        payload = migrate_legacy_test_case_design(decoded)
    spec = TestSpec.from_payload(payload, validate=False)
    violations = validate_test_spec(spec, current_context=current_context)
    if violations:
        raise TestSpecContractError(violations)
    return spec


def save_test_spec(
    path: Path,
    spec: TestSpec,
    *,
    expected_revision: int | None,
    current_context: CurrentArtifactContext | None = None,
) -> ProducedArtifact:
    path = Path(path)
    if current_context is None:
        raise TestSpecContractError(
            (
                ContractViolation(
                    "missing_current_context",
                    "$",
                    "Saving test_spec requires explicit current source and signature context.",
                    "blocking",
                ),
            )
        )
    root = (current_context.workspace_root or path.parent.parent).resolve()
    expected_path = root / "reports" / "test_spec.json"
    lexical_path = Path(os.path.abspath(path))
    if lexical_path != expected_path:
        raise ValueError("Canonical test specifications must be written to the workspace reports/test_spec.json.")
    resolved_parent = path.parent.resolve(strict=False)
    if resolved_parent != root / "reports":
        raise ValueError("Canonical test_spec parent must not escape through a symlink.")
    if path.is_symlink():
        raise ValueError("Canonical test_spec.json must not be a symbolic link.")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    if lock_path.is_symlink():
        raise ValueError("Canonical test_spec lock must not be a symbolic link.")
    with _exclusive_lock(lock_path):
        exists = path.exists()
        if exists:
            current = load_test_spec(path, mode=ContractMode.STRICT)
            if expected_revision is None or current.revision != expected_revision:
                raise StaleRevisionError(
                    f"Expected test_spec revision {expected_revision!r}; current revision is {current.revision}."
                )
            if spec.revision != expected_revision:
                raise StaleRevisionError(
                    f"Candidate revision {spec.revision} does not match expected revision {expected_revision}."
                )
            final_revision = current.revision + 1
        else:
            if expected_revision is not None:
                raise StaleRevisionError(
                    f"Cannot update missing test_spec at expected revision {expected_revision}."
                )
            if spec.revision not in {0, 1}:
                raise StaleRevisionError(
                    "Initial test_spec creation must start at revision 0 or 1."
                )
            final_revision = 1
        candidate = spec.with_revision(final_revision)
        violations = validate_test_spec(candidate, current_context=current_context)
        if violations:
            raise TestSpecContractError(violations)
        final_bytes = _canonical_json_bytes(candidate.to_payload())
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(final_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    return build_produced_artifact(
        root,
        path,
        kind=ArtifactKind.TEST_SPEC.value,
    )


def canonical_json_bytes(spec: TestSpec) -> bytes:
    return _canonical_json_bytes(spec.to_payload())


def _canonical_json_bytes(payload: dict) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


@contextmanager
def _exclusive_lock(path: Path, *, timeout_seconds: float = 10.0):
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out acquiring test_spec lock: {path}")
            time.sleep(0.01)
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
        yield
    finally:
        os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
