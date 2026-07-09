from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .c90_writer import sanitize_identifier, write_c_file

_FUNCTION_RE_TEMPLATE = r"void\s+{name}\s*\(\s*void\s*\)\s*\{{(?P<body>.*?)^\}}"
_LVALUE_RE = re.compile(r"^[A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*|\s*\[[A-Za-z0-9_+\-*/% ()]+\])*$")
_FORBIDDEN_FRAGMENT_RE = re.compile(r"[{}#;\n\r]")
_POINTER_CHAIN_RE = re.compile(r"\b(?P<root>[A-Za-z_]\w*)\s*->\s*(?P<field>[A-Za-z_]\w*)\s*->")
_EXTERN_POINTER_RE_TEMPLATE = r"(?m)^\s*(?:extern|EXTERN)\s+(?P<type>[^;\n()]*?)\s*\*\s*{name}\s*;"
_TYPEDEF_STRUCT_RE = re.compile(r"typedef\s+struct\s+(?:[A-Za-z_]\w*)?\s*\{(?P<body>.*?)\}\s*(?P<alias>[A-Za-z_]\w*)\s*;", re.DOTALL)
_FIELD_RE = re.compile(r"(?P<type>[A-Za-z_]\w*(?:\s+[A-Za-z_]\w*)*)\s*(?P<pointer>\*+)?\s*(?P<name>[A-Za-z_]\w*)\s*(?:\[[^\]]+\])?$")
_COMPACT_POINTER_FIELD_RE = re.compile(r"(?P<type>[A-Za-z_]\w*(?:\s+[A-Za-z_]\w*)*)\s*(?P<pointer>\*+)\s*(?P<name>[A-Za-z_]\w*)\s*(?:\[[^\]]+\])?$")
_INCLUDE_TARGET_RE = re.compile(r'^\s*#include\s+[<"]([^>"]+)[>"]', re.MULTILINE)


def reflect_state_setups(output_root: Path | str, test_case_design: Any, function_name: str | None = None) -> list[Path]:
    """Reflect test_cases[].state_setups[] into generated/tests/test_<Function>.c.

    This is intentionally conservative: unsafe lvalues/statements are emitted as review
    comments instead of executable C statements.  If state_setups does not already
    contain pointer fixture setup for expressions such as g_com->ptr->member, a
    simple fixture is inferred from copied target headers when possible.
    """
    output_root = Path(output_root).resolve()
    payload = _payload(test_case_design)
    function_name = function_name or payload.get("function", {}).get("name") or "unknown_function"
    test_source = output_root / "generated" / "tests" / f"test_{sanitize_identifier(function_name)}.c"
    if not test_source.exists():
        return []
    cases = payload.get("test_cases", [])
    inferred = _infer_pointer_fixture_state_setups(output_root, payload, function_name)
    if inferred:
        _append_inferred_state_setups(cases, inferred)
        _write_back_test_case_design(output_root, payload)
    if not any(case.get("state_setups") for case in cases):
        return []
    text = test_source.read_text(encoding="cp932", errors="replace")
    text = _ensure_fixture_includes(text, cases, output_root)
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


def _write_back_test_case_design(output_root: Path, payload: dict[str, Any]) -> None:
    path = output_root / "reports" / "test_case_design.json"
    if not path.exists():
        return
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_inferred_state_setups(cases: list[dict[str, Any]], inferred: list[dict[str, Any]]) -> None:
    for case in cases:
        setups = case.setdefault("state_setups", [])
        existing = {str(setup.get("variable_name")) for setup in setups if isinstance(setup, dict)}
        for setup in inferred:
            if setup.get("variable_name") not in existing:
                setups.append(dict(setup))


def _infer_pointer_fixture_state_setups(output_root: Path, payload: dict[str, Any], function_name: str) -> list[dict[str, Any]]:
    target_source = _target_source_text(output_root, payload)
    if not target_source:
        return []
    chains = _pointer_chains_for_function(target_source, function_name)
    if not chains:
        return []
    headers = _workspace_headers(output_root)
    if not headers:
        return []
    declarations = _extern_pointer_declarations(headers)
    structs = _typedef_structs(headers)
    result: list[dict[str, Any]] = []
    for root, field in sorted(chains):
        declaration = declarations.get(root)
        if declaration is None:
            continue
        root_type, header_path = declaration
        field_info = structs.get(root_type, {}).get(field)
        if field_info is None or not field_info.get("pointer"):
            continue
        pointee_type = str(field_info["type"])
        root_fixture = f"fixture_{sanitize_identifier(root)}"
        field_fixture = f"fixture_{sanitize_identifier(root)}_{sanitize_identifier(field)}"
        result.append(
            {
                "variable_name": root,
                "scope": "extern",
                "value_expression": f"&{root_fixture}",
                "setup_method_hint": "fixture_pointer",
                "source_candidate_id": None,
                "review_required": True,
                "confidence": "medium",
                "fixture_includes": [_relative_include_from_generated_tests(output_root, header_path)],
                "fixture_declarations": [f"static {pointee_type} {field_fixture}", f"static {root_type} {root_fixture}"],
                "setup_statements": [f"{root_fixture}.{field} = &{field_fixture}"],
                "inferred_from": f"{root}->{field}->...",
            }
        )
    return result


def _target_source_text(output_root: Path, payload: dict[str, Any]) -> str:
    source_path = Path(payload.get("source", {}).get("path") or "")
    candidates: list[Path] = []
    if source_path.as_posix():
        if source_path.is_absolute():
            candidates.append(output_root / "extracted" / source_path.name)
        else:
            candidates.append(output_root / "extracted" / source_path)
            candidates.append(output_root / "extracted" / source_path.name)
    candidates.extend((output_root / "extracted").rglob("*.c"))
    for candidate in candidates:
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="cp932", errors="replace")
            except OSError:
                continue
    return ""


def _pointer_chains_for_function(source_text: str, function_name: str) -> set[tuple[str, str]]:
    body = _function_body(source_text, function_name) or source_text
    return {(match.group("root"), match.group("field")) for match in _POINTER_CHAIN_RE.finditer(body)}


def _function_body(source_text: str, function_name: str) -> str:
    match = re.search(rf"\b{re.escape(function_name)}\s*\([^)]*\)\s*\{{", source_text)
    if not match:
        return ""
    start = match.end()
    depth = 1
    index = start
    while index < len(source_text):
        char = source_text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source_text[start:index]
        index += 1
    return ""


def _workspace_headers(output_root: Path) -> dict[Path, str]:
    headers: dict[Path, str] = {}
    for header in (output_root / "extracted").rglob("*.h"):
        try:
            headers[header] = header.read_text(encoding="cp932", errors="replace")
        except OSError:
            continue
    return headers


def _extern_pointer_declarations(headers: dict[Path, str]) -> dict[str, tuple[str, Path]]:
    names: dict[str, tuple[str, Path]] = {}
    candidate_names = set(re.findall(r"\b[A-Za-z_]\w*\b", "\n".join(headers.values())))
    for name in candidate_names:
        pattern = re.compile(_EXTERN_POINTER_RE_TEMPLATE.format(name=re.escape(name)))
        for path, text in headers.items():
            match = pattern.search(text)
            if match:
                root_type = " ".join(match.group("type").strip().split())
                if root_type:
                    names[name] = (root_type, path)
                break
    return names


def _typedef_structs(headers: dict[Path, str]) -> dict[str, dict[str, dict[str, Any]]]:
    structs: dict[str, dict[str, dict[str, Any]]] = {}
    for text in headers.values():
        for match in _TYPEDEF_STRUCT_RE.finditer(text):
            alias = match.group("alias")
            fields: dict[str, dict[str, Any]] = {}
            for raw_field in match.group("body").split(";"):
                field = _parse_field(raw_field)
                if field:
                    fields[field["name"]] = field
            structs[alias] = fields
    return structs


def _parse_field(raw_field: str) -> dict[str, Any] | None:
    text = " ".join(raw_field.strip().split())
    if not text:
        return None
    match = _FIELD_RE.match(text) or _COMPACT_POINTER_FIELD_RE.match(text)
    if not match:
        return None
    return {"type": match.group("type").strip(), "name": match.group("name"), "pointer": bool(match.group("pointer"))}


def _relative_include_from_generated_tests(output_root: Path, header_path: Path) -> str:
    try:
        relative = header_path.resolve().relative_to(output_root.resolve())
        return (Path("../..") / relative).as_posix()
    except (OSError, ValueError):
        return header_path.as_posix()


def _ensure_fixture_includes(text: str, cases: list[dict[str, Any]], output_root: Path) -> str:
    include_lines: list[str] = []
    for setup in _all_state_setups(cases):
        for include in _list(setup.get("fixture_includes")) + _list(setup.get("setup_includes")):
            include_text = _include_line(include)
            if include_text and include_text not in include_lines:
                include_lines.append(include_text)
    if not include_lines:
        return text
    fixture_basenames = {_include_basename(line) for line in include_lines}
    text = _remove_redundant_fixture_include_lines(text, fixture_basenames, output_root)
    existing = set(re.findall(r'^#include\s+[^\n]+', text, flags=re.MULTILINE))
    provided_basenames = _provided_include_basenames(text, output_root)
    additions = [line for line in include_lines if line not in existing and _include_basename(line) not in provided_basenames]
    if not additions:
        return text
    include_matches = list(re.finditer(r'^#include\s+[^\n]+\n?', text, flags=re.MULTILINE))
    if include_matches:
        insert_at = include_matches[-1].end()
        return text[:insert_at] + "".join(line + "\n" for line in additions) + text[insert_at:]
    return "".join(line + "\n" for line in additions) + "\n" + text


def _remove_redundant_fixture_include_lines(text: str, fixture_basenames: set[str], output_root: Path) -> str:
    if not fixture_basenames:
        return text
    text_without_fixture_includes = _remove_include_lines_by_basename(text, fixture_basenames)
    provided_elsewhere = _provided_include_basenames(text_without_fixture_includes, output_root)
    redundant_basenames = fixture_basenames & provided_elsewhere
    if not redundant_basenames:
        return text
    return _remove_include_lines_by_basename(text, redundant_basenames)


def _remove_include_lines_by_basename(text: str, basenames: set[str]) -> str:
    if not basenames:
        return text
    result: list[str] = []
    for line in text.splitlines(keepends=True):
        match = _INCLUDE_TARGET_RE.match(line)
        if match and Path(match.group(1)).name in basenames:
            continue
        result.append(line)
    return "".join(result)


def _provided_include_basenames(text: str, output_root: Path) -> set[str]:
    basenames: set[str] = set()
    pending = list(_include_targets(text))
    visited: set[Path] = set()
    while pending:
        target = pending.pop(0)
        basenames.add(Path(target).name)
        resolved = _resolve_include_target(output_root, target)
        if resolved is None or resolved in visited:
            continue
        visited.add(resolved)
        try:
            nested_text = resolved.read_text(encoding="cp932", errors="replace")
        except OSError:
            continue
        for nested in _include_targets(nested_text):
            if Path(nested).name not in basenames:
                pending.append(nested)
    return basenames


def _include_targets(text: str) -> list[str]:
    return [match.group(1) for match in _INCLUDE_TARGET_RE.finditer(text)]


def _include_basename(include_line: str) -> str:
    targets = _include_targets(include_line)
    return Path(targets[0]).name if targets else include_line


def _resolve_include_target(output_root: Path, target: str) -> Path | None:
    target_path = Path(target)
    candidates = [
        output_root / "generated" / "harness" / target_path,
        output_root / "generated" / "include" / target_path,
        output_root / "generated" / "stubs" / target_path,
        output_root / "generated" / "tests" / target_path,
        output_root / "generated" / "tests" / target_path.name,
        output_root / "generated" / "harness" / target_path.name,
        output_root / "extracted" / target_path,
        output_root / "extracted" / target_path.name,
    ]
    candidates.extend((output_root / "extracted").rglob(target_path.name))
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


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
    insert_index = _first_executable_line_index(lines)
    block = ["    /* state_setups auto reflection */"] + declarations + statements + [""]
    return "\n".join(lines[:insert_index] + block + lines[insert_index:])


def _fixture_declaration_lines(state_setups: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for setup in state_setups:
        for declaration in _list(setup.get("fixture_declarations")):
            if _forbidden_statement_fragment(declaration):
                lines.append(f"    /* review required: skipped unsafe fixture declaration: {declaration} */")
            else:
                lines.append(f"    {declaration.rstrip(';')};")
    return lines


def _state_setup_statement_lines(state_setups: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for setup in state_setups:
        for statement in _list(setup.get("setup_statements")):
            if _forbidden_statement_fragment(statement):
                lines.append(f"    /* review required: skipped unsafe setup statement: {statement} */")
            else:
                lines.append(f"    {statement.rstrip(';')};")
        variable = str(setup.get("variable_name") or "")
        value = str(setup.get("value_expression") or "")
        if not variable:
            continue
        if not _safe_lvalue(variable) or _forbidden_statement_fragment(value):
            lines.append(f"    /* review required: skipped unsafe state setup for {variable}: {value} */")
            continue
        lines.append(f"    {variable} = {value};")
    return lines


def _first_executable_line_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("/*") or stripped.startswith("//"):
            continue
        if re.match(r"(?:static\s+)?[A-Za-z_]\w*(?:\s+[A-Za-z_]\w*|\s*\*)*\s+[A-Za-z_]\w*(?:\[[^\]]+\])?\s*(?:=\s*[^;]+)?;", stripped):
            continue
        return index
    return len(lines)


def _safe_lvalue(value: str) -> bool:
    return bool(_LVALUE_RE.match(value))


def _forbidden_statement_fragment(value: str) -> bool:
    return bool(_FORBIDDEN_FRAGMENT_RE.search(str(value)))


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _all_state_setups(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    setups: list[dict[str, Any]] = []
    for case in cases:
        for setup in case.get("state_setups") or []:
            if isinstance(setup, dict):
                setups.append(setup)
    return setups


def _include_line(include: str) -> str | None:
    text = str(include).strip()
    if not text:
        return None
    if text.startswith("#include"):
        return text
    if text.startswith("<") or text.startswith('"'):
        return f"#include {text}"
    return f'#include "{text}"'
