from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class EvidencePaths:
    evidence_id: str
    source_run_id: str
    root: Path
    evidence_manifest: Path
    evidence_package: Path

    @property
    def source_run(self) -> Path:
        return self.root / "source_run.json"


def create_evidence_paths(
    workspace: Path,
    source_run_id: str,
    evidence_id: str | None = None,
) -> EvidencePaths:
    workspace = Path(workspace).resolve()
    selected_id = evidence_id or _new_evidence_id()
    _validate_id(selected_id, "evidence")
    _validate_id(source_run_id, "run")
    evidence_root = workspace / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    root = evidence_root / selected_id
    root.mkdir(exist_ok=False)
    return EvidencePaths(
        evidence_id=selected_id,
        source_run_id=source_run_id,
        root=root,
        evidence_manifest=root / "evidence_manifest.json",
        evidence_package=root / "evidence_package.md",
    )


def _new_evidence_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"evidence-{timestamp}-{uuid4().hex[:8]}"


def _validate_id(value: str, kind: str) -> None:
    if not value or value in {".", ".."} or Path(value).name != value or "/" in value or "\\" in value:
        raise ValueError(f"Invalid {kind} ID: {value!r}")
