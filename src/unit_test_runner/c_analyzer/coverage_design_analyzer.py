from __future__ import annotations

import re

from .analysis_common import (
    body_base_offset,
    body_text,
    find_matching_char,
    identifiers_in,
    normalize_space,
    position_from_offset,
    range_from_offsets,
    split_top_level,
)
from .call_models import CallReport
from .coverage_models import (
    BranchNode,
    ConditionExpression,
    ConditionOperand,
    CoverageDesignReport,
    CoverageItem,
    LoopNode,
    ReturnPath,
    SwitchNode,
    CaseNode,
)
from .global_access_models import GlobalAccessReport
from .signature_models import FunctionSignature
from .source_models import SourceDigest


def analyze_coverage_design(
    digest: SourceDigest,
    function_location: object,
    function_signature: FunctionSignature,
    global_access: GlobalAccessReport,
    call_report: CallReport,
) -> CoverageDesignReport:
    body = body_text(digest, function_location, masked=True)
    original_body = body_text(digest, function_location, masked=False)
    base_offset = body_base_offset(function_location)
    all_conditions: list[ConditionExpression] = []
    branches = _scan_branches(digest.source.text, body, base_offset, global_access, call_report, all_conditions)
    switches = _scan_switches(digest.source.text, body, base_offset, global_access, call_report, all_conditions)
    loops = _scan_loops(digest.source.text, body, base_offset, global_access, call_report, all_conditions)
    returns = _scan_returns(digest.source.text, body, base_offset, global_access, call_report)
    coverage_items = _coverage_items(function_signature.function_name, branches, switches, loops, returns, all_conditions)
    return CoverageDesignReport(
        source_path=digest.source.path,
        source_sha256=digest.source.sha256,
        function_name=function_signature.function_name,
        status="analyzed",
        branches=branches,
        switches=switches,
        loops=loops,
        ternaries=[],
        return_paths=returns,
        condition_expressions=all_conditions,
        coverage_items=coverage_items,
        warnings=[],
    )


def _scan_branches(original: str, body: str, base_offset: int, global_access: GlobalAccessReport, call_report: CallReport, conditions: list[ConditionExpression]) -> list[BranchNode]:
    branches: list[BranchNode] = []
    for match in re.finditer(r"\bif\s*\(", body):
        open_paren = body.find("(", match.start())
        close_paren = find_matching_char(body, open_paren)
        if close_paren == -1:
            continue
        raw = body[open_paren + 1 : close_paren]
        condition = _condition(original, body, base_offset, open_paren + 1, raw, global_access, call_report, f"COND_{len(conditions) + 1:03d}")
        conditions.append(condition)
        prefix = body[max(0, match.start() - 8) : match.start()]
        kind = "else_if" if re.search(r"\belse\s*$", prefix) else "if"
        absolute_start = base_offset + match.start()
        branches.append(
            BranchNode(
                branch_id=f"BR_{len(branches) + 1:03d}",
                kind=kind,
                condition=condition,
                branch_range=range_from_offsets(original, absolute_start, base_offset + close_paren + 1),
                nesting_level=body[: match.start()].count("{") - body[: match.start()].count("}"),
                evidence=normalize_space(body[match.start() : close_paren + 1]),
                confidence="high",
            )
        )
    for match in re.finditer(r"\belse\b(?!\s*if)", body):
        absolute_start = base_offset + match.start()
        branches.append(
            BranchNode(
                branch_id=f"BR_{len(branches) + 1:03d}",
                kind="else",
                condition=None,
                branch_range=range_from_offsets(original, absolute_start, absolute_start + len(match.group(0))),
                nesting_level=body[: match.start()].count("{") - body[: match.start()].count("}"),
                evidence="else",
                confidence="medium",
            )
        )
    return branches


def _scan_switches(original: str, body: str, base_offset: int, global_access: GlobalAccessReport, call_report: CallReport, conditions: list[ConditionExpression]) -> list[SwitchNode]:
    switches: list[SwitchNode] = []
    for match in re.finditer(r"\bswitch\s*\(", body):
        open_paren = body.find("(", match.start())
        close_paren = find_matching_char(body, open_paren)
        if close_paren == -1:
            continue
        raw = body[open_paren + 1 : close_paren]
        condition = _condition(original, body, base_offset, open_paren + 1, raw, global_access, call_report, f"COND_{len(conditions) + 1:03d}")
        conditions.append(condition)
        cases: list[CaseNode] = []
        for case_match in re.finditer(r"\b(case)\s+([^:]+):|\b(default)\s*:", body[close_paren:]):
            absolute_relative = close_paren + case_match.start()
            label = "default" if case_match.group(3) else normalize_space(case_match.group(2))
            label_kind = "default" if label == "default" else ("constant" if re.fullmatch(r"-?\d+", label) else "macro")
            cases.append(
                CaseNode(
                    case_id=f"CASE_{len(cases) + 1:03d}",
                    label_raw=label,
                    label_kind=label_kind,
                    label_value=None if label == "default" else label,
                    case_range=range_from_offsets(original, base_offset + absolute_relative, base_offset + absolute_relative + len(case_match.group(0))),
                    fallthrough_candidate=False,
                    confidence="high",
                )
            )
            if label == "default":
                break
        switches.append(
            SwitchNode(
                switch_id=f"SW_{len(switches) + 1:03d}",
                expression=condition,
                switch_range=range_from_offsets(original, base_offset + match.start(), base_offset + close_paren + 1),
                cases=cases,
                has_default=any(case.label_kind == "default" for case in cases),
                confidence="high",
            )
        )
    return switches


def _scan_loops(original: str, body: str, base_offset: int, global_access: GlobalAccessReport, call_report: CallReport, conditions: list[ConditionExpression]) -> list[LoopNode]:
    loops: list[LoopNode] = []
    for match in re.finditer(r"\b(for|while)\s*\(", body):
        kind = match.group(1)
        open_paren = body.find("(", match.start())
        close_paren = find_matching_char(body, open_paren)
        if close_paren == -1:
            continue
        raw = body[open_paren + 1 : close_paren]
        initializer = increment = None
        condition_raw = raw
        if kind == "for":
            parts = split_top_level(raw, ";")
            if len(parts) == 3:
                initializer, condition_raw, increment = parts
        condition = _condition(original, body, base_offset, open_paren + 1, condition_raw, global_access, call_report, f"COND_{len(conditions) + 1:03d}") if condition_raw.strip() else None
        if condition:
            conditions.append(condition)
        hints = ["zero_iterations", "one_iteration", "multiple_iterations"]
        loops.append(
            LoopNode(
                loop_id=f"LOOP_{len(loops) + 1:03d}",
                kind=kind,
                condition=condition,
                initializer_raw=normalize_space(initializer) if initializer else None,
                increment_raw=normalize_space(increment) if increment else None,
                loop_range=range_from_offsets(original, base_offset + match.start(), base_offset + close_paren + 1),
                coverage_hints=hints,
                confidence="high",
            )
        )
    return loops


def _scan_returns(original: str, body: str, base_offset: int, global_access: GlobalAccessReport, call_report: CallReport) -> list[ReturnPath]:
    returns: list[ReturnPath] = []
    for match in re.finditer(r"\breturn\b\s*([^;]*);", body):
        expression = normalize_space(match.group(1))
        variables = [name for name in identifiers_in(expression) if name in _known_variables(global_access)]
        calls = [call.name for call in call_report.calls if call.name in expression]
        return_kind = _return_kind(expression, variables, calls)
        returns.append(
            ReturnPath(
                return_id=f"RET_{len(returns) + 1:03d}",
                return_range=range_from_offsets(original, base_offset + match.start(), base_offset + match.end()),
                expression_raw=expression or None,
                return_kind=return_kind,
                related_variables=variables,
                related_calls=calls,
                confidence="high",
                evidence=normalize_space(match.group(0)),
            )
        )
    return returns


def _condition(original: str, body: str, base_offset: int, relative_start: int, raw: str, global_access: GlobalAccessReport, call_report: CallReport, condition_id: str) -> ConditionExpression:
    raw_normalized = normalize_space(raw)
    variables = [name for name in identifiers_in(raw_normalized) if name in _known_variables(global_access) or name not in {call.name for call in call_report.calls}]
    calls = [call.name for call in call_report.calls if re.search(rf"\b{re.escape(call.name)}\s*\(", raw_normalized)]
    operators = re.findall(r"&&|\|\||==|!=|<=|>=|<|>", raw_normalized)
    condition_kind = _condition_kind(raw_normalized, operators, calls)
    operands = []
    for name in variables:
        offset = relative_start + max(0, raw.find(name))
        operands.append(ConditionOperand(name, "unknown", "unknown", name, None, position_from_offset(original, base_offset + offset), "medium"))
    complexity = "compound" if "&&" in operators or "||" in operators else "simple"
    return ConditionExpression(
        condition_id=condition_id,
        raw=raw_normalized,
        expression_range=range_from_offsets(original, base_offset + relative_start, base_offset + relative_start + len(raw)),
        condition_kind=condition_kind,
        operands=operands,
        operators=operators,
        related_variables=variables,
        related_calls=calls,
        complexity=complexity,
        confidence="high",
    )


def _condition_kind(raw: str, operators: list[str], calls: list[str]) -> str:
    if "&&" in operators or "||" in operators:
        if _looks_like_range(raw):
            return "range_check"
        return "compound"
    if re.search(r"\bNULL\b|\b0\b", raw) and any(operator in operators for operator in ("==", "!=")):
        return "null_check"
    if _looks_like_range(raw):
        return "range_check"
    if calls:
        return "call_result"
    if any(operator in operators for operator in ("==", "!=", "<=", ">=", "<", ">")):
        return "comparison"
    return "boolean"


def _looks_like_range(raw: str) -> bool:
    comparisons = re.findall(r"([A-Za-z_]\w*)\s*(<=|>=|<|>)\s*([A-Za-z_]\w*|-?\d+)", raw)
    names = [left for left, _operator, _right in comparisons]
    return len(comparisons) >= 2 and len(set(names)) == 1


def _coverage_items(function_name: str, branches: list[BranchNode], switches: list[SwitchNode], loops: list[LoopNode], returns: list[ReturnPath], conditions: list[ConditionExpression]) -> list[CoverageItem]:
    items: list[CoverageItem] = []
    for branch in branches:
        if branch.condition is None:
            items.append(CoverageItem(f"{branch.branch_id}_ELSE", "branch_false", branch.branch_id, "else branch is reached", "false", confidence="medium"))
            continue
        for value in ("true", "false"):
            items.append(
                CoverageItem(
                    f"{branch.branch_id}_{value.upper()}",
                    f"branch_{value}",
                    branch.branch_id,
                    f"{branch.kind} condition is {value}",
                    value,
                    related_variables=branch.condition.related_variables,
                    related_calls=branch.condition.related_calls,
                    confidence=branch.confidence,
                )
            )
    for condition in conditions:
        if condition.complexity == "compound":
            for index, part in enumerate(re.split(r"&&|\|\|", condition.raw), start=1):
                for value in ("true", "false"):
                    items.append(
                        CoverageItem(
                            f"{condition.condition_id}_PART{index}_{value.upper()}",
                            f"condition_{value}",
                            condition.condition_id,
                            f"compound condition part {index} is {value}: {normalize_space(part)}",
                            value,
                            related_variables=condition.related_variables,
                            related_calls=condition.related_calls,
                            confidence="medium",
                        )
                    )
    for switch in switches:
        for case in switch.cases:
            coverage_type = "switch_default" if case.label_kind == "default" else "switch_case"
            items.append(CoverageItem(f"{switch.switch_id}_{case.case_id}", coverage_type, switch.switch_id, f"switch reaches {case.label_raw}", case.label_raw, related_variables=switch.expression.related_variables, confidence="high"))
    for loop in loops:
        for coverage_type, value in [("loop_zero", "zero"), ("loop_one", "one"), ("loop_many", "many")]:
            items.append(CoverageItem(f"{loop.loop_id}_{value.upper()}", coverage_type, loop.loop_id, f"{loop.kind} loop executes {value}", value, related_variables=loop.condition.related_variables if loop.condition else [], confidence="medium"))
    for path in returns:
        items.append(CoverageItem(f"{path.return_id}_PATH", "return_path", path.return_id, f"return path is reached: {path.expression_raw or 'void'}", related_variables=path.related_variables, related_calls=path.related_calls, confidence=path.confidence))
    return items


def _known_variables(global_access: GlobalAccessReport) -> set[str]:
    return {item.name for item in global_access.file_scope_declarations} | {item.name for item in global_access.local_declarations} | {item.parameter_name for item in global_access.parameter_accesses}


def _return_kind(expression: str, variables: list[str], calls: list[str]) -> str:
    if not expression:
        return "void_return"
    if calls:
        return "call_return"
    if variables:
        return "global_return" if any(name.startswith("g_") for name in variables) else "local_return"
    if re.fullmatch(r"-?\d+|[A-Z_][A-Z0-9_]*", expression):
        return "error_like_return" if any(token in expression.upper() for token in ("ERR", "FAIL", "NG", "ERROR")) else "constant_return"
    return "unknown"
