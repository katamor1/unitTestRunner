from __future__ import annotations

from .brace_matcher import annotate_brace_depth, find_matching_token
from .function_models import ConditionalContext, FunctionCandidate, FunctionLocation, FunctionLocatorWarning, SourcePosition, SourceRange
from .source_models import LexToken, SourceDigest


def locate_function(digest: SourceDigest, function_name: str) -> FunctionLocation:
    tokens = digest.tokens
    depths = annotate_brace_depth(tokens)
    candidates: list[FunctionCandidate] = []
    warnings: list[FunctionLocatorWarning] = []

    if any(macro.name == function_name and macro.is_function_like for macro in digest.macros):
        warnings.append(FunctionLocatorWarning("macro_like_candidate_ignored", f"Function-like macro ignored: {function_name}"))

    for index, token in enumerate(tokens):
        if token.kind != "identifier" or token.value != function_name:
            continue
        pointer_candidate = _function_pointer_candidate(tokens, index)
        if pointer_candidate:
            candidates.append(pointer_candidate)
            warnings.append(FunctionLocatorWarning("function_pointer_candidate_ignored", f"Function pointer candidate ignored: {function_name}", token.line_number, token.column))
            continue
        if index + 1 >= len(tokens) or tokens[index + 1].value != "(":
            continue
        close_paren = find_matching_token(tokens, index + 1, "(", ")")
        if close_paren == -1:
            continue
        next_index = _next_significant(tokens, close_paren + 1)
        if depths[index] != 0:
            candidates.append(_non_definition_candidate(digest, tokens, index, close_paren, "call", "low", "identifier appears inside a function body"))
            continue
        if next_index == -1:
            continue
        if tokens[next_index].value == ";":
            candidates.append(_non_definition_candidate(digest, tokens, index, close_paren, "prototype", "high", "candidate ends with semicolon"))
            warnings.append(FunctionLocatorWarning("prototype_only", f"Prototype found for {function_name}.", token.line_number, token.column))
            continue
        if tokens[next_index].value == "{":
            candidate, candidate_warnings = _definition_candidate(digest, tokens, depths, index, next_index, "high", "definition followed by function body")
            candidates.append(candidate)
            warnings.extend(candidate_warnings)
            continue
        brace_index = _old_style_brace(tokens, close_paren + 1)
        if brace_index != -1:
            candidate, candidate_warnings = _definition_candidate(digest, tokens, depths, index, brace_index, "medium", "old-style C definition")
            candidates.append(candidate)
            warnings.append(FunctionLocatorWarning("old_style_definition_detected", f"Old-style function definition detected: {function_name}", token.line_number, token.column))
            warnings.extend(candidate_warnings)

    definitions = [candidate for candidate in candidates if candidate.kind == "definition" and candidate.body_range is not None]
    malformed = [candidate for candidate in candidates if candidate.kind == "definition" and candidate.body_range is None]
    if malformed and not definitions:
        return FunctionLocation(function_name, digest.source.path, "malformed", None, candidates, warnings)
    if len(definitions) > 1:
        warnings.append(FunctionLocatorWarning("multiple_function_definitions", f"Multiple definitions found for {function_name}."))
        return FunctionLocation(function_name, digest.source.path, "multiple_candidates", None, candidates, warnings)
    if len(definitions) == 1:
        selected = definitions[0]
        if selected.conditional_context and selected.conditional_context.active_state == "inactive":
            warnings.append(FunctionLocatorWarning("candidate_in_inactive_region", f"Candidate is in an inactive conditional region: {function_name}."))
        if selected.conditional_context and selected.conditional_context.active_state == "unknown":
            warnings.append(FunctionLocatorWarning("unknown_active_state", f"Candidate active state is unknown: {function_name}."))
        return FunctionLocation(function_name, digest.source.path, "found", selected, candidates, warnings)
    if not candidates:
        warnings.append(FunctionLocatorWarning("function_not_found", f"Function not found: {function_name}."))
    return FunctionLocation(function_name, digest.source.path, "not_found", None, candidates, warnings)


def _definition_candidate(
    digest: SourceDigest,
    tokens: list[LexToken],
    depths: list[int],
    name_index: int,
    open_brace_index: int,
    confidence: str,
    reason: str,
) -> tuple[FunctionCandidate, list[FunctionLocatorWarning]]:
    warnings: list[FunctionLocatorWarning] = []
    close_brace_index = find_matching_token(tokens, open_brace_index, "{", "}")
    header_start_index = _header_start(tokens, depths, name_index)
    header_range = _range(tokens[header_start_index], tokens[open_brace_index - 1])
    opening = _position(tokens[open_brace_index])
    conditional = _conditional_context(digest, tokens[header_start_index].line_number)
    storage = "static" if any(token.value == "static" for token in tokens[header_start_index:name_index]) else None
    if close_brace_index == -1:
        warnings.append(FunctionLocatorWarning("unmatched_opening_brace", "Opening brace has no matching closing brace.", tokens[open_brace_index].line_number, tokens[open_brace_index].column))
        full_range = _range(tokens[header_start_index], tokens[open_brace_index])
        return (
            FunctionCandidate(tokens[name_index].value, "definition", "low", header_range, None, full_range, opening, None, storage, conditional, _preview(digest, tokens[header_start_index], tokens[open_brace_index]), "unmatched opening brace"),
            warnings,
        )
    closing = _position(tokens[close_brace_index])
    body_range = SourceRange(opening, closing)
    full_range = _range(tokens[header_start_index], tokens[close_brace_index])
    return (
        FunctionCandidate(tokens[name_index].value, "definition", confidence, header_range, body_range, full_range, opening, closing, storage, conditional, _preview(digest, tokens[header_start_index], tokens[open_brace_index]), reason),
        warnings,
    )


def _non_definition_candidate(
    digest: SourceDigest,
    tokens: list[LexToken],
    name_index: int,
    end_index: int,
    kind: str,
    confidence: str,
    reason: str,
) -> FunctionCandidate:
    header_start = max(0, name_index - 2)
    candidate_range = _range(tokens[header_start], tokens[end_index])
    return FunctionCandidate(tokens[name_index].value, kind, confidence, candidate_range, None, candidate_range, None, None, None, _conditional_context(digest, tokens[name_index].line_number), _preview(digest, tokens[header_start], tokens[end_index]), reason)


def _function_pointer_candidate(tokens: list[LexToken], index: int) -> FunctionCandidate | None:
    if index >= 2 and tokens[index - 2].value == "(" and tokens[index - 1].value == "*":
        end = min(len(tokens) - 1, index + 2)
        candidate_range = _range(tokens[index - 2], tokens[end])
        return FunctionCandidate(tokens[index].value, "function_pointer", "high", candidate_range, None, candidate_range, None, None, None, None, "", "(* name) function pointer pattern")
    return None


def _old_style_brace(tokens: list[LexToken], start_index: int) -> int:
    saw_semicolon = False
    for index in range(start_index, min(len(tokens), start_index + 40)):
        if tokens[index].value == "{":
            return index if saw_semicolon else -1
        if tokens[index].value == ";":
            saw_semicolon = True
        if tokens[index].value == "=":
            return -1
    return -1


def _header_start(tokens: list[LexToken], depths: list[int], name_index: int) -> int:
    for index in range(name_index - 1, -1, -1):
        if depths[index] == 0 and tokens[index].value in {";", "}"}:
            return index + 1
    return 0


def _next_significant(tokens: list[LexToken], start_index: int) -> int:
    return start_index if start_index < len(tokens) else -1


def _range(start: LexToken, end: LexToken) -> SourceRange:
    return SourceRange(_position(start), SourcePosition(end.line_number, end.column + len(end.value), end.end_offset))


def _position(token: LexToken) -> SourcePosition:
    return SourcePosition(token.line_number, token.column, token.start_offset)


def _preview(digest: SourceDigest, start: LexToken, end: LexToken) -> str:
    return " ".join(digest.source.text[start.start_offset:end.start_offset].strip().split())


def _conditional_context(digest: SourceDigest, line_number: int) -> ConditionalContext:
    stack = []
    for directive in digest.directives:
        if directive.line_number >= line_number:
            break
        if directive.kind in {"if", "ifdef", "ifndef"}:
            stack.append(directive)
        elif directive.kind in {"elif", "else"} and stack:
            stack[-1] = directive
        elif directive.kind == "endif" and stack:
            stack.pop()
    states = [directive.active_state for directive in stack]
    if "inactive" in states:
        active = "inactive"
    elif "unknown" in states:
        active = "unknown"
    else:
        active = "active"
    return ConditionalContext(active_state=active, nesting_level=len(stack), directives=list(stack))
