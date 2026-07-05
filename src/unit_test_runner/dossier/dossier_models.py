from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _path_text(path: Path | None) -> str | None:
    if path is None:
        return None
    return path.as_posix()


@dataclass
class DossierGenerationPolicy:
    include_raw_artifact_index: bool = True
    include_traceability_matrix: bool = True
    include_review_checklist: bool = True
    include_next_actions: bool = True
    require_schema_version_match: bool = False
    allow_missing_optional_artifacts: bool = True
    markdown_detail_level: str = "summary_with_links"

    def to_dict(self) -> dict[str, Any]:
        return {
            "include_raw_artifact_index": self.include_raw_artifact_index,
            "include_traceability_matrix": self.include_traceability_matrix,
            "include_review_checklist": self.include_review_checklist,
            "include_next_actions": self.include_next_actions,
            "require_schema_version_match": self.require_schema_version_match,
            "allow_missing_optional_artifacts": self.allow_missing_optional_artifacts,
            "markdown_detail_level": self.markdown_detail_level,
        }


@dataclass
class DossierWarning:
    code: str
    message: str
    related_artifact_id: str | None = None
    related_step: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "related_artifact_id": self.related_artifact_id,
            "related_step": self.related_step,
        }


@dataclass
class DossierArtifact:
    artifact_id: str
    artifact_kind: str
    path: Path
    exists: bool
    sha256: str | None
    schema_version: str | None
    produced_by_step: str
    required_level: str
    stale_candidate: bool = False
    warnings: list[DossierWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "path": _path_text(self.path),
            "exists": self.exists,
            "sha256": self.sha256,
            "schema_version": self.schema_version,
            "produced_by_step": self.produced_by_step,
            "required_level": self.required_level,
            "stale_candidate": self.stale_candidate,
            "warnings": [item.to_dict() for item in self.warnings],
        }


@dataclass
class TraceabilityLink:
    link_id: str
    source_kind: str
    source_id: str
    target_kind: str
    target_id: str
    relation: str
    confidence: str = "medium"
    review_required: bool = False
    test_case_id: str | None = None
    coverage_id: str | None = None
    candidate_id: str | None = None
    stub_name: str | None = None
    execution_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "relation": self.relation,
            "confidence": self.confidence,
            "review_required": self.review_required,
            "test_case_id": self.test_case_id,
            "coverage_id": self.coverage_id,
            "candidate_id": self.candidate_id,
            "stub_name": self.stub_name,
            "execution_status": self.execution_status,
        }


@dataclass
class DossierReviewItem:
    review_id: str
    category: str
    title: str
    description: str
    related_artifacts: list[str] = field(default_factory=list)
    related_test_cases: list[str] = field(default_factory=list)
    severity: str = "warning"
    suggested_reviewer_role: str = "unit_test_reviewer"
    done: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "related_artifacts": self.related_artifacts,
            "related_test_cases": self.related_test_cases,
            "severity": self.severity,
            "suggested_reviewer_role": self.suggested_reviewer_role,
            "done": self.done,
        }


@dataclass
class DossierUnresolvedItem:
    item_id: str
    source_step: str
    item_kind: str
    description: str
    impact: str
    related_artifacts: list[str] = field(default_factory=list)
    related_test_cases: list[str] = field(default_factory=list)
    suggested_action: str = "Review this item before approving the function dossier."
    blocks_readiness: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "source_step": self.source_step,
            "item_kind": self.item_kind,
            "description": self.description,
            "impact": self.impact,
            "related_artifacts": self.related_artifacts,
            "related_test_cases": self.related_test_cases,
            "suggested_action": self.suggested_action,
            "blocks_readiness": self.blocks_readiness,
        }


@dataclass
class DossierNextAction:
    action_id: str
    priority: str
    action_kind: str
    title: str
    description: str
    owner_role: str
    related_unresolved_items: list[str] = field(default_factory=list)
    expected_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "priority": self.priority,
            "action_kind": self.action_kind,
            "title": self.title,
            "description": self.description,
            "owner_role": self.owner_role,
            "related_unresolved_items": self.related_unresolved_items,
            "expected_output": self.expected_output,
        }


@dataclass
class DossierReadiness:
    mvp_level: str
    ready_for_review: bool
    ready_for_harness_generation: bool
    ready_for_build_probe: bool
    ready_for_execution: bool
    evidence_ready: bool
    blocked: bool
    blocked_reasons: list[str] = field(default_factory=list)
    quality_score: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mvp_level": self.mvp_level,
            "ready_for_review": self.ready_for_review,
            "ready_for_harness_generation": self.ready_for_harness_generation,
            "ready_for_build_probe": self.ready_for_build_probe,
            "ready_for_execution": self.ready_for_execution,
            "evidence_ready": self.evidence_ready,
            "blocked": self.blocked,
            "blocked_reasons": self.blocked_reasons,
            "quality_score": self.quality_score,
        }


@dataclass
class FunctionDossier:
    function_name: str
    source_path: Path | None
    workspace_root: Path
    status: str
    created_at: str
    artifact_index: list[DossierArtifact]
    summaries: dict[str, Any]
    traceability: list[TraceabilityLink]
    review_items: list[DossierReviewItem]
    unresolved_items: list[DossierUnresolvedItem]
    next_actions: list[DossierNextAction]
    readiness: DossierReadiness
    warnings: list[DossierWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "function": {
                "name": self.function_name,
                "source_path": _path_text(self.source_path),
                "status": self.status,
            },
            "workspace_root": _path_text(self.workspace_root),
            "created_at": self.created_at,
            "artifact_index": [item.to_dict() for item in self.artifact_index],
            "summaries": self.summaries,
            "traceability": [item.to_dict() for item in self.traceability],
            "review_items": [item.to_dict() for item in self.review_items],
            "unresolved_items": [item.to_dict() for item in self.unresolved_items],
            "next_actions": [item.to_dict() for item in self.next_actions],
            "readiness": self.readiness.to_dict(),
            "warnings": [item.to_dict() for item in self.warnings],
        }
