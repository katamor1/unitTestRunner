from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from unit_test_runner.review_ids import (
    StableReviewIdRegistry,
    build_function_id,
    semantic_case_id_token,
)

from .identity import signature_sha256
from .models import (
    ArtifactReference,
    FunctionReference,
    SourceReference,
    TestSpec,
    TestSpecContractError,
    materialize_test_spec_containers,
    require_exact_unresolved_case_id_lists,
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
    design_test_cases = _optional_design_list(design_payload, "test_cases")
    design_candidates = _optional_design_list(
        design_payload,
        "additional_case_candidates",
    )
    design_unresolved = _optional_design_list(
        design_payload,
        "unresolved_items",
    )
    design_warnings = _optional_design_list(design_payload, "warnings")
    signature_function = _signature_function(function_signature)
    function_name = signature_function.get("name")
    if type(function_name) is not str:
        raise TypeError("Function name must be an exact string.")
    source_sha = _signature_source_sha(function_signature)
    function_id = build_function_id(source_path, function_name)

    raw_cases = [(False, item) for item in design_test_cases] + [
        (True, item) for item in design_candidates
    ]
    actual_case_by_token = _case_association_index(raw_cases)
    unresolved_items = design_unresolved
    _discard_review_identity(unresolved_items)
    review_by_case: dict[str, list[str]] = defaultdict(list)
    all_review_ids: list[str] = []
    review_registry = StableReviewIdRegistry()
    for item_index, raw_item in enumerate(unresolved_items):
        if not isinstance(raw_item, Mapping):
            raise TypeError("TestSpec unresolved items must be objects.")
        item = dict(raw_item)
        unresolved_items[item_index] = item
        item_kind = _required_string(
            item.get("item_kind"),
            "unresolved item_kind",
        )
        related_case_ids = [
            _canonical_case_reference(
                case_id,
                actual_case_by_token,
            )
            for case_id in _related_case_ids(item)
        ]
        if "related_test_case_ids" in item:
            item["related_test_case_ids"] = related_case_ids
        if not related_case_ids:
            all_review_ids.append(
                review_registry.register(
                    category="expected_result_review",
                    function_id=function_id,
                    case_id=None,
                    semantic_subject_key=item_kind,
                )
            )
        for raw_case_id in related_case_ids:
            case_id = _required_string(raw_case_id, "related test case ID")
            review_id = review_registry.register(
                category="expected_result_review",
                function_id=function_id,
                case_id=case_id,
                semantic_subject_key=item_kind,
            )
            all_review_ids.append(review_id)
            review_by_case[case_id].append(review_id)

    executable: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for already_candidate, raw_case in raw_cases:
        case = dict(raw_case)
        _discard_review_identity(case)
        case_id = _required_string(case.get("test_case_id"), "test case ID")
        legacy_status = case.pop("review_status", None)
        if legacy_status is not None and type(legacy_status) is not str:
            raise TypeError("review_status must be an exact string or null.")
        case_review_ids = list(review_by_case.get(case_id, ()))
        if legacy_status in {"review_required", "candidate"} and not case_review_ids:
            generated_review_id = review_registry.register(
                category="expected_result_review",
                function_id=function_id,
                case_id=case_id,
                semantic_subject_key="test_case_review_required",
            )
            case_review_ids.append(generated_review_id)
            all_review_ids.append(generated_review_id)
        elif legacy_status not in {None, "review_required", "candidate"}:
            raise ValueError(
                f"Generated design contains unsupported review authority for {case_id}: {legacy_status!r}"
            )
        if case_review_ids:
            case["review_item_ids"] = sorted(set(case_review_ids))
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
        generated_from=list(materialize_test_spec_containers(generated_from)),
        generation_policy=dict(design_payload.get("generation_policy") or {}),
        test_cases=executable,
        additional_case_candidates=candidates,
        coverage_summary=dict(design_payload.get("coverage_summary") or {}),
        unresolved_items=unresolved_items,
        warnings=design_warnings,
        review_item_ids=sorted(set(all_review_ids)),
    )
    violations = validate_test_spec(spec)
    if violations:
        raise TestSpecContractError(violations)
    return spec


def test_spec_consumer_payload(spec: TestSpec) -> dict[str, Any]:
    return spec.to_payload()["data"]


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        raise TypeError(f"Unsupported test design type: {type(value)!r}")
    payload = value if isinstance(value, dict) else dict(value)
    require_exact_unresolved_case_id_lists(payload)
    return materialize_test_spec_containers(payload)


def _optional_design_list(
    payload: Mapping[str, Any],
    field_name: str,
) -> list[Any]:
    if field_name not in payload:
        return []
    value = payload[field_name]
    if not isinstance(value, list):
        raise TypeError(f"test design {field_name} must be a list.")
    return value


def _signature_function(value: Mapping[str, Any]) -> Mapping[str, Any]:
    data = value.get("data")
    if isinstance(data, Mapping) and isinstance(data.get("function"), Mapping):
        return data["function"]
    function = value.get("function")
    if not isinstance(function, Mapping):
        raise ValueError("Function signature payload has no function object.")
    return function


def _signature_source_sha(value: Mapping[str, Any]) -> str:
    source = value.get("source")
    if source is not None and not isinstance(source, Mapping):
        raise TypeError("Function signature source must be an object.")
    source_sha = source.get("sha256") if isinstance(source, Mapping) else None
    if source_sha is None or (type(source_sha) is str and not source_sha):
        data = value.get("data")
        nested_source = data.get("source") if isinstance(data, Mapping) else None
        if nested_source is not None and not isinstance(nested_source, Mapping):
            raise TypeError("Function signature source must be an object.")
        source_sha = (
            nested_source.get("sha256")
            if isinstance(nested_source, Mapping)
            else None
        )
    return _required_string(source_sha, "function signature source sha256")


def _has_unresolved_executable_value(case: Mapping[str, Any]) -> bool:
    collections = (
        ("input_assignments", "value_expression"),
        ("state_setups", "value_expression"),
        ("stub_setups", "value_expression"),
        ("expected_observations", "expected_expression"),
    )
    for collection, field in collections:
        items = case.get(collection)
        if items is None:
            continue
        if not isinstance(items, list):
            return True
        for item in items:
            if not isinstance(item, Mapping):
                continue
            if collection == "stub_setups":
                setup_kind = item.get("setup_kind")
                if type(setup_kind) is str and setup_kind in {
                    "call_count_observation",
                    "argument_capture",
                }:
                    continue
                if setup_kind is not None and type(setup_kind) is not str:
                    return True
            value = item.get(field)
            if type(value) is not str:
                return True
            normalized = value.strip().upper()
            if not normalized or normalized.startswith(
                ("TBD", "UNKNOWN", "UNRESOLVED", "TODO")
            ):
                return True
    return False


def _required_string(value: object, field: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact string.")
    if not value:
        raise ValueError(f"{field} must not be empty.")
    if "\x00" in value:
        raise ValueError(f"{field} must not contain NUL.")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValueError(f"{field} must be strict UTF-8.") from error
    return value


def _related_case_ids(item: Mapping[str, Any]) -> list[str]:
    if "related_test_case_ids" not in item:
        return []
    value = item["related_test_case_ids"]
    if type(value) is not list:
        raise TypeError("related_test_case_ids must be an exact list.")
    return [
        _required_string(case_id, "related test case ID")
        for case_id in value
    ]


def _case_association_index(
    raw_cases: list[tuple[bool, Any]],
) -> dict[str, str]:
    actual_case_by_token: dict[str, str] = {}
    for _already_candidate, raw_case in raw_cases:
        case = dict(raw_case)
        case_id = _required_string(case.get("test_case_id"), "test case ID")
        token = semantic_case_id_token(case_id)
        existing = actual_case_by_token.get(token)
        if existing is not None and existing != case_id:
            raise ValueError(
                "Ambiguous test case IDs normalize to one semantic identity: "
                f"{existing!r} and {case_id!r}."
            )
        actual_case_by_token[token] = case_id
    return actual_case_by_token


def _canonical_case_reference(
    case_id: str,
    actual_case_by_token: Mapping[str, str],
) -> str:
    token = semantic_case_id_token(case_id)
    return actual_case_by_token.get(token, case_id)


def _discard_review_identity(value: Any) -> None:
    if isinstance(value, dict):
        value.pop("review_item_id", None)
        value.pop("review_item_ids", None)
        for child in value.values():
            _discard_review_identity(child)
    elif isinstance(value, list):
        for child in value:
            _discard_review_identity(child)
