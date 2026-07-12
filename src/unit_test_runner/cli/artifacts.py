from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from unit_test_runner.contracts import ArtifactKind, validate_payload
from unit_test_runner.contracts.registry import get_contract


class UnclaimableUntypedJsonError(ValueError):
    """The file may exist, but it cannot be truthfully promoted as a produced artifact."""


@dataclass(frozen=True)
class ProducedArtifact:
    kind: str
    path: str
    exists: bool
    sha256: str | None
    schema_version: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": self.kind,
            "path": self.path,
            "exists": self.exists,
            "sha256": self.sha256,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class ExpectedArtifact:
    kind: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "artifact_kind": self.kind,
            "path": self.path,
        }


def build_produced_artifact(
    root: Path | str,
    path: Path | str,
    *,
    kind: str | None,
) -> ProducedArtifact:
    root_path = Path(root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    resolved = candidate.resolve()
    relative = _contained_relative(root_path, resolved)
    if not resolved.is_file():
        if not resolved.exists():
            raise FileNotFoundError(f"Produced artifact does not exist: {resolved}")
        raise ValueError(f"Produced artifact is not a regular file: {resolved}")

    final_bytes = resolved.read_bytes()
    actual_kind = kind
    schema_version: str | None = None
    if resolved.suffix.lower() == ".json":
        try:
            decoded = json.loads(final_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Produced JSON artifact is invalid: {resolved}: {error}") from error
        if not isinstance(decoded, dict):
            raise ValueError(f"Produced JSON artifact root must be an object: {resolved}")
        declared_kind = decoded.get("artifact_kind")
        declared_version = decoded.get("schema_version")
        if declared_kind is not None:
            if not isinstance(declared_kind, str) or not isinstance(declared_version, str):
                raise ValueError(
                    f"Produced JSON artifact has partial contract identity: {resolved}"
                )
            try:
                contract_kind = ArtifactKind(declared_kind)
                get_contract(contract_kind, declared_version)
            except (ValueError, KeyError) as error:
                raise ValueError(
                    f"Produced JSON artifact has unknown or unsupported contract identity: {resolved}"
                ) from error
            if kind is not None and declared_kind != kind:
                raise ValueError(
                    "Produced JSON artifact kind does not match the declared artifact kind: "
                    f"expected {kind!r}, received {declared_kind!r}."
                )
            violations = validate_payload(contract_kind, decoded)
            if violations:
                detail = "; ".join(
                    f"{item.code} at {item.json_path}: {item.message}"
                    for item in violations
                )
                raise ValueError(f"Produced JSON artifact violates its contract: {resolved}: {detail}")
            actual_kind = declared_kind
            schema_version = declared_version
        else:
            if kind is not None:
                raise ValueError(
                    f"Produced JSON artifact is missing verifiable contract identity: {resolved}"
                )
            if declared_version is None:
                raise UnclaimableUntypedJsonError(
                    f"Produced JSON artifact has no claimable contract identity: {resolved}"
                )
            if declared_version == "0.1" and not _is_recognized_legacy_shape(decoded):
                raise UnclaimableUntypedJsonError(
                    f"Produced JSON artifact is not a recognized genuine legacy shape: {resolved}"
                )
            if declared_version != "0.1":
                raise ValueError(
                    f"Produced JSON artifact has partial or unsupported contract identity: {resolved}"
                )
            actual_kind = "untyped_json"
            schema_version = "0.1"

    if actual_kind is None:
        raise ValueError(f"Produced non-JSON artifact requires an explicit artifact kind: {resolved}")

    return ProducedArtifact(
        kind=actual_kind,
        path=relative.as_posix(),
        exists=True,
        sha256=hashlib.sha256(final_bytes).hexdigest(),
        schema_version=schema_version,
    )


def build_expected_artifact(
    root: Path | str,
    path: Path | str,
    *,
    kind: str,
) -> ExpectedArtifact:
    root_path = Path(root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    resolved = candidate.resolve(strict=False)
    relative = _contained_relative(root_path, resolved)
    return ExpectedArtifact(kind=kind, path=relative.as_posix())


def _contained_relative(root: Path, path: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"Artifact path escapes allowed root: {path}") from error


def _is_recognized_legacy_shape(payload: dict[str, Any]) -> bool:
    if payload.get("schema_version") != "0.1" or "artifact_kind" in payload:
        return False

    def has_types(required: dict[str, type]) -> bool:
        return all(isinstance(payload.get(key), value_type) for key, value_type in required.items())

    recognizers = (
        has_types(
            {
                "status": str,
                "command": str,
                "exit_code": int,
                "data": dict,
                "warnings": list,
                "errors": list,
            }
        ),
        has_types({"suite_id": str, "entries": list}),
        has_types(
            {
                "suite_id": str,
                "selector": dict,
                "policy": dict,
                "summary": dict,
                "results": list,
            }
        )
        and isinstance(payload.get("outcome") or payload.get("status"), str),
        has_types({"function": dict, "test_cases": list}),
        has_types({"target": dict})
        and isinstance(payload["target"].get("function"), str)
        and isinstance(payload["target"].get("source"), str),
    )
    return sum(bool(item) for item in recognizers) == 1
