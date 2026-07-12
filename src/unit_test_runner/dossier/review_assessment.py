from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable

from .review_decision_models import ReviewItemSnapshot, ReviewSubjectReference


class ReviewIdCollisionError(ValueError):
    """Two distinct semantic subjects resolved to one review identifier."""


def _normalize_component(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"\s*[/\\|:]+\s*", "/", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip("/")


def build_stable_review_id(
    category: str,
    function_id: str,
    case_id: str | None,
    semantic_subject_key: str,
) -> str:
    normalized = (
        _normalize_component(category),
        _normalize_component(function_id),
        _normalize_component(case_id) if case_id is not None else None,
        _normalize_component(semantic_subject_key),
    )
    canonical = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    slug = re.sub(r"[^a-z0-9]+", "-", normalized[0].lower()).strip("-")
    return f"review-{slug or 'item'}-{digest}"


def validate_review_item_identities(items: Iterable[ReviewItemSnapshot]) -> None:
    seen: dict[str, tuple[str, str, str | None, str]] = {}
    for item in items:
        semantic_tuple = tuple(
            _normalize_component(value) if value is not None else None
            for value in item.semantic_tuple
        )
        previous = seen.get(item.review_id)
        if previous is not None and previous != semantic_tuple:
            raise ReviewIdCollisionError(
                f"review identifier collision for {item.review_id}: "
                f"{previous!r} != {semantic_tuple!r}"
            )
        seen[item.review_id] = semantic_tuple


def subject_fingerprint(subjects: Iterable[ReviewSubjectReference]) -> str:
    rows = [item.to_dict() for item in sorted(subjects)]
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
