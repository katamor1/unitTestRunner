from __future__ import annotations

import hashlib
import re

from .boundary_models import (
    BoundaryEquivalenceReport,
    BoundaryGroup,
    CandidateCoverageLink,
    EquivalenceClass,
    InputValueCandidate,
    StateValueCandidate,
    StubReturnCandidate,
)
from .call_models import CallReport
from .coverage_models import CoverageDesignReport
from .global_access_models import GlobalAccessReport
from .signature_models import FunctionSignature


def generate_boundary_equivalence_candidates(
    function_signature: FunctionSignature,
    global_access: GlobalAccessReport,
    call_report: CallReport,
    coverage_design: CoverageDesignReport,
) -> BoundaryEquivalenceReport:
    input_candidates: list[InputValueCandidate] = []
    state_candidates: list[StateValueCandidate] = []
    stub_candidates: list[StubReturnCandidate] = []
    equivalence_classes: list[EquivalenceClass] = []
    boundary_groups: list[BoundaryGroup] = []

    input_candidates.extend(_type_based_candidates(function_signature, equivalence_classes))
    for condition in coverage_design.condition_expressions:
        coverage_ids = _coverage_for_condition(condition.condition_id, coverage_design)
        generated, groups = _comparison_candidates(condition.condition_id, condition.raw, coverage_ids)
        input_candidates.extend(generated)
        boundary_groups.extend(groups)
        input_candidates.extend(_null_condition_candidates(condition.condition_id, condition.raw, coverage_ids))
        stub_candidates.extend(_stub_return_candidates(condition.condition_id, condition.raw, coverage_ids, call_report))
        state_candidates.extend(_state_candidates(condition.condition_id, condition.raw, coverage_ids, global_access))

    input_candidates.extend(_switch_candidates(coverage_design))
    input_candidates.extend(_loop_candidates(coverage_design))
    deduped_input_candidates = _dedupe_inputs(input_candidates)
    links = _coverage_links(
        deduped_input_candidates,
        state_candidates,
        stub_candidates,
        coverage_design,
    )
    status = "generated" if deduped_input_candidates or state_candidates or stub_candidates else "insufficient_information"
    return BoundaryEquivalenceReport(
        source_path=function_signature.source_path,
        source_sha256=function_signature.source_sha256,
        function_name=function_signature.function_name,
        status=status,
        input_candidates=deduped_input_candidates,
        state_candidates=state_candidates,
        stub_return_candidates=stub_candidates,
        equivalence_classes=equivalence_classes,
        boundary_groups=boundary_groups,
        coverage_links=links,
        warnings=[],
    )


def _type_based_candidates(signature: FunctionSignature, classes: list[EquivalenceClass]) -> list[InputValueCandidate]:
    candidates: list[InputValueCandidate] = []
    for parameter in signature.parameters:
        if not parameter.name:
            continue
        type_info = parameter.type_info
        if type_info.pointer_level or type_info.is_array:
            values = [("NULL", "null", "null pointer candidate")]
            if type_info.is_array:
                values.extend([("empty_array", "zero", "empty array candidate"), ("one_element_array", "one", "single element array candidate"), ("many_elements_array", "many", "multi element array candidate")])
            elif "const" in type_info.qualifiers:
                values.append(("valid_readable_object", "non_null", "valid readable object candidate"))
            else:
                values.append(("valid_writable_object", "non_null", "valid writable object candidate"))
            for value, kind, purpose in values:
                candidates.append(_input(parameter.name, "parameter", value, kind, "type", None, [], purpose, parameter.raw, "medium"))
            classes.append(EquivalenceClass(f"EQ_{parameter.name}_pointer", parameter.name, "parameter", "pointer_validity", [value for value, _kind, _purpose in values], "Pointer or array validity classes.", [], [], "medium", True))
        elif type_info.base_type and "unsigned" in type_info.base_type:
            for value, kind in [("0", "zero"), ("1", "one"), ("UINT_MAX", "boundary_at")]:
                candidates.append(_input(parameter.name, "parameter", value, kind, "type", None, [], "unsigned scalar representative", parameter.raw, "low"))
        elif type_info.base_type and any(word in type_info.base_type for word in ("int", "short", "long", "char")):
            for value, kind in [("-1", "invalid_equivalence"), ("0", "zero"), ("1", "one")]:
                candidates.append(_input(parameter.name, "parameter", value, kind, "type", None, [], "signed scalar representative", parameter.raw, "low"))
    return candidates


def _comparison_candidates(condition_id: str, raw: str, coverage_ids: list[str]) -> tuple[list[InputValueCandidate], list[BoundaryGroup]]:
    candidates: list[InputValueCandidate] = []
    groups: list[BoundaryGroup] = []
    for match in re.finditer(r"(?P<left>[A-Za-z_]\w*(?:\s*\([^)]*\))?)\s*(?P<op><=|>=|<|>|==|!=)\s*(?P<right>[A-Za-z_]\w*|-?\d+|NULL)", raw):
        left = match.group("left").strip()
        operator = match.group("op")
        right = match.group("right").strip()
        if "(" in left:
            continue
        if right == "NULL":
            continue
        target_kind = "parameter"
        if operator in {"<", "<=", ">", ">=", "=="}:
            expressions = _around(right)
            kind_names = ["boundary_below", "boundary_at", "boundary_above"]
        else:
            expressions = [right, f"{right} other"]
            kind_names = ["enum_value", "invalid_equivalence"]
        ids = []
        for expression, kind in zip(expressions, kind_names):
            candidate = _input(left, target_kind, expression, kind, "condition", condition_id, coverage_ids, f"exercise comparison {left} {operator} {right}", raw, "high")
            candidates.append(candidate)
            ids.append(candidate.candidate_id)
        groups.append(BoundaryGroup(f"BND_{condition_id}_{left}_{len(groups) + 1}", left, right, operator, ids, condition_id, "high", True))
    return candidates, groups


def _null_condition_candidates(condition_id: str, raw: str, coverage_ids: list[str]) -> list[InputValueCandidate]:
    candidates: list[InputValueCandidate] = []
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*(==|!=)\s*(NULL|0)\b", raw):
        target = match.group(1)
        for value, kind in [("NULL", "null"), ("valid_pointer", "non_null")]:
            candidates.append(_input(target, "parameter", value, kind, "condition", condition_id, coverage_ids, "exercise NULL check", raw, "high"))
    return candidates


def _switch_candidates(coverage: CoverageDesignReport) -> list[InputValueCandidate]:
    candidates: list[InputValueCandidate] = []
    for switch in coverage.switches:
        target = switch.expression.raw
        coverage_ids = [item.coverage_id for item in coverage.coverage_items if item.target_id == switch.switch_id]
        for case in switch.cases:
            if case.label_kind == "default":
                candidates.append(_input(target, "parameter", "case labels other than listed values", "default_case_value", "switch", switch.expression.condition_id, coverage_ids, "reach switch default", case.label_raw, "medium"))
            else:
                candidates.append(_input(target, "parameter", case.label_raw, "enum_value", "switch", switch.expression.condition_id, coverage_ids, "reach switch case", case.label_raw, "high"))
    return candidates


def _loop_candidates(coverage: CoverageDesignReport) -> list[InputValueCandidate]:
    candidates: list[InputValueCandidate] = []
    for loop in coverage.loops:
        target = loop.condition.related_variables[-1] if loop.condition and loop.condition.related_variables else "loop_count"
        coverage_ids = [item.coverage_id for item in coverage.coverage_items if item.target_id == loop.loop_id]
        for value, kind in [("0", "zero"), ("1", "one"), ("2", "many")]:
            candidates.append(_input(target, "parameter", value, kind, "loop", loop.condition.condition_id if loop.condition else None, coverage_ids, f"exercise {loop.kind} loop {kind}", loop.condition.raw if loop.condition else loop.kind, "medium"))
    return candidates


def _state_candidates(condition_id: str, raw: str, coverage_ids: list[str], global_access: GlobalAccessReport) -> list[StateValueCandidate]:
    candidates: list[StateValueCandidate] = []
    for declaration in global_access.file_scope_declarations:
        if not re.search(rf"\b{re.escape(declaration.name)}\b", raw):
            continue
        values = ["0"]
        for _operator, right in re.findall(rf"\b{re.escape(declaration.name)}\b\s*(==|!=|<=|>=|<|>)\s*([A-Za-z_]\w*|-?\d+)", raw):
            values.append(right)
        for value in values:
            candidates.append(
                StateValueCandidate(
                    candidate_id=_candidate_id(
                        "STATE",
                        declaration.name,
                        value,
                        declaration.scope,
                        condition_id,
                    ),
                    variable_name=declaration.name,
                    scope=declaration.scope,
                    value_expression=value,
                    value_kind="enum_value" if value[:1].isupper() else "boundary_at",
                    related_condition_id=condition_id,
                    related_coverage_ids=coverage_ids,
                    setup_hint="set global before call" if declaration.scope != "file_static" else "file static setup may require wrapper or initialization path",
                    confidence="medium",
                    review_required=True,
                    evidence=raw,
                )
            )
    return candidates


def _stub_return_candidates(condition_id: str, raw: str, coverage_ids: list[str], call_report: CallReport) -> list[StubReturnCandidate]:
    candidates: list[StubReturnCandidate] = []
    for call in call_report.calls:
        if not re.search(rf"\b{re.escape(call.name)}\s*\(", raw):
            continue
        compare = re.search(rf"\b{re.escape(call.name)}\s*\([^)]*\)\s*(<=|>=|<|>|==|!=)\s*([A-Za-z_]\w*|-?\d+)", raw)
        if compare:
            for expression, kind in zip(_around(compare.group(2)), ["boundary_below", "boundary_at", "boundary_above"]):
                candidates.append(_stub(call.name, expression, kind, call.call_id, condition_id, coverage_ids, "exercise call-result comparison", raw, "high"))
        else:
            candidates.append(_stub(call.name, "true", "true", call.call_id, condition_id, coverage_ids, "make condition true", raw, "high"))
            candidates.append(_stub(call.name, "false", "false", call.call_id, condition_id, coverage_ids, "make condition false", raw, "high"))
    return candidates


def _coverage_for_condition(condition_id: str, coverage: CoverageDesignReport) -> list[str]:
    target_ids = {condition_id}
    for branch in coverage.branches:
        if branch.condition and branch.condition.condition_id == condition_id:
            target_ids.add(branch.branch_id)
    for switch in coverage.switches:
        if switch.expression.condition_id == condition_id:
            target_ids.add(switch.switch_id)
    for loop in coverage.loops:
        if loop.condition and loop.condition.condition_id == condition_id:
            target_ids.add(loop.loop_id)
    for ternary in coverage.ternaries:
        if ternary.condition.condition_id == condition_id:
            target_ids.add(ternary.ternary_id)
    return [
        item.coverage_id
        for item in coverage.coverage_items
        if item.target_id in target_ids
    ]


def _coverage_links(inputs: list[InputValueCandidate], states: list[StateValueCandidate], stubs: list[StubReturnCandidate], coverage: CoverageDesignReport) -> list[CandidateCoverageLink]:
    by_coverage: dict[str, list[str]] = {}
    for candidate in inputs:
        for coverage_id in candidate.related_coverage_ids:
            by_coverage.setdefault(coverage_id, []).append(candidate.candidate_id)
    for candidate in states:
        for coverage_id in candidate.related_coverage_ids:
            by_coverage.setdefault(coverage_id, []).append(candidate.candidate_id)
    for candidate in stubs:
        for coverage_id in candidate.related_coverage_ids:
            by_coverage.setdefault(coverage_id, []).append(candidate.candidate_id)
    return [CandidateCoverageLink(coverage_id, sorted(set(ids)), "candidate generated from related coverage context", "medium") for coverage_id, ids in by_coverage.items()]


def _around(value: str) -> list[str]:
    if re.fullmatch(r"-?\d+", value):
        number = int(value)
        return [str(number - 1), str(number), str(number + 1)]
    return [f"{value} - 1", value, f"{value} + 1"]


def _input(target: str, target_kind: str, value: str, value_kind: str, source: str, condition_id: str | None, coverage_ids: list[str], purpose: str, evidence: str, confidence: str) -> InputValueCandidate:
    return InputValueCandidate(
        candidate_id=_candidate_id(
            "IN",
            target,
            value,
            target_kind,
            value_kind,
            source,
            condition_id,
        ),
        target_name=target,
        target_kind=target_kind,
        value_expression=value,
        value_kind=value_kind,
        source=source,
        related_condition_id=condition_id,
        related_coverage_ids=coverage_ids,
        purpose=purpose,
        confidence=confidence,
        review_required=True,
        evidence=evidence,
    )


def _stub(call_name: str, value: str, value_kind: str, call_id: str | None, condition_id: str, coverage_ids: list[str], purpose: str, evidence: str, confidence: str) -> StubReturnCandidate:
    candidate_id = _candidate_id(
        "STUB",
        call_name,
        value,
        value_kind,
        call_id,
        condition_id,
    )
    return StubReturnCandidate(candidate_id, call_name, value, value_kind, call_id, condition_id, coverage_ids, purpose, confidence, True, evidence)


def _candidate_id(prefix: str, *parts: object) -> str:
    values = ["" if part is None else str(part) for part in parts]
    semantic_key = "\x1f".join(values)
    digest = hashlib.sha256(semantic_key.encode("utf-8")).hexdigest()[:12]
    readable_parts = [
        _candidate_id_component(value)
        for value in values[:2]
        if value
    ]
    readable = "_".join(part for part in readable_parts if part)
    stem = f"{prefix}_{readable}" if readable else prefix
    max_stem_length = 80 - len(digest) - 1
    return f"{stem[:max_stem_length]}_{digest}"


def _candidate_id_component(value: str) -> str:
    stripped = value.strip()
    sign = ""
    if stripped.startswith("-"):
        sign = "neg_"
        stripped = stripped[1:]
    elif stripped.startswith("+"):
        sign = "pos_"
        stripped = stripped[1:]
    safe = re.sub(r"\W+", "_", stripped).strip("_") or "value"
    return f"{sign}{safe}"


def _dedupe_inputs(candidates: list[InputValueCandidate]) -> list[InputValueCandidate]:
    seen = set()
    result = []
    for candidate in candidates:
        key = (candidate.target_name, candidate.value_expression, candidate.value_kind, candidate.source)
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result
