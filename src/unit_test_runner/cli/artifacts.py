from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from unit_test_runner.contracts import ArtifactKind, validate_artifact


@dataclass(frozen=True)
class ProducedArtifact:
    kind: str
    path: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "path": self.path,
            "sha256": self.sha256,
        }


def build_produced_artifact(
    root: Path | str,
    path: Path | str,
    *,
    kind: str | None,
) -> ProducedArtifact:
    if kind is None:
        raise ValueError("A produced artifact requires a public artifact kind.")
    try:
        public_kind = ArtifactKind(kind)
    except ValueError as error:
        raise ValueError(f"Unsupported public artifact kind: {kind!r}") from error

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
    if resolved.suffix.lower() != ".json":
        raise ValueError("Public artifacts must be JSON documents; views are not artifacts.")

    final_bytes = resolved.read_bytes()
    try:
        decoded = json.loads(final_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Produced JSON artifact is invalid: {resolved}: {error}") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"Produced JSON artifact root must be an object: {resolved}")
    if decoded.get("artifact_kind") != public_kind.value:
        raise ValueError(
            "Produced JSON artifact kind does not match the declared artifact kind: "
            f"expected {public_kind.value!r}, received {decoded.get('artifact_kind')!r}."
        )
    violations = validate_artifact(public_kind, decoded)
    if violations:
        detail = "; ".join(
            f"{item.code} at {item.json_path}: {item.message}" for item in violations
        )
        raise ValueError(f"Produced JSON artifact violates its contract: {resolved}: {detail}")

    return ProducedArtifact(
        kind=public_kind.value,
        path=relative.as_posix(),
        sha256=hashlib.sha256(final_bytes).hexdigest(),
    )


def _contained_relative(root: Path, path: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"Artifact path escapes allowed root: {path}") from error
