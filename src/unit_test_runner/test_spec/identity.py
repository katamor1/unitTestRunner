from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from unit_test_runner.contracts import ArtifactKind, migrate_payload, validate_payload
from unit_test_runner.contracts.registry import get_contract

from .models import ArtifactReference, CurrentArtifactContext, TestSpec


_TOP_LEVEL_PROVENANCE_FILES = (
    ("source_digest", "source_digest.json"),
    ("function_location", "function_location.json"),
    ("function_signature", "function_signature.json"),
    ("global_access", "global_access.json"),
    ("call_report", "call_report.json"),
    ("dependency_policy", "dependency_policy.json"),
    ("coverage_design", "coverage_design.json"),
    ("boundary_candidates", "boundary_equivalence_candidates.json"),
)
_REANALYSIS_PROVENANCE_FILES = tuple(
    item for item in _TOP_LEVEL_PROVENANCE_FILES if item[0] != "dependency_policy"
)
_PROVENANCE_LAYOUTS = (
    (Path("reports"), _TOP_LEVEL_PROVENANCE_FILES),
    (Path("reports/reanalysis/current"), _REANALYSIS_PROVENANCE_FILES),
)
_LEGACY_REQUIRED_FIELDS: dict[str, dict[str, type]] = {
    "source_digest": {
        "source": dict,
        "masking": dict,
        "preprocessor": dict,
        "token_summary": dict,
        "warnings": list,
    },
    "function_location": {"source": dict, "function": dict, "warnings": list},
    "function_signature": {"source": dict, "function": dict, "warnings": list},
    "global_access": {
        "source": dict,
        "function": dict,
        "global_accesses": list,
        "warnings": list,
    },
    "call_report": {
        "source": dict,
        "function": dict,
        "calls": list,
        "warnings": list,
    },
    "dependency_policy": {
        "source": dict,
        "function": dict,
        "dependencies": list,
        "warnings": list,
    },
    "coverage_design": {
        "source": dict,
        "function": dict,
        "coverage_items": list,
        "warnings": list,
    },
    "boundary_candidates": {
        "source": dict,
        "function": dict,
        "input_candidates": list,
        "warnings": list,
    },
}
_LEGACY_ALLOWED_FIELDS: dict[str, set[str]] = {
    "source_digest": {
        "schema_version", "source", "masking", "preprocessor",
        "token_summary", "warnings", "tokens",
    },
    "function_location": {"schema_version", "source", "function", "warnings"},
    "function_signature": {"schema_version", "source", "function", "warnings"},
    "global_access": {
        "schema_version", "source", "function", "file_scope_declarations",
        "local_declarations", "parameter_accesses", "global_accesses",
        "unresolved_identifiers", "side_effect_candidates", "warnings",
    },
    "call_report": {
        "schema_version", "source", "function", "calls", "stub_candidates",
        "side_effect_candidates", "unresolved_calls", "warnings",
    },
    "dependency_policy": {
        "schema_version", "source", "function", "dependencies",
        "external_objects", "warnings",
    },
    "coverage_design": {
        "schema_version", "source", "function", "branches", "switches",
        "loops", "ternaries", "return_paths", "condition_expressions",
        "coverage_items", "warnings",
    },
    "boundary_candidates": {
        "schema_version", "source", "function", "input_candidates",
        "state_candidates", "stub_return_candidates", "equivalence_classes",
        "boundary_groups", "coverage_links", "warnings",
    },
}


def signature_sha256(payload: Mapping[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, Mapping) and isinstance(data.get("function"), Mapping):
        function = data["function"]
    else:
        function = payload.get("function")
    if not isinstance(function, Mapping):
        raise ValueError("Function signature artifact has no function object.")
    encoded = json.dumps(
        dict(function),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stable_function_id(source_path: str, function_name: str) -> str:
    normalized_path = _relative_path(source_path)
    name = str(function_name).strip()
    if not name:
        raise ValueError("Function name is required for stable identity.")
    suffix = hashlib.sha256(
        f"{normalized_path}\0{name}".encode("utf-8")
    ).hexdigest()[:12]
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"fn_{slug or 'function'}_{suffix}"


def build_current_artifact_context(
    workspace: Path,
    spec: TestSpec,
) -> CurrentArtifactContext:
    workspace = Path(workspace).resolve()
    request_path = workspace / "input" / "request.json"
    request = _read_json(request_path) if request_path.is_file() else {}
    source_path = _relative_path(spec.source.path)
    if request.get("source") and _relative_path(str(request["source"])) != source_path:
        raise ValueError("Canonical test spec source differs from input/request.json.")
    source_candidates = [workspace / source_path, workspace / "extracted" / source_path]
    request_workspace = request.get("workspace")
    if isinstance(request_workspace, str) and request_workspace:
        declared_root = Path(request_workspace).expanduser().resolve()
        declared_source = (declared_root / source_path).resolve(strict=False)
        try:
            declared_source.relative_to(declared_root)
        except ValueError:
            pass
        else:
            source_candidates.insert(0, declared_source)
    source_file = _first_regular_from_scoped_roots(
        workspace,
        tuple(source_candidates),
        extra_root=(Path(request_workspace).expanduser().resolve() if isinstance(request_workspace, str) and request_workspace else None),
    )
    source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    prefix, layout, references = _saved_provenance_layout(spec)
    expected_function = str(request.get("function") or spec.function.name)
    current_references: list[ArtifactReference] = []
    signature_payload: dict[str, Any] | None = None
    for artifact_kind, filename in layout:
        relative_path = (prefix / filename).as_posix()
        artifact_path = _contained_file(workspace, relative_path)
        raw_bytes = artifact_path.read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        reference = references[artifact_kind]
        if digest != reference.sha256:
            raise ValueError(
                f"Provenance hash mismatch for {artifact_kind}: {relative_path}"
            )
        payload = _validated_provenance_payload(
            artifact_kind,
            raw_bytes,
            source_path=source_path,
            source_sha256=source_hash,
            function_name=expected_function,
        )
        if artifact_kind == "function_signature":
            signature_payload = payload
        current_references.append(reference)
    if signature_payload is None:
        raise ValueError("Saved provenance has no function_signature artifact.")
    function = signature_payload.get("data")
    if isinstance(function, Mapping):
        function = function.get("function")
    else:
        function = signature_payload.get("function")
    if not isinstance(function, Mapping):
        raise ValueError("Function signature artifact has no current function identity.")
    function_name = str(function.get("name") or "")
    function_id = stable_function_id(source_path, function_name)
    return CurrentArtifactContext(
        source_path=source_path,
        source_sha256=source_hash,
        function_id=function_id,
        function_name=function_name,
        signature_sha256=signature_sha256(signature_payload),
        workspace_root=workspace,
        generated_from=tuple(current_references),
    )


def _saved_provenance_layout(
    spec: TestSpec,
) -> tuple[Path, tuple[tuple[str, str], ...], dict[str, ArtifactReference]]:
    actual = [(item.artifact_kind, item.path) for item in spec.generated_from]
    for prefix, layout in _PROVENANCE_LAYOUTS:
        expected = [(kind, (prefix / filename).as_posix()) for kind, filename in layout]
        if len(actual) == len(expected) and set(actual) == set(expected):
            references = {item.artifact_kind: item for item in spec.generated_from}
            if len(references) != len(spec.generated_from):
                break
            return prefix, layout, references
    raise ValueError(
        "Canonical test spec provenance must exactly match one known producing root "
        "with no missing, duplicate, extra, or redirected artifacts."
    )


def _validated_provenance_payload(
    artifact_kind: str,
    raw_bytes: bytes,
    *,
    source_path: str,
    source_sha256: str,
    function_name: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Invalid {artifact_kind} provenance JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ValueError(f"{artifact_kind} provenance root must be an object.")
    declared_kind = payload.get("artifact_kind")
    if declared_kind is None:
        _validate_legacy_provenance_shape(artifact_kind, payload)
        normalized = payload
    else:
        if declared_kind != artifact_kind:
            raise ValueError(
                f"Provenance kind mismatch: expected {artifact_kind}, "
                f"received {declared_kind!r}."
            )
        try:
            kind = ArtifactKind(artifact_kind)
        except ValueError as error:
            raise ValueError(f"Unknown provenance artifact kind: {artifact_kind}") from error
        contract = get_contract(kind)
        version = str(payload.get("schema_version") or "")
        if version == contract.current_version:
            normalized = payload
        elif version in contract.compatible_source_versions:
            try:
                normalized = migrate_payload(
                    kind,
                    payload,
                    target_version=contract.current_version,
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid compatible {artifact_kind} provenance: {error}"
                ) from error
        else:
            raise ValueError(
                f"Unsupported {artifact_kind} provenance version: {version or '<missing>'}"
            )
        violations = validate_payload(kind, normalized)
        if violations:
            detail = "; ".join(
                f"{item.code} at {item.json_path}: {item.message}"
                for item in violations
            )
            raise ValueError(
                f"Invalid {artifact_kind} provenance contract: {detail}"
            )
    _validate_provenance_identity(
        artifact_kind,
        normalized,
        source_path=source_path,
        source_sha256=source_sha256,
        function_name=function_name,
    )
    return normalized


def _validate_legacy_provenance_shape(
    artifact_kind: str,
    payload: Mapping[str, Any],
) -> None:
    if payload.get("schema_version") != "0.1":
        raise ValueError(
            f"Untyped {artifact_kind} provenance must be the explicit v0.1 shape."
        )
    requirements = _LEGACY_REQUIRED_FIELDS.get(artifact_kind)
    if requirements is None:
        raise ValueError(f"Unsupported legacy provenance kind: {artifact_kind}")
    invalid = [
        field
        for field, expected_type in requirements.items()
        if not isinstance(payload.get(field), expected_type)
    ]
    if invalid:
        raise ValueError(
            f"Legacy {artifact_kind} provenance has missing or invalid fields: "
            + ", ".join(invalid)
        )
    unknown = set(payload) - _LEGACY_ALLOWED_FIELDS[artifact_kind]
    if unknown:
        raise ValueError(
            f"Legacy {artifact_kind} provenance has unknown fields: "
            + ", ".join(sorted(unknown))
        )
    function = payload.get("function")
    if artifact_kind == "function_location" and (
        not isinstance(function, Mapping)
        or not isinstance(function.get("candidates"), list)
    ):
        raise ValueError("Legacy function_location has no candidates array.")
    if artifact_kind == "function_signature" and (
        not isinstance(function, Mapping)
        or not isinstance(function.get("parameters"), list)
        or not isinstance(function.get("header_text_normalized"), str)
    ):
        raise ValueError("Legacy function_signature has no parsed signature identity.")


def _validate_provenance_identity(
    artifact_kind: str,
    payload: Mapping[str, Any],
    *,
    source_path: str,
    source_sha256: str,
    function_name: str,
) -> None:
    data = payload.get("data")
    identity = data if isinstance(data, Mapping) else payload
    source = identity.get("source")
    if not isinstance(source, Mapping) or not _source_path_matches(
        str(source.get("path") or ""), source_path
    ):
        raise ValueError(
            f"{artifact_kind} provenance source path does not match {source_path}."
        )
    declared_sha = str(source.get("sha256") or "")
    hash_required = artifact_kind not in {
        "function_location",
        "dependency_policy",
    }
    if (hash_required and not declared_sha) or (
        declared_sha and declared_sha != source_sha256
    ):
        raise ValueError(
            f"{artifact_kind} provenance source hash does not match current source."
        )
    if artifact_kind != "source_digest":
        function = identity.get("function")
        if not isinstance(function, Mapping) or str(function.get("name") or "") != function_name:
            raise ValueError(
                f"{artifact_kind} provenance function does not match {function_name}."
            )
    subject = payload.get("subject")
    if isinstance(subject, Mapping):
        subject_path = subject.get("source_path")
        if subject_path and not _source_path_matches(str(subject_path), source_path):
            raise ValueError(f"{artifact_kind} subject source path is inconsistent.")
        subject_sha = subject.get("source_sha256")
        if subject_sha and str(subject_sha) != source_sha256:
            raise ValueError(f"{artifact_kind} subject source hash is inconsistent.")
        subject_function = subject.get("function_id")
        if (
            artifact_kind != "source_digest"
            and subject_function
            and str(subject_function) != stable_function_id(source_path, function_name)
        ):
            raise ValueError(f"{artifact_kind} subject function is inconsistent.")


def _source_path_matches(declared: str, expected_relative: str) -> bool:
    normalized = declared.replace("\\", "/")
    if normalized == expected_relative:
        return True
    return normalized.endswith("/" + expected_relative)


def artifact_reference(
    workspace: Path,
    path: Path,
    *,
    artifact_kind: str,
) -> ArtifactReference:
    workspace = Path(workspace).resolve()
    resolved = path.resolve()
    relative = resolved.relative_to(workspace).as_posix()
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError(f"Artifact reference must identify a regular non-symlink file: {path}")
    return ArtifactReference(
        artifact_kind=artifact_kind,
        path=relative,
        sha256=hashlib.sha256(resolved.read_bytes()).hexdigest(),
    )


def bind_test_spec_inputs(
    workspace: Path,
    spec: TestSpec,
    inputs: Mapping[str, Path | str],
) -> None:
    workspace = Path(workspace).resolve()
    _prefix, _layout, references = _saved_provenance_layout(spec)
    required = {"function_signature", "global_access", "call_report"}
    if "dependency_policy" in references:
        required.add("dependency_policy")
    if set(inputs) != required:
        raise ValueError(
            "Harness inputs must exactly include canonical provenance kinds: "
            + ", ".join(sorted(required))
        )
    for artifact_kind in sorted(required):
        reference = references[artifact_kind]
        supplied = Path(inputs[artifact_kind])
        if supplied.is_symlink():
            raise ValueError(f"Harness input must not be a symlink: {supplied}")
        supplied_path = supplied.resolve(strict=False)
        expected_path = (workspace / reference.path).resolve(strict=False)
        if supplied_path != expected_path or not supplied_path.is_file():
            raise ValueError(
                f"Harness {artifact_kind} input must be the exact canonical "
                f"provenance file: {reference.path}"
            )
        digest = hashlib.sha256(supplied_path.read_bytes()).hexdigest()
        if digest != reference.sha256:
            raise ValueError(
                f"Harness {artifact_kind} input hash does not match test_spec provenance."
            )


def _relative_path(value: str) -> str:
    text = str(value).replace("\\", "/")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", text):
        raise ValueError(f"Expected normalized relative path: {value}")
    return path.as_posix()


def _contained_file(workspace: Path, relative: str) -> Path:
    normalized = _relative_path(relative)
    return _first_regular_contained(workspace, (workspace / normalized,))


def _first_regular_contained(workspace: Path, candidates: tuple[Path, ...]) -> Path:
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(workspace)
        except ValueError:
            continue
        if resolved.is_file() and not candidate.is_symlink():
            return resolved
    raise FileNotFoundError(
        "Current artifact file is missing or escapes the workspace: "
        + ", ".join(str(item) for item in candidates)
    )


def _first_regular_from_scoped_roots(
    workspace: Path,
    candidates: tuple[Path, ...],
    *,
    extra_root: Path | None,
) -> Path:
    roots = (workspace,) if extra_root is None else (workspace, extra_root)
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if not any(_is_within(resolved, root) for root in roots):
            continue
        if resolved.is_file() and not candidate.is_symlink():
            return resolved
    raise FileNotFoundError(
        "Current source artifact is missing or escapes declared roots: "
        + ", ".join(str(item) for item in candidates)
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Artifact root must be an object: {path}")
    return value
