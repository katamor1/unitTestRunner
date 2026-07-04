from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .source_models import IncludeDirective, MacroDefinition, PreprocessorDirective, SourceWarning


DIRECTIVE_RE = re.compile(r"^\s*#\s*(?P<kind>[A-Za-z_]\w*)\s*(?P<argument>.*)$")
KNOWN_DIRECTIVES = {"include", "define", "undef", "if", "ifdef", "ifndef", "elif", "else", "endif", "pragma", "error"}


def scan_preprocessor(
    original_text: str,
    masked_text: str,
    source_path: Path | str,
    build_context: dict[str, Any] | None = None,
) -> tuple[list[PreprocessorDirective], list[IncludeDirective], list[MacroDefinition], list[SourceWarning]]:
    build_context = build_context or {}
    defines = set(build_context.get("defines", []))
    include_dirs = _include_dirs(build_context)
    source_dir = Path(source_path).resolve().parent
    directives: list[PreprocessorDirective] = []
    includes: list[IncludeDirective] = []
    macros: list[MacroDefinition] = []
    warnings: list[SourceWarning] = []
    conditional_stack: list[str] = []

    original_lines = original_text.splitlines()
    masked_lines = masked_text.splitlines()
    for index, masked_line in enumerate(masked_lines):
        match = DIRECTIVE_RE.match(masked_line)
        if not match:
            continue
        raw = _logical_raw(original_lines, index)
        raw_match = DIRECTIVE_RE.match(raw) or match
        kind = raw_match.group("kind").lower()
        argument = raw_match.group("argument").strip()
        active_state = _current_active(conditional_stack)
        nesting = len(conditional_stack)

        if kind in {"if", "ifdef", "ifndef"}:
            active_state = _evaluate_condition(kind, argument, defines)
            conditional_stack.append(active_state)
            nesting = len(conditional_stack)
        elif kind in {"elif", "else"}:
            if not conditional_stack:
                warnings.append(SourceWarning("conditional_stack_underflow", f"#{kind} without opening conditional.", index + 1, 1, raw))
                active_state = "unknown"
            else:
                active_state = _flip_state(conditional_stack[-1]) if kind == "else" else _evaluate_condition("if", argument, defines)
                conditional_stack[-1] = active_state
            nesting = len(conditional_stack)
        elif kind == "endif":
            if not conditional_stack:
                warnings.append(SourceWarning("conditional_stack_underflow", "#endif without opening conditional.", index + 1, 1, raw))
                active_state = "unknown"
            else:
                active_state = conditional_stack.pop()
            nesting = len(conditional_stack)

        directives.append(PreprocessorDirective(kind if kind in KNOWN_DIRECTIVES else "unknown", index + 1, 1, raw, argument, active_state, nesting))

        if kind == "include":
            include = _include(argument, source_dir, include_dirs, index + 1, active_state)
            includes.append(include)
            if include.style == "quote" and include.exists is False:
                warnings.append(SourceWarning("include_not_found", f"Include not found: {include.target}", index + 1, 1, raw))
        elif kind == "define":
            macro = _macro(argument, index + 1, active_state)
            if macro is not None:
                macros.append(macro)

    for state in conditional_stack:
        warnings.append(SourceWarning("conditional_stack_unclosed", f"Conditional block left open with state {state}."))
    return directives, includes, macros, warnings


def _logical_raw(lines: list[str], index: int) -> str:
    parts = []
    while index < len(lines):
        line = lines[index]
        parts.append(line)
        if not line.rstrip().endswith("\\"):
            break
        index += 1
    return "\n".join(parts)


def _include(argument: str, source_dir: Path, include_dirs: list[Path], line_number: int, active_state: str) -> IncludeDirective:
    style = "unknown"
    target = argument
    candidates: list[Path] = []
    exists: bool | None = None
    if argument.startswith('"') and '"' in argument[1:]:
        style = "quote"
        target = argument.split('"', 2)[1]
        candidates = [source_dir / target] + [path / target for path in include_dirs]
        exists = any(path.exists() for path in candidates)
    elif argument.startswith("<") and ">" in argument:
        style = "angle"
        target = argument[1:].split(">", 1)[0]
        candidates = [path / target for path in include_dirs]
        exists = any(path.exists() for path in candidates) if candidates else None
    elif argument:
        style = "macro"
    return IncludeDirective(target, style, line_number, [path.resolve() for path in candidates], exists, active_state)


def _macro(argument: str, line_number: int, active_state: str) -> MacroDefinition | None:
    match = re.match(r"(?P<name>[A-Za-z_]\w*)(?P<params>\([^)]*\))?\s*(?P<value>.*)$", argument)
    if not match:
        return None
    params = match.group("params")
    parameters = [part.strip() for part in params.strip("()").split(",") if part.strip()] if params else None
    return MacroDefinition(match.group("name"), match.group("value").strip() or None, parameters, line_number, params is not None, active_state)


def _evaluate_condition(kind: str, argument: str, defines: set[str]) -> str:
    if kind == "ifdef":
        return "active" if argument.strip() in defines else "inactive"
    if kind == "ifndef":
        return "inactive" if argument.strip() in defines else "active"
    expression = " ".join(argument.split())
    if expression == "0":
        return "inactive"
    if expression == "1":
        return "active"
    match = re.fullmatch(r"defined\s*\(\s*([A-Za-z_]\w*)\s*\)", expression)
    if match:
        return "active" if match.group(1) in defines else "inactive"
    match = re.fullmatch(r"!\s*defined\s*\(\s*([A-Za-z_]\w*)\s*\)", expression)
    if match:
        return "inactive" if match.group(1) in defines else "active"
    return "unknown"


def _current_active(stack: list[str]) -> str:
    if "inactive" in stack:
        return "inactive"
    if "unknown" in stack:
        return "unknown"
    return "active"


def _flip_state(state: str) -> str:
    if state == "active":
        return "inactive"
    if state == "inactive":
        return "active"
    return "unknown"


def _include_dirs(build_context: dict[str, Any]) -> list[Path]:
    result = []
    for item in build_context.get("include_dirs", []):
        if isinstance(item, dict) and item.get("absolute"):
            result.append(Path(item["absolute"]))
        elif isinstance(item, str):
            result.append(Path(item))
    return result
