from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..contracts import ArtifactKind, ConsumerContractError, normalize_consumer_data
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

CORE_CONSUMER_KINDS = {
    "source_digest": ArtifactKind.SOURCE_DIGEST,
    "function_location": ArtifactKind.FUNCTION_LOCATION,
    "function_signature": ArtifactKind.FUNCTION_SIGNATURE,
}


def build_analysis_snapshot(
    snapshot_id: str,
    workspace: Path | str,
    function_name: str,
    report_subdir: Path | str = Path("reports"),
    *,
    exclude_kinds: Collection[str] = (),
) -> tuple[AnalysisSnapshot, list[ReanalysisWarning], dict[str, dict[str, Any]]]:
    workspace = Path(workspace).resolve()
    report_root = workspace / report_subdir
    warnings: list[ReanalysisWarning] = []
    payloads: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, SnapshotArtifact] = {}
    excluded = set(exclude_kinds)
    for kind, filename in STANDARD_ARTIFACTS.items():
        if kind in excluded:
            continue
        path = report_root / filename
        relative = _relative_or_absolute(path, workspace)
        exists = path.exists()
        schema_version = None
        sha256 = None
        if exists:
            try:
                raw_bytes = path.read_bytes()
                sha256 = hashlib.sha256(raw_bytes).hexdigest()
                decoded = json.loads(raw_bytes.decode("utf-8"))
                if not isinstance(decoded, dict):
                    raise ConsumerContractError("Artifact root must be an object.")
                schema_version = decoded.get("schema_version")
                expected_kind = CORE_CONSUMER_KINDS.get(kind)
                payload = (
                    normalize_consumer_data(
                        decoded,
                        expected_kind=expected_kind,
                        allow_legacy_v01=True,
                    )
                    if expected_kind is not None
                    else decoded
                )
                payloads[kind] = payload
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                warnings.append(
                    ReanalysisWarning(
                        "artifact_parse_failed",
                        f"Failed to parse artifact {relative.as_posix()}: {exc}",
                        related_artifact=kind,
                    )
                )
            except ConsumerContractError as exc:
                warnings.append(
                    ReanalysisWarning(
                        "artifact_contract_invalid",
                        f"Invalid artifact {relative.as_posix()}: {exc}",
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


def _payload_hash(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _relative_or_absolute(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root)
    except ValueError:
        return path.resolve()
