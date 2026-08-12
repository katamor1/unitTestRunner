from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar
from uuid import uuid4

from unit_test_runner.cli.artifacts import ProducedArtifact, build_produced_artifact
from unit_test_runner.contracts import (
    ArtifactKind,
    ContractViolation,
    validate_artifact,
)
from unit_test_runner.path_utils import resolved_relative_to
from unit_test_runner.workspace_artifacts import (
    WorkspaceRegenerationRequired,
    load_public_artifact,
)

from .models import (
    CurrentArtifactContext,
    TestSpec,
    TestSpecContractError,
    validate_test_spec,
)
from .path_safety import assert_safe_canonical_test_spec_path


class StaleRevisionError(ValueError):
    pass


_T = TypeVar("_T")
_WINDOWS_SHARING_RETRY_SECONDS = 1.0
_WINDOWS_SHARING_RETRY_DELAY_SECONDS = 0.01


@dataclass(frozen=True)
class TestSpecSnapshot:
    spec: TestSpec
    raw_bytes: bytes
    sha256: str


def load_test_spec(
    path: Path,
    *,
    current_context: CurrentArtifactContext | None = None,
) -> TestSpec:
    return load_test_spec_snapshot(
        path,
        current_context=current_context,
    ).spec


def load_test_spec_snapshot(
    path: Path,
    *,
    current_context: CurrentArtifactContext | None = None,
) -> TestSpecSnapshot:
    path = Path(path)
    try:
        assert_safe_canonical_test_spec_path(path)
    except ValueError as error:
        raise TestSpecContractError(
            (
                ContractViolation(
                    "unsafe_canonical_path", "$", str(error), "blocking"
                ),
            )
        ) from error
    try:
        raw_bytes = path.read_bytes()
    except OSError as error:
        raise TestSpecContractError(
            (ContractViolation("parse_error", "$", str(error)),)
        ) from error
    return _snapshot_from_bytes(
        raw_bytes,
        current_context=current_context,
    )


def _snapshot_from_bytes(
    raw_bytes: bytes,
    *,
    current_context: CurrentArtifactContext | None = None,
) -> TestSpecSnapshot:
    try:
        decoded = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise TestSpecContractError(
            (ContractViolation("parse_error", "$", str(error)),)
        ) from error
    if not isinstance(decoded, dict):
        raise TestSpecContractError(
            (ContractViolation("schema_error", "$", "Artifact root must be an object."),)
        )
    source_version = decoded.get("schema_version")
    if source_version != "1.0.0":
        raise WorkspaceRegenerationRequired(
            f"Workspace test_spec uses schema {source_version!r}; regenerate the workspace for v0.1."
        )
    if decoded.get("artifact_kind") != ArtifactKind.TEST_SPEC.value:
        raise TestSpecContractError(
            (
                ContractViolation(
                    "artifact_kind_mismatch",
                    "$.artifact_kind",
                    "Expected test_spec; received "
                    + repr(decoded.get("artifact_kind"))
                    + ".",
                ),
            )
        )
    contract_violations = validate_artifact(ArtifactKind.TEST_SPEC, decoded)
    if contract_violations:
        raise TestSpecContractError(contract_violations)
    spec = TestSpec.from_payload(decoded, validate=False)
    violations = validate_test_spec(spec, current_context=current_context)
    if violations:
        raise TestSpecContractError(violations)
    return TestSpecSnapshot(
        spec=spec,
        raw_bytes=raw_bytes,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def save_test_spec(
    path: Path,
    spec: TestSpec,
    *,
    expected_revision: int | None,
    current_context: CurrentArtifactContext | None = None,
) -> ProducedArtifact:
    _snapshot, artifact = save_test_spec_snapshot(
        path,
        spec,
        expected_revision=expected_revision,
        current_context=current_context,
    )
    return artifact


def save_test_spec_snapshot(
    path: Path,
    spec: TestSpec,
    *,
    expected_revision: int | None,
    current_context: CurrentArtifactContext | None = None,
) -> tuple[TestSpecSnapshot, ProducedArtifact]:
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
    lexical_path, lexical_workspace = assert_safe_canonical_test_spec_path(path)
    root = Path(current_context.workspace_root or lexical_workspace)
    try:
        relative_path = resolved_relative_to(lexical_path, root)
    except ValueError as error:
        raise ValueError(
            "Canonical test specifications must be written to the workspace reports/test_spec.json."
        ) from error
    if relative_path != Path("reports") / "test_spec.json":
        raise ValueError(
            "Canonical test specifications must be written to the workspace reports/test_spec.json."
        )
    resolved_root = root.resolve(strict=False)
    resolved_parent = lexical_path.parent.resolve(strict=False)
    if resolved_parent != resolved_root / "reports":
        raise ValueError("Canonical test_spec parent must not escape through a symlink.")
    path = lexical_path
    if path.is_symlink():
        raise ValueError("Canonical test_spec.json must not be a symbolic link.")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    if lock_path.is_symlink():
        raise ValueError("Canonical test_spec lock must not be a symbolic link.")
    with _exclusive_lock(lock_path):
        exists = path.exists()
        current: TestSpec | None = None
        if exists:
            current = load_test_spec(path)
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
        candidate = _bind_subject_context(
            spec.with_revision(final_revision),
            current_context,
            current=current,
            workspace=resolved_root,
        )
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
            _replace_with_windows_retry(temporary, path)
        finally:
            try:
                _unlink_with_windows_retry(temporary)
            except FileNotFoundError:
                pass
        snapshot = _snapshot_from_bytes(
            final_bytes,
            current_context=current_context,
        )
        artifact = build_produced_artifact(
            resolved_root,
            path,
            kind=ArtifactKind.TEST_SPEC.value,
        )
    return snapshot, artifact


def _bind_subject_context(
    spec: TestSpec,
    context: CurrentArtifactContext,
    *,
    current: TestSpec | None,
    workspace: Path,
) -> TestSpec:
    candidates = [
        _complete_subject_pair(context.project, context.configuration),
        resolve_workspace_subject_context(workspace),
        _complete_subject_pair(
            current.project if current is not None else None,
            current.configuration if current is not None else None,
        ),
    ]
    resolved = next((value for value in candidates if value is not None), None)
    if resolved is None:
        raise WorkspaceRegenerationRequired(
            "Cannot bind test_spec project and full configuration; regenerate the workspace for v0.1."
        )
    project, configuration = resolved
    mismatches: list[ContractViolation] = []
    for field_name, actual, expected in (
        ("project", spec.project, project),
        ("configuration", spec.configuration, configuration),
    ):
        if isinstance(actual, str) and actual.strip() and actual != expected:
            mismatches.append(
                ContractViolation(
                    f"stale_{field_name}",
                    f"$.subject.{field_name}",
                    f"Test spec {field_name} does not match the current workspace.",
                    "blocking",
                )
            )
    if mismatches:
        raise TestSpecContractError(tuple(mismatches))
    return spec.with_subject_context(
        project=project,
        configuration=configuration,
    )


def resolve_workspace_subject_context(
    workspace: Path,
) -> tuple[str, str] | None:
    return _subject_pair_from_current_dossier(
        workspace
    ) or _subject_pair_from_request(workspace)


def _complete_subject_pair(
    project: object,
    configuration: object,
) -> tuple[str, str] | None:
    if not isinstance(project, str) or not project.strip():
        return None
    if not isinstance(configuration, str) or not configuration.strip():
        return None
    return project, configuration


def _subject_pair_from_current_dossier(
    workspace: Path,
) -> tuple[str, str] | None:
    path = workspace / "reports" / "function_dossier.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, Mapping)
        or payload.get("schema_version") != "1.0.0"
        or payload.get("artifact_kind") != ArtifactKind.FUNCTION_DOSSIER.value
    ):
        return None
    current = load_public_artifact(path, ArtifactKind.FUNCTION_DOSSIER)
    subject = current.get("subject")
    if not isinstance(subject, Mapping):
        return None
    return _complete_subject_pair(
        subject.get("project"),
        subject.get("configuration"),
    )


def _subject_pair_from_request(workspace: Path) -> tuple[str, str] | None:
    path = workspace / "input" / "request.json"
    if not path.is_file():
        return None
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(request, Mapping):
            raise ValueError("request root is not an object")
        source_root = Path(_required_request_text(request, "workspace")).resolve()
        dsw = Path(_required_request_text(request, "dsw"))
        if not dsw.is_absolute():
            dsw = source_root / dsw
        source = _required_request_text(request, "source")
        requested_configuration = _required_request_text(
            request,
            "configuration",
        )
        raw_project = request.get("project")
        requested_project = (
            raw_project
            if isinstance(raw_project, str) and raw_project.strip()
            else None
        )
        from unit_test_runner.vc6 import select_project_context

        project, configuration, _memberships = select_project_context(
            source_root,
            dsw,
            source,
            requested_configuration,
            requested_project,
        )
        resolved = _complete_subject_pair(
            project.get("project_name"),
            configuration.get("full_name"),
        )
        if resolved is None:
            raise ValueError("selected project has no full configuration")
        return resolved
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise WorkspaceRegenerationRequired(
            "Cannot bind test_spec subject from input/request.json; "
            f"regenerate the workspace for v0.1: {error}"
        ) from error


def _required_request_text(request: Mapping[str, Any], key: str) -> str:
    value = request.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {key}")
    return value


def canonical_json_bytes(spec: TestSpec) -> bytes:
    return _canonical_json_bytes(spec.to_payload())


def _canonical_json_bytes(payload: dict) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _running_on_windows() -> bool:
    return os.name == "nt"


def _retry_windows_permission_error(
    operation: Callable[[], _T],
    *,
    timeout_seconds: float = _WINDOWS_SHARING_RETRY_SECONDS,
) -> _T:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    last_permission_error: PermissionError | None = None
    while True:
        if (
            last_permission_error is not None
            and time.monotonic() >= deadline
        ):
            raise last_permission_error
        try:
            return operation()
        except PermissionError as error:
            if not _running_on_windows():
                raise
            last_permission_error = error
            now = time.monotonic()
            if now >= deadline:
                raise
            time.sleep(
                min(_WINDOWS_SHARING_RETRY_DELAY_SECONDS, deadline - now)
            )


def _replace_with_windows_retry(source: Path, destination: Path) -> None:
    _retry_windows_permission_error(lambda: os.replace(source, destination))


def _unlink_with_windows_retry(path: Path) -> None:
    _retry_windows_permission_error(path.unlink)


@contextmanager
def _exclusive_lock(path: Path, *, timeout_seconds: float = 10.0):
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            remaining = max(0.0, deadline - time.monotonic())
            descriptor = _retry_windows_permission_error(
                lambda: os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY),
                timeout_seconds=remaining,
            )
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
            _unlink_with_windows_retry(path)
        except FileNotFoundError:
            pass
