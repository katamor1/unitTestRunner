from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .c90_writer import sanitize_identifier, write_c_file

_FUNCTION_RE_TEMPLATE = r"void\s+{name}\s*\(\s*void\s*\)\s*\{{(?P<body>.*?)^\}}"
_LVALUE_RE = re.compile(r"^[A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*|\s*\[[A-Za-z0-9_+\-*/% ()]+\])*$")
_FORBIDDEN_FRAGMENT_RE = re.compile(r"[{}#;\n\r]")


def reflect_state_setups(output_root: Path | str, test_case_design: Any, function_name: str | None = None) -> list[Path]:
    """Reflect test_cases[].state_setups[] into generated/tests/test_<Function>.c.

    This is intentionally conservative: unsafe lvalues/statements are emitted as review
    comments instead of executable C statements.
    """
    output_root = Path(output_root).resolve()
    payload = _payload(test_case_design)
    function_name = function_name or payload.get("function", {}).get("name") or "unknown_function"
    test_source = output_root / "generated" / "tests" / f"test_{sanitize_identifier(function_name)}.c"
    if not test_source.exists():
        return []
    cases = payload.get("test_cases", [])
    if not any(case.get("state_setups") for case in cases):
        return []
    text = test_source.read_text(encoding="cp932", errors="replace")
    text = _ensure_fixture_includes(text, cases)
    for case in cases:
        text = _reflect_case(text, case)
    write_c_file(test_source, text, overwrite=True)
    return [test_source]


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return value
    raise TypeError(f"Unsupported test case design type: {type(value)!r}")


def _ensure_fixture_includes(text: str, cases: list[dict[str, Any]]) -> str:
    include_lines: list[str] = []
    for setup in _all_state_setups(cases):
        for include in _list(setup.get("fixture_includes")) + _list(setup.get("setup_includes")):
            include_text = _include_line(include)
            if include_text and include_text not in include_lines:
                include_lines.append(include_text)
    if not include_lines:
        return text
    existing = set(re.findall(r'^#include\s+[^\n]+', text, flags=re.MULTILINE))
    additions = [line for line in include_lines if line not in existing]
    if not additions:
        return text
    include_matches = list(re.finditer(r'^#include\s+[^\n]+\n?', text, flags=re.MULTILINE))
    if include_matches:
        insert_at = include_matches[-1].end()
        return text[:insert_at] + "".join(line + "\n" for line in additions) + text[insert_at:]
    return "".join(line + "\n" for line in additions) + "\n" + text


def _reflect_case(text: str, case: dict[str, Any]) -> str:
    state_setups = case.get("state_setups") or []
    if not state_setups:
        return text
    test_case_id = case.get("test_case_id") or case.get("id")
    if not test_case_id:
        return text
    function_name = f"Test_{sanitize_identifier(test_case_id)}"
    pattern = re.compile(_FUNCTION_RE_TEMPLATE.format(name=re.escape(function_name)), re.DOTALL | re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return text
    body = match.group("body")
    reflected = _reflect_body(body, state_setups)
    if reflected == body:
        return text
    return text[: match.start("body")] + reflected + text[match.end("body") :]


def _reflect_body(body: str, state_setups: list[dict[str, Any]]) -> str:
    if "/* state_setups auto reflection */" in body:
        return body
    lines = body.splitlines()
    declarations = _fixture_declaration_lines(state_setups)
    statements = _state_setup_statement_lines(state_setups)
    if not declarations and not statements:
        return body
    declaration_insert = _declaration_insert_index(lines)
    if declarations:
        for line in reversed(declarations):
            lines.insert(declaration_insert, line)
        declaration_insert += len(declarations)
    statement_insert = _statement_insert_index(lines, declaration_insert)
    block = ["    /* state_setups auto reflection */", *statements, ""] if statements else []
    for line in reversed(block):
        lines.insert(statement_insert, line)
    return "\n".join(lines) + ("\n" if body.endswith("\n") else "")


def _declaration_insert_index(lines: list[str]) -> int:
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            return index
        if _looks_like_declaration(stripped):
            index += 1
            continue
        return index
    return len(lines)


def _statement_insert_index(lines: list[str], start: int) -> int:
    index = start
    while index < len(lines) and not lines[index].strip():
        index += 1
    while index < len(lines):
        stripped = lines[index].strip()
        if re.match(r"Stub_\w+_Reset\s*\(\s*\)\s*;", stripped):
            index += 1
            continue
        break
    return index


def _fixture_declaration_lines(state_setups: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for setup in state_setups:
        for declaration in _list(setup.get("fixture_declarations")):
            line = _declaration_line(declaration)
            if line and line not in lines:
                lines.append(line)
    return lines


def _state_setup_statement_lines(state_setups: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for setup in state_setups:
        hint = str(setup.get("setup_method_hint") or "direct_assignment")
        variable_name = str(setup.get("variable_name") or "").strip()
        if hint == "not_directly_accessible":
            lines.append(f"    /* REVIEW REQUIRED: {variable_name or 'state'} is not directly accessible. */")
            continue
        for statement in _list(setup.get("setup_statements")):
            lines.append(_statement_line(statement))
        if hint == "custom_statements":
            continue
        target = str(setup.get("target_expression") or variable_name).strip()
        value = str(setup.get("value_expression") or "").strip()
        if target and value:
            if _safe_lvalue(target) and _safe_expression(value):
                lines.append(f"    {target} = {value};")
            else:
                lines.append(f"    /* REVIEW REQUIRED: state setup was not auto-reflected for {variable_name or target}. */")
    return [line for line in lines if line]


def _statement_line(statement: object) -> str:
    text = _strip_semicolon(str(statement or "").strip())
    if not text:
        return ""
    if "=" in text:
        lhs, rhs = text.split("=", 1)
        if _safe_lvalue(lhs.strip()) and _safe_expression(rhs.strip()):
            return f"    {lhs.strip()} = {rhs.strip()};"
    if _FORBIDDEN_FRAGMENT_RE.search(text):
        return "    /* REVIEW REQUIRED: unsafe state setup statement was omitted. */"
    return f"    {text};"


def _declaration_line(declaration: object) -> str:
    text = _strip_semicolon(str(declaration or "").strip())
    if not text or _FORBIDDEN_FRAGMENT_RE.search(text) or "=" in text:
        return ""
    return f"    {text};"


def _include_line(include: object) -> str:
    text = str(include or "").strip().replace("\\", "/")
    if not text or "\n" in text or "\r" in text:
        return ""
    if text.startswith("#include"):
        return text
    if text.startswith("<") and text.endswith(">"):
        return f"#include {text}"
    if text.startswith('"') and text.endswith('"'):
        return f"#include {text}"
    return f'#include "{text}"'


def _looks_like_declaration(stripped: str) -> bool:
    if not stripped.endswith(";"):
        return False
    if stripped.startswith(("return ", "if ", "for ", "while ", "switch ", "UTR_", "Stub_")):
        return False
    return "=" not in stripped and "(" not in stripped


def _safe_lvalue(value: str) -> bool:
    return _LVALUE_RE.match(value.strip()) is not None


def _safe_expression(value: str) -> bool:
    return bool(value.strip()) and _FORBIDDEN_FRAGMENT_RE.search(value) is None


def _strip_semicolon(value: str) -> str:
    return value[:-1].strip() if value.endswith(";") else value


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _all_state_setups(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for case in cases:
        for setup in case.get("state_setups") or []:
            if isinstance(setup, dict):
                result.append(setup)
    return result
