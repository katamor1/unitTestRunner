from __future__ import annotations

import re
from dataclasses import dataclass

from .masker import mask_source_text
from .source_models import LexToken
from .tokens import extract_tokens


@dataclass(frozen=True)
class ObjectDefinition:
    name: str
    type_text: str
    storage_class: str | None
    line: int
    is_tentative: bool


def find_file_scope_object_definitions(source_text: str) -> list[ObjectDefinition]:
    masked = mask_source_text(source_text, "<object-definition-scan>").masked_text
    tokens = extract_tokens(masked)
    definitions: list[ObjectDefinition] = []
    current: list[LexToken] = []
    declaration_brace_depth = 0
    function_brace_depth = 0

    for token in tokens:
        value = token.value
        if function_brace_depth:
            if value == "{":
                function_brace_depth += 1
            elif value == "}":
                function_brace_depth -= 1
            continue
        if value == "{" and declaration_brace_depth == 0 and _starts_function_body(current):
            current = []
            function_brace_depth = 1
            continue
        if value == "{":
            declaration_brace_depth += 1
            current.append(token)
            continue
        if value == "}" and declaration_brace_depth:
            declaration_brace_depth -= 1
            current.append(token)
            continue
        if value == ";" and declaration_brace_depth == 0:
            current.append(token)
            definitions.extend(_parse_declaration(source_text, current))
            current = []
            continue
        if value == "}" and declaration_brace_depth == 0:
            current = []
            continue
        current.append(token)
    return definitions


def _starts_function_body(tokens: list[LexToken]) -> bool:
    if not tokens or any(token.value == "typedef" for token in tokens):
        return False
    if _contains_top_level(tokens, "="):
        return False
    return _contains_top_level(tokens, ")")


def _parse_declaration(source_text: str, tokens: list[LexToken]) -> list[ObjectDefinition]:
    if not tokens or any(token.value == "typedef" for token in tokens):
        return []
    chunks = _split_top_level(tokens[:-1], ",")
    if not chunks:
        return []
    storage = next(
        (token.value for token in chunks[0] if token.value in {"extern", "static", "auto", "register"}),
        None,
    )
    base_type = ""
    definitions: list[ObjectDefinition] = []
    for index, chunk in enumerate(chunks):
        if not chunk or _contains_top_level(chunk, "("):
            continue
        before_initializer, has_initializer = _before_top_level_initializer(chunk)
        candidates = _top_level_identifiers(before_initializer)
        if not candidates:
            continue
        name_token = candidates[-1]
        if index == 0:
            type_start = chunk[0].start_offset
            base_type = _normalize_type(source_text[type_start:name_token.start_offset], storage)
            type_text = base_type
        else:
            prefix = source_text[chunk[0].start_offset:name_token.start_offset].strip()
            type_text = " ".join(part for part in (base_type, prefix) if part).strip()
        if not type_text:
            continue
        if storage == "extern" and not has_initializer:
            continue
        definitions.append(
            ObjectDefinition(
                name=name_token.value,
                type_text=type_text,
                storage_class=storage,
                line=name_token.line_number,
                is_tentative=not has_initializer,
            )
        )
    return definitions


def _split_top_level(tokens: list[LexToken], separator: str) -> list[list[LexToken]]:
    chunks: list[list[LexToken]] = [[]]
    depths = {"(": 0, "[": 0, "{": 0}
    closing = {")": "(", "]": "[", "}": "{"}
    for token in tokens:
        value = token.value
        if value in depths:
            depths[value] += 1
        elif value in closing:
            opener = closing[value]
            depths[opener] = max(0, depths[opener] - 1)
        if value == separator and not any(depths.values()):
            chunks.append([])
            continue
        chunks[-1].append(token)
    return chunks


def _before_top_level_initializer(tokens: list[LexToken]) -> tuple[list[LexToken], bool]:
    depths = {"(": 0, "[": 0, "{": 0}
    closing = {")": "(", "]": "[", "}": "{"}
    for index, token in enumerate(tokens):
        value = token.value
        if value == "=" and not any(depths.values()):
            return tokens[:index], True
        if value in depths:
            depths[value] += 1
        elif value in closing:
            opener = closing[value]
            depths[opener] = max(0, depths[opener] - 1)
    return tokens, False


def _top_level_identifiers(tokens: list[LexToken]) -> list[LexToken]:
    result: list[LexToken] = []
    depths = {"(": 0, "[": 0, "{": 0}
    closing = {")": "(", "]": "[", "}": "{"}
    for token in tokens:
        value = token.value
        if value in depths:
            depths[value] += 1
            continue
        if value in closing:
            opener = closing[value]
            depths[opener] = max(0, depths[opener] - 1)
            continue
        if token.kind == "identifier" and not any(depths.values()):
            result.append(token)
    return result


def _contains_top_level(tokens: list[LexToken], target: str) -> bool:
    depths = {"(": 0, "[": 0, "{": 0}
    closing = {")": "(", "]": "[", "}": "{"}
    for token in tokens:
        value = token.value
        if value == target and not any(depths.values()):
            return True
        if value in depths:
            depths[value] += 1
        elif value in closing:
            opener = closing[value]
            depths[opener] = max(0, depths[opener] - 1)
            if value == target and not any(depths.values()):
                return True
    return False


def _normalize_type(value: str, storage: str | None) -> str:
    text = value
    if storage:
        text = re.sub(rf"\b{re.escape(storage)}\b", " ", text, count=1)
    return " ".join(text.split())
