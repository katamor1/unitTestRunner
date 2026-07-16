from __future__ import annotations

from collections.abc import Iterable

from unit_test_runner.contracts import RunOutcome

from .dossier_models import DossierArtifact, DossierReadiness, DossierUnresolvedItem
from .review_assessment import ReviewAssessment


_CORE_REVIEW_KINDS = {
    "source_digest",
    "function_location",
    "function_signature",
}


def assess_readiness(
    artifacts: list[DossierArtifact],
    blocked_reasons: list[str],
    unresolved_items: list[DossierUnresolvedItem],
    *,
    review_assessment: ReviewAssessment | None = None,
    execution_outcome: RunOutcome | str | None = None,
    evidence_integrity: bool | None = None,
) -> DossierReadiness:
    authoritative = {
        artifact.artifact_kind
        for artifact in artifacts
        if artifact.contract_status == "valid" and not artifact.compatible_migrated
    }
    semantic_blockers = list(blocked_reasons)
    for artifact in artifacts:
        if artifact.compatible_migrated and artifact.required_level != "optional":
            semantic_blockers.append(
                f"{artifact.artifact_kind} is compatible-migrated display-only"
            )
        elif (
            artifact.artifact_kind in _CORE_REVIEW_KINDS
            and artifact.required_level != "optional"
            and artifact.contract_status != "valid"
        ):
            semantic_blockers.append(
                f"{artifact.artifact_kind} is not a strict current valid artifact"
            )
    semantic_blockers = _unique(semantic_blockers)

    ready_for_review = _CORE_REVIEW_KINDS.issubset(authoritative) and not any(
        reason for reason in blocked_reasons
    )
    review_complete = (
        review_assessment.review_complete if review_assessment is not None else False
    )
    outcome = _coerce_outcome(execution_outcome)
    test_green = outcome is RunOutcome.PASSED
    if evidence_integrity is None:
        evidence_ready = {
            "test_execution_report",
            "evidence_manifest",
        }.issubset(authoritative)
    else:
        evidence_ready = bool(evidence_integrity)

    blocked = bool(semantic_blockers)
    mvp_level = _mvp_level(authoritative) if not blocked else "unknown"
    quality_score = max(
        0,
        100
        - len([item for item in unresolved_items if item.blocks_readiness]) * 20
        - len(semantic_blockers) * 30,
    )
    return DossierReadiness(
        mvp_level=mvp_level,
        ready_for_review=ready_for_review,
        ready_for_harness_generation=(
            not blocked
            and {
                "function_signature",
                "global_access",
                "call_report",
                "test_spec",
            }.issubset(authoritative)
        ),
        ready_for_build_probe=(
            not blocked
            and {"harness_skeleton_report", "build_workspace_report"}.issubset(
                authoritative
            )
        ),
        ready_for_execution=(
            not blocked and "build_probe_report" in authoritative
        ),
        evidence_ready=evidence_ready,
        blocked=blocked,
        review_complete=review_complete,
        test_green=test_green,
        blocked_reasons=semantic_blockers,
        quality_score=quality_score,
    )


def _coerce_outcome(value: RunOutcome | str | None) -> RunOutcome | None:
    if value is None:
        return None
    try:
        return RunOutcome(value)
    except ValueError:
        return None


def _mvp_level(authoritative: set[str]) -> str:
    if {"test_execution_report", "evidence_manifest"}.issubset(authoritative):
        return "mvp4_execution_evidence"
    if {
        "harness_skeleton_report",
        "build_workspace_report",
        "build_probe_report",
        "build_completion_plan",
    }.issubset(authoritative):
        return "mvp3_build_probe"
    if {
        "global_access",
        "call_report",
        "coverage_design",
        "boundary_equivalence_candidates",
        "test_spec",
    }.issubset(authoritative):
        return "mvp2_test_design"
    if _CORE_REVIEW_KINDS.issubset(authoritative):
        return "mvp1_analysis_only"
    return "unknown"


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
