from __future__ import annotations

from .test_case_models import ExpectedObservation, TestCaseDraftWarning, UnresolvedTestDesignItem


def build_expected_observations(test_case_id: str, coverage_item: dict) -> tuple[list[ExpectedObservation], list[TestCaseDraftWarning], list[UnresolvedTestDesignItem]]:
    coverage_id = coverage_item.get("coverage_id", "")
    observations = [
        ExpectedObservation(
            observation_kind="return_value",
            target_name="return",
            expected_expression="TBD_EXPECTED_RETURN",
            source="placeholder",
            review_required=True,
            confidence="low",
            note="Expected return must be reviewed against the function specification.",
        ),
        ExpectedObservation(
            observation_kind="coverage_target",
            target_name=coverage_id,
            expected_expression="covered_by_design",
            source="coverage_design",
            review_required=True,
            confidence=coverage_item.get("confidence", "medium"),
            note=None,
        ),
    ]
    warning = TestCaseDraftWarning(
        "expected_result_not_determined",
        "Expected return value is a review placeholder.",
        related_test_case_id=test_case_id,
        related_coverage_id=coverage_id,
    )
    unresolved = UnresolvedTestDesignItem(
        item_id=f"UNRES_{test_case_id}_RET",
        item_kind="expected_return_unknown",
        description="Expected return value must be reviewed from specification.",
        related_test_case_ids=[test_case_id],
        reason="Static analysis does not determine final expected result.",
        suggested_action="Review function specification and source behavior.",
    )
    return observations, [warning], [unresolved]
