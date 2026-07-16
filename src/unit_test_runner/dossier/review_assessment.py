from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Iterable, Mapping

from unit_test_runner.contracts import ArtifactKind, ContractMode, load_artifact

from .review_decision_models import (
    ReviewDecision,
    ReviewDecisionSet,
    ReviewItemCollection,
    ReviewItemSnapshot,
    ReviewResolution,
    ReviewSnapshot,
    ReviewSubjectReference,
)


class ReviewAssessmentStatus(StrEnum):
    MISSING = "missing"
    OPEN = "open"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    WAIVED = "waived"
    STALE = "stale"


@dataclass(frozen=True)
class ReviewItemAssessment:
    review_id: str
    status: ReviewAssessmentStatus
    resolution: ReviewResolution | None
    reasons: tuple[str, ...]
    subject_fingerprint: str

    @property
    def complete(self) -> bool:
        return self.status in {
            ReviewAssessmentStatus.APPROVED,
            ReviewAssessmentStatus.WAIVED,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "review_id": self.review_id,
            "status": self.status.value,
            "resolution": self.resolution.value if self.resolution is not None else None,
            "reasons": list(self.reasons),
            "subject_fingerprint": self.subject_fingerprint,
        }


@dataclass(frozen=True)
class ReviewAssessment:
    ledger_revision: int | None
    items: tuple[ReviewItemAssessment, ...]
    orphan_review_ids: tuple[str, ...]

    @property
    def review_complete(self) -> bool:
        return all(item.complete for item in self.items)

    def for_review_id(self, review_id: str) -> ReviewItemAssessment:
        candidate = str(review_id)
        for item in self.items:
            if item.review_id == candidate:
                return item
        raise KeyError(candidate)

    def to_dict(self) -> dict[str, object]:
        return {
            "ledger_revision": self.ledger_revision,
            "review_complete": self.review_complete,
            "items": [item.to_dict() for item in self.items],
            "orphan_review_ids": list(self.orphan_review_ids),
        }


def discover_review_snapshot(workspace: Path | str) -> ReviewSnapshot:
    root = Path(workspace).resolve()
    dossier_path = root / "reports" / "function_dossier.json"
    loaded = load_artifact(
        dossier_path,
        expected_kind=ArtifactKind.FUNCTION_DOSSIER,
        mode=ContractMode.STRICT,
    )
    if loaded.violations:
        detail = "; ".join(
            f"{item.code} at {item.json_path}: {item.message}"
            for item in loaded.violations
        )
        raise ValueError(f"Current function dossier is invalid: {detail}")

    payload = loaded.payload
    subject = payload.get("subject")
    data = payload.get("data")
    if not isinstance(subject, Mapping) or not isinstance(data, Mapping):
        raise ValueError("Current function dossier is missing its subject or data object")
    raw_items = data.get("review_items")
    if not isinstance(raw_items, list):
        raise ValueError("Current function dossier review_items must be an array")

    snapshots: list[ReviewItemSnapshot] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            raise ValueError("Current function dossier contains a non-object review item")
        raw_subjects = raw_item.get("subject_artifacts")
        if not isinstance(raw_subjects, list):
            raise ValueError("Current review item subject_artifacts must be an array")
        references = tuple(
            ReviewSubjectReference.from_dict(value)
            for value in raw_subjects
            if isinstance(value, Mapping)
        )
        if len(references) != len(raw_subjects):
            raise ValueError("Current review item contains a non-object subject reference")
        if any(
            reference.path == "reports/function_dossier.json"
            for reference in references
        ):
            raise ValueError(
                "Review decisions must not bind the mutable function dossier itself"
            )
        snapshots.append(
            ReviewItemSnapshot(
                review_id=str(raw_item.get("review_id") or ""),
                category=str(raw_item.get("category") or ""),
                function_id=str(subject.get("function_id") or ""),
                case_id=(
                    str(raw_item["case_id"])
                    if raw_item.get("case_id") is not None
                    else None
                ),
                semantic_subject_key=str(
                    raw_item.get("semantic_subject_key") or ""
                ),
                subject_artifacts=references,
            )
        )
    return ReviewSnapshot(
        items=ReviewItemCollection(tuple(snapshots)),
        function_id=str(subject.get("function_id") or ""),
        source_path=str(subject.get("source_path") or ""),
        source_sha256=str(subject.get("source_sha256") or ""),
    )


def assess_review_decisions(
    current_items: ReviewItemCollection,
    decisions: ReviewDecisionSet | None,
    *,
    workspace: Path | None = None,
) -> ReviewAssessment:
    by_id = {
        decision.review_id: decision
        for decision in (decisions.decisions if decisions is not None else ())
    }
    current_ids = {item.review_id for item in current_items.items}
    orphan_ids = tuple(sorted(set(by_id) - current_ids))
    assessments = tuple(
        _assess_item(
            item,
            by_id.get(item.review_id),
            workspace=Path(workspace).resolve() if workspace is not None else None,
        )
        for item in current_items.items
    )
    return ReviewAssessment(
        ledger_revision=decisions.revision if decisions is not None else None,
        items=assessments,
        orphan_review_ids=orphan_ids,
    )


def _assess_item(
    item: ReviewItemSnapshot,
    decision: ReviewDecision | None,
    *,
    workspace: Path | None,
) -> ReviewItemAssessment:
    reasons: list[str] = []
    if workspace is not None:
        for subject in item.subject_artifacts:
            reasons.extend(_subject_file_reasons(workspace, subject))

    if decision is None:
        return ReviewItemAssessment(
            review_id=item.review_id,
            status=(
                ReviewAssessmentStatus.STALE
                if reasons
                else ReviewAssessmentStatus.MISSING
            ),
            resolution=None,
            reasons=tuple(_unique(reasons or ["decision_missing"])),
            subject_fingerprint=item.subject_fingerprint,
        )

    reasons.extend(
        _subject_identity_reasons(item.subject_artifacts, decision.subject_artifacts)
    )
    if reasons:
        return ReviewItemAssessment(
            review_id=item.review_id,
            status=ReviewAssessmentStatus.STALE,
            resolution=decision.resolution,
            reasons=tuple(_unique(reasons)),
            subject_fingerprint=item.subject_fingerprint,
        )

    status = {
        ReviewResolution.OPEN: ReviewAssessmentStatus.OPEN,
        ReviewResolution.APPROVED: ReviewAssessmentStatus.APPROVED,
        ReviewResolution.CHANGES_REQUESTED: ReviewAssessmentStatus.CHANGES_REQUESTED,
        ReviewResolution.WAIVED: ReviewAssessmentStatus.WAIVED,
    }[decision.resolution]
    return ReviewItemAssessment(
        review_id=item.review_id,
        status=status,
        resolution=decision.resolution,
        reasons=(),
        subject_fingerprint=item.subject_fingerprint,
    )


def _subject_identity_reasons(
    current: tuple[ReviewSubjectReference, ...],
    recorded: tuple[ReviewSubjectReference, ...],
) -> list[str]:
    if current == recorded:
        return []
    reasons: list[str] = []
    if len(current) != len(recorded):
        reasons.append("subject_count_changed")
    for expected, actual in zip(_sorted_subjects(current), _sorted_subjects(recorded)):
        fields = (
            ("artifact_kind", "subject_kind_changed"),
            ("path", "subject_path_changed"),
            ("sha256", "subject_hash_changed"),
            ("revision", "subject_revision_changed"),
            ("source_path", "subject_source_path_changed"),
            ("source_sha256", "subject_source_hash_changed"),
            ("function_id", "subject_function_changed"),
            ("semantic_subject_key", "subject_semantic_key_changed"),
        )
        for field, code in fields:
            if getattr(expected, field) != getattr(actual, field):
                reasons.append(code)
    return reasons or ["subject_identity_changed"]


def _subject_file_reasons(
    workspace: Path,
    subject: ReviewSubjectReference,
) -> list[str]:
    path = workspace / Path(subject.path)
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(workspace)
    except (OSError, ValueError):
        return ["subject_missing"]
    if not resolved.is_file():
        return ["subject_missing"]

    raw = resolved.read_bytes()
    if hashlib.sha256(raw).hexdigest() != subject.sha256:
        return ["subject_hash_mismatch"]

    try:
        kind = ArtifactKind(subject.artifact_kind)
    except ValueError:
        return ["subject_schema_invalid"]
    loaded = load_artifact(resolved, expected_kind=kind, mode=ContractMode.STRICT)
    if loaded.violations:
        if any(item.code == "parse_error" for item in loaded.violations):
            return ["subject_invalid_json"]
        return ["subject_schema_invalid"]

    reasons: list[str] = []
    data = loaded.payload.get("data")
    data = data if isinstance(data, dict) else {}
    if subject.revision is not None and data.get("revision") != subject.revision:
        reasons.append("subject_revision_mismatch")
    identity = loaded.payload.get("subject")
    identity = identity if isinstance(identity, dict) else {}
    if (
        subject.source_path is not None
        and identity.get("source_path") != subject.source_path
    ):
        reasons.append("subject_source_path_mismatch")
    if (
        subject.source_sha256 is not None
        and identity.get("source_sha256") != subject.source_sha256
    ):
        reasons.append("subject_source_hash_mismatch")
    if (
        subject.function_id is not None
        and identity.get("function_id") != subject.function_id
    ):
        reasons.append("subject_function_mismatch")
    return reasons


def _sorted_subjects(
    subjects: Iterable[ReviewSubjectReference],
) -> tuple[ReviewSubjectReference, ...]:
    return tuple(
        sorted(
            subjects,
            key=lambda item: (
                item.artifact_kind,
                item.path,
                item.sha256,
                item.revision or 0,
                item.source_path or "",
                item.source_sha256 or "",
                item.function_id or "",
                item.semantic_subject_key or "",
            ),
        )
    )


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


__all__ = [
    "ReviewAssessment",
    "ReviewAssessmentStatus",
    "ReviewItemAssessment",
    "assess_review_decisions",
    "discover_review_snapshot",
]
