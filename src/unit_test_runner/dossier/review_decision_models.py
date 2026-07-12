from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ReviewResolution(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    WAIVED = "waived"


@dataclass(frozen=True, order=True)
class ReviewSubjectReference:
    artifact_kind: str
    path: str
    sha256: str
    revision: int | None = None
    function_id: str | None = None
    source_path: str | None = None
    source_sha256: str | None = None
    semantic_subject_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "artifact_kind": self.artifact_kind,
            "path": self.path,
            "sha256": self.sha256,
            "revision": self.revision,
        }
        optional = {
            "function_id": self.function_id,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "semantic_subject_key": self.semantic_subject_key,
        }
        result.update({key: value for key, value in optional.items() if value is not None})
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReviewSubjectReference":
        return cls(
            artifact_kind=str(value["artifact_kind"]),
            path=str(value["path"]),
            sha256=str(value["sha256"]),
            revision=(int(value["revision"]) if value.get("revision") is not None else None),
            function_id=(str(value["function_id"]) if value.get("function_id") is not None else None),
            source_path=(str(value["source_path"]) if value.get("source_path") is not None else None),
            source_sha256=(str(value["source_sha256"]) if value.get("source_sha256") is not None else None),
            semantic_subject_key=(
                str(value["semantic_subject_key"])
                if value.get("semantic_subject_key") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class ReviewItemSnapshot:
    review_id: str
    category: str
    function_id: str
    case_id: str | None
    semantic_subject_key: str
    title: str
    description: str
    subjects: tuple[ReviewSubjectReference, ...] = ()
    severity: str = "warning"
    suggested_reviewer_role: str = "unit_test_reviewer"

    @property
    def semantic_tuple(self) -> tuple[str, str, str | None, str]:
        return (
            self.category,
            self.function_id,
            self.case_id,
            self.semantic_subject_key,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "category": self.category,
            "function_id": self.function_id,
            "case_id": self.case_id,
            "semantic_subject_key": self.semantic_subject_key,
            "title": self.title,
            "description": self.description,
            "subjects": [item.to_dict() for item in self.subjects],
            "severity": self.severity,
            "suggested_reviewer_role": self.suggested_reviewer_role,
        }


@dataclass(frozen=True)
class ReviewDecision:
    review_id: str
    resolution: ReviewResolution
    reviewer: str
    rationale: str
    decided_at: str
    subject_fingerprint: str
    subject_artifacts: tuple[ReviewSubjectReference, ...]
    migration_metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "review_id": self.review_id,
            "resolution": self.resolution.value,
            "reviewer": self.reviewer,
            "rationale": self.rationale,
            "decided_at": self.decided_at,
            "subject_fingerprint": self.subject_fingerprint,
            "subject_artifacts": [item.to_dict() for item in self.subject_artifacts],
        }
        if self.migration_metadata:
            result["migration_metadata"] = dict(self.migration_metadata)
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReviewDecision":
        return cls(
            review_id=str(value["review_id"]),
            resolution=ReviewResolution(str(value["resolution"])),
            reviewer=str(value.get("reviewer") or ""),
            rationale=str(value.get("rationale") or ""),
            decided_at=str(value.get("decided_at") or ""),
            subject_fingerprint=str(value.get("subject_fingerprint") or ""),
            subject_artifacts=tuple(
                ReviewSubjectReference.from_dict(dict(item))
                for item in value.get("subject_artifacts") or []
            ),
            migration_metadata=dict(value.get("migration_metadata") or {}),
        )


@dataclass(frozen=True)
class ReviewDecisionSet:
    revision: int
    decisions: tuple[ReviewDecision, ...] = ()

    def by_id(self) -> dict[str, ReviewDecision]:
        return {item.review_id: item for item in self.decisions}


class ReviewCurrency(StrEnum):
    MISSING = "missing"
    CURRENT = "current"
    STALE = "stale"
    ORPHANED = "orphaned"


@dataclass(frozen=True)
class ReviewDecisionAssessment:
    review_id: str
    resolution: ReviewResolution | None
    currency: ReviewCurrency
    reasons: tuple[str, ...] = ()

    @property
    def authorizes_review_completion(self) -> bool:
        return (
            self.currency is ReviewCurrency.CURRENT
            and self.resolution in {
                ReviewResolution.APPROVED,
                ReviewResolution.WAIVED,
            }
        )

    @property
    def authorizes_executable_generation(self) -> bool:
        return (
            self.currency is ReviewCurrency.CURRENT
            and self.resolution is ReviewResolution.APPROVED
        )
