from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..encoding import read_text_auto


KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
    "case",
    "do",
}


def _read_text(path: Path) -> str:
    return read_text_auto(path)


def mask_comments_and_strings(text: str) -> str:
    chars = list(text)
    i = 0
    state = "code"
    quote = ""
    while i < len(chars):
        current = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if state == "code":
            if current == "/" and nxt == "*":
                chars[i] = chars[i + 1] = " "
                i += 2
                state = "block_comment"
                continue
            if current == "/" and nxt == "/":
                chars[i] = chars[i + 1] = " "
                i += 2
                state = "line_comment"
                continue
            if current in ("'", '"'):
                quote = current
                chars[i] = " "
                i += 1
                state = "string"
                continue
        elif state == "block_comment":
            if current == "*" and nxt == "/":
                chars[i] = chars[i + 1] = " "
                i += 2
                state = "code"
                continue
            if current != "\n":
                chars[i] = " "
        elif state == "line_comment":
            if current == "\n":
                state = "code"
            else:
                chars[i] = " "
        elif state == "string":
            if current == "\\":
                chars[i] = " "
                if i + 1 < len(chars) and chars[i + 1] != "\n":
                    chars[i + 1] = " "
                    i += 2
                    continue
            elif current == quote:
                chars[i] = " "
                state = "code"
                i += 1
                continue
            elif current != "\n":
                chars[i] = " "
        i += 1
    return "".join(chars)


FUNCTION_RE = re.compile(
    r"(?m)^[ \t]*(?P<prefix>(?:(?:static|extern|const|unsigned|signed|long|short|void|char|int|float|double|struct\s+\w+|enum\s+\w+|[A-Za-z_]\w*)[ \t\*]+)+)"
    r"(?P<name>[A-Za-z_]\w*)[ \t]*\((?P<params>[^;{}]*)\)[ \t\r\n]*\{"
)


def _find_matching(text: str, start: int, open_char: str, close_char: str) -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == open_char:
            depth += 1
        elif text[index] == close_char:
            depth -= 1
            if depth == 0:
                return index
    return -1


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _parse_parameter(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    array = bool(re.search(r"\[[^\]]*\]\s*$", raw))
    raw_no_array = re.sub(r"\s*\[[^\]]*\]\s*$", "", raw)
    match = re.match(r"(?P<type>.+?)(?P<name>[A-Za-z_]\w*)$", raw_no_array)
    if not match:
        return {"name": raw, "type": "", "is_pointer": "*" in raw, "is_array": array, "is_const": "const" in raw.split()}
    type_text = " ".join(match.group("type").replace("*", " * ").split())
    name = match.group("name")
    if type_text.endswith("*"):
        type_text = type_text[:-1].rstrip() + " *"
    return {
        "name": name,
        "type": type_text,
        "is_pointer": "*" in match.group("type"),
        "is_array": array,
        "is_const": "const" in type_text.split(),
    }


def _parse_parameters(raw: str) -> list[dict[str, Any]]:
    raw = raw.strip()
    if not raw or raw == "void":
        return []
    return [_parse_parameter(part) for part in raw.split(",")]


def _return_type(prefix: str) -> tuple[str, bool]:
    words = prefix.strip()
    is_static = bool(re.search(r"\bstatic\b", words))
    words = re.sub(r"\b(static|extern)\b", "", words)
    return " ".join(words.split()), is_static


def list_functions(source_path: Path | str) -> list[dict[str, Any]]:
    text = _read_text(Path(source_path))
    masked = mask_comments_and_strings(text)
    functions: list[dict[str, Any]] = []
    for match in FUNCTION_RE.finditer(masked):
        name = match.group("name")
        if name in KEYWORDS:
            continue
        open_brace = masked.find("{", match.end() - 1)
        close_brace = _find_matching(masked, open_brace, "{", "}")
        if close_brace == -1:
            continue
        return_type, is_static = _return_type(match.group("prefix"))
        functions.append(
            {
                "name": name,
                "return_type": return_type,
                "parameters": _parse_parameters(match.group("params")),
                "start_line": _line_number(masked, match.start()),
                "end_line": _line_number(masked, close_brace),
                "start_index": match.start(),
                "body_start_index": open_brace,
                "end_index": close_brace + 1,
                "static": is_static,
                "signature": text[match.start() : open_brace].strip(),
            }
        )
    return functions


def _extract_file_scope_globals(masked: str, before_index: int) -> list[str]:
    prefix = masked[:before_index]
    globals_: list[str] = []
    declaration = re.compile(
        r"(?m)^[ \t]*(?:static\s+|extern\s+)?(?:const\s+)?(?:struct\s+\w+|enum\s+\w+|[A-Za-z_]\w+)"
        r"(?:[ \t\*]+)(?P<name>[A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?:=|;)"
    )
    for match in declaration.finditer(prefix):
        line = match.group(0)
        if "(" in line:
            continue
        name = match.group("name")
        if name not in globals_:
            globals_.append(name)
    return globals_


def _extract_local_names(masked_body: str, parameters: list[dict[str, Any]]) -> set[str]:
    names = {parameter["name"] for parameter in parameters}
    declaration = re.compile(
        r"(?m)^[ \t]*(?:const\s+)?(?:struct\s+\w+|enum\s+\w+|[A-Za-z_]\w+)(?:[ \t\*]+)(?P<name>[A-Za-z_]\w*)\s*(?:=|;|,|\[)"
    )
    for match in declaration.finditer(masked_body):
        names.add(match.group("name"))
    return names


def _line_at(body_prefix: str, source_start_line: int, index: int) -> int:
    return source_start_line + body_prefix.count("\n", 0, index)


def _extract_calls(masked_body: str, source_start_line: int, defined_functions: dict[str, dict[str, Any]], current_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    external: list[dict[str, Any]] = []
    static_calls: list[dict[str, Any]] = []
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", masked_body):
        name = match.group(1)
        if name in KEYWORDS or name == current_name:
            continue
        call = {"name": name, "line": _line_at(masked_body, source_start_line, match.start())}
        if name in defined_functions and defined_functions[name].get("static"):
            if call not in static_calls:
                static_calls.append(call)
        elif name not in defined_functions:
            if call not in external:
                external.append(call)
    return external, static_calls


def _extract_balanced_keyword_expressions(masked_body: str, source_start_line: int, keyword: str) -> list[dict[str, Any]]:
    results = []
    for match in re.finditer(rf"\b{keyword}\s*\(", masked_body):
        open_index = masked_body.find("(", match.start())
        close_index = _find_matching(masked_body, open_index, "(", ")")
        if close_index == -1:
            continue
        expression = " ".join(masked_body[open_index + 1 : close_index].split())
        results.append({"expression": expression, "condition": expression, "line": _line_at(masked_body, source_start_line, match.start())})
    return results


def _extract_globals(masked_body: str, globals_: list[str]) -> tuple[list[str], list[str]]:
    reads: list[str] = []
    writes: list[str] = []
    for name in globals_:
        if not re.search(rf"\b{re.escape(name)}\b", masked_body):
            continue
        if name not in reads:
            reads.append(name)
        write_patterns = [
            rf"\b{re.escape(name)}\b\s*(?:\+\+|--|[+\-*/%&|^]?=)",
            rf"(?:\+\+|--)\s*\b{re.escape(name)}\b",
        ]
        if any(re.search(pattern, masked_body) for pattern in write_patterns):
            writes.append(name)
    return reads, writes


def _extract_returns(masked_body: str, source_start_line: int) -> list[dict[str, Any]]:
    returns = []
    for index, match in enumerate(re.finditer(r"\breturn\b\s*([^;]*);", masked_body), start=1):
        returns.append(
            {
                "id": f"RET-{index:03d}",
                "line": _line_at(masked_body, source_start_line, match.start()),
                "expression": " ".join(match.group(1).split()),
            }
        )
    return returns


def analyze_function(source_path: Path | str, function_name: str) -> dict[str, Any]:
    source_path = Path(source_path)
    text = _read_text(source_path)
    masked = mask_comments_and_strings(text)
    functions = list_functions(source_path)
    function_map = {function["name"]: function for function in functions}
    if function_name not in function_map:
        raise ValueError(f"Function not found: {function_name}")
    target = function_map[function_name]
    body_masked = masked[target["body_start_index"] + 1 : target["end_index"] - 1]
    globals_ = _extract_file_scope_globals(masked, target["start_index"])
    local_names = _extract_local_names(body_masked, target["parameters"])
    globals_ = [name for name in globals_ if name not in local_names]
    globals_read, globals_written = _extract_globals(body_masked, globals_)
    external_calls, static_calls = _extract_calls(body_masked, target["start_line"], function_map, function_name)
    branches = _extract_balanced_keyword_expressions(body_masked, target["start_line"], "if")
    for index, branch in enumerate(branches, start=1):
        branch["id"] = f"BR-{index:03d}"
    switches = _extract_balanced_keyword_expressions(body_masked, target["start_line"], "switch")
    cases = [
        {"value": " ".join(match.group(1).split()), "line": _line_at(body_masked, target["start_line"], match.start())}
        for match in re.finditer(r"\bcase\s+([^:]+):", body_masked)
    ]
    if re.search(r"\bdefault\s*:", body_masked):
        default_match = re.search(r"\bdefault\s*:", body_masked)
        if default_match:
            cases.append({"value": "default", "line": _line_at(body_masked, target["start_line"], default_match.start())})
    loops = _extract_balanced_keyword_expressions(body_masked, target["start_line"], "for")
    loops.extend(_extract_balanced_keyword_expressions(body_masked, target["start_line"], "while"))
    for loop in loops:
        loop["condition"] = loop["expression"]
    result = dict(target)
    result.pop("start_index", None)
    result.pop("body_start_index", None)
    result.pop("end_index", None)
    result.update(
        {
            "globals_read": globals_read,
            "globals_written": globals_written,
            "external_calls": external_calls,
            "static_calls": static_calls,
            "branches": branches,
            "switches": switches,
            "cases": cases,
            "loops": loops,
            "returns": _extract_returns(body_masked, target["start_line"]),
            "diagnostics": [],
        }
    )
    return result
