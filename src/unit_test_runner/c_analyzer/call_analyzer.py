from __future__ import annotations

import re
from collections import defaultdict

from .analysis_common import (
    CONTROL_KEYWORDS,
    body_base_offset,
    body_text,
    find_matching_char,
    identifiers_in,
    normalize_space,
    position_from_offset,
    range_from_offsets,
    snippet_around_statement,
    split_top_level,
)
from .call_models import (
    CallArgument,
    CallReport,
    CallSideEffectCandidate,
    FunctionCall,
    ReturnUsage,
    StubCandidate,
)
from .global_access_models import GlobalAccessReport, IdentifierUse
from .legacy import list_functions
from .signature_models import FunctionSignature
from .source_models import SourceDigest


STANDARD_LIBRARY = {"memcpy", "memset", "memcmp", "strcpy", "strncpy", "strcmp", "strlen", "sprintf", "printf", "malloc", "free", "abs", "labs"}


def analyze_calls(digest: SourceDigest, function_location: object, function_signature: FunctionSignature, global_access: GlobalAccessReport) -> CallReport:
    body = body_text(digest, function_location, masked=True)
    original_body = body_text(digest, function_location, masked=False)
    base_offset = body_base_offset(function_location)
    defined = {item["name"]: item for item in list_functions(digest.source.path)}
    macro_names = {macro.name for macro in digest.macros if macro.is_function_like}
    parameter_names = {parameter.name for parameter in function_signature.parameters if parameter.name}
    pointer_parameters = {parameter.name for parameter in function_signature.parameters if parameter.name and (parameter.type_info.pointer_level or parameter.type_info.is_array or parameter.type_info.is_function_pointer)}
    globals_by_name = {declaration.name: declaration for declaration in global_access.file_scope_declarations}
    local_names = {declaration.name for declaration in global_access.local_declarations}

    calls: list[FunctionCall] = []
    side_effects: list[CallSideEffectCandidate] = []
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", body):
        name = match.group(1)
        if name in CONTROL_KEYWORDS or name == function_signature.function_name:
            continue
        open_paren = body.find("(", match.start())
        close_paren = find_matching_char(body, open_paren)
        if close_paren == -1:
            continue
        if _looks_like_cast(body, match.start(), close_paren, name):
            continue
        call_id = f"CALL_{len(calls) + 1:03d}"
        absolute_start = base_offset + match.start()
        absolute_end = base_offset + close_paren + 1
        evidence = normalize_space(digest.source.text[absolute_start:absolute_end])
        arguments = _parse_arguments(
            digest.source.text,
            body,
            base_offset,
            body[open_paren + 1 : close_paren],
            open_paren + 1,
            parameter_names,
            pointer_parameters,
            globals_by_name,
            local_names,
            macro_names,
        )
        target_kind = _target_kind(name, defined, macro_names, pointer_parameters)
        return_usage = _return_usage(digest.source.text, body, base_offset, match.start(), close_paren + 1)
        call = FunctionCall(
            call_id=call_id,
            name=name,
            target_kind=target_kind,
            call_range=range_from_offsets(digest.source.text, absolute_start, absolute_end),
            name_position=position_from_offset(digest.source.text, absolute_start),
            arguments=arguments,
            return_usage=return_usage,
            nesting_level=body[: match.start()].count("(") - body[: match.start()].count(")"),
            confidence="high" if target_kind != "unknown" else "low",
            evidence=evidence,
        )
        calls.append(call)
        side_effects.extend(_call_side_effects(call, arguments))

    stubs = _stub_candidates(calls)
    unresolved = [call for call in calls if call.target_kind == "unknown"]
    status = "analyzed" if not unresolved else "partial"
    return CallReport(
        source_path=digest.source.path,
        source_sha256=digest.source.sha256,
        function_name=function_signature.function_name,
        status=status,
        calls=calls,
        stub_candidates=stubs,
        side_effect_candidates=side_effects,
        unresolved_calls=unresolved,
        warnings=[],
    )


def _parse_arguments(
    original: str,
    body: str,
    base_offset: int,
    raw: str,
    raw_start: int,
    parameter_names: set[str],
    pointer_parameters: set[str],
    globals_by_name: dict[str, object],
    local_names: set[str],
    macro_names: set[str],
) -> list[CallArgument]:
    arguments: list[CallArgument] = []
    cursor = raw_start
    for index, part in enumerate(split_top_level(raw), start=0):
        relative = body.find(part, cursor)
        if relative == -1:
            relative = cursor
        cursor = relative + len(part)
        absolute_start = base_offset + relative
        identifiers = [
            IdentifierUse(
                name=name,
                position=position_from_offset(original, absolute_start + max(0, part.find(name))),
                context=normalize_space(part),
                token_index=i,
                resolved_as=_resolve_identifier(name, parameter_names, globals_by_name, local_names, macro_names),
                confidence="medium",
            )
            for i, name in enumerate(identifiers_in(part))
        ]
        argument_kind, passing_mode = _argument_kind(part, parameter_names, pointer_parameters, globals_by_name, local_names, macro_names)
        arguments.append(
            CallArgument(
                index=index,
                raw=normalize_space(part),
                expression_range=range_from_offsets(original, absolute_start, absolute_start + len(part)),
                identifiers=identifiers,
                argument_kind=argument_kind,
                passing_mode_hint=passing_mode,
                confidence="high" if argument_kind != "unknown" else "low",
            )
        )
    return arguments


def _resolve_identifier(name: str, parameters: set[str], globals_by_name: dict[str, object], locals_: set[str], macros: set[str]) -> str:
    if name in parameters:
        return "parameter"
    if name in locals_:
        return "local"
    if name in globals_by_name:
        return "global_candidate"
    if name in macros or name[:1].isupper():
        return "macro"
    return "unknown"


def _argument_kind(raw: str, parameters: set[str], pointer_parameters: set[str], globals_by_name: dict[str, object], locals_: set[str], macros: set[str]) -> tuple[str, str]:
    value = raw.strip()
    if re.fullmatch(r"[-+]?\d+|0[xX][0-9A-Fa-f]+|'.*'|\".*\"", value):
        return "literal", "by_value"
    if re.match(r"&\s*([A-Za-z_]\w*)", value):
        address_match = re.match(r"&\s*([A-Za-z_]\w*)", value)
        if address_match is None:
            return "expression", "unknown"
        name = address_match.group(1)
        if name in globals_by_name:
            return "address_of_global", "by_address"
        if name in locals_:
            return "address_of_local", "by_address"
        if name in parameters:
            return "parameter", "by_address"
    if re.search(r"\b[A-Za-z_]\w*\s*\(", value):
        return "call_expression", "unknown"
    names = identifiers_in(value)
    if names:
        first = names[0]
        if first in pointer_parameters:
            return "parameter", "pointer_or_array"
        if first in parameters:
            return "parameter", "by_value"
        if first in globals_by_name:
            return "global", "by_value"
        if first in locals_:
            return "local", "by_value"
        if first in macros or first[:1].isupper():
            return "constant_or_macro", "by_value"
    return "expression", "unknown"


def _target_kind(name: str, defined: dict[str, dict], macros: set[str], pointer_parameters: set[str]) -> str:
    if name in macros:
        return "macro_like"
    if name in pointer_parameters:
        return "function_pointer"
    if name in defined:
        return "same_file_static_function" if defined[name].get("static") else "same_file_function"
    if name in STANDARD_LIBRARY:
        return "standard_library"
    return "external_function"


def _return_usage(original: str, body: str, base_offset: int, start: int, end: int) -> ReturnUsage:
    statement = snippet_around_statement(body, start, end)
    consumer_range = range_from_offsets(original, base_offset + max(0, start - len(statement)), base_offset + end)
    prefix = body[max(0, start - 80) : start]
    suffix = body[end : min(len(body), end + 40)]
    assigned = re.search(r"([A-Za-z_]\w*)\s*=\s*$", prefix)
    if re.search(r"\breturn\s*$", prefix):
        return ReturnUsage("returned", consumer_range=consumer_range, evidence=statement, confidence="high")
    if assigned:
        return ReturnUsage("assigned", consumer_range=consumer_range, assigned_to=assigned.group(1), evidence=statement, confidence="high")
    comparison = re.match(r"\s*(==|!=|<=|>=|<|>)\s*([A-Za-z_]\w*|-?\d+)", suffix)
    if comparison:
        return ReturnUsage("comparison", consumer_range=consumer_range, compared_with=comparison.group(2), evidence=statement, confidence="high")
    if re.search(r"\b(if|while|for)\s*\([^;{}]*$", prefix):
        return ReturnUsage("condition", consumer_range=consumer_range, evidence=statement, confidence="high")
    if re.match(r"\s*(&&|\|\|)", suffix):
        return ReturnUsage("logical", consumer_range=consumer_range, evidence=statement, confidence="medium")
    return ReturnUsage("ignored", consumer_range=consumer_range, evidence=statement, confidence="medium")


def _call_side_effects(call: FunctionCall, arguments: list[CallArgument]) -> list[CallSideEffectCandidate]:
    side_effects: list[CallSideEffectCandidate] = []
    for argument in arguments:
        kind = None
        if argument.argument_kind == "address_of_global":
            kind = "global_passed_by_address"
        elif argument.argument_kind == "address_of_local":
            kind = "local_passed_by_address"
        elif argument.passing_mode_hint == "pointer_or_array":
            kind = "parameter_pointer_passed"
        if kind:
            side_effects.append(
                CallSideEffectCandidate(
                    call_id=call.call_id,
                    call_name=call.name,
                    kind=kind,
                    argument_index=argument.index,
                    related_identifier=argument.identifiers[0].name if argument.identifiers else None,
                    reason=f"{argument.raw} is passed in a way that may allow side effects.",
                    confidence="high",
                    evidence=call.evidence,
                )
            )
    return side_effects


def _stub_candidates(calls: list[FunctionCall]) -> list[StubCandidate]:
    grouped: dict[str, list[FunctionCall]] = defaultdict(list)
    for call in calls:
        if call.target_kind in {"external_function", "unknown", "macro_like"}:
            grouped[call.name].append(call)
    candidates: list[StubCandidate] = []
    for name, related in grouped.items():
        return_needed = any(call.return_usage.usage_kind not in {"ignored", "unknown"} for call in related)
        side_effect_needed = any(any(argument.passing_mode_hint in {"by_address", "pointer_or_array"} or argument.argument_kind in {"address_of_global", "address_of_local", "global"} for argument in call.arguments) for call in related)
        tags = ["external_dependency"] if any(call.target_kind == "external_function" for call in related) else ["unknown_dependency"]
        upper_name = name.upper()
        if any(hint.upper() in upper_name for hint in ("PORT", "IO", "DEVICE", "SENSOR", "REG")):
            tags.append("hardware_like")
        if any(hint.upper() in upper_name for hint in ("READ", "WRITE", "SEND", "RECV", "OPEN", "CLOSE")):
            tags.append("io_like")
        if return_needed:
            tags.append("return_value_used")
        if side_effect_needed:
            tags.append("pointer_argument")
        candidates.append(
            StubCandidate(
                name=name,
                reason="external or unresolved function call candidate",
                target_kind=related[0].target_kind,
                call_count=len(related),
                return_value_control_needed=return_needed,
                argument_capture_needed=bool(related and related[0].arguments),
                side_effect_control_needed=side_effect_needed,
                related_calls=[call.call_id for call in related],
                confidence="medium",
                tags=tags,
            )
        )
    return candidates


def _looks_like_cast(body: str, start: int, close_paren: int, name: str) -> bool:
    before = body[max(0, start - 2) : start]
    after = body[close_paren + 1 : close_paren + 3]
    return before.endswith("(") and name[:1].isupper() and after and after[0] not in {";", ","}
