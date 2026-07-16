from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping

from unit_test_runner.review_ids import (
    ReviewIdCollisionError,
    ReviewSemanticKey,
    StableReviewIdRegistry,
    build_review_id,
    subject_fingerprint,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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
    revision: int | None
    source_path: str | None
    source_sha256: str | None
    function_id: str | None
    semantic_subject_key: str | None

    def __post_init__(self) -> None:
        artifact_kind = str(self.artifact_kind).strip()
        if not artifact_kind:
            raise ValueError("artifact_kind must not be blank")
        object.__setattr__(self, "artifact_kind", artifact_kind)

        normalized_path = _normalize_relative_path(self.path, field_name="path")
        object.__setattr__(self, "path", normalized_path)

        sha256 = str(self.sha256).lower()
        if not _SHA256_RE.fullmatch(sha256):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        object.__setattr__(self, "sha256", sha256)

        if self.revision is not None and (
            isinstance(self.revision, bool) or int(self.revision) < 1
        ):
            raise ValueError("revision must be null or a positive integer")

        if self.source_path is not None:
            object.__setattr__(
                self,
                "source_path",
                _normalize_relative_path(self.source_path, field_name="source_path"),
            )
        if self.source_sha256 is not None:
            source_sha256 = str(self.source_sha256).lower()
            if not _SHA256_RE.fullmatch(source_sha256):
                raise ValueError(
                    "source_sha256 must be null or 64 lowercase hexadecimal characters"
                )
            object.__setattr__(self, "source_sha256", source_sha256)
        if self.function_id is not None:
            function_id = str(self.function_id).strip()
            if not function_id:
                raise ValueError("function_id must not be blank when supplied")
            object.__setattr__(self, "function_id", function_id)
        if self.semantic_subject_key is not None:
            semantic_subject_key = str(self.semantic_subject_key).strip()
            if not semantic_subject_key:
                raise ValueError(
                    "semantic_subject_key must not be blank when supplied"
                )
            object.__setattr__(
                self,
                "semantic_subject_key",
                semantic_subject_key,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": self.artifact_kind,
            "path": self.path,
            "sha256": self.sha256,
            "revision": self.revision,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "function_id": self.function_id,
            "semantic_subject_key": self.semantic_subject_key,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReviewSubjectReference":
        return cls(
            artifact_kind=str(value.get("artifact_kind") or ""),
            path=str(value.get("path") or ""),
            sha256=str(value.get("sha256") or ""),
            revision=(
                int(value["revision"])
                if value.get("revision") is not None
                else None
            ),
            source_path=(
                str(value["source_path"])
                if value.get("source_path") is not None
                else None
            ),
            source_sha256=(
                str(value["source_sha256"])
                if value.get("source_sha256") is not None
                else None
            ),
            function_id=(
                str(value["function_id"])
                if value.get("function_id") is not None
                else None
            ),
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
    subject_artifacts: tuple[ReviewSubjectReference, ...]

    def __post_init__(self) -> None:
        category = str(self.category).strip()
        function_id = str(self.function_id).strip()
        semantic_subject_key = str(self.semantic_subject_key).strip()
        case_id = str(self.case_id).strip() if self.case_id is not None else None
        expected_id = build_review_id(
            category,
            function_id,
            case_id,
            semantic_subject_key,
        )
        if str(self.review_id).strip() != expected_id:
            raise ValueError(
                f"review_id does not match semantic identity: expected {expected_id}"
            )
        subjects = tuple(self.subject_artifacts)
        if not subjects:
            raise ValueError("Review items require at least one exact subject artifact")
        if len(set(subjects)) != len(subjects):
            raise ValueError("Review item subject_artifacts must be unique")
        for subject in subjects:
            if subject.function_id != function_id:
                raise ValueError(
                    "Review item subject function_id must match the semantic identity"
                )
            if subject.semantic_subject_key != semantic_subject_key:
                raise ValueError(
                    "Review item subject semantic_subject_key must match the semantic identity"
                )
        object.__setattr__(self, "review_id", expected_id)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "function_id", function_id)
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "semantic_subject_key", semantic_subject_key)
        object.__setattr__(self, "subject_artifacts", subjects)

    @property
    def identity_tuple(self) -> tuple[str, str, str | None, str]:
        return (
            self.category,
            self.function_id,
            self.case_id,
            self.semantic_subject_key,
        )

    @property
    def subject_fingerprint(self) -> str:
        return subject_fingerprint(self.subject_artifacts)


@dataclass(frozen=True)
class ReviewItemCollection:
    items: tuple[ReviewItemSnapshot, ...]

    def __post_init__(self) -> None:
        items = tuple(self.items)
        by_id: dict[str, ReviewItemSnapshot] = {}
        for item in items:
            existing = by_id.get(item.review_id)
            if existing is not None:
                if existing.identity_tuple != item.identity_tuple:
                    raise ReviewIdCollisionError(
                        item.review_id,
                        ReviewSemanticKey(*existing.identity_tuple),
                        ReviewSemanticKey(*item.identity_tuple),
                    )
                raise ValueError(f"Duplicate review_id in collection: {item.review_id}")
            by_id[item.review_id] = item
        object.__setattr__(self, "items", items)

    def resolve(self, review_id: str) -> ReviewItemSnapshot | None:
        candidate = str(review_id)
        return next(
            (item for item in self.items if item.review_id == candidate),
            None,
        )


@dataclass(frozen=True)
class ReviewSnapshot:
    items: ReviewItemCollection
    function_id: str
    source_path: str
    source_sha256: str

    def __post_init__(self) -> None:
        function_id = str(self.function_id).strip()
        if not function_id:
            raise ValueError("Review snapshot function_id must not be blank")
        source_path = _normalize_relative_path(
            self.source_path,
            field_name="source_path",
        )
        source_sha256 = str(self.source_sha256).lower()
        if not _SHA256_RE.fullmatch(source_sha256):
            raise ValueError(
                "Review snapshot source_sha256 must be 64 lowercase hexadecimal characters"
            )
        if not self.items.items:
            raise ValueError("Review snapshot must contain at least one current item")
        for item in self.items.items:
            if item.function_id != function_id:
                raise ValueError(
                    "Review snapshot item function_id must match snapshot identity"
                )
            for subject in item.subject_artifacts:
                if (
                    subject.source_path != source_path
                    or subject.source_sha256 != source_sha256
                ):
                    raise ValueError(
                        "Review snapshot subject source identity must match snapshot identity"
                    )
        object.__setattr__(self, "function_id", function_id)
        object.__setattr__(self, "source_path", source_path)
        object.__setattr__(self, "source_sha256", source_sha256)


@dataclass(frozen=True)
class ReviewDecision:
    review_id: str
    resolution: ReviewResolution
    reviewer: str
    rationale: str
    decided_at: str | None
    subject_artifacts: tuple[ReviewSubjectReference, ...]

    def __post_init__(self) -> None:
        review_id = str(self.review_id).strip()
        if not review_id:
            raise ValueError("review_id must not be blank")
        object.__setattr__(self, "review_id", review_id)

        resolution = ReviewResolution(self.resolution)
        object.__setattr__(self, "resolution", resolution)

        reviewer = str(self.reviewer).strip()
        rationale = str(self.rationale).strip()
        object.__setattr__(self, "reviewer", reviewer)
        object.__setattr__(self, "rationale", rationale)

        subjects = tuple(self.subject_artifacts)
        if not subjects:
            raise ValueError("subject_artifacts must not be empty")
        if len(set(subjects)) != len(subjects):
            raise ValueError("subject_artifacts must not contain duplicates")
        object.__setattr__(self, "subject_artifacts", subjects)

        terminal = resolution is not ReviewResolution.OPEN
        if terminal and not reviewer:
            raise ValueError("reviewer is required for a terminal decision")
        if terminal and not rationale:
            raise ValueError("rationale is required for a terminal decision")
        if terminal and self.decided_at is None:
            raise ValueError("decided_at with timezone is required for a terminal decision")
        if self.decided_at is not None:
            object.__setattr__(self, "decided_at", _canonical_timestamp(self.decided_at))

    @property
    def subject_fingerprint(self) -> str:
        return subject_fingerprint(self.subject_artifacts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "resolution": self.resolution.value,
            "reviewer": self.reviewer,
            "rationale": self.rationale,
            "decided_at": self.decided_at,
            "subject_artifacts": [item.to_dict() for item in self.subject_artifacts],
            "subject_fingerprint": self.subject_fingerprint,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReviewDecision":
        subjects = value.get("subject_artifacts")
        if not isinstance(subjects, list):
            raise ValueError("subject_artifacts must be an array")
        decision = cls(
            review_id=str(value.get("review_id") or ""),
            resolution=ReviewResolution(str(value.get("resolution") or "")),
            reviewer=str(value.get("reviewer") or ""),
            rationale=str(value.get("rationale") or ""),
            decided_at=(
                str(value["decided_at"])
                if value.get("decided_at") is not None
                else None
            ),
            subject_artifacts=tuple(
                ReviewSubjectReference.from_dict(item)
                for item in subjects
                if isinstance(item, Mapping)
            ),
        )
        declared_fingerprint = value.get("subject_fingerprint")
        if (
            declared_fingerprint is not None
            and str(declared_fingerprint) != decision.subject_fingerprint
        ):
            raise ValueError("subject_fingerprint does not match subject_artifacts")
        return decision


@dataclass(frozen=True)
class ReviewDecisionSet:
    revision: int
    decisions: tuple[ReviewDecision, ...]

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or int(self.revision) < 1:
            raise ValueError("revision must be a positive integer")
        object.__setattr__(self, "revision", int(self.revision))
        decisions = tuple(self.decisions)
        ids = [item.review_id for item in decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("decisions must contain unique review_id values")
        object.__setattr__(self, "decisions", decisions)

    def to_data(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "decisions": [item.to_dict() for item in self.decisions],
        }

    @classmethod
    def from_data(cls, value: Mapping[str, Any]) -> "ReviewDecisionSet":
        decisions = value.get("decisions")
        if not isinstance(decisions, list):
            raise ValueError("decisions must be an array")
        return cls(
            revision=int(value.get("revision") or 0),
            decisions=tuple(
                ReviewDecision.from_dict(item)
                for item in decisions
                if isinstance(item, Mapping)
            ),
        )


def _normalize_relative_path(value: str, *, field_name: str) -> str:
    text = str(value).strip()
    normalized = text.replace("\\", "/")
    windows = PureWindowsPath(text)
    posix = PurePosixPath(normalized)
    if (
        not normalized
        or windows.is_absolute()
        or posix.is_absolute()
        or ".." in posix.parts
        or re.match(r"^[A-Za-z]:", text)
    ):
        raise ValueError(f"{field_name} must be a normalized relative path")
    return posix.as_posix()


def _canonical_timestamp(value: str) -> str:
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("decided_at must be an ISO-8601 timestamp with timezone") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("decided_at must include a timezone offset")
    return parsed.isoformat()


__all__ = [
    "ReviewDecision",
    "ReviewDecisionSet",
    "ReviewIdCollisionError",
    "ReviewItemCollection",
    "ReviewItemSnapshot",
    "ReviewResolution",
    "ReviewSemanticKey",
    "ReviewSnapshot",
    "ReviewSubjectReference",
    "StableReviewIdRegistry",
    "build_review_id",
    "subject_fingerprint",
]
