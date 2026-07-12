from __future__ import annotations

import copy
from typing import Any

from .coverage_diff import CoverageMapping
from .reanalysis_models import (
    CoverageChange,
    DependencyChange,
    InterfaceChange,
    ManualMergeItem,
    ReanalysisWarning,
    ReconciledTestCase,
    TestCaseReconciliationReport,
)

PROTECTED_FIELDS = [
    "title",
    "target_function",
    "purpose",
    "priority",
    "case_kind",
    "preconditions",
    "input_assignments",
    "state_setups",
    "stub_setups",
    "dependency_overrides",
    "execution_steps",
    "expected_observations",
    "candidate_links",
    "confidence",
    "warnings",
    "review_item_ids",
]

_EMBEDDED_REVIEW_AUTHORITY_FIELDS = {
    "approved",
    "approval",
    "approval_status",
    "is_approved",
    "review_status",
    "review_decision",
}


def reconcile_test_cases(
    previous_design: dict[str, Any],
    current_design: dict[str, Any],
    coverage_mappings: list[CoverageMapping],
    coverage_changes: list[CoverageChange],
    interface_changes: list[InterfaceChange],
    dependency_changes: list[DependencyChange],
    generate_updated_test_case_design: bool = False,
) -> tuple[TestCaseReconciliationReport, dict[str, Any] | None]:
    function_name = _function_name(previous_design, current_design)
    mapping_by_old = {item.old_coverage_id: item for item in coverage_mappings}
    coverage_changes_by_test = _changes_by_test(coverage_changes)
    interface_changes_by_test = _changes_by_test(interface_changes)
    dependency_changes_by_test = _changes_by_test(dependency_changes)
    current_by_coverage = _current_cases_by_coverage(current_design)
    report = TestCaseReconciliationReport(function_name=function_name, status="completed")
    updated_cases: list[dict[str, Any]] = []
    previous_cases = list(previous_design.get("test_cases", []))
    for previous_case in previous_cases:
        test_case_id = str(previous_case.get("test_case_id") or previous_case.get("id") or "")
        previous_coverage_ids = _coverage_ids(previous_case)
        previous_candidate_ids = list(previous_case.get("candidate_links", []))
        current_coverage_ids = [_mapped_coverage_id(item, mapping_by_old) for item in previous_coverage_ids]
        current_coverage_ids = [item for item in current_coverage_ids if item]
        proposed = _first_case_for_coverage(current_by_coverage, current_coverage_ids)
        preserved_fields = [field for field in PROTECTED_FIELDS if field in previous_case]
        updated_fields: list[str] = []
        review_fields: list[str] = []
        reason = "No related changes."
        confidence = "high"
        reuse_status = "reusable"
        if test_case_id in interface_changes_by_test and any(change.impact_level == "high" for change in interface_changes_by_test[test_case_id]):
            reuse_status = "blocked"
            reason = "Function signature changed incompatibly."
            confidence = "high"
        elif any(change.change_kind == "coverage_item_removed" for change in coverage_changes_by_test.get(test_case_id, [])):
            reuse_status = "obsolete"
            reason = "Related coverage item was removed."
            confidence = "high"
        elif test_case_id in coverage_changes_by_test or test_case_id in dependency_changes_by_test:
            reuse_status = "needs_update"
            reason = "Related coverage or dependency changed."
            confidence = "medium"
            if test_case_id in coverage_changes_by_test:
                updated_fields.append("coverage_links")
            review_fields.extend(["expected_observations", "stub_setups"])
        elif proposed:
            reuse_status = "reusable"
        reconciled = ReconciledTestCase(
            test_case_id=test_case_id,
            reuse_status=reuse_status,
            previous_coverage_ids=previous_coverage_ids,
            current_coverage_ids=current_coverage_ids,
            previous_candidate_ids=previous_candidate_ids,
            current_candidate_ids=list(proposed.get("candidate_links", [])) if proposed else previous_candidate_ids,
            preserved_fields=preserved_fields,
            updated_fields=updated_fields,
            review_required_fields=sorted(set(review_fields)),
            reason=reason,
            confidence=confidence,
        )
        if reuse_status == "blocked":
            report.blocked_test_cases.append(reconciled)
        elif reuse_status == "obsolete":
            report.obsolete_test_cases.append(reconciled)
        elif reuse_status == "needs_update":
            report.updated_test_cases.append(reconciled)
        else:
            report.preserved_test_cases.append(reconciled)
        updated_cases.append(_merge_case(previous_case, proposed, current_coverage_ids, generate_updated_test_case_design))
    previous_ids = {str(case.get("test_case_id") or case.get("id") or "") for case in previous_cases}
    for new_case in _new_required_cases(current_design, previous_ids, mapping_by_old):
        report.new_test_case_candidates.append(new_case)
    if report.updated_test_cases:
        report.warnings.append(ReanalysisWarning("stale_expected_value", "Expected observations may be stale after source changes."))
    updated_payload = None
    if generate_updated_test_case_design:
        updated_payload = copy.deepcopy(previous_design)
        updated_payload["test_cases"] = updated_cases
        updated_payload.setdefault("reanalysis", {})["source"] = "updated_by_reanalysis"
        updated_payload = _without_embedded_review_authority(updated_payload)
    return report, updated_payload


def _function_name(previous: dict[str, Any], current: dict[str, Any]) -> str:
    return (
        previous.get("function", {}).get("name")
        or current.get("function", {}).get("name")
        or previous.get("target", {}).get("function")
        or "unknown"
    )


def _changes_by_test(changes: list[Any]) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    for change in changes:
        for test_case_id in getattr(change, "affected_test_case_ids", []):
            result.setdefault(test_case_id, []).append(change)
    return result


def _coverage_ids(test_case: dict[str, Any]) -> list[str]:
    ids = []
    for link in test_case.get("coverage_links", []):
        if isinstance(link, dict) and link.get("coverage_id"):
            ids.append(str(link["coverage_id"]))
    coverage = test_case.get("coverage")
    if isinstance(coverage, str) and coverage and coverage != "review required":
        ids.append(coverage)
    return ids


def _current_cases_by_coverage(current_design: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for case in current_design.get("test_cases", []):
        for coverage_id in _coverage_ids(case):
            result.setdefault(coverage_id, []).append(case)
    return result


def _mapped_coverage_id(old_id: str, mapping_by_old: dict[str, CoverageMapping]) -> str | None:
    mapping = mapping_by_old.get(old_id)
    if mapping is None:
        return old_id
    return mapping.new_coverage_id


def _first_case_for_coverage(current_by_coverage: dict[str, list[dict[str, Any]]], coverage_ids: list[str]) -> dict[str, Any] | None:
    for coverage_id in coverage_ids:
        cases = current_by_coverage.get(coverage_id, [])
        if cases:
            return cases[0]
    return None


def _merge_case(previous: dict[str, Any], proposed: dict[str, Any] | None, current_coverage_ids: list[str], should_update: bool) -> dict[str, Any]:
    merged = copy.deepcopy(previous)
    if not should_update:
        return _without_embedded_review_authority(merged)
    if proposed:
        for key, value in proposed.items():
            if key not in PROTECTED_FIELDS and key != "test_case_id":
                merged[key] = copy.deepcopy(value)
    if current_coverage_ids:
        merged["coverage_links"] = [_remap_coverage_link(link, current_coverage_ids) for link in merged.get("coverage_links", [])]
    return _without_embedded_review_authority(merged)


def _without_embedded_review_authority(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_embedded_review_authority(child)
            for key, child in value.items()
            if str(key).lower() not in _EMBEDDED_REVIEW_AUTHORITY_FIELDS
        }
    if isinstance(value, list):
        return [_without_embedded_review_authority(child) for child in value]
    return copy.deepcopy(value)


def _remap_coverage_link(link: dict[str, Any], current_coverage_ids: list[str]) -> dict[str, Any]:
    updated = copy.deepcopy(link)
    if current_coverage_ids:
        updated["coverage_id"] = current_coverage_ids[0]
    return updated


def _new_required_cases(current_design: dict[str, Any], previous_ids: set[str], mapping_by_old: dict[str, CoverageMapping]) -> list[ReconciledTestCase]:
    mapped_current = {item.new_coverage_id for item in mapping_by_old.values() if item.new_coverage_id}
    candidates: list[ReconciledTestCase] = []
    for case in current_design.get("test_cases", []):
        case_id = str(case.get("test_case_id") or "")
        coverage_ids = _coverage_ids(case)
        if case_id not in previous_ids and any(coverage_id not in mapped_current for coverage_id in coverage_ids):
            candidates.append(
                ReconciledTestCase(
                    test_case_id=case_id,
                    reuse_status="new_required",
                    previous_coverage_ids=[],
                    current_coverage_ids=coverage_ids,
                    previous_candidate_ids=[],
                    current_candidate_ids=list(case.get("candidate_links", [])),
                    preserved_fields=[],
                    updated_fields=[],
                    review_required_fields=["expected_observations", "stub_setups"],
                    reason="New coverage item requires a test case.",
                    confidence="medium",
                )
            )
    return candidates
