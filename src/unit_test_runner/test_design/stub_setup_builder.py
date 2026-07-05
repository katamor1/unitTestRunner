from __future__ import annotations

from .test_case_models import TestCaseDraftWarning, TestStubSetup


def build_stub_setups(selected_candidates: list[dict], call_report: dict, coverage_item: dict, test_case_id: str) -> tuple[list[TestStubSetup], list[TestCaseDraftWarning], list[str]]:
    setups: list[TestStubSetup] = []
    warnings: list[TestCaseDraftWarning] = []
    candidate_ids: list[str] = []
    for candidate in selected_candidates:
        if candidate.get("_candidate_collection") != "stub_return_candidates":
            continue
        setups.append(
            TestStubSetup(
                stub_name=candidate.get("call_name", "unknown"),
                setup_kind="return_value",
                value_expression=candidate.get("value_expression"),
                call_behavior=None,
                source_candidate_id=candidate.get("candidate_id"),
                related_call_id=candidate.get("related_call_id"),
                review_required=candidate.get("review_required", True),
                confidence=candidate.get("confidence", "medium"),
            )
        )
        if candidate.get("candidate_id"):
            candidate_ids.append(candidate["candidate_id"])
    related_calls = set(coverage_item.get("related_calls", []))
    for stub in call_report.get("stub_candidates", []):
        if related_calls and stub.get("name") not in related_calls:
            continue
        if stub.get("call_count", 0) > 0:
            setups.append(
                TestStubSetup(
                    stub_name=stub.get("name", "unknown"),
                    setup_kind="call_count_observation",
                    value_expression=None,
                    call_behavior="observe call count",
                    source_candidate_id=None,
                    related_call_id=(stub.get("related_calls") or [None])[0],
                    review_required=True,
                    confidence=stub.get("confidence", "medium"),
                )
            )
        if stub.get("argument_capture_needed"):
            setups.append(
                TestStubSetup(
                    stub_name=stub.get("name", "unknown"),
                    setup_kind="argument_capture",
                    value_expression=None,
                    call_behavior="capture arguments",
                    source_candidate_id=None,
                    related_call_id=(stub.get("related_calls") or [None])[0],
                    review_required=True,
                    confidence=stub.get("confidence", "medium"),
                )
            )
        warnings.append(
            TestCaseDraftWarning(
                "stub_required_but_not_generated",
                f"Stub behavior must be reviewed for {stub.get('name', 'unknown')}.",
                related_test_case_id=test_case_id,
                related_coverage_id=coverage_item.get("coverage_id"),
            )
        )
    return setups, warnings, candidate_ids
