from __future__ import annotations


def select_candidates_for_coverage(boundary_payload: dict, coverage_id: str, max_items: int = 2) -> tuple[list[dict], list[dict]]:
    matching = []
    for collection in ("input_candidates", "state_candidates", "stub_return_candidates"):
        for candidate in boundary_payload.get(collection, []):
            if coverage_id in candidate.get("related_coverage_ids", []):
                item = dict(candidate)
                item["_candidate_collection"] = collection
                matching.append(item)
    matching.sort(key=_candidate_sort_key)

    selected: list[dict] = []
    additional: list[dict] = []
    selected_subjects: set[tuple[str, ...]] = set()
    for candidate in matching:
        subject = _candidate_subject(candidate)
        if len(selected) < max_items and subject not in selected_subjects:
            selected.append(candidate)
            selected_subjects.add(subject)
        else:
            additional.append(candidate)
    return selected, additional


def fallback_input_candidates(boundary_payload: dict, max_items: int = 2) -> list[dict]:
    candidates = list(boundary_payload.get("input_candidates", []))
    candidates.sort(key=_candidate_sort_key)
    return candidates[:max_items]


def _candidate_sort_key(candidate: dict) -> tuple[int, int, int, str]:
    confidence_rank = {"high": 0, "medium": 1, "low": 2}.get(candidate.get("confidence"), 3)
    review_rank = 1 if candidate.get("review_required", True) else 0
    value_kind_rank = 0 if candidate.get("value_kind") == "boundary_at" else 1
    return confidence_rank, review_rank, value_kind_rank, candidate.get("candidate_id", "")


def _candidate_subject(candidate: dict) -> tuple[str, ...]:
    collection = str(candidate.get("_candidate_collection") or "unknown")
    if collection == "input_candidates":
        return (
            collection,
            str(candidate.get("target_kind") or "unknown"),
            str(candidate.get("target_name") or "unknown"),
        )
    if collection == "state_candidates":
        return (collection, str(candidate.get("variable_name") or "unknown"))
    if collection == "stub_return_candidates":
        return (collection, str(candidate.get("call_name") or "unknown"))
    return (collection, str(candidate.get("candidate_id") or "unknown"))
