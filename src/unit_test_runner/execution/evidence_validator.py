from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from .execution_models import EvidenceFile


def validate_evidence_files(
    workspace: Path,
    files: Iterable[EvidenceFile],
) -> list[EvidenceFile]:
    workspace = Path(workspace).resolve()
    return [_validate_evidence_file(workspace, item) for item in files]


def required_evidence_is_valid(files: Iterable[EvidenceFile]) -> bool:
    return all(
        not item.required or item.integrity_status == "valid"
        for item in files
    )


def _validate_evidence_file(workspace: Path, item: EvidenceFile) -> EvidenceFile:
    path = (workspace / item.path).resolve()
    try:
        path.relative_to(workspace)
    except ValueError:
        return replace(item, exists=False, integrity_status="missing")
    if not path.is_file():
        return replace(item, exists=False, integrity_status="missing")
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    status = "valid" if item.sha256 is not None and actual_hash == item.sha256 else "hash_mismatch"
    return replace(item, exists=True, integrity_status=status)
