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
    return matching[:max_items], matching[max_items:]


def fallback_input_candidates(boundary_payload: dict, max_items: int = 2) -> list[dict]:
    candidates = list(boundary_payload.get("input_candidates", []))
    candidates.sort(key=_candidate_sort_key)
    return candidates[:max_items]


def _candidate_sort_key(candidate: dict) -> tuple[int, int, str]:
    confidence_rank = {"high": 0, "medium": 1, "low": 2}.get(candidate.get("confidence"), 3)
    review_rank = 1 if candidate.get("review_required", True) else 0
    return confidence_rank, review_rank, candidate.get("candidate_id", "")
