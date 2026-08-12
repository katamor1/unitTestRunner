from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .source_models import IncludeDirective, MacroDefinition, PreprocessorDirective, SourceWarning


DIRECTIVE_RE = re.compile(r"^\s*#\s*(?P<kind>[A-Za-z_]\w*)\s*(?P<argument>.*)$")
KNOWN_DIRECTIVES = {"include", "define", "undef", "if", "ifdef", "ifndef", "elif", "else", "endif", "pragma", "error"}


@dataclass
class _ConditionalFrame:
    current_state: str
    prior_taken: str


def scan_preprocessor(
    original_text: str,
    masked_text: str,
    source_path: Path | str,
    build_context: dict[str, Any] | None = None,
) -> tuple[list[PreprocessorDirective], list[IncludeDirective], list[MacroDefinition], list[SourceWarning]]:
    build_context = build_context or {}
    defines_complete = "defines" in build_context
    define_values = _define_values(build_context.get("defines", []))
    include_dirs = _include_dirs(build_context)
    source_dir = Path(source_path).resolve().parent
    directives: list[PreprocessorDirective] = []
    includes: list[IncludeDirective] = []
    macros: list[MacroDefinition] = []
    warnings: list[SourceWarning] = []
    conditional_stack: list[_ConditionalFrame] = []

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
            branch_state = _evaluate_condition(kind, argument, define_values, defines_complete)
            conditional_stack.append(_ConditionalFrame(branch_state, branch_state))
            active_state = _current_active(conditional_stack)
            nesting = len(conditional_stack)
        elif kind in {"elif", "else"}:
            if not conditional_stack:
                warnings.append(SourceWarning("conditional_stack_underflow", f"#{kind} without opening conditional.", index + 1, 1, raw))
                active_state = "unknown"
            else:
                frame = conditional_stack[-1]
                if kind == "else":
                    frame.current_state = _flip_state(frame.prior_taken)
                    frame.prior_taken = "active"
                else:
                    condition = _evaluate_condition("if", argument, define_values, defines_complete)
                    frame.current_state = _remaining_branch_state(frame.prior_taken, condition)
                    frame.prior_taken = _or_state(frame.prior_taken, condition)
                active_state = _current_active(conditional_stack)
            nesting = len(conditional_stack)
        elif kind == "endif":
            if not conditional_stack:
                warnings.append(SourceWarning("conditional_stack_underflow", "#endif without opening conditional.", index + 1, 1, raw))
                active_state = "unknown"
            else:
                active_state = _current_active(conditional_stack)
                conditional_stack.pop()
            nesting = len(conditional_stack)

        directives.append(PreprocessorDirective(kind if kind in KNOWN_DIRECTIVES else "unknown", index + 1, 1, raw, argument, active_state, nesting))

        if kind in {"if", "elif"} and active_state == "unknown":
            warnings.append(SourceWarning("preprocessor_condition_unknown", f"Preprocessor condition could not be resolved: {argument}", index + 1, 1, raw))

        if kind == "include":
            include = _include(argument, source_dir, include_dirs, index + 1, active_state)
            includes.append(include)
            if include.style == "quote" and include.exists is False:
                warnings.append(SourceWarning("include_not_found", f"Include not found: {include.target}", index + 1, 1, raw))
        elif kind == "define":
            macro = _macro(argument, index + 1, active_state)
            if macro is not None:
                macros.append(macro)
                if active_state == "active":
                    define_values[macro.name] = macro.value or "1"
        elif kind == "undef" and active_state == "active":
            define_values.pop(argument.split()[0] if argument.split() else "", None)

    for frame in conditional_stack:
        warnings.append(SourceWarning("conditional_stack_unclosed", f"Conditional block left open with state {frame.current_state}."))
    return directives, includes, macros, warnings


def mask_known_inactive_regions(text: str, directives: list[PreprocessorDirective]) -> str:
    by_line = {item.line_number: item for item in directives}
    stack: list[str] = []
    output: list[str] = []
    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        directive = by_line.get(line_number)
        if directive is not None:
            if directive.kind in {"if", "ifdef", "ifndef"}:
                stack.append(directive.active_state)
            elif directive.kind in {"elif", "else"} and stack:
                stack[-1] = directive.active_state
            elif directive.kind == "endif" and stack:
                stack.pop()
            output.append(line)
            continue
        if "inactive" in stack:
            output.append("".join("\n" if char == "\n" else "\r" if char == "\r" else " " for char in line))
        else:
            output.append(line)
    return "".join(output)


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


def _evaluate_condition(kind: str, argument: str, defines: dict[str, str], defines_complete: bool) -> str:
    if kind == "ifdef":
        name = argument.strip()
        return "active" if name in defines else "inactive" if defines_complete else "unknown"
    if kind == "ifndef":
        name = argument.strip()
        return "inactive" if name in defines else "active" if defines_complete else "unknown"
    expression = " ".join(argument.split())
    if expression == "0":
        return "inactive"
    if expression == "1":
        return "active"
    match = re.fullmatch(r"defined\s*\(\s*([A-Za-z_]\w*)\s*\)", expression)
    if match:
        return _defined_state(match.group(1), defines, defines_complete)
    match = re.fullmatch(r"defined\s+([A-Za-z_]\w*)", expression)
    if match:
        return _defined_state(match.group(1), defines, defines_complete)
    match = re.fullmatch(r"!\s*defined\s*\(\s*([A-Za-z_]\w*)\s*\)", expression)
    if match:
        return _flip_state(_defined_state(match.group(1), defines, defines_complete))
    if re.fullmatch(r"[A-Za-z_]\w*", expression) and expression in defines:
        try:
            return "inactive" if int(defines[expression], 0) == 0 else "active"
        except ValueError:
            return "unknown"
    return "unknown"


def _current_active(stack: list[_ConditionalFrame]) -> str:
    states = [item.current_state for item in stack]
    if "inactive" in states:
        return "inactive"
    if "unknown" in states:
        return "unknown"
    return "active"


def _flip_state(state: str) -> str:
    if state == "active":
        return "inactive"
    if state == "inactive":
        return "active"
    return "unknown"


def _defined_state(name: str, defines: dict[str, str], defines_complete: bool) -> str:
    return "active" if name in defines else "inactive" if defines_complete else "unknown"


def _remaining_branch_state(prior_taken: str, condition: str) -> str:
    if prior_taken == "active":
        return "inactive"
    if prior_taken == "inactive":
        return condition
    return "inactive" if condition == "inactive" else "unknown"


def _or_state(left: str, right: str) -> str:
    if "active" in {left, right}:
        return "active"
    if "unknown" in {left, right}:
        return "unknown"
    return "inactive"


def _define_values(values: list[Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in values:
        text = str(raw).strip()
        if not text:
            continue
        name, separator, value = text.partition("=")
        if re.fullmatch(r"[A-Za-z_]\w*", name.strip()):
            result[name.strip()] = value.strip() if separator else "1"
    return result


def _include_dirs(build_context: dict[str, Any]) -> list[Path]:
    result = []
    workspace_root = build_context.get("workspace_root")
    workspace = Path(workspace_root) if workspace_root else None
    for item in build_context.get("include_dirs", []):
        if isinstance(item, dict) and item.get("absolute"):
            result.append(Path(item["absolute"]))
        elif isinstance(item, dict) and item.get("normalized"):
            path = Path(item["normalized"])
            result.append(path if path.is_absolute() or workspace is None else workspace / path)
        elif isinstance(item, str):
            path = Path(item)
            result.append(path if path.is_absolute() or workspace is None else workspace / path)
    return result
