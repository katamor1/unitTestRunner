from __future__ import annotations

from typing import Any

from .dossier_models import DossierReviewItem, DossierUnresolvedItem


def build_review_items(payloads: dict[str, dict[str, Any]]) -> tuple[list[DossierReviewItem], list[DossierUnresolvedItem]]:
    review_items: list[DossierReviewItem] = []
    unresolved: list[DossierUnresolvedItem] = []
    _from_test_case_draft(payloads.get("test_case_draft", {}), review_items, unresolved)
    _from_harness(payloads.get("harness_skeleton_report", {}), review_items, unresolved)
    _from_completion(payloads.get("build_completion_plan", {}), review_items, unresolved)
    _from_execution(payloads.get("test_execution_report", {}), review_items, unresolved)
    if not review_items:
        review_items.append(
            DossierReviewItem(
                "REVIEW_FINAL_001",
                "evidence_review",
                "Review generated function dossier",
                "Confirm generated analysis, test design, build status, and evidence before approval.",
                severity="info",
                suggested_reviewer_role="unit_test_lead",
            )
        )
    if not unresolved:
        unresolved.append(
            DossierUnresolvedItem(
                "UNRESOLVED_REVIEW_001",
                "Step 17",
                "manual_final_review",
                "Final human review is still required.",
                "Dossier generation is not an approval decision.",
                suggested_action="Review function_dossier.md and mark checklist items outside this tool.",
            )
        )
    return review_items, unresolved


def _from_test_case_draft(payload: dict[str, Any], review_items: list[DossierReviewItem], unresolved: list[DossierUnresolvedItem]) -> None:
    for case in payload.get("test_cases", []):
        test_case_id = case.get("test_case_id") or case.get("id")
        needs_review = case.get("review_status") == "review_required"
        has_tbd = any(str(obs.get("expected_expression", "")).startswith("TBD") or obs.get("expected_expression") is None for obs in case.get("expected_observations", []))
        if needs_review or has_tbd:
            item_id = f"UNRESOLVED_EXPECTED_{len(unresolved) + 1:03d}"
            unresolved.append(
                DossierUnresolvedItem(
                    item_id,
                    "Step 12",
                    "expected_result_unknown",
                    f"Expected result requires review for {test_case_id}.",
                    "The generated test cannot be treated as approved until expected values are reviewed.",
                    ["test_case_draft"],
                    [test_case_id] if test_case_id else [],
                    "Review function specification and replace TBD expected values.",
                )
            )
            review_items.append(
                DossierReviewItem(
                    f"REVIEW_EXPECTED_{len(review_items) + 1:03d}",
                    "expected_result_review",
                    "Review expected result",
                    f"Confirm expected observations for {test_case_id}.",
                    ["test_case_draft"],
                    [test_case_id] if test_case_id else [],
                )
            )


def _from_harness(payload: dict[str, Any], review_items: list[DossierReviewItem], unresolved: list[DossierUnresolvedItem]) -> None:
    for placeholder in payload.get("unresolved_placeholders", []):
        test_case_id = placeholder.get("related_test_case_id")
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_PLACEHOLDER_{len(unresolved) + 1:03d}",
                "Step 13",
                "harness_placeholder",
                f"Placeholder remains: {placeholder.get('name')}",
                "Generated harness needs manual completion.",
                ["harness_skeleton_report"],
                [test_case_id] if test_case_id else [],
                placeholder.get("suggested_action", "Review generated harness placeholders."),
            )
        )
        review_items.append(DossierReviewItem(f"REVIEW_HARNESS_{len(review_items) + 1:03d}", "stub_behavior_review", "Review harness placeholder", str(placeholder.get("name")), ["harness_skeleton_report"], [test_case_id] if test_case_id else []))


def _from_completion(payload: dict[str, Any], review_items: list[DossierReviewItem], unresolved: list[DossierUnresolvedItem]) -> None:
    for manual in payload.get("manual_action_items", []):
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_BUILD_{len(unresolved) + 1:03d}",
                "Step 15",
                manual.get("item_kind", "manual_action"),
                manual.get("description", "Manual build completion action remains."),
                manual.get("reason", "Build completion cannot be fully automated."),
                ["build_completion_plan"],
                [],
                manual.get("suggested_action", "Review build completion plan."),
                blocks_readiness=False,
            )
        )
        review_items.append(DossierReviewItem(f"REVIEW_BUILD_{len(review_items) + 1:03d}", "build_review", "Review build completion item", manual.get("description", ""), ["build_completion_plan"]))


def _from_execution(payload: dict[str, Any], review_items: list[DossierReviewItem], unresolved: list[DossierUnresolvedItem]) -> None:
    status = payload.get("function", {}).get("status") or payload.get("status")
    if status in {"inconclusive", "failed", "blocked", "timeout", "not_run"}:
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_EXEC_{len(unresolved) + 1:03d}",
                "Step 16",
                "execution_inconclusive",
                f"Test execution status is {status}.",
                "Evidence is not a final pass result.",
                ["test_execution_report"],
                [],
                "Resolve placeholders or rerun tests after review.",
            )
        )
        review_items.append(DossierReviewItem(f"REVIEW_EXEC_{len(review_items) + 1:03d}", "execution_review", "Review execution evidence", f"Execution status is {status}.", ["test_execution_report"]))
