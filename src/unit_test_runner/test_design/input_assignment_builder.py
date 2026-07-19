from __future__ import annotations

from .test_case_models import TestInputAssignment


def build_input_assignments(function_signature: dict, selected_candidates: list[dict], fallback_candidates: list[dict]) -> tuple[list[TestInputAssignment], list[str]]:
    assignments: list[TestInputAssignment] = []
    candidate_ids: list[str] = []
    source_candidates = [candidate for candidate in selected_candidates if candidate.get("_candidate_collection", "input_candidates") == "input_candidates"]
    if not source_candidates:
        source_candidates = fallback_candidates
    source_candidates = _first_candidate_per_target(source_candidates)
    for candidate in source_candidates:
        assignments.append(
            TestInputAssignment(
                target_name=candidate.get("target_name", "unknown"),
                target_kind=candidate.get("target_kind", "unknown"),
                value_expression=candidate.get("value_expression", "TBD_VALID_VALUE"),
                value_kind=candidate.get("value_kind", "unknown"),
                source_candidate_id=candidate.get("candidate_id"),
                rationale=candidate.get("purpose", "candidate selected for coverage"),
                review_required=candidate.get("review_required", True),
                confidence=candidate.get("confidence", "medium"),
            )
        )
        if candidate.get("candidate_id"):
            candidate_ids.append(candidate["candidate_id"])
    assigned_targets = {assignment.target_name for assignment in assignments}
    for parameter in function_signature.get("function", {}).get("parameters", []):
        name = parameter.get("name")
        if not name or name in assigned_targets:
            continue
        fallback = next((candidate for candidate in fallback_candidates if candidate.get("target_name") == name), None)
        if fallback:
            assignments.append(
                TestInputAssignment(
                    target_name=name,
                    target_kind=fallback.get("target_kind", "parameter"),
                    value_expression=fallback.get("value_expression", "TBD_VALID_VALUE"),
                    value_kind=fallback.get("value_kind", "valid_equivalence"),
                    source_candidate_id=fallback.get("candidate_id"),
                    rationale=fallback.get("purpose", "default candidate selected for parameter"),
                    review_required=fallback.get("review_required", True),
                    confidence=fallback.get("confidence", "medium"),
                )
            )
            if fallback.get("candidate_id"):
                candidate_ids.append(fallback["candidate_id"])
            continue
        assignments.append(
            TestInputAssignment(
                target_name=name,
                target_kind="parameter",
                value_expression="TBD_VALID_VALUE",
                value_kind="valid_equivalence",
                source_candidate_id=None,
                rationale="default valid value placeholder",
                review_required=True,
                confidence="low",
            )
        )
    return assignments, candidate_ids


def _first_candidate_per_target(candidates: list[dict]) -> list[dict]:
    result: list[dict] = []
    positions: dict[tuple[str, str], int] = {}
    for candidate in candidates:
        key = (
            str(candidate.get("target_kind") or "unknown"),
            str(candidate.get("target_name") or "unknown"),
        )
        position = positions.get(key)
        if position is None:
            positions[key] = len(result)
            result.append(candidate)
            continue
        current = result[position]
        if _candidate_preference(candidate) < _candidate_preference(current):
            result[position] = candidate
    return result


def _candidate_preference(candidate: dict) -> int:
    return 0 if candidate.get("value_kind") == "boundary_at" else 1
