from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unit_test_runner.contracts import ArtifactKind, load_artifact
from unit_test_runner.contracts.models import ContractViolation
from unit_test_runner.harness.c90_writer import sha256_file

from .dossier_models import DossierArtifact, DossierWarning


STANDARD_ARTIFACTS: list[tuple[str, str, str, str, str]] = [
    ("source_digest", "reports/source_digest.json", "c_source_reading", "mvp1_required", "json"),
    ("function_location", "reports/function_location.json", "function_location", "mvp1_required", "json"),
    ("function_signature", "reports/function_signature.json", "function_signature", "mvp1_required", "json"),
    ("global_access", "reports/global_access.json", "global_access_analysis", "mvp2_required", "json"),
    ("call_report", "reports/call_report.json", "call_analysis", "mvp2_required", "json"),
    ("dependency_policy", "reports/dependency_policy.json", "dependency_policy_analysis", "mvp2_required", "json"),
    ("coverage_design", "reports/coverage_design.json", "coverage_design", "mvp2_required", "json"),
    ("boundary_equivalence_candidates", "reports/boundary_equivalence_candidates.json", "boundary_equivalence_candidates", "mvp2_required", "json"),
    ("test_spec", "reports/test_spec.json", "test_case_design_generation", "mvp2_required", "json"),
    ("harness_skeleton_report", "reports/harness_skeleton_report.json", "harness_skeleton_generation", "mvp3_required", "json"),
    ("build_workspace_report", "reports/build_workspace_report.json", "build_workspace_generation", "mvp3_required", "json"),
    ("build_probe_report", "reports/build_probe_report.json", "build_probe", "mvp3_required", "json"),
]


PUBLIC_JSON_KINDS = {
    "test_spec": ArtifactKind.TEST_SPEC,
    "build_probe_report": ArtifactKind.BUILD_PROBE_REPORT,
}


def collect_artifacts(
    workspace: Path | str,
) -> tuple[list[DossierArtifact], dict[str, dict[str, Any]], list[DossierWarning]]:
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
        contract_violations: list[ContractViolation] = []
        schema_version = None
        contract_subject: dict[str, Any] = {}
        contract_revision: int | None = None
        exists = absolute.exists()
        modified_at = _modified_at(absolute) if exists else None
        stale_candidate = False
        if not exists:
            warning = DossierWarning("missing_artifact", f"Artifact is missing: {path.as_posix()}", artifact_id, item)
            artifact_warnings.append(warning)
            warnings.append(warning)
        else:
            if request_mtime is not None and absolute.stat().st_mtime < request_mtime:
                stale_candidate = True
                warning = DossierWarning("artifact_older_than_request", f"Artifact is older than input/request.json: {path.as_posix()}", artifact_id, item)
                artifact_warnings.append(warning)
                warnings.append(warning)
            if file_kind == "json":
                loaded_payload, loaded_violations = _load_json_artifact(
                    absolute,
                    PUBLIC_JSON_KINDS.get(kind),
                )
                schema_version = str(loaded_payload.get("schema_version") or "") or None
                raw_subject = loaded_payload.get("subject")
                if isinstance(raw_subject, dict):
                    contract_subject = dict(raw_subject)
                raw_data = loaded_payload.get("data")
                if isinstance(raw_data, dict):
                    raw_revision = raw_data.get("revision")
                    if isinstance(raw_revision, int) and not isinstance(raw_revision, bool):
                        contract_revision = raw_revision
                contract_violations.extend(loaded_violations)
                for violation in loaded_violations:
                    warning = DossierWarning(
                        violation.code,
                        f"{path.as_posix()} {violation.json_path}: {violation.message} "
                        f"(severity: {violation.severity})",
                        artifact_id,
                        item,
                    )
                    artifact_warnings.append(warning)
                    warnings.append(warning)
                contract_status = _contract_status(
                    exists=True,
                    violations=contract_violations,
                    stale_candidate=stale_candidate,
                )
                dossier_payload = _dossier_payload(loaded_payload)
                if contract_status in {"valid", "stale"} and dossier_payload:
                    payloads[kind] = dossier_payload
            else:
                contract_status = "stale" if stale_candidate else "valid"
        if not exists:
            contract_status = "missing"
        artifact = DossierArtifact(
            artifact_id=artifact_id,
            artifact_kind=kind,
            path=path,
            exists=exists,
            sha256=sha256_file(absolute),
            schema_version=schema_version,
            produced_by_item=item,
            required_level=required_level,
            contract_status=contract_status,
            contract_violations=contract_violations,
            contract_subject=contract_subject,
            contract_revision=contract_revision,
            stale_candidate=stale_candidate,
            modified_at=modified_at,
            warnings=artifact_warnings,
        )
        artifacts.append(artifact)
    return artifacts, payloads, warnings


def _contract_status(
    *,
    exists: bool,
    violations: list[ContractViolation],
    stale_candidate: bool,
) -> str:
    if not exists:
        return "missing"
    codes = {item.code for item in violations}
    if "parse_error" in codes:
        return "parse_error"
    if "unsupported_version" in codes:
        return "unsupported_version"
    if any(item.severity not in {"info", "warning"} for item in violations):
        return "schema_error"
    if stale_candidate:
        return "stale"
    return "valid"


def _dossier_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return dict(data) if isinstance(data, dict) else dict(payload)


def _load_json_artifact(
    path: Path,
    public_kind: ArtifactKind | None,
) -> tuple[dict[str, Any], tuple[ContractViolation, ...]]:
    if public_kind is not None:
        loaded = load_artifact(path, expected_kind=public_kind)
        return loaded.payload, loaded.violations
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {}, (
            ContractViolation(
                "parse_error",
                "$",
                f"Cannot read internal analysis data: {error}",
            ),
        )
    if not isinstance(payload, dict):
        return {}, (
            ContractViolation(
                "schema_error",
                "$",
                "Internal analysis data root must be an object.",
            ),
        )
    return payload, ()


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
