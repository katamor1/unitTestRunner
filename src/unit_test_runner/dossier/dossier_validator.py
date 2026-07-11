from __future__ import annotations

from pathlib import Path
from typing import Any

from .dossier_models import DossierArtifact, DossierWarning


MVP1_REQUIRED = {"source_digest", "function_location", "function_signature"}


def validate_artifacts(
    artifacts: list[DossierArtifact],
    payloads: dict[str, dict[str, Any]],
    function_name: str | None,
    strict_schema_version: bool = False,
) -> tuple[str | None, Path | None, list[DossierWarning], list[str]]:
    warnings: list[DossierWarning] = []
    blocked_reasons: list[str] = []
    by_kind = {artifact.artifact_kind: artifact for artifact in artifacts}
    for kind in sorted(MVP1_REQUIRED):
        if not by_kind.get(kind) or not by_kind[kind].exists:
            blocked_reasons.append(f"Missing MVP-1 required artifact: {kind}")
    for artifact in artifacts:
        if artifact.contract_status not in {
            "parse_error",
            "schema_error",
            "unsupported_version",
        }:
            continue
        blocking = [
            item
            for item in artifact.contract_violations
            if item.severity not in {"info", "warning"}
        ]
        if not blocking:
            blocked_reasons.append(
                f"Artifact contract {artifact.artifact_kind} is "
                f"{artifact.contract_status}."
            )
        for violation in blocking:
            blocked_reasons.append(
                f"Artifact contract {artifact.artifact_kind} is "
                f"{artifact.contract_status} at {violation.json_path}: "
                f"{violation.code}: {violation.message}"
            )
    discovered_names = _function_names(payloads)
    if function_name is None and discovered_names:
        function_name = sorted(discovered_names)[0]
    if function_name is not None:
        for kind, names in _function_names_by_artifact(payloads).items():
            if names and function_name not in names:
                warning = DossierWarning("function_name_mismatch", f"{kind} has function name(s) {sorted(names)}; expected {function_name}.", related_item=_item_for_kind(artifacts, kind))
                warnings.append(warning)
                _mark_stale(artifacts, kind, warning)
    source_path = _source_path(payloads)
    source_paths = _source_paths_by_artifact(payloads)
    canonical_sources = {_canonical_path(path) for path in source_paths.values() if path}
    if len(canonical_sources) > 1:
        expected = _canonical_path(source_path) if source_path is not None else sorted(canonical_sources)[0]
        for kind, path in source_paths.items():
            if _canonical_path(path) != expected:
                warning = DossierWarning(
                    "source_path_mismatch",
                    f"{kind} has source path {path}; expected {source_path}.",
                    related_item=_item_for_kind(artifacts, kind),
                )
                warnings.append(warning)
                _mark_stale(artifacts, kind, warning)
    return function_name, source_path, warnings, blocked_reasons


def _function_names(payload: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(payload, dict):
        function = payload.get("function")
        if isinstance(function, dict):
            for key in ("name", "function_name"):
                value = function.get(key)
                if isinstance(value, str) and value:
                    names.add(value)
        for key in ("function_name",):
            value = payload.get(key)
            if isinstance(value, str) and value:
                names.add(value)
        target = payload.get("target")
        if isinstance(target, dict):
            value = target.get("function")
            if isinstance(value, str) and value:
                names.add(value)
        for value in payload.values():
            names.update(_function_names(value))
    elif isinstance(payload, list):
        for item in payload:
            names.update(_function_names(item))
    return names


def _function_names_by_artifact(payloads: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    return {kind: _function_names(payload) for kind, payload in payloads.items()}


def _source_path(payloads: dict[str, dict[str, Any]]) -> Path | None:
    for payload in payloads.values():
        path = _source_path_from_payload(payload)
        if path:
            return Path(path)
    return None


def _source_paths_by_artifact(payloads: dict[str, dict[str, Any]]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for kind, payload in payloads.items():
        path = _source_path_from_payload(payload)
        if path:
            paths[kind] = Path(path)
    return paths


def _source_path_from_payload(payload: Any) -> str | None:
    if isinstance(payload, dict):
        source = payload.get("source")
        if isinstance(source, dict):
            for key in ("path", "relative_path", "source_path"):
                value = source.get(key)
                if isinstance(value, str) and value:
                    return value
        target = payload.get("target")
        if isinstance(target, dict):
            value = target.get("source")
            if isinstance(value, str) and value:
                return value
        for key in ("source_path",):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        for value in payload.values():
            nested = _source_path_from_payload(value)
            if nested:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = _source_path_from_payload(item)
            if nested:
                return nested
    return None


def _item_for_kind(artifacts: list[DossierArtifact], kind: str) -> str | None:
    for artifact in artifacts:
        if artifact.artifact_kind == kind:
            return artifact.produced_by_item
    return None


def _mark_stale(artifacts: list[DossierArtifact], kind: str, warning: DossierWarning) -> None:
    for artifact in artifacts:
        if artifact.artifact_kind == kind:
            artifact.stale_candidate = True
            if artifact.contract_status == "valid":
                artifact.contract_status = "stale"
            warning.related_artifact_id = artifact.artifact_id
            artifact.warnings.append(warning)
            return


def _canonical_path(path: Path | None) -> str:
    if path is None:
        return ""
    return path.as_posix().lower()
