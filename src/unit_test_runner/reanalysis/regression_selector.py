from __future__ import annotations

from .reanalysis_models import RegressionSelection, RegressionTestCase, TestCaseReconciliationReport


def select_regression_tests(function_name: str, reconciliation: TestCaseReconciliationReport) -> RegressionSelection:
    selection = RegressionSelection(function_name=function_name, status="completed")
    for case in reconciliation.updated_test_cases:
        selection.selected_test_cases.append(
            RegressionTestCase(
                test_case_id=case.test_case_id,
                selection_status="selected",
                priority="high" if case.reuse_status in ("needs_update", "blocked") else "medium",
                reasons=[case.reason],
                related_changes=case.current_coverage_ids,
                review_required=bool(case.review_required_fields),
            )
        )
    for case in reconciliation.preserved_test_cases:
        selection.skipped_test_cases.append(
            RegressionTestCase(
                test_case_id=case.test_case_id,
                selection_status="skipped_no_impact",
                priority="low",
                reasons=[case.reason],
                related_changes=case.current_coverage_ids,
                review_required=False,
            )
        )
    for case in reconciliation.obsolete_test_cases:
        selection.skipped_test_cases.append(
            RegressionTestCase(
                test_case_id=case.test_case_id,
                selection_status="skipped_no_impact",
                priority="low",
                reasons=[case.reason],
                related_changes=case.previous_coverage_ids,
                review_required=True,
            )
        )
    for case in reconciliation.blocked_test_cases:
        selection.blocked_test_cases.append(
            RegressionTestCase(
                test_case_id=case.test_case_id,
                selection_status="blocked",
                priority="high",
                reasons=[case.reason],
                related_changes=case.previous_coverage_ids,
                review_required=True,
            )
        )
    for case in reconciliation.new_test_case_candidates:
        selection.new_required_test_cases.append(
            RegressionTestCase(
                test_case_id=case.test_case_id,
                selection_status="new_required",
                priority="high",
                reasons=[case.reason],
                related_changes=case.current_coverage_ids,
                review_required=True,
            )
        )
    selection.selection_reason_summary = (
        f"selected={len(selection.selected_test_cases)}, "
        f"skipped={len(selection.skipped_test_cases)}, "
        f"new_required={len(selection.new_required_test_cases)}, "
        f"blocked={len(selection.blocked_test_cases)}"
    )
    return selection
