from __future__ import annotations

import re

from .analysis_common import (
    KEYWORDS,
    body_base_offset,
    body_text,
    identifiers_in,
    position_from_offset,
    range_from_offsets,
    selected_candidate,
    snippet_around_statement,
)
from .global_access_models import (
    GlobalAccessReport,
    GlobalAccessWarning,
    IdentifierUse,
    ParameterAccess,
    SideEffectCandidate,
    VariableAccess,
    VariableDeclaration,
)
from .signature_models import FunctionSignature
from .source_models import SourceDigest


DECLARATION_RE = re.compile(
    r"(?m)^[ \t]*(?P<storage>static|extern)?[ \t]*(?P<type>(?:const\s+|volatile\s+)?(?:struct\s+\w+|union\s+\w+|enum\s+\w+|unsigned\s+long|unsigned\s+int|unsigned\s+short|long|short|int|char|float|double|[A-Za-z_]\w+)(?:\s+\*)?)\s+(?P<name>[A-Za-z_]\w*)\s*(?P<array>\[[^\]]*\])?\s*(?P<tail>=|;)"
)
NON_DECLARATION_STARTERS = {"return", "if", "for", "while", "switch", "case", "break", "continue", "else", "do", "goto", "sizeof"}


def analyze_global_access(digest: SourceDigest, function_location: object, function_signature: FunctionSignature) -> GlobalAccessReport:
    candidate = selected_candidate(function_location)
    masked = digest.masked_source.masked_text
    original = digest.source.text
    body = body_text(digest, function_location, masked=True)
    body_offset = body_base_offset(function_location)
    file_scope = _scan_declarations(masked[: candidate.header_range.start.offset], original, 0, "file")
    locals_ = _scan_declarations(body, original, body_offset, "local")
    warnings: list[GlobalAccessWarning] = []

    parameter_names = {parameter.name for parameter in function_signature.parameters if parameter.name}
    local_names = {declaration.name for declaration in locals_} | parameter_names
    filtered_file_scope = []
    for declaration in file_scope:
        if declaration.name in local_names:
            warnings.append(GlobalAccessWarning("local_shadows_global", f"Local or parameter shadows file-scope candidate: {declaration.name}", text=declaration.name))
            continue
        filtered_file_scope.append(declaration)

    declaration_by_name = {declaration.name: declaration for declaration in filtered_file_scope}
    global_accesses = _scan_global_accesses(original, body, body_offset, declaration_by_name)
    parameter_accesses, side_effects = _scan_parameter_accesses(original, body, body_offset, function_signature)
    unresolved = _scan_unresolved_identifiers(original, body, body_offset, declaration_by_name, local_names, digest.macros)
    status = "analyzed"
    if unresolved:
        status = "partial"
    return GlobalAccessReport(
        source_path=digest.source.path,
        source_sha256=digest.source.sha256,
        function_name=function_signature.function_name,
        status=status,
        file_scope_declarations=filtered_file_scope,
        local_declarations=locals_,
        parameter_accesses=parameter_accesses,
        global_accesses=global_accesses,
        unresolved_identifiers=unresolved,
        side_effect_candidates=side_effects,
        warnings=warnings,
    )


def _scan_declarations(text: str, original: str, base_offset: int, scope_kind: str) -> list[VariableDeclaration]:
    declarations: list[VariableDeclaration] = []
    for match in DECLARATION_RE.finditer(text):
        raw_line = match.group(0).strip()
        first_word = re.match(r"[A-Za-z_]\w*", raw_line)
        if first_word and first_word.group(0) in NON_DECLARATION_STARTERS:
            continue
        if "(" in raw_line:
            continue
        storage = match.group("storage")
        name = match.group("name")
        if name in KEYWORDS:
            continue
        scope = scope_kind
        if scope_kind == "file" and storage == "static":
            scope = "file_static"
        elif scope_kind == "file" and storage == "extern":
            scope = "extern"
        elif scope_kind == "local" and storage == "static":
            scope = "local_static"
        declarations.append(
            VariableDeclaration(
                name=name,
                scope=scope,
                storage_class=storage,
                type_raw=match.group("type").strip(),
                declaration_range=range_from_offsets(original, base_offset + match.start(), base_offset + match.end()),
                is_array=bool(match.group("array")),
                is_pointer="*" in match.group("type"),
                is_struct_like=match.group("type").strip().startswith(("struct ", "union ", "enum ")),
                confidence="high",
                raw=raw_line,
            )
        )
    return declarations


def _scan_global_accesses(original: str, body: str, body_offset: int, declarations: dict[str, VariableDeclaration]) -> list[VariableAccess]:
    accesses: list[VariableAccess] = []
    seen: set[tuple[str, str, int]] = set()
    for name, declaration in declarations.items():
        for match in re.finditer(rf"\b{re.escape(name)}\b(?:\s*(?:->|\.)\s*[A-Za-z_]\w*|\s*\[[^\]]+\])?", body):
            absolute = body_offset + match.start()
            access_path = re.sub(r"\s+", "", match.group(0))
            operator = _operator_after(body, match.end())
            before = body[max(0, match.start() - 3) : match.start()]
            if before.rstrip().endswith("&"):
                kind = "address_taken"
                operator = "&"
            elif operator in {"++", "--", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="}:
                kind = "read_write"
            elif operator == "=":
                kind = "write"
            else:
                kind = "read"
            key = (name, kind, absolute)
            if key in seen:
                continue
            seen.add(key)
            evidence = snippet_around_statement(body, match.start(), match.end())
            accesses.append(
                VariableAccess(
                    name=name,
                    access_kind=kind,
                    scope=declaration.scope,
                    position=position_from_offset(original, absolute),
                    expression_range=range_from_offsets(original, absolute, absolute + len(match.group(0))),
                    access_path=access_path,
                    operator=operator,
                    confidence="high",
                    evidence=evidence,
                    related_declaration=declaration,
                )
            )
    return accesses


def _scan_parameter_accesses(original: str, body: str, body_offset: int, signature: FunctionSignature) -> tuple[list[ParameterAccess], list[SideEffectCandidate]]:
    accesses: list[ParameterAccess] = []
    side_effects: list[SideEffectCandidate] = []
    for parameter in signature.parameters:
        if not parameter.name:
            continue
        name = parameter.name
        for pattern, hint, kind, access_path_builder in [
            (rf"\*\s*{re.escape(name)}\b\s*=", "write_candidate", "parameter_write", lambda m: "*" + name),
            (rf"\b{re.escape(name)}\s*\[[^\]]+\]\s*=", "write_candidate", "parameter_write", lambda m: re.sub(r"\s+", "", m.group(0).split("=")[0])),
            (rf"\b{re.escape(name)}\s*->\s*[A-Za-z_]\w+\s*=", "write_candidate", "parameter_write", lambda m: re.sub(r"\s+", "", m.group(0).split("=")[0])),
            (rf"&\s*{re.escape(name)}\b", "address_taken", "address_escape", lambda m: "&" + name),
        ]:
            for match in re.finditer(pattern, body):
                absolute = body_offset + match.start()
                expression_range = range_from_offsets(original, absolute, absolute + len(match.group(0)))
                evidence = snippet_around_statement(body, match.start(), match.end())
                access_path = access_path_builder(match)
                accesses.append(
                    ParameterAccess(
                        parameter_name=name,
                        access_kind=hint,
                        position=position_from_offset(original, absolute),
                        expression_range=expression_range,
                        access_path=access_path,
                        direction_hint_before_body=parameter.direction_hint,
                        body_access_hint=hint,
                        confidence="high",
                        evidence=evidence,
                    )
                )
                side_effects.append(
                    SideEffectCandidate(
                        kind=kind,
                        name=name,
                        position=position_from_offset(original, absolute),
                        expression_range=expression_range,
                        reason=f"{name} is modified or escapes through the function body.",
                        confidence="high",
                        evidence=evidence,
                    )
                )
        if (parameter.type_info.pointer_level or parameter.type_info.is_array) and not any(item.parameter_name == name for item in accesses):
            for match in re.finditer(rf"\b{re.escape(name)}\b", body):
                absolute = body_offset + match.start()
                accesses.append(
                    ParameterAccess(
                        parameter_name=name,
                        access_kind="read",
                        position=position_from_offset(original, absolute),
                        expression_range=range_from_offsets(original, absolute, absolute + len(name)),
                        access_path=name,
                        direction_hint_before_body=parameter.direction_hint,
                        body_access_hint="read",
                        confidence="medium",
                        evidence=snippet_around_statement(body, match.start(), match.end()),
                    )
                )
                break
    return accesses, side_effects


def _scan_unresolved_identifiers(original: str, body: str, body_offset: int, globals_: dict[str, VariableDeclaration], locals_: set[str], macros: list[object]) -> list[IdentifierUse]:
    macro_names = {macro.name for macro in macros}
    unresolved: list[IdentifierUse] = []
    for index, name in enumerate(identifiers_in(body)):
        if name in globals_ or name in locals_ or name in macro_names:
            continue
        if name[:1].isupper():
            continue
        match = re.search(rf"\b{re.escape(name)}\b", body)
        if not match:
            continue
        absolute = body_offset + match.start()
        unresolved.append(
            IdentifierUse(
                name=name,
                position=position_from_offset(original, absolute),
                context=snippet_around_statement(body, match.start(), match.end()),
                token_index=index,
                resolved_as="unknown",
                confidence="low",
            )
        )
    return unresolved


def _operator_after(text: str, index: int) -> str | None:
    tail = text[index:]
    match = re.match(r"\s*(\+\+|--|<<=|>>=|[+\-*/%&|^]?=)", tail)
    return match.group(1) if match else None
