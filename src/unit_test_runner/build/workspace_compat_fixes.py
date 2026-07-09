from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import build_workspace_generator as bwg
from .build_models import BuildPathEntry

_ENV_INCLUDE_RE = re.compile(r"%[^%]+%")
_EXTERN_OR_EXTERN_MACRO_RE = re.compile(
    r"(?m)^\s*(?:extern|EXTERN)\s+(?P<prefix>[^;\n()]*?)(?P<name>[A-Za-z_]\w*)\s*(?P<array>(?:\[[^\]]*\])*)\s*;"
)


def _include_dir_text(raw: Any) -> str:
    if isinstance(raw, dict):
        value = raw.get("normalized") or raw.get("raw") or raw.get("path") or raw.get("absolute")
    else:
        value = raw
    if value is None:
        return ""
    return str(value).strip().strip('"').replace("\\", "/")


def _is_passthrough_include_dir(text: str) -> bool:
    return "$" in text or _ENV_INCLUDE_RE.search(text) is not None


def _include_dir_path(raw: Any, workspace_root: Path) -> Path | None:
    text = _include_dir_text(raw)
    if not text or _is_passthrough_include_dir(text):
        return None
    path = Path(text.replace("\\", "/"))
    return path if path.is_absolute() else workspace_root / path


def _include_dirs(output_root: Path, build_context: dict[str, Any]) -> list[BuildPathEntry]:
    entries = [
        BuildPathEntry("generated/include", Path("generated/include"), output_root / "generated" / "include", (output_root / "generated" / "include").exists(), "generated_include"),
        BuildPathEntry("generated/harness", Path("generated/harness"), output_root / "generated" / "harness", (output_root / "generated" / "harness").exists(), "generated_include"),
        BuildPathEntry("generated/stubs", Path("generated/stubs"), output_root / "generated" / "stubs", (output_root / "generated" / "stubs").exists(), "generated_include"),
        BuildPathEntry("generated/tests", Path("generated/tests"), output_root / "generated" / "tests", (output_root / "generated" / "tests").exists(), "generated_include"),
        BuildPathEntry("extracted/include", Path("extracted/include"), output_root / "extracted" / "include", (output_root / "extracted" / "include").exists(), "extracted_include"),
    ]
    workspace_root = Path(build_context.get("workspace_root") or "")
    for raw in build_context.get("include_dirs", []):
        normalized = _include_dir_text(raw)
        if not normalized:
            continue
        if _is_passthrough_include_dir(normalized):
            entries.append(BuildPathEntry(normalized, None, None, False, "dsp_include"))
            continue
        original = (workspace_root / normalized).resolve() if workspace_root.as_posix() else Path(normalized)
        entries.append(BuildPathEntry(normalized, Path("extracted") / normalized, original, original.exists(), "dsp_include"))
    return entries


def _makefile_include_arg(entry: BuildPathEntry) -> str:
    if _is_passthrough_include_dir(entry.raw):
        include_path = entry.raw
    elif Path(entry.raw).is_absolute():
        include_path = entry.raw
    else:
        workspace_path = entry.workspace_path or Path(entry.raw)
        include_path = (Path("..") / workspace_path).as_posix()
    include_path = include_path.replace("/", "\\")
    return f'/I"{include_path}"'


def _function_level_source_text(source: Path, source_digest: dict[str, Any], function_name: str) -> str | None:
    if not source.exists():
        return None
    tokens = bwg._source_tokens(source_digest)
    definitions = bwg._function_definitions_from_tokens(tokens)
    if not definitions or not any(item["name"] == function_name for item in definitions):
        return None
    keep = bwg._reachable_function_names(function_name, definitions, tokens)
    if all(item["name"] in keep for item in definitions):
        return None
    try:
        text = bwg.decode_bytes_auto(source.read_bytes())
    except OSError:
        return None
    return _remove_unkept_functions_from_text(text, definitions, keep)


def _remove_unkept_functions_from_text(text: str, definitions: list[dict[str, Any]], keep: set[str]) -> str:
    result = text
    for definition in sorted(definitions, key=lambda item: int(item["start"]), reverse=True):
        if definition["name"] in keep:
            continue
        start = int(definition["start"])
        end = _safe_definition_end(result, definition)
        if start < 0 or end < start or end > len(result):
            continue
        removed = result[start:end]
        result = result[:start] + _removed_function_replacement_text(definition["name"], removed) + result[end:]
    return result


def _safe_definition_end(text: str, definition: dict[str, Any]) -> int:
    start = max(0, int(definition.get("start", 0)))
    expected_end = min(len(text), max(start, int(definition.get("end", start))))
    if expected_end > start and text[expected_end - 1] == "}":
        return expected_end
    open_index = text.find("{", start, expected_end + 1)
    if open_index == -1:
        return expected_end
    close_index = _matching_brace_index(text, open_index)
    if close_index == -1:
        return expected_end
    return close_index + 1


def _matching_brace_index(text: str, open_index: int) -> int:
    depth = 0
    index = open_index
    state = "normal"
    quote = ""
    while index < len(text):
        current = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if state == "normal":
            if current == "/" and nxt == "*":
                state = "block_comment"
                index += 2
                continue
            if current == "/" and nxt == "/":
                state = "line_comment"
                index += 2
                continue
            if current in {'"', "'"}:
                quote = current
                state = "literal"
                index += 1
                continue
            if current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    return index
        elif state == "block_comment":
            if current == "*" and nxt == "/":
                state = "normal"
                index += 2
                continue
        elif state == "line_comment":
            if current == "\n":
                state = "normal"
        elif state == "literal":
            if current == "\\":
                index += 2
                continue
            if current == quote:
                state = "normal"
        index += 1
    return -1


def _removed_function_replacement_text(name: str, removed: str) -> str:
    newline = "\r\n" if "\r\n" in removed else "\n"
    newline_count = removed.count("\n")
    comment = f"/* unit-test-runner build probe: unused peer function {name} removed for function-level linking. */"
    return comment + (newline * max(1, newline_count))


def apply_build_probe_compat_fixes() -> None:
    bwg._EXTERN_VARIABLE_RE = _EXTERN_OR_EXTERN_MACRO_RE
    bwg._include_dir_text = _include_dir_text
    bwg._is_passthrough_include_dir = _is_passthrough_include_dir
    bwg._include_dir_path = _include_dir_path
    bwg._include_dirs = _include_dirs
    bwg._makefile_include_arg = _makefile_include_arg
    bwg._function_level_source_text = _function_level_source_text
