from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterable, Mapping


_SEPARATOR_RE = re.compile(r"[\s_:/\\|.\-]+", re.UNICODE)
_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


class ReviewIdCollisionError(ValueError):
    """Two distinct normalized semantic subjects resolved to one review ID."""

    def __init__(
        self,
        review_id: str,
        existing: "ReviewSemanticKey",
        candidate: "ReviewSemanticKey",
    ) -> None:
        self.review_id = review_id
        self.existing = existing
        self.candidate = candidate
        super().__init__(
            "Stable review ID collision for "
            f"{review_id}: {existing!r} != {candidate!r}."
        )


@dataclass(frozen=True, order=True)
class ReviewSemanticKey:
    category: str
    function_id: str
    case_id: str | None
    semantic_subject_key: str

    @classmethod
    def normalized(
        cls,
        *,
        category: str,
        function_id: str,
        case_id: str | None,
        semantic_subject_key: str,
    ) -> "ReviewSemanticKey":
        normalized_category = _normalize_semantic_component(category)
        normalized_function = _normalize_semantic_component(function_id)
        normalized_case = (
            _normalize_semantic_component(case_id) if case_id is not None else None
        )
        normalized_subject = _normalize_semantic_component(semantic_subject_key)
        if not normalized_category:
            raise ValueError("Review category must not be blank.")
        if not normalized_function:
            raise ValueError("Review function_id must not be blank.")
        if case_id is not None and not normalized_case:
            raise ValueError("Review case_id must not be blank when supplied.")
        if not normalized_subject:
            raise ValueError("Review semantic_subject_key must not be blank.")
        return cls(
            category=normalized_category,
            function_id=normalized_function,
            case_id=normalized_case,
            semantic_subject_key=normalized_subject,
        )

    def components(self) -> tuple[str, str, str, str]:
        return (
            self.category,
            self.function_id,
            self.case_id or "",
            self.semantic_subject_key,
        )


def build_review_id(
    category: str,
    function_id: str,
    case_id: str | None,
    semantic_subject_key: str,
) -> str:
    key = ReviewSemanticKey.normalized(
        category=category,
        function_id=function_id,
        case_id=case_id,
        semantic_subject_key=semantic_subject_key,
    )
    category_slug = _SLUG_RE.sub("-", key.category).strip("-").lower()
    if not category_slug:
        category_slug = "review"
    return f"review-{category_slug}-{_semantic_digest(key)}"


def _semantic_digest(key: ReviewSemanticKey) -> str:
    encoded = "\0".join(key.components()).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _normalize_semantic_component(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return _SEPARATOR_RE.sub("/", text).strip("/")


def subject_fingerprint(references: Iterable[Any]) -> str:
    """Hash exact subject identity in an order-independent canonical form."""

    canonical: list[dict[str, Any]] = []
    for reference in references:
        if isinstance(reference, Mapping):
            value = reference
            getter = value.get
        else:
            getter = lambda name, default=None, item=reference: getattr(
                item, name, default
            )
        canonical.append(
            {
                "artifact_kind": getter("artifact_kind"),
                "path": getter("path"),
                "sha256": getter("sha256"),
                "revision": getter("revision"),
            }
        )
    canonical.sort(
        key=lambda item: (
            str(item.get("artifact_kind") or ""),
            str(item.get("path") or ""),
            str(item.get("sha256") or ""),
            -1 if item.get("revision") is None else int(item["revision"]),
        )
    )
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class StableReviewIdRegistry:
    _keys_by_id: dict[str, ReviewSemanticKey] = field(default_factory=dict)

    def register(
        self,
        *,
        category: str,
        function_id: str,
        case_id: str | None,
        semantic_subject_key: str,
    ) -> str:
        key = ReviewSemanticKey.normalized(
            category=category,
            function_id=function_id,
            case_id=case_id,
            semantic_subject_key=semantic_subject_key,
        )
        review_id = build_review_id(
            category,
            function_id,
            case_id,
            semantic_subject_key,
        )
        existing = self._keys_by_id.get(review_id)
        if existing is not None and existing != key:
            raise ReviewIdCollisionError(review_id, existing, key)
        self._keys_by_id[review_id] = key
        return review_id

    def register_many(
        self,
        values: Iterable[ReviewSemanticKey],
    ) -> tuple[str, ...]:
        return tuple(
            self.register(
                category=value.category,
                function_id=value.function_id,
                case_id=value.case_id,
                semantic_subject_key=value.semantic_subject_key,
            )
            for value in values
        )
