from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .kinds import ArtifactKind


@dataclass(frozen=True)
class ContractViolation:
    code: str
    json_path: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class LoadedArtifact:
    kind: ArtifactKind
    payload: dict[str, Any]
    violations: tuple[ContractViolation, ...]
