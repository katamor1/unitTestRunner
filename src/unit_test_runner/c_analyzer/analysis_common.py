from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .function_models import SourcePosition, SourceRange
from .source_models import SourceDigest, LexToken


KEYWORDS = {
    "auto",
    "break",
    "case",
    "char",
    "const",
    "continue",
    "default",
    "do",
    "double",
    "else",
    "enum",
    "extern",
    "float",
    "for",
    "goto",
    "if",
    "int",
    "long",
    "register",
    "return",
    "short",
    "signed",
    "sizeof",
    "static",
    "struct",
    "switch",
    "typedef",
    "union",
    "unsigned",
    "void",
    "volatile",
    "while",
}

CONTROL_KEYWORDS = {"if", "while", "switch", "for", "sizeof", "return"}
STORAGE_CLASSES = {"static", "extern", "register", "auto"}
TYPE_QUALIFIERS = {"const", "volatile"}
CALLING_CONVENTIONS = {"__stdcall", "__cdecl", "__fastcall", "stdcall", "cdecl", "fastcall", "WINAPI", "CALLBACK"}
BASIC_TYPE_WORDS = {
    "void",
    "char",
    "short",
    "int",
    "long",
    "float",
    "double",
    "signed",
    "unsigned",
}


def path_text(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def normalize_space(value: str) -> str:
    return " ".join(value.replace("\r\n", "\n").replace("\r", "\n").split())


def selected_candidate(location: Any) -> Any:
    candidate = getattr(location, "selected_candidate", None)
    if candidate is None:
        raise ValueError(f"Function not found: {getattr(location, 'function_name', '<unknown>')}")
    if getattr(candidate, "body_range", None) is None:
        raise ValueError(f"Function body not available: {getattr(location, 'function_name', '<unknown>')}")
    return candidate


def slice_range(text: str, source_range: SourceRange, include_end: bool = True) -> str:
    end = source_range.end.offset if include_end else max(source_range.start.offset, source_range.end.offset - 1)
    return text[source_range.start.offset : end]


def body_text(digest: SourceDigest, location: Any, masked: bool = False) -> str:
    candidate = selected_candidate(location)
    body_range = candidate.body_range
    assert body_range is not None
    text = digest.masked_source.masked_text if masked else digest.source.text
    start = body_range.start.offset + 1
    end = max(start, body_range.end.offset - 1)
    return text[start:end]


def body_base_offset(location: Any) -> int:
    candidate = selected_candidate(location)
    body_range = candidate.body_range
    assert body_range is not None
    return body_range.start.offset + 1


def range_from_offsets(text: str, start: int, end: int) -> SourceRange:
    return SourceRange(position_from_offset(text, start), position_from_offset(text, end))


def position_from_offset(text: str, offset: int) -> SourcePosition:
    offset = max(0, min(offset, len(text)))
    line = text.count("\n", 0, offset) + 1
    line_start = text.rfind("\n", 0, offset)
    column = offset + 1 if line_start == -1 else offset - line_start
    return SourcePosition(line, column, offset)


def line_at(text: str, base_line: int, relative_offset: int) -> int:
    return base_line + text.count("\n", 0, relative_offset)


def identifiers_in(text: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r"\b[A-Za-z_]\w*\b", text):
        name = match.group(0)
        if name in KEYWORDS:
            continue
        if name not in names:
            names.append(name)
    return names


def split_top_level(text: str, delimiter: str = ",") -> list[str]:
    parts: list[str] = []
    start = 0
    paren = bracket = brace = 0
    for index, char in enumerate(text):
        if char == "(":
            paren += 1
        elif char == ")" and paren:
            paren -= 1
        elif char == "[":
            bracket += 1
        elif char == "]" and bracket:
            bracket -= 1
        elif char == "{":
            brace += 1
        elif char == "}" and brace:
            brace -= 1
        elif char == delimiter and paren == 0 and bracket == 0 and brace == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def find_matching_char(text: str, open_index: int, open_char: str = "(", close_char: str = ")") -> int:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
    return -1


def tokens_in_body(digest: SourceDigest, location: Any) -> list[LexToken]:
    candidate = selected_candidate(location)
    body_range = candidate.body_range
    assert body_range is not None
    start = body_range.start.offset
    end = body_range.end.offset
    return [token for token in digest.tokens if start < token.start_offset < end]


def snippet_around_statement(text: str, start: int, end: int) -> str:
    left = max(text.rfind(";", 0, start), text.rfind("{", 0, start), text.rfind("}", 0, start), text.rfind("\n", 0, start))
    right_candidates = [pos for pos in (text.find(";", end), text.find("\n", end), text.find("}", end)) if pos != -1]
    right = min(right_candidates) if right_candidates else min(len(text), end + 80)
    return normalize_space(text[left + 1 : right + 1])


def is_type_like(raw: str) -> bool:
    words = [word for word in re.findall(r"\b[A-Za-z_]\w*\b", raw) if word not in STORAGE_CLASSES and word not in TYPE_QUALIFIERS and word not in CALLING_CONVENTIONS]
    return bool(words and (words[0] in BASIC_TYPE_WORDS or words[0] in {"struct", "union", "enum"} or words[0][:1].isupper()))
