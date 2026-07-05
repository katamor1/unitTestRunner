from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unit_test_runner.harness.c90_writer import sha256_file

from .dossier_models import DossierArtifact, DossierWarning


STANDARD_ARTIFACTS: list[tuple[str, str, str, str, str]] = [
    ("source_digest", "reports/source_digest.json", "c_source_reading", "mvp1_required", "json"),
    ("function_location", "reports/function_location.json", "function_location", "mvp1_required", "json"),
    ("function_signature", "reports/function_signature.json", "function_signature", "mvp1_required", "json"),
    ("global_access", "reports/global_access.json", "global_access_analysis", "mvp2_required", "json"),
    ("call_report", "reports/call_report.json", "call_analysis", "mvp2_required", "json"),
    ("coverage_design", "reports/coverage_design.json", "coverage_design", "mvp2_required", "json"),
    ("boundary_equivalence_candidates", "reports/boundary_equivalence_candidates.json", "boundary_equivalence_candidates", "mvp2_required", "json"),
    ("test_case_design", "reports/test_case_design.json", "test_case_design_generation", "mvp2_required", "json"),
    ("harness_skeleton_report", "reports/harness_skeleton_report.json", "harness_skeleton_generation", "mvp3_required", "json"),
    ("build_workspace_report", "reports/build_workspace_report.json", "build_workspace_generation", "mvp3_required", "json"),
    ("build_probe_report", "reports/build_probe_report.json", "build_probe", "mvp3_required", "json"),
    ("build_completion_plan", "reports/build_completion_plan.json", "build_completion", "mvp3_required", "json"),
    ("build_completion_iteration_report", "reports/build_completion_iteration_report.json", "build_completion", "mvp3_required", "json"),
    ("test_execution_report", "reports/test_execution_report.json", "execution_evidence", "mvp4_required", "json"),
    ("test_result_csv", "reports/test_result.csv", "execution_evidence", "mvp4_required", "csv"),
    ("evidence_manifest", "reports/evidence_manifest.json", "evidence_package", "mvp4_required", "json"),
]


def collect_artifacts(workspace: Path | str) -> tuple[list[DossierArtifact], dict[str, dict[str, Any]], list[DossierWarning]]:
    workspace = Path(workspace).resolve()
    request_mtime = _request_mtime(workspace)
    artifacts: list[DossierArtifact] = []
    payloads: dict[str, dict[str, Any]] = {}
    warnings: list[DossierWarning] = []
    for index, (kind, relative, item, required_level, file_kind) in enumerate(STANDARD_ARTIFACTS, start=1):
        artifact_id = f"ART_{index:03d}_{kind}"
        path = Path(relative)
        absolute = workspace / path
        artifact_warnings: list[DossierWarning] = []
        schema_version = None
        exists = absolute.exists()
        modified_at = _modified_at(absolute) if exists else None
        if not exists:
            warning = DossierWarning("missing_artifact", f"Artifact is missing: {path.as_posix()}", artifact_id, item)
            artifact_warnings.append(warning)
            warnings.append(warning)
        else:
            if request_mtime is not None and absolute.stat().st_mtime < request_mtime:
                warning = DossierWarning("artifact_older_than_request", f"Artifact is older than input/request.json: {path.as_posix()}", artifact_id, item)
                artifact_warnings.append(warning)
                warnings.append(warning)
            if file_kind == "json":
                try:
                    payload = json.loads(absolute.read_text(encoding="utf-8"))
                    payloads[kind] = payload
                    schema_version = payload.get("schema_version")
                    if schema_version is None:
                        warning = DossierWarning("schema_version_unknown", f"Schema version is not present: {path.as_posix()}", artifact_id, item)
                        artifact_warnings.append(warning)
                        warnings.append(warning)
                except (OSError, json.JSONDecodeError) as exc:
                    warning = DossierWarning("artifact_parse_failed", f"Failed to parse artifact {path.as_posix()}: {exc}", artifact_id, item)
                    artifact_warnings.append(warning)
                    warnings.append(warning)
        artifact = DossierArtifact(
            artifact_id=artifact_id,
            artifact_kind=kind,
            path=path,
            exists=exists,
            sha256=sha256_file(absolute),
            schema_version=schema_version,
            produced_by_item=item,
            required_level=required_level,
            stale_candidate=any(warning.code == "artifact_older_than_request" for warning in artifact_warnings),
            modified_at=modified_at,
            warnings=artifact_warnings,
        )
        artifacts.append(artifact)
    return artifacts, payloads, warnings


def _request_mtime(workspace: Path) -> float | None:
    request = workspace / "input" / "request.json"
    if not request.exists():
        return None
    return request.stat().st_mtime


def _modified_at(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        return None
