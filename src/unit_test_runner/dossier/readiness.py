from __future__ import annotations

from .dossier_models import DossierArtifact, DossierReadiness, DossierUnresolvedItem


def assess_readiness(artifacts: list[DossierArtifact], blocked_reasons: list[str], unresolved_items: list[DossierUnresolvedItem]) -> DossierReadiness:
    existing = {artifact.artifact_kind for artifact in artifacts if artifact.exists}
    blocked = bool(blocked_reasons)
    mvp_level = _mvp_level(existing) if not blocked else "unknown"
    quality_score = max(0, 100 - (len([item for item in unresolved_items if item.blocks_readiness]) * 20) - len(blocked_reasons) * 30)
    return DossierReadiness(
        mvp_level=mvp_level,
        ready_for_review=not blocked,
        ready_for_harness_generation=not blocked and {"function_signature", "global_access", "call_report", "test_case_draft"}.issubset(existing),
        ready_for_build_probe=not blocked and {"harness_skeleton_report", "build_workspace_report"}.issubset(existing),
        ready_for_execution=not blocked and "build_probe_report" in existing,
        evidence_ready=not blocked and {"test_execution_report", "evidence_manifest"}.issubset(existing),
        blocked=blocked,
        blocked_reasons=blocked_reasons,
        quality_score=quality_score,
    )


def _mvp_level(existing: set[str]) -> str:
    if {"test_execution_report", "evidence_manifest"}.issubset(existing):
        return "mvp4_execution_evidence"
    if {"harness_skeleton_report", "build_workspace_report", "build_probe_report", "build_completion_plan"}.issubset(existing):
        return "mvp3_build_probe"
    if {"global_access", "call_report", "coverage_design", "boundary_equivalence_candidates", "test_case_draft"}.issubset(existing):
        return "mvp2_test_design"
    if {"source_digest", "function_location", "function_signature"}.issubset(existing):
        return "mvp1_analysis_only"
    return "unknown"
