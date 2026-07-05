from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _path_text(path: Path | None) -> str | None:
    return None if path is None else path.as_posix()


@dataclass
class ReanalysisPolicy:
    preserve_manual_edits: bool = True
    reuse_test_case_ids: bool = True
    generate_updated_test_case_design: bool = False
    overwrite_test_case_design: bool = False
    compare_build_context: bool = True
    compare_dependencies: bool = True
    compare_coverage: bool = True
    select_regression_tests: bool = True
    include_low_confidence_matches: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "preserve_manual_edits": self.preserve_manual_edits,
            "reuse_test_case_ids": self.reuse_test_case_ids,
            "generate_updated_test_case_design": self.generate_updated_test_case_design,
            "overwrite_test_case_design": self.overwrite_test_case_design,
            "compare_build_context": self.compare_build_context,
            "compare_dependencies": self.compare_dependencies,
            "compare_coverage": self.compare_coverage,
            "select_regression_tests": self.select_regression_tests,
            "include_low_confidence_matches": self.include_low_confidence_matches,
        }


@dataclass
class SnapshotArtifact:
    artifact_kind: str
    path: Path
    sha256: str | None
    schema_version: str | None
    exists: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": self.artifact_kind,
            "path": _path_text(self.path),
            "sha256": self.sha256,
            "schema_version": self.schema_version,
            "exists": self.exists,
        }


@dataclass
class AnalysisSnapshot:
    snapshot_id: str
    function_name: str
    source_path: Path | None
    source_sha256: str | None
    build_context_hash: str | None
    created_at: str | None
    artifacts: dict[str, SnapshotArtifact] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "function_name": self.function_name,
            "source_path": _path_text(self.source_path),
            "source_sha256": self.source_sha256,
            "build_context_hash": self.build_context_hash,
            "created_at": self.created_at,
            "artifacts": {key: value.to_dict() for key, value in self.artifacts.items()},
        }


@dataclass
class ReanalysisWarning:
    code: str
    message: str
    related_test_case_id: str | None = None
    related_artifact: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.related_test_case_id is not None:
            value["related_test_case_id"] = self.related_test_case_id
        if self.related_artifact is not None:
            value["related_artifact"] = self.related_artifact
        return value


@dataclass
class SourceChange:
    change_kind: str
    description: str
    old_value: str | None
    new_value: str | None
    impact_level: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class InterfaceChange:
    change_kind: str
    target_name: str
    old_signature: str | None
    new_signature: str | None
    impact_level: str
    affected_test_case_ids: list[str]
    suggested_action: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class DependencyChange:
    change_kind: str
    name: str
    old_kind: str | None
    new_kind: str | None
    impact_level: str
    affected_test_case_ids: list[str]
    suggested_action: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class CoverageChange:
    change_kind: str
    old_coverage_id: str | None
    new_coverage_id: str | None
    old_condition: str | None
    new_condition: str | None
    similarity: float | None
    affected_test_case_ids: list[str]
    suggested_action: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class TestDesignImpact:
    test_case_id: str
    impact_kind: str
    old_status: str
    new_reuse_status: str
    reason: str
    required_updates: list[str]
    review_required: bool
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class RegressionRecommendation:
    recommendation_kind: str
    reason: str
    selected_count: int
    blocked_count: int
    new_required_count: int
    manual_review_count: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ChangeImpactReport:
    function_name: str
    status: str
    previous_snapshot: AnalysisSnapshot
    current_snapshot: AnalysisSnapshot
    source_changes: list[SourceChange] = field(default_factory=list)
    interface_changes: list[InterfaceChange] = field(default_factory=list)
    dependency_changes: list[DependencyChange] = field(default_factory=list)
    coverage_changes: list[CoverageChange] = field(default_factory=list)
    test_design_impacts: list[TestDesignImpact] = field(default_factory=list)
    regression_recommendation: RegressionRecommendation | None = None
    warnings: list[ReanalysisWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "function": {"name": self.function_name, "status": self.status},
            "previous_snapshot": self.previous_snapshot.to_dict(),
            "current_snapshot": self.current_snapshot.to_dict(),
            "source_changes": [item.to_dict() for item in self.source_changes],
            "interface_changes": [item.to_dict() for item in self.interface_changes],
            "dependency_changes": [item.to_dict() for item in self.dependency_changes],
            "coverage_changes": [item.to_dict() for item in self.coverage_changes],
            "test_design_impacts": [item.to_dict() for item in self.test_design_impacts],
            "regression_recommendation": self.regression_recommendation.to_dict() if self.regression_recommendation else None,
            "warnings": [item.to_dict() for item in self.warnings],
        }


@dataclass
class ReconciledTestCase:
    test_case_id: str
    reuse_status: str
    previous_coverage_ids: list[str]
    current_coverage_ids: list[str]
    previous_candidate_ids: list[str]
    current_candidate_ids: list[str]
    preserved_fields: list[str]
    updated_fields: list[str]
    review_required_fields: list[str]
    reason: str
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ManualMergeItem:
    item_id: str
    test_case_id: str
    field_name: str
    previous_value: str | None
    proposed_value: str | None
    reason: str
    suggested_action: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class TestCaseReconciliationReport:
    function_name: str
    status: str
    preserved_test_cases: list[ReconciledTestCase] = field(default_factory=list)
    updated_test_cases: list[ReconciledTestCase] = field(default_factory=list)
    obsolete_test_cases: list[ReconciledTestCase] = field(default_factory=list)
    blocked_test_cases: list[ReconciledTestCase] = field(default_factory=list)
    new_test_case_candidates: list[ReconciledTestCase] = field(default_factory=list)
    manual_merge_items: list[ManualMergeItem] = field(default_factory=list)
    warnings: list[ReanalysisWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "function": {"name": self.function_name, "status": self.status},
            "preserved_test_cases": [item.to_dict() for item in self.preserved_test_cases],
            "updated_test_cases": [item.to_dict() for item in self.updated_test_cases],
            "obsolete_test_cases": [item.to_dict() for item in self.obsolete_test_cases],
            "blocked_test_cases": [item.to_dict() for item in self.blocked_test_cases],
            "new_test_case_candidates": [item.to_dict() for item in self.new_test_case_candidates],
            "manual_merge_items": [item.to_dict() for item in self.manual_merge_items],
            "warnings": [item.to_dict() for item in self.warnings],
        }


@dataclass
class RegressionTestCase:
    test_case_id: str
    selection_status: str
    priority: str
    reasons: list[str]
    related_changes: list[str]
    review_required: bool

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class RegressionSelection:
    function_name: str
    status: str
    selected_test_cases: list[RegressionTestCase] = field(default_factory=list)
    skipped_test_cases: list[RegressionTestCase] = field(default_factory=list)
    new_required_test_cases: list[RegressionTestCase] = field(default_factory=list)
    blocked_test_cases: list[RegressionTestCase] = field(default_factory=list)
    selection_reason_summary: str = ""
    warnings: list[ReanalysisWarning] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "function": {"name": self.function_name, "status": self.status},
            "selected_test_cases": [item.to_dict() for item in self.selected_test_cases],
            "skipped_test_cases": [item.to_dict() for item in self.skipped_test_cases],
            "new_required_test_cases": [item.to_dict() for item in self.new_required_test_cases],
            "blocked_test_cases": [item.to_dict() for item in self.blocked_test_cases],
            "selection_reason_summary": self.selection_reason_summary,
            "warnings": [item.to_dict() for item in self.warnings],
        }
