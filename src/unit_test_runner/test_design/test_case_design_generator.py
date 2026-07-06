from __future__ import annotations

from pathlib import Path
from typing import Any

from .candidate_selector import fallback_input_candidates, select_candidates_for_coverage
from .coverage_case_mapper import case_kind_for_coverage, priority_for_coverage, title_for_coverage
from .expected_observation_builder import build_expected_observations
from .input_assignment_builder import build_input_assignments
from .state_setup_builder import build_state_setups
from .stub_setup_builder import build_stub_setups
from .test_case_models import (
    CoverageTestDesignSummary,
    TestCaseDesign,
    TestCaseDesignReport,
    TestCaseGenerationPolicy,
    TestCoverageLink,
    TestExecutionStep,
    TestPrecondition,
)


def generate_test_case_design(
    function_signature: Any,
    global_access: Any,
    call_report: Any,
    coverage_design: Any,
    boundary_candidates: Any,
    policy: TestCaseGenerationPolicy | None = None,
) -> TestCaseDesignReport:
    policy = policy or TestCaseGenerationPolicy()
    signature_payload = _as_dict(function_signature)
    global_payload = _as_dict(global_access)
    call_payload = _as_dict(call_report)
    coverage_payload = _as_dict(coverage_design)
    boundary_payload = _as_dict(boundary_candidates)
    function = signature_payload["function"]
    source = signature_payload.get("source", {})
    cases: list[TestCaseDesign] = []
    additional_cases: list[TestCaseDesign] = []
    unresolved = []
    warnings = []
    coverage_to_cases: dict[str, list[str]] = {}

    fallback_candidates = fallback_input_candidates(boundary_payload, 1000)
    for index, coverage_item in enumerate(coverage_payload.get("coverage_items", []), start=1):
        coverage_id = coverage_item["coverage_id"]
        selected, additional = select_candidates_for_coverage(boundary_payload, coverage_id, policy.max_cases_per_coverage_item)
        test_case_id = f"TC_{function['name']}_{index:03d}"
        related_candidates = selected + additional
        inputs, input_candidate_ids = build_input_assignments(signature_payload, selected, fallback_candidates)
        states, state_warnings, state_candidate_ids = build_state_setups(related_candidates, test_case_id, coverage_id)
        stubs, stub_warnings, stub_candidate_ids = build_stub_setups(related_candidates, call_payload, coverage_item, test_case_id)
        observations, observation_warnings, unresolved_items = build_expected_observations(test_case_id, coverage_item, global_payload, signature_payload)
        candidate_links = input_candidate_ids + state_candidate_ids + stub_candidate_ids
        case = TestCaseDesign(
            test_case_id=test_case_id,
            title=title_for_coverage(function["name"], coverage_item),
            target_function=function["name"],
            purpose=coverage_item.get("purpose", f"Cover {coverage_id}"),
            priority=priority_for_coverage(coverage_item.get("coverage_type", "")),
            case_kind=case_kind_for_coverage(coverage_item.get("coverage_type", "")),
            preconditions=_preconditions(function["name"], bool(stubs)),
            input_assignments=inputs,
            state_setups=states,
            stub_setups=stubs,
            execution_steps=_execution_steps(function["name"]),
            expected_observations=observations,
            coverage_links=[
                TestCoverageLink(
                    coverage_id=coverage_id,
                    coverage_type=coverage_item.get("coverage_type", "unknown"),
                    target_id=coverage_item.get("target_id", ""),
                    intended_value=coverage_item.get("condition_value"),
                    link_reason="one test design case generated for coverage item",
                    confidence=coverage_item.get("confidence", "medium"),
                )
            ],
            candidate_links=candidate_links,
            confidence=_case_confidence(coverage_item, selected),
            warnings=state_warnings + stub_warnings + observation_warnings,
        )
        cases.append(case)
        unresolved.extend(unresolved_items)
        warnings.extend(state_warnings + stub_warnings + observation_warnings)
        coverage_to_cases[coverage_id] = [test_case_id]
        if policy.include_additional_candidates:
            additional_cases.extend(_additional_candidate_cases(function["name"], coverage_item, additional, len(additional_cases)))

    coverage_ids = [item["coverage_id"] for item in coverage_payload.get("coverage_items", [])]
    uncovered = [coverage_id for coverage_id in coverage_ids if coverage_id not in coverage_to_cases]
    summary = CoverageTestDesignSummary(len(coverage_ids), len(coverage_ids) - len(uncovered), uncovered, coverage_to_cases)
    status = "generated" if cases and not uncovered else ("partial" if cases else "insufficient_information")
    return TestCaseDesignReport(
        source_path=Path(source.get("path") or ""),
        source_sha256=source.get("sha256") or "",
        function_name=function["name"],
        status=status,
        generation_policy=policy,
        test_cases=cases,
        additional_case_candidates=additional_cases,
        coverage_summary=summary,
        unresolved_items=unresolved,
        warnings=warnings,
    )


def generate_test_case_design_from_payloads(
    function_signature: dict,
    global_access: dict,
    call_report: dict,
    coverage_design: dict,
    boundary_candidates: dict,
    policy: TestCaseGenerationPolicy | None = None,
) -> TestCaseDesignReport:
    return generate_test_case_design(function_signature, global_access, call_report, coverage_design, boundary_candidates, policy)


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    return value.to_dict()


def _preconditions(function_name: str, has_stubs: bool) -> list[TestPrecondition]:
    result = [
        TestPrecondition("VC6 target configuration is selected.", "build_context", True),
        TestPrecondition(f"Target function {function_name} is callable from the harness skeleton.", "function_signature", True),
    ]
    if has_stubs:
        result.append(TestPrecondition("Required stubs are configurable before function call.", "call_report", True))
    return result


def _execution_steps(function_name: str) -> list[TestExecutionStep]:
    return [
        TestExecutionStep(1, "reset_stubs", "Reset generated stub state.", True),
        TestExecutionStep(2, "setup_state", "Apply input assignments, globals, and stub settings.", True),
        TestExecutionStep(3, "call_function", f"Call {function_name} with designed inputs.", True),
        TestExecutionStep(4, "observe_results", "Observe return value, state changes, and stub calls.", True),
    ]


def _case_confidence(coverage_item: dict, selected: list[dict]) -> str:
    ranks = {"high": 0, "medium": 1, "low": 2}
    values = [coverage_item.get("confidence", "medium")] + [candidate.get("confidence", "medium") for candidate in selected]
    worst = max(values, key=lambda item: ranks.get(item, 3))
    return worst


def _additional_candidate_cases(function_name: str, coverage_item: dict, candidates: list[dict], start_index: int) -> list[TestCaseDesign]:
    result = []
    for offset, candidate in enumerate(candidates, start=1):
        candidate_id = candidate.get("candidate_id", f"CAND_{offset}")
        test_case_id = f"TC_{function_name}_ADD_{start_index + offset:03d}"
        result.append(
            TestCaseDesign(
                test_case_id=test_case_id,
                title=f"{function_name}: additional candidate {candidate_id}",
                target_function=function_name,
                purpose=f"Additional candidate for {coverage_item.get('coverage_id')}: {candidate.get('purpose', '')}",
                priority="low",
                case_kind=case_kind_for_coverage(coverage_item.get("coverage_type", "")),
                candidate_links=[candidate_id],
                review_status="candidate",
                confidence=candidate.get("confidence", "medium"),
            )
        )
    return result
