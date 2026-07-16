from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath


_REVIEW_SEPARATOR = re.compile(r"[\s_:/\\|.\-]+")


@dataclass(frozen=True)
class ReviewSemanticKey:
    category: str
    function_id: str
    case_id: str | None
    semantic_subject_key: str


class ReviewIdCollisionError(ValueError):
    def __init__(
        self,
        review_id: str,
        existing_key: ReviewSemanticKey,
        candidate_key: ReviewSemanticKey,
    ) -> None:
        self.review_id = review_id
        self.collided_id = review_id
        self.existing_key = existing_key
        self.candidate_key = candidate_key
        super().__init__(
            f"Review ID collision for {review_id}: "
            f"{existing_key!r} != {candidate_key!r}"
        )


def build_function_id(logical_source_path: str, function_name: str) -> str:
    path_text = _exact_string(logical_source_path, "logical_source_path")
    normalized_input = path_text.replace("\\", "/")
    path = PurePosixPath(normalized_input)
    normalized_path = path.as_posix()
    if (
        not normalized_input
        or path.is_absolute()
        or ".." in path.parts
        or re.match(r"^[A-Za-z]:", normalized_input)
        or re.match(r"^[A-Za-z]:", normalized_path)
    ):
        raise ValueError(
            f"Expected normalized relative path: {logical_source_path}"
        )
    _strict_utf8(normalized_path, "logical_source_path")

    name = _exact_string(function_name, "function_name").strip()
    if not name:
        raise ValueError("Function name is required for stable identity.")
    _strict_utf8(name, "function_name")

    digest_bytes = (
        normalized_path.encode("utf-8")
        + b"\x00"
        + name.encode("utf-8")
    )
    suffix = hashlib.sha256(digest_bytes).hexdigest()[:12]
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"fn_{slug or 'function'}_{suffix}"


def build_review_id(
    category: str,
    function_id: str,
    case_id: str | None,
    semantic_subject_key: str,
) -> str:
    key = _normalized_semantic_key(
        category=category,
        function_id=function_id,
        case_id=case_id,
        semantic_subject_key=semantic_subject_key,
    )
    components = (
        key.category,
        key.function_id,
        key.case_id or "",
        key.semantic_subject_key,
    )
    digest = hashlib.sha256("\x00".join(components).encode("utf-8")).hexdigest()[:16]
    slug = re.sub(r"[^A-Za-z0-9]+", "-", key.category).strip("-").lower()
    return f"review-{slug or 'review'}-{digest}"


def semantic_case_id_token(case_id: str) -> str:
    """Return the exact case-ID token used by stable review identity."""
    return _normalize_review_component(case_id, "case_id")


def semantic_review_subject_token(semantic_subject_key: str) -> str:
    """Return the exact subject token used by stable review identity."""
    return _normalize_review_component(
        semantic_subject_key,
        "semantic_subject_key",
    )


class StableReviewIdRegistry:
    def __init__(self) -> None:
        self._keys_by_id: dict[str, ReviewSemanticKey] = {}

    def register(
        self,
        *,
        category: str,
        function_id: str,
        case_id: str | None,
        semantic_subject_key: str,
    ) -> str:
        candidate_key = _normalized_semantic_key(
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
        existing_key = self._keys_by_id.get(review_id)
        if existing_key is None:
            self._keys_by_id[review_id] = candidate_key
        elif existing_key != candidate_key:
            raise ReviewIdCollisionError(review_id, existing_key, candidate_key)
        return review_id


def _normalized_semantic_key(
    *,
    category: str,
    function_id: str,
    case_id: str | None,
    semantic_subject_key: str,
) -> ReviewSemanticKey:
    normalized_case = (
        None
        if case_id is None
        else semantic_case_id_token(case_id)
    )
    return ReviewSemanticKey(
        category=_normalize_review_component(category, "category"),
        function_id=_normalize_review_component(function_id, "function_id"),
        case_id=normalized_case,
        semantic_subject_key=semantic_review_subject_token(semantic_subject_key),
    )


def _normalize_review_component(value: str, field: str) -> str:
    text = _exact_string(value, field)
    normalized = unicodedata.normalize("NFKC", text).strip()
    normalized = _REVIEW_SEPARATOR.sub("/", normalized).strip("/")
    if not normalized:
        raise ValueError(f"{field} must not be empty.")
    _strict_utf8(normalized, field)
    return normalized


def _exact_string(value: object, field: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact string.")
    if "\x00" in value:
        raise ValueError(f"{field} must not contain NUL.")
    _strict_utf8(value, field)
    return value


def _strict_utf8(value: str, field: str) -> None:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValueError(f"{field} must be strict UTF-8.") from error


__all__ = [
    "ReviewIdCollisionError",
    "ReviewSemanticKey",
    "StableReviewIdRegistry",
    "build_function_id",
    "build_review_id",
    "semantic_case_id_token",
    "semantic_review_subject_token",
]
