from __future__ import annotations

from typing import Any

from .execution_models import ExecutionReviewItem, TestCaseExecutionResult, TestExecutionWarning


def map_results_to_test_design(
    parsed_output: Any | None,
    test_case_design: dict[str, Any],
    treat_placeholder_as_inconclusive: bool = True,
) -> tuple[list[TestCaseExecutionResult], list[ExecutionReviewItem]]:
    parsed_cases = {}
    if parsed_output is not None:
        parsed_cases = {case.test_case_id: case for case in getattr(parsed_output, "case_results", []) if case.test_case_id}
    results: list[TestCaseExecutionResult] = []
    review_items: list[ExecutionReviewItem] = []
    for case in test_case_design.get("test_cases", []):
        test_case_id = case.get("test_case_id")
        parsed_case = parsed_cases.get(test_case_id)
        coverage = [link.get("coverage_id", "") for link in case.get("coverage_links", []) if link.get("coverage_id")]
        placeholder = _case_has_placeholder(case)
        if parsed_case:
            status = parsed_case.status
            assertions = parsed_case.assertions
            evidence = parsed_case.evidence or "runner output observed"
        else:
            status = "not_found_in_output"
            assertions = []
            evidence = "test case was not found in runner output" if parsed_output is not None else "test execution was not run"
        review_required = case.get("review_status") == "review_required" or placeholder
        warnings: list[TestExecutionWarning] = []
        if placeholder:
            warnings.append(TestExecutionWarning("placeholder_detected", "TBD expected value remains in generated test.", related_test_case_id=test_case_id))
            review_items.append(
                ExecutionReviewItem(
                    f"REVIEW_EXPECTED_{len(review_items) + 1:03d}",
                    "placeholder_expected_value",
                    test_case_id,
                    "Expected observation is not finalized.",
                    "Review function specification and replace TBD expected value.",
                    "warning",
                )
            )
            if treat_placeholder_as_inconclusive and status in {"passed", "not_found_in_output"}:
                status = "inconclusive"
        results.append(
            TestCaseExecutionResult(
                test_case_id=test_case_id,
                generated_function_name=None,
                status=status,
                exit_related=False,
                assertions=assertions,
                related_coverage_ids=coverage,
                review_required=review_required,
                evidence=evidence,
                warnings=warnings,
            )
        )
    if parsed_output is not None:
        design_ids = {case.get("test_case_id") for case in test_case_design.get("test_cases", [])}
        for test_case_id in parsed_cases:
            if test_case_id not in design_ids:
                review_items.append(
                    ExecutionReviewItem(
                        f"REVIEW_UNMAPPED_{len(review_items) + 1:03d}",
                        "unmapped_test_output",
                        test_case_id,
                        "Runner output contains a test case that is not present in the test design.",
                        "Review runner generation and test case design synchronization.",
                        "warning",
                    )
                )
    return results, review_items


def _case_has_placeholder(case: dict[str, Any]) -> bool:
    if case.get("review_status") == "review_required":
        return True
    for observation in case.get("expected_observations", []):
        expected = observation.get("expected_expression")
        if expected is None or str(expected).startswith("TBD"):
            return True
    return False
