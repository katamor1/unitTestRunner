from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Mapping

from unit_test_runner.review_ids import StableReviewIdRegistry

from .identity import signature_sha256, stable_function_id
from .models import (
    ArtifactReference,
    FunctionReference,
    SourceReference,
    TestSpec,
    TestSpecContractError,
    validate_test_spec,
)


def create_test_spec_from_design(
    design: Any,
    function_signature: Mapping[str, Any],
    *,
    source_path: str,
    generated_from: list[ArtifactReference],
    revision: int = 1,
) -> TestSpec:
    design_payload = _payload(design)
    signature_function = _signature_function(function_signature)
    function_name = str(signature_function.get("name") or "")
    source_sha = str((function_signature.get("source") or {}).get("sha256") or "")
    if not source_sha:
        signature_data = function_signature.get("data")
        if isinstance(signature_data, Mapping):
            source_sha = str((signature_data.get("source") or {}).get("sha256") or "")
    function_id = stable_function_id(source_path, function_name)

    unresolved_items = copy.deepcopy(list(design_payload.get("unresolved_items") or []))
    review_by_case: dict[str, list[str]] = defaultdict(list)
    all_review_ids: list[str] = []
    review_registry = StableReviewIdRegistry()
    for item in unresolved_items:
        if not isinstance(item, dict) or not item.get("item_id"):
            continue
        semantic_subject_key = str(item["item_id"])
        category = str(item.get("item_kind") or "test_spec_review")
        related_case_ids = [
            str(case_id)
            for case_id in item.get("related_test_case_ids") or []
            if str(case_id).strip()
        ]
        semantic_case_ids: list[str | None] = related_case_ids or [None]
        item_review_ids: list[str] = []
        for semantic_case_id in semantic_case_ids:
            review_id = review_registry.register(
                category=category,
                function_id=function_id,
                case_id=semantic_case_id,
                semantic_subject_key=semantic_subject_key,
            )
            item_review_ids.append(review_id)
            all_review_ids.append(review_id)
            if semantic_case_id is not None:
                review_by_case[semantic_case_id].append(review_id)
        item["review_item_ids"] = list(dict.fromkeys(item_review_ids))

    executable: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    raw_cases = [
        (False, item) for item in design_payload.get("test_cases") or []
    ] + [
        (True, item)
        for item in design_payload.get("additional_case_candidates") or []
    ]
    for already_candidate, raw_case in raw_cases:
        case = copy.deepcopy(dict(raw_case))
        case_id = str(case.get("test_case_id") or "")
        legacy_status = case.pop("review_status", None)
        case_review_ids = list(review_by_case.get(case_id, ()))
        if legacy_status in {"review_required", "candidate"} and not case_review_ids:
            generated_review_id = review_registry.register(
                category="generated_case_review",
                function_id=function_id,
                case_id=case_id or None,
                semantic_subject_key="legacy/review-required",
            )
            case_review_ids.append(generated_review_id)
            all_review_ids.append(generated_review_id)
        elif legacy_status not in {None, "review_required", "candidate"}:
            raise ValueError(
                f"Generated design contains unsupported review authority for {case_id}: {legacy_status!r}"
            )
        if case_review_ids:
            case["review_item_ids"] = list(dict.fromkeys(case_review_ids))
        if already_candidate or _has_unresolved_executable_value(case):
            candidates.append(case)
        else:
            executable.append(case)

    spec = TestSpec(
        spec_id=f"spec-{function_id.removeprefix('fn_')}",
        revision=revision,
        source=SourceReference(source_path, source_sha),
        function=FunctionReference(
            function_id=function_id,
            name=function_name,
            signature_sha256=signature_sha256(function_signature),
        ),
        generated_from=list(generated_from),
        generation_policy=copy.deepcopy(dict(design_payload.get("generation_policy") or {})),
        test_cases=executable,
        additional_case_candidates=candidates,
        coverage_summary=copy.deepcopy(dict(design_payload.get("coverage_summary") or {})),
        unresolved_items=unresolved_items,
        warnings=copy.deepcopy(list(design_payload.get("warnings") or [])),
        review_item_ids=list(dict.fromkeys(all_review_ids)),
    )
    violations = validate_test_spec(spec)
    if violations:
        raise TestSpecContractError(violations)
    return spec


def test_spec_consumer_payload(spec: TestSpec) -> dict[str, Any]:
    return copy.deepcopy(spec.to_payload()["data"])


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        raise TypeError(f"Unsupported test design type: {type(value)!r}")
    return copy.deepcopy(dict(value))


def _signature_function(value: Mapping[str, Any]) -> Mapping[str, Any]:
    data = value.get("data")
    if isinstance(data, Mapping) and isinstance(data.get("function"), Mapping):
        return data["function"]
    function = value.get("function")
    if not isinstance(function, Mapping):
        raise ValueError("Function signature payload has no function object.")
    return function


def _has_unresolved_executable_value(case: Mapping[str, Any]) -> bool:
    collections = (
        ("input_assignments", "value_expression"),
        ("state_setups", "value_expression"),
        ("stub_setups", "value_expression"),
        ("expected_observations", "expected_expression"),
    )
    for collection, field in collections:
        for item in case.get(collection) or []:
            if not isinstance(item, Mapping):
                continue
            if collection == "stub_setups" and item.get("setup_kind") in {
                "call_count_observation",
                "argument_capture",
            }:
                continue
            value = item.get(field)
            if value is None or not str(value).strip() or str(value).upper().startswith(
                ("TBD", "UNKNOWN", "UNRESOLVED", "TODO")
            ):
                return True
    return False
