from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .reanalysis_models import CoverageChange


@dataclass
class CoverageMapping:
    old_coverage_id: str
    new_coverage_id: str | None
    similarity: float | None
    match_reason: str


@dataclass
class CoverageDiffResult:
    changes: list[CoverageChange]
    mappings: dict[str, CoverageMapping]


def compare_coverage_designs(
    previous: dict[str, Any],
    current: dict[str, Any],
    coverage_to_test_cases: dict[str, list[str]],
    include_low_confidence_matches: bool = False,
) -> CoverageDiffResult:
    previous_items = {str(item.get("coverage_id")): item for item in previous.get("coverage_items", []) if item.get("coverage_id")}
    current_items = {str(item.get("coverage_id")): item for item in current.get("coverage_items", []) if item.get("coverage_id")}
    previous_conditions = _conditions(previous)
    current_conditions = _conditions(current)
    changes: list[CoverageChange] = []
    mappings: dict[str, CoverageMapping] = {}
    matched_current: set[str] = set()
    for old_id, old_item in previous_items.items():
        affected = coverage_to_test_cases.get(old_id, [])
        if old_id in current_items:
            new_item = current_items[old_id]
            matched_current.add(old_id)
            old_condition = _condition_text(old_item, previous_conditions)
            new_condition = _condition_text(new_item, current_conditions)
            if old_condition == new_condition:
                mappings[old_id] = CoverageMapping(old_id, old_id, 1.0, "coverage_id")
                continue
            changes.append(
                CoverageChange("condition_changed", old_id, old_id, old_condition, new_condition, 0.95, affected, "Review changed condition.")
            )
            mappings[old_id] = CoverageMapping(old_id, old_id, 0.95, "coverage_id_changed_condition")
            continue
        match_id, similarity, reason = _best_match(old_item, current_items, current_conditions, matched_current)
        if match_id and (include_low_confidence_matches or similarity >= 0.75):
            matched_current.add(match_id)
            new_item = current_items[match_id]
            mappings[old_id] = CoverageMapping(old_id, match_id, similarity, reason)
            changes.append(
                CoverageChange(
                    "coverage_item_modified",
                    old_id,
                    match_id,
                    _condition_text(old_item, previous_conditions),
                    _condition_text(new_item, current_conditions),
                    similarity,
                    affected,
                    "Review remapped coverage item and boundary candidates.",
                )
            )
        else:
            mappings[old_id] = CoverageMapping(old_id, None, similarity if match_id else None, "removed")
            changes.append(
                CoverageChange(
                    "coverage_item_removed",
                    old_id,
                    None,
                    _condition_text(old_item, previous_conditions),
                    None,
                    None,
                    affected,
                    "Mark related test cases obsolete unless manually retained.",
                )
            )
    for new_id, new_item in current_items.items():
        if new_id not in matched_current and new_id not in previous_items:
            changes.append(
                CoverageChange(
                    "coverage_item_added",
                    None,
                    new_id,
                    None,
                    _condition_text(new_item, current_conditions),
                    None,
                    [],
                    "Add a new test case candidate.",
                )
            )
    return CoverageDiffResult(changes, mappings)


def _conditions(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("condition_id")): item for item in payload.get("condition_expressions", []) if item.get("condition_id")}


def _condition_text(item: dict[str, Any], conditions: dict[str, dict[str, Any]]) -> str | None:
    target = str(item.get("target_id") or "")
    condition = conditions.get(target)
    if condition and condition.get("raw"):
        return str(condition.get("raw"))
    return str(item.get("purpose") or item.get("condition_value") or "") or None


def _best_match(
    old_item: dict[str, Any],
    current_items: dict[str, dict[str, Any]],
    current_conditions: dict[str, dict[str, Any]],
    matched_current: set[str],
) -> tuple[str | None, float, str]:
    old_text = _condition_text(old_item, {}) or str(old_item.get("purpose") or "")
    best_id: str | None = None
    best_score = 0.0
    best_reason = "similarity"
    for new_id, new_item in current_items.items():
        if new_id in matched_current:
            continue
        if _shape_key(old_item) == _shape_key(new_item):
            shape_bonus = 0.25
            best_reason = "shape_similarity"
        else:
            shape_bonus = 0.0
        new_text = _condition_text(new_item, current_conditions) or str(new_item.get("purpose") or "")
        score = min(1.0, SequenceMatcher(None, old_text, new_text).ratio() + shape_bonus)
        if score > best_score:
            best_id = new_id
            best_score = score
    return best_id, best_score, best_reason


def _shape_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("coverage_type"),
        item.get("condition_value"),
        tuple(sorted(item.get("related_variables", []))),
        tuple(sorted(item.get("related_calls", []))),
    )
