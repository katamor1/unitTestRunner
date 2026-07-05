from __future__ import annotations

import json
import shutil
import hashlib
from pathlib import Path
from typing import Any

from .coverage_diff import compare_coverage_designs
from .current_analysis import build_current_reanalysis
from .dependency_diff import compare_dependencies
from .reanalysis_models import (
    AnalysisSnapshot,
    ChangeImpactReport,
    ReanalysisPolicy,
    RegressionRecommendation,
    SnapshotArtifact,
    SourceChange,
)
from .reanalysis_report_writer import write_reanalysis_reports
from .regression_selector import select_regression_tests
from .signature_diff import compare_signatures
from .snapshot_builder import build_analysis_snapshot
from .test_case_reconciler import reconcile_test_cases


def reanalyze_function_workflow(
    workspace_root: Path | str,
    dsw_path: Path | str,
    source: str | Path,
    function_name: str,
    configuration: str,
    out_dir: Path | str,
    project_name: str | None = None,
    previous_dossier_path: Path | str | None = None,
    previous_test_case_design_path: Path | str | None = None,
    policy: ReanalysisPolicy | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir).resolve()
    policy = policy or ReanalysisPolicy()
    previous_dossier_path = Path(previous_dossier_path).resolve() if previous_dossier_path else out_dir / "reports" / "function_dossier.json"
    previous_dossier_payload, dossier_payloads, dossier_artifact_paths = _payloads_from_previous_dossier(previous_dossier_path)
    if previous_test_case_design_path is None:
        previous_test_case_design_path = dossier_artifact_paths.get("test_case_design") or out_dir / "reports" / "test_case_design.json"
    previous_test_case_design_path = Path(previous_test_case_design_path).resolve()
    current_payloads = build_current_reanalysis(workspace_root, dsw_path, source, function_name, configuration, out_dir, project_name)
    previous_snapshot, previous_warnings, previous_payloads = build_analysis_snapshot("previous", out_dir, function_name)
    if dossier_payloads:
        previous_payloads.update(dossier_payloads)
        previous_snapshot = _snapshot_from_previous_dossier(function_name, previous_dossier_payload, dossier_payloads, dossier_artifact_paths)
    current_snapshot, current_warnings, current_snapshot_payloads = build_analysis_snapshot(
        "current",
        out_dir,
        function_name,
        report_subdir=Path("reports") / "reanalysis" / "current",
    )
    if "test_case_design" not in current_snapshot_payloads and "test_case_design" in current_payloads:
        current_snapshot_payloads["test_case_design"] = current_payloads["test_case_design"]
    previous_design = _read_json(previous_test_case_design_path)
    current_design = current_payloads["test_case_design"]
    test_case_ids = _test_case_ids(previous_design)
    coverage_to_cases = _coverage_to_cases(previous_design)
    interface_changes = compare_signatures(previous_payloads.get("function_signature", {}), current_payloads["function_signature"], test_case_ids)
    dependency_changes = compare_dependencies(
        previous_payloads.get("global_access", {}),
        current_payloads["global_access"],
        previous_payloads.get("call_report", {}),
        current_payloads["call_report"],
        test_case_ids,
    )
    coverage_result = compare_coverage_designs(
        previous_payloads.get("coverage_design", {}),
        current_payloads["coverage_design"],
        coverage_to_cases,
        include_low_confidence_matches=policy.include_low_confidence_matches,
    )
    source_changes = _source_changes(previous_snapshot.source_sha256, current_snapshot.source_sha256)
    reconciliation, updated_design = reconcile_test_cases(
        previous_design,
        current_design,
        list(coverage_result.mappings.values()),
        coverage_result.changes,
        interface_changes,
        dependency_changes,
        generate_updated_test_case_design=policy.generate_updated_test_case_design,
    )
    selection = select_regression_tests(function_name, reconciliation)
    change_status = "no_change_detected"
    if source_changes or interface_changes or dependency_changes or coverage_result.changes:
        change_status = "changed"
    if reconciliation.blocked_test_cases:
        change_status = "incompatible_change"
    change_impact = ChangeImpactReport(
        function_name=function_name,
        status=change_status,
        previous_snapshot=previous_snapshot,
        current_snapshot=current_snapshot,
        source_changes=source_changes,
        interface_changes=interface_changes,
        dependency_changes=dependency_changes,
        coverage_changes=coverage_result.changes,
        regression_recommendation=RegressionRecommendation(
            recommendation_kind=_recommendation(selection, reconciliation),
            reason=selection.selection_reason_summary,
            selected_count=len(selection.selected_test_cases),
            blocked_count=len(selection.blocked_test_cases),
            new_required_count=len(selection.new_required_test_cases),
            manual_review_count=sum(1 for item in selection.selected_test_cases if item.review_required),
        ),
        warnings=previous_warnings + current_warnings,
    )
    paths = write_reanalysis_reports(out_dir, change_impact, reconciliation, selection, updated_design)
    if policy.overwrite_test_case_design:
        if not policy.generate_updated_test_case_design or updated_design is None:
            raise ValueError("--overwrite-test-case-design requires --generate-updated-test-case-design")
        shutil.copy2(paths["updated_test_case_design_json"], out_dir / "reports" / "test_case_design.json")
    return {
        "status": "reanalysis_completed",
        "change_impact": change_impact,
        "reconciliation": reconciliation,
        "regression_selection": selection,
        "reports": paths,
        "previous_dossier": previous_dossier_path,
        "previous_test_case_design": previous_test_case_design_path,
    }


def reconcile_test_case_reports(
    previous_test_case_design: Path | str,
    previous_coverage_design: Path | str,
    current_test_case_design: Path | str,
    current_coverage_design: Path | str,
    current_boundary_candidates: Path | str,
    out: Path | str,
    policy: ReanalysisPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or ReanalysisPolicy()
    previous_design = _read_json(Path(previous_test_case_design))
    current_design = _read_json(Path(current_test_case_design))
    previous_coverage = _read_json(Path(previous_coverage_design))
    current_coverage = _read_json(Path(current_coverage_design))
    _read_json(Path(current_boundary_candidates))
    coverage_result = compare_coverage_designs(previous_coverage, current_coverage, _coverage_to_cases(previous_design), policy.include_low_confidence_matches)
    report, updated = reconcile_test_cases(previous_design, current_design, list(coverage_result.mappings.values()), coverage_result.changes, [], [], policy.generate_updated_test_case_design)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    updated_path = None
    if updated is not None:
        updated_path = out.with_name("updated_test_case_design.json")
        updated_path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"reconciliation": report, "updated_test_case_design": updated, "updated_test_case_design_path": updated_path, "out": out}


def select_regression_from_reports(change_impact: Path | str, reconciliation: Path | str, out: Path | str) -> dict[str, Any]:
    change_payload = _read_json(Path(change_impact))
    reconciliation_payload = _read_json(Path(reconciliation))
    report = _reconciliation_from_payload(reconciliation_payload)
    selection = select_regression_tests(change_payload.get("function", {}).get("name", report.function_name), report)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".csv":
        from unit_test_runner.reports.regression_selection_csv import render_regression_selection_csv

        out.write_text(render_regression_selection_csv(selection.to_dict()), encoding="utf-8", newline="")
    else:
        out.write_text(json.dumps(selection.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"regression_selection": selection, "out": out}


def _source_changes(previous_sha: str | None, current_sha: str | None) -> list[SourceChange]:
    if previous_sha == current_sha:
        return []
    return [
        SourceChange(
            "source_hash_changed",
            "Source digest hash changed.",
            previous_sha,
            current_sha,
            "medium",
            "source_digest.sha256",
        )
    ]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _payloads_from_previous_dossier(dossier_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Path]]:
    dossier = _read_json(dossier_path)
    payloads: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    for key in (
        "source_digest",
        "function_location",
        "function_signature",
        "global_access",
        "call_report",
        "coverage_design",
        "boundary_equivalence_candidates",
        "test_case_design",
    ):
        path = _artifact_json_path(dossier, key, dossier_path)
        if path is None:
            continue
        paths[key] = path
        payloads[key] = _read_json(path)
    if "build_context" in dossier:
        payloads["build_context"] = {"schema_version": "0.1", "build_context": dossier["build_context"]}
    return dossier, payloads, paths


def _artifact_json_path(dossier: dict[str, Any], key: str, dossier_path: Path) -> Path | None:
    value = dossier.get(key)
    if isinstance(value, dict) and isinstance(value.get("json"), str):
        path = Path(value["json"])
        if not path.is_absolute():
            path = dossier_path.parent / path
        return path.resolve()
    return _artifact_index_json_path(dossier, key, dossier_path)


def _artifact_index_json_path(dossier: dict[str, Any], key: str, dossier_path: Path) -> Path | None:
    artifacts = dossier.get("artifact_index")
    if not isinstance(artifacts, list):
        return None
    artifact_root = _artifact_index_root(dossier, dossier_path)
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("artifact_kind") != key:
            continue
        raw_path = artifact.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            return None
        path = Path(raw_path)
        if not path.is_absolute():
            path = artifact_root / path
        return path.resolve()
    return None


def _artifact_index_root(dossier: dict[str, Any], dossier_path: Path) -> Path:
    workspace_root = dossier.get("workspace_root")
    if isinstance(workspace_root, str) and workspace_root:
        return Path(workspace_root).expanduser().resolve()
    if dossier_path.parent.name == "reports":
        return dossier_path.parent.parent.resolve()
    return dossier_path.parent.resolve()


def _snapshot_from_previous_dossier(
    function_name: str,
    dossier: dict[str, Any],
    payloads: dict[str, dict[str, Any]],
    artifact_paths: dict[str, Path],
) -> AnalysisSnapshot:
    artifacts = {
        key: SnapshotArtifact(
            artifact_kind=key,
            path=path,
            sha256=_sha256_file(path),
            schema_version=payloads.get(key, {}).get("schema_version"),
            exists=path.exists(),
        )
        for key, path in artifact_paths.items()
    }
    source_payload = payloads.get("source_digest", {}).get("source", {})
    source_path = Path(source_payload["path"]) if isinstance(source_payload.get("path"), str) else None
    source_sha256 = source_payload.get("sha256") if isinstance(source_payload.get("sha256"), str) else None
    return AnalysisSnapshot(
        snapshot_id="previous",
        function_name=function_name,
        source_path=source_path,
        source_sha256=source_sha256,
        build_context_hash=_payload_hash(dossier.get("build_context")),
        created_at=dossier.get("created_at") if isinstance(dossier.get("created_at"), str) else None,
        artifacts=artifacts,
    )


def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _payload_hash(payload: Any) -> str | None:
    if payload is None:
        return None
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _test_case_ids(design: dict[str, Any]) -> list[str]:
    return [str(case.get("test_case_id") or case.get("id")) for case in design.get("test_cases", []) if case.get("test_case_id") or case.get("id")]


def _coverage_to_cases(design: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for case in design.get("test_cases", []):
        case_id = str(case.get("test_case_id") or case.get("id") or "")
        for link in case.get("coverage_links", []):
            coverage_id = link.get("coverage_id") if isinstance(link, dict) else None
            if coverage_id:
                result.setdefault(str(coverage_id), []).append(case_id)
    return result


def _recommendation(selection, reconciliation) -> str:
    if reconciliation.blocked_test_cases:
        return "blocked"
    if reconciliation.updated_test_cases or reconciliation.new_test_case_candidates:
        return "run_impacted_tests"
    return "no_regression_needed"


def _reconciliation_from_payload(payload: dict[str, Any]):
    from .reanalysis_models import ReconciledTestCase, TestCaseReconciliationReport

    def cases(name: str) -> list[ReconciledTestCase]:
        return [ReconciledTestCase(**item) for item in payload.get(name, [])]

    return TestCaseReconciliationReport(
        function_name=payload.get("function", {}).get("name", "unknown"),
        status=payload.get("function", {}).get("status", "completed"),
        preserved_test_cases=cases("preserved_test_cases"),
        updated_test_cases=cases("updated_test_cases"),
        obsolete_test_cases=cases("obsolete_test_cases"),
        blocked_test_cases=cases("blocked_test_cases"),
        new_test_case_candidates=cases("new_test_case_candidates"),
    )
