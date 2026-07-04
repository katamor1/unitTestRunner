from __future__ import annotations

from .source_models import LexToken


def annotate_brace_depth(tokens: list[LexToken]) -> list[int]:
    depths: list[int] = []
    depth = 0
    for token in tokens:
        depths.append(depth)
        if token.value == "{":
            depth += 1
        elif token.value == "}":
            depth = max(0, depth - 1)
    return depths


def find_matching_token(tokens: list[LexToken], open_index: int, open_value: str, close_value: str) -> int:
    depth = 0
    for index in range(open_index, len(tokens)):
        value = tokens[index].value
        if value == open_value:
            depth += 1
        elif value == close_value:
            depth -= 1
            if depth == 0:
                return index
    return -1
