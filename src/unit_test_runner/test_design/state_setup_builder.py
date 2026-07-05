from __future__ import annotations

from .test_case_models import TestCaseDesignWarning, TestStateSetup


def build_state_setups(selected_candidates: list[dict], test_case_id: str, coverage_id: str) -> tuple[list[TestStateSetup], list[TestCaseDesignWarning], list[str]]:
    setups: list[TestStateSetup] = []
    warnings: list[TestCaseDesignWarning] = []
    candidate_ids: list[str] = []
    for candidate in selected_candidates:
        if candidate.get("_candidate_collection") != "state_candidates":
            continue
        scope = candidate.get("scope", "unknown")
        setup_hint = "direct_assignment"
        if scope == "file_static":
            setup_hint = "not_directly_accessible"
            warnings.append(
                TestCaseDesignWarning(
                    "file_static_setup_requires_wrapper",
                    f"File static state may require a wrapper or initialization path: {candidate.get('variable_name')}",
                    related_test_case_id=test_case_id,
                    related_coverage_id=coverage_id,
                )
            )
        setups.append(
            TestStateSetup(
                variable_name=candidate.get("variable_name", "unknown"),
                scope=scope,
                value_expression=candidate.get("value_expression", "TBD_STATE"),
                setup_method_hint=setup_hint,
                source_candidate_id=candidate.get("candidate_id"),
                review_required=candidate.get("review_required", True),
                confidence=candidate.get("confidence", "medium"),
            )
        )
        if candidate.get("candidate_id"):
            candidate_ids.append(candidate["candidate_id"])
    return setups, warnings, candidate_ids
