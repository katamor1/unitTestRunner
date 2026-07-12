from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unit_test_runner.contracts import ArtifactKind, ContractMode, load_artifact
from unit_test_runner.contracts.models import ContractViolation
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
    ("test_spec", "reports/test_spec.json", "test_case_design_generation", "mvp2_required", "json"),
    ("harness_skeleton_report", "reports/harness_skeleton_report.json", "harness_skeleton_generation", "mvp3_required", "json"),
    ("build_workspace_report", "reports/build_workspace_report.json", "build_workspace_generation", "mvp3_required", "json"),
    ("build_probe_report", "reports/build_probe_report.json", "build_probe", "mvp3_required", "json"),
    ("build_completion_plan", "reports/build_completion_plan.json", "build_completion", "mvp3_required", "json"),
    ("build_completion_iteration_report", "reports/build_completion_iteration_report.json", "build_completion", "mvp3_required", "json"),
    ("test_execution_report", "reports/test_execution_report.json", "execution_evidence", "mvp4_required", "json"),
    ("test_result_csv", "reports/test_result.csv", "execution_evidence", "mvp4_required", "csv"),
    ("evidence_manifest", "reports/evidence_manifest.json", "evidence_package", "mvp4_required", "json"),
]


JSON_CONTRACT_KINDS = {
    "source_digest": ArtifactKind.SOURCE_DIGEST,
    "function_location": ArtifactKind.FUNCTION_LOCATION,
    "function_signature": ArtifactKind.FUNCTION_SIGNATURE,
    "global_access": ArtifactKind.GLOBAL_ACCESS,
    "call_report": ArtifactKind.CALL_REPORT,
    "coverage_design": ArtifactKind.COVERAGE_DESIGN,
    "boundary_equivalence_candidates": ArtifactKind.BOUNDARY_CANDIDATES,
    "test_spec": ArtifactKind.TEST_SPEC,
    "harness_skeleton_report": ArtifactKind.HARNESS_SKELETON_REPORT,
    "build_workspace_report": ArtifactKind.BUILD_WORKSPACE_REPORT,
    "build_probe_report": ArtifactKind.BUILD_PROBE_REPORT,
    "build_completion_plan": ArtifactKind.BUILD_COMPLETION_PLAN,
    "build_completion_iteration_report": ArtifactKind.BUILD_COMPLETION_ITERATION,
    "test_execution_report": ArtifactKind.TEST_EXECUTION_REPORT,
    "evidence_manifest": ArtifactKind.EVIDENCE_MANIFEST,
}


def collect_artifacts(
    workspace: Path | str,
    strict_schema_version: bool = False,
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
                loaded = load_artifact(
                    absolute,
                    expected_kind=JSON_CONTRACT_KINDS[kind],
                    mode=(
                        ContractMode.STRICT
                        if strict_schema_version
                        else ContractMode.COMPATIBLE
                    ),
                )
                schema_version = loaded.source_version or None
                contract_violations.extend(loaded.violations)
                for violation in loaded.violations:
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
                dossier_payload = _dossier_payload(loaded.payload)
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
    return dict(data) if isinstance(data, dict) else {}


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
