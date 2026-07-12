from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .reanalysis_models import AnalysisSnapshot, ReanalysisWarning, SnapshotArtifact


STANDARD_ARTIFACTS = {
    "source_digest": "source_digest.json",
    "function_location": "function_location.json",
    "function_signature": "function_signature.json",
    "global_access": "global_access.json",
    "call_report": "call_report.json",
    "coverage_design": "coverage_design.json",
    "boundary_equivalence_candidates": "boundary_equivalence_candidates.json",
    "test_spec": "test_spec.json",
    "build_context": "build_context.json",
}


def build_analysis_snapshot(
    snapshot_id: str,
    workspace: Path | str,
    function_name: str,
    report_subdir: Path | str = Path("reports"),
) -> tuple[AnalysisSnapshot, list[ReanalysisWarning], dict[str, dict[str, Any]]]:
    workspace = Path(workspace).resolve()
    report_root = workspace / report_subdir
    warnings: list[ReanalysisWarning] = []
    payloads: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, SnapshotArtifact] = {}
    for kind, filename in STANDARD_ARTIFACTS.items():
        path = report_root / filename
        relative = _relative_or_absolute(path, workspace)
        exists = path.exists()
        schema_version = None
        sha256 = _sha256(path) if exists else None
        if exists:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                payloads[kind] = payload
                schema_version = payload.get("schema_version")
            except (OSError, json.JSONDecodeError) as exc:
                warnings.append(
                    ReanalysisWarning(
                        "artifact_parse_failed",
                        f"Failed to parse artifact {relative.as_posix()}: {exc}",
                        related_artifact=kind,
                    )
                )
        else:
            warnings.append(
                ReanalysisWarning(
                    f"{snapshot_id}_artifact_missing",
                    f"Artifact is missing: {relative.as_posix()}",
                    related_artifact=kind,
                )
            )
        artifacts[kind] = SnapshotArtifact(kind, relative, sha256, schema_version, exists)
    source_payload = payloads.get("source_digest", {}).get("source", {})
    source_path = Path(source_payload["path"]) if isinstance(source_payload.get("path"), str) else None
    source_sha256 = source_payload.get("sha256") if isinstance(source_payload.get("sha256"), str) else None
    build_context_hash = _payload_hash(payloads.get("build_context")) if "build_context" in payloads else None
    snapshot = AnalysisSnapshot(
        snapshot_id=snapshot_id,
        function_name=function_name,
        source_path=source_path,
        source_sha256=source_sha256,
        build_context_hash=build_context_hash,
        created_at=datetime.now(timezone.utc).isoformat(),
        artifacts=artifacts,
    )
    return snapshot, warnings, payloads


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _payload_hash(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _relative_or_absolute(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root)
    except ValueError:
        return path.resolve()
