from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
        declared_kind = decoded.get("artifact_kind") if isinstance(decoded, dict) else None
        declared_version = decoded.get("schema_version") if isinstance(decoded, dict) else None
        has_contract_identity = isinstance(declared_kind, str) and isinstance(declared_version, str)
        if kind is not None and not has_contract_identity:
            raise ValueError(
                f"Produced JSON artifact is missing verifiable contract identity: {resolved}"
            )
        if has_contract_identity:
            if kind is not None and declared_kind != kind:
                raise ValueError(
                    "Produced JSON artifact kind does not match the declared artifact kind: "
                    f"expected {kind!r}, received {declared_kind!r}."
                )
            actual_kind = declared_kind
            schema_version = declared_version
        else:
            actual_kind = "untyped_json"
            schema_version = declared_version if isinstance(declared_version, str) else None

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
