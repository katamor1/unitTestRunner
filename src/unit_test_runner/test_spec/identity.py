from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .models import ArtifactReference, CurrentArtifactContext, TestSpec


_CANONICAL_PROVENANCE_FILES = (
    ("source_digest", "source_digest.json"),
    ("function_location", "function_location.json"),
    ("function_signature", "function_signature.json"),
    ("global_access", "global_access.json"),
    ("call_report", "call_report.json"),
    ("dependency_policy", "dependency_policy.json"),
    ("coverage_design", "coverage_design.json"),
    ("boundary_candidates", "boundary_equivalence_candidates.json"),
)


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
    if request.get("source"):
        source_path = _relative_path(str(request["source"]))
    else:
        signature_candidates = [
            workspace / "reports" / "function_signature.json",
            workspace / "reports" / "reanalysis" / "current" / "function_signature.json",
        ]
        signature_source = None
        for candidate in signature_candidates:
            if candidate.is_file():
                signature_source = _signature_source(_read_json(candidate))
                if isinstance(signature_source, Mapping) and signature_source.get("path"):
                    break
        if not isinstance(signature_source, Mapping) or not signature_source.get("path"):
            raise ValueError("Function signature artifact has no current source identity.")
        source_path = _relative_path(str(signature_source["path"]))
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
    prefix, signature_payload = _select_current_provenance_root(
        workspace,
        source_path=source_path,
        source_sha256=source_hash,
        expected_function=(str(request.get("function") or "") or None),
    )
    current_references: list[ArtifactReference] = []
    for artifact_kind, filename in _CANONICAL_PROVENANCE_FILES:
        relative_path = (prefix / filename).as_posix()
        candidate = workspace / relative_path
        if not candidate.is_file():
            continue
        artifact_path = _contained_file(workspace, relative_path)
        current_references.append(
            ArtifactReference(
                artifact_kind=artifact_kind,
                path=relative_path,
                sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            )
        )
    function = signature_payload.get("data")
    if isinstance(function, Mapping):
        function = function.get("function")
    else:
        function = signature_payload.get("function")
    if not isinstance(function, Mapping):
        raise ValueError("Function signature artifact has no current function identity.")
    function_name = str(function.get("name") or "")
    signature_subject = signature_payload.get("subject")
    declared_function_id = (
        str(signature_subject.get("function_id"))
        if isinstance(signature_subject, Mapping) and signature_subject.get("function_id")
        else str(function.get("function_id") or "")
    )
    return CurrentArtifactContext(
        source_path=source_path,
        source_sha256=source_hash,
        function_id=declared_function_id or stable_function_id(source_path, function_name),
        function_name=function_name,
        signature_sha256=signature_sha256(signature_payload),
        workspace_root=workspace,
        generated_from=tuple(current_references),
    )


def _select_current_provenance_root(
    workspace: Path,
    *,
    source_path: str,
    source_sha256: str,
    expected_function: str | None,
) -> tuple[Path, dict[str, Any]]:
    candidates: list[tuple[float, Path, dict[str, Any]]] = []
    for prefix in (Path("reports"), Path("reports/reanalysis/current")):
        path = workspace / prefix / "function_signature.json"
        if not path.is_file() or path.is_symlink():
            continue
        payload = _read_json(path)
        source = _signature_source(payload)
        function = _signature_function(payload)
        if not isinstance(source, Mapping) or not isinstance(function, Mapping):
            continue
        if str(source.get("sha256") or "") != source_sha256:
            continue
        if not _source_path_matches(str(source.get("path") or ""), source_path):
            continue
        if expected_function and str(function.get("name") or "") != expected_function:
            continue
        candidates.append((path.stat().st_mtime_ns, prefix, payload))
    if not candidates:
        raise ValueError("No source-consistent current function signature artifact is available.")
    candidates.sort(key=lambda item: item[0], reverse=True)
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        raise ValueError("Current analysis provenance root is ambiguous.")
    _mtime, prefix, payload = candidates[0]
    return prefix, payload


def _signature_source(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    data = payload.get("data")
    source = data.get("source") if isinstance(data, Mapping) else payload.get("source")
    return source if isinstance(source, Mapping) else None


def _signature_function(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    data = payload.get("data")
    function = data.get("function") if isinstance(data, Mapping) else payload.get("function")
    return function if isinstance(function, Mapping) else None


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
