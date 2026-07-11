from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import build_workspace_generator as bwg
from .build_models import BuildDiagnostic, BuildPathEntry, WorkspaceFile

_ENV_INCLUDE_RE = re.compile(r"%[^%]+%")
_EXTERN_OR_EXTERN_MACRO_RE = re.compile(
    r"(?m)^\s*(?:extern|EXTERN)\s+(?P<prefix>[^;\n()]*?)(?P<name>[A-Za-z_]\w*)\s*(?P<array>(?:\[[^\]]*\])*)\s*;"
)
_HEADER_REFERENCE_DIRS_BY_OUTPUT: dict[str, set[Path]] = {}


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


def _copy_target_and_headers(
    output_root: Path,
    source_path: Path,
    source_digest: dict[str, Any],
    build_context: dict[str, Any],
    function_name: str,
    diagnostics: list[BuildDiagnostic],
) -> list[WorkspaceFile]:
    """Copy only the target C file and keep headers as original-file references.

    Large projects can have thousands of transitive headers. Copying those for every
    function workspace is slow and can also duplicate unguarded legacy headers.  The
    build workspace therefore keeps the extracted/isolated target C file local, but
    resolves headers through include paths pointing back to the original project.
    """
    output_root = Path(output_root).resolve()
    copied: list[WorkspaceFile] = []
    workspace_root = Path(build_context.get("workspace_root") or source_path.parent)
    include_roots = bwg._include_search_roots(workspace_root, build_context)
    target_relative = bwg._relative_or_name(source_path, workspace_root)
    target_workspace = Path("extracted") / target_relative
    bwg._copy_target_source(source_path, output_root / target_workspace, copied, target_workspace, source_digest, function_name, diagnostics)

    header_queue: list[Path] = []
    referenced_dirs: set[Path] = set()
    if source_path.parent.exists():
        referenced_dirs.add(source_path.parent.resolve())
    for include in source_digest.get("preprocessor", {}).get("includes", []):
        candidates = [Path(item) for item in include.get("resolved_candidates", []) if item]
        existing = next((item for item in candidates if item.exists()), None)
        if existing is None:
            continue
        _reference_header(existing, workspace_root, copied, diagnostics, header_queue, referenced_dirs)
    _reference_transitive_header_includes(workspace_root, include_roots, copied, diagnostics, header_queue, referenced_dirs)
    if workspace_root.as_posix():
        try:
            referenced_dirs.add(workspace_root.resolve())
        except OSError:
            referenced_dirs.add(workspace_root)
    _HEADER_REFERENCE_DIRS_BY_OUTPUT[str(output_root)] = referenced_dirs
    return copied


def _reference_header(
    source: Path,
    workspace_root: Path,
    copied: list[WorkspaceFile],
    diagnostics: list[BuildDiagnostic],
    queue: list[Path] | None = None,
    referenced_dirs: set[Path] | None = None,
) -> None:
    try:
        resolved = source.resolve()
    except OSError:
        resolved = source
    existing = next((item for item in copied if item.source_path is not None and _same_file(item.source_path, resolved)), None)
    if existing is not None:
        if queue is not None:
            queue.append(source)
        return
    if not source.exists():
        diagnostics.append(BuildDiagnostic("missing_header_file", "warning", f"Referenced header is missing: {source}", source, None, None))
        copied.append(WorkspaceFile(Path("referenced") / source.name, "target_header", source_path=source, copied=False, generated=False, required=True, exists=False))
        return
    workspace_path = Path("referenced") / bwg._relative_or_name(source, workspace_root)
    copied.append(WorkspaceFile(workspace_path, "target_header", source_path=resolved, copied=False, generated=False, required=True, exists=True))
    if referenced_dirs is not None:
        referenced_dirs.add(resolved.parent)
    if queue is not None:
        queue.append(source)


def _reference_transitive_header_includes(
    workspace_root: Path,
    include_roots: list[Path],
    copied: list[WorkspaceFile],
    diagnostics: list[BuildDiagnostic],
    header_queue: list[Path],
    referenced_dirs: set[Path],
) -> None:
    scanned: set[Path] = set()
    while header_queue:
        current = header_queue.pop(0)
        try:
            resolved_current = current.resolve()
        except OSError:
            continue
        if resolved_current in scanned:
            continue
        scanned.add(resolved_current)
        for include_target in bwg._quote_include_targets(current):
            included = bwg._resolve_quoted_include(current, include_target, include_roots)
            if included is None:
                diagnostics.append(BuildDiagnostic("missing_transitive_include", "warning", f"Header include not found while preparing build workspace: {include_target}", current, None, None))
                continue
            try:
                resolved_included = included.resolve()
            except OSError:
                resolved_included = included
            already_referenced = any(item.source_path is not None and _same_file(item.source_path, resolved_included) for item in copied if item.exists)
            if not already_referenced:
                _reference_header(included, workspace_root, copied, diagnostics, header_queue, referenced_dirs)
            elif resolved_included not in scanned:
                header_queue.append(included)



def _copy_dependency_sources(
    output_root: Path,
    build_context: dict[str, Any],
    harness_report: dict[str, Any],
    copied_files: list[WorkspaceFile],
    diagnostics: list[BuildDiagnostic],
) -> None:
    """Copy real dependency/object C files while retaining headers by reference."""
    output_root = Path(output_root).resolve()
    workspace_root = Path(build_context.get("workspace_root") or "")
    include_roots = bwg._include_search_roots(workspace_root, build_context)
    referenced_dirs = _HEADER_REFERENCE_DIRS_BY_OUTPUT.setdefault(str(output_root), set())
    copied_sources: set[Path] = set()
    for item in copied_files:
        if item.source_path is None or not item.source_path.exists():
            continue
        try:
            copied_sources.add(item.source_path.resolve())
        except OSError:
            copied_sources.add(item.source_path)

    def copy_source(raw_source: Any, file_kind: str, root_folder: str) -> None:
        if not raw_source:
            return
        source = Path(str(raw_source))
        if not source.is_absolute():
            source = workspace_root / source
        try:
            source = source.resolve()
        except OSError:
            pass
        if source in copied_sources:
            return
        if not source.is_file():
            diagnostics.append(BuildDiagnostic(f"missing_{file_kind}", "error", f"Required product source is missing: {source}", source, None, None))
            return
        copied_sources.add(source)
        relative = bwg._relative_or_name(source, workspace_root) if workspace_root.as_posix() else Path(source.name)
        workspace_path = Path(root_folder) / relative
        bwg._copy_file(source, output_root / workspace_path, copied_files, workspace_path, file_kind, diagnostics)
        referenced_dirs.add(source.parent)
        header_queue: list[Path] = []
        for include_target in bwg._quote_include_targets(source):
            included = bwg._resolve_quoted_include(source, include_target, include_roots)
            if included is None:
                diagnostics.append(BuildDiagnostic("missing_dependency_include", "warning", f"Product source include not found while preparing build workspace: {include_target}", source, None, None))
                continue
            _reference_header(included, workspace_root, copied_files, diagnostics, header_queue, referenced_dirs)
        _reference_transitive_header_includes(workspace_root, include_roots, copied_files, diagnostics, header_queue, referenced_dirs)

    for dispatch in harness_report.get("dependency_dispatches", []):
        if dispatch.get("real_available") and dispatch.get("implementation_source"):
            copy_source(dispatch.get("implementation_source"), "dependency_source", "extracted/dependencies")

    policy = _load_dependency_policy(output_root)
    for external_object in policy.get("external_objects", []):
        if external_object.get("resolved_mode") != "real":
            continue
        definition_source = external_object.get("definition_source")
        if not definition_source:
            diagnostics.append(BuildDiagnostic("external_object_definition_missing", "error", f"External object {external_object.get('symbol', '')} is configured as real but has no definition source.", None, None, None))
            continue
        copy_source(definition_source, "external_object_source", "extracted/external_objects")


def _load_dependency_policy(output_root: Path) -> dict[str, Any]:
    path = Path(output_root) / "reports" / "dependency_policy.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}

def _include_dirs(output_root: Path, build_context: dict[str, Any]) -> list[BuildPathEntry]:
    output_root = Path(output_root).resolve()
    entries: list[BuildPathEntry] = []
    seen: set[str] = set()

    def append(raw: str, workspace_path: Path | None, original_path: Path | None, exists: bool, source: str) -> None:
        key = raw.replace("\\", "/").lower()
        if key in seen:
            return
        seen.add(key)
        entries.append(BuildPathEntry(raw, workspace_path, original_path, exists, source))

    append("generated/include", Path("generated/include"), output_root / "generated" / "include", (output_root / "generated" / "include").exists(), "generated_include")
    append("generated/harness", Path("generated/harness"), output_root / "generated" / "harness", (output_root / "generated" / "harness").exists(), "generated_include")
    append("generated/stubs", Path("generated/stubs"), output_root / "generated" / "stubs", (output_root / "generated" / "stubs").exists(), "generated_include")
    append("generated/tests", Path("generated/tests"), output_root / "generated" / "tests", (output_root / "generated" / "tests").exists(), "generated_include")
    append("generated/dependencies", Path("generated/dependencies"), output_root / "generated" / "dependencies", (output_root / "generated" / "dependencies").exists(), "generated_include")
    append("extracted/include", Path("extracted/include"), output_root / "extracted" / "include", (output_root / "extracted" / "include").exists(), "extracted_include")

    for directory in sorted(_HEADER_REFERENCE_DIRS_BY_OUTPUT.get(str(output_root), set()), key=lambda item: item.as_posix().lower()):
        append(directory.as_posix(), None, directory, directory.exists(), "referenced_header_dir")

    workspace_root = Path(build_context.get("workspace_root") or "")
    if workspace_root.as_posix():
        try:
            resolved_workspace = workspace_root.resolve()
        except OSError:
            resolved_workspace = workspace_root
        append(resolved_workspace.as_posix(), None, resolved_workspace, resolved_workspace.exists(), "workspace_root")
    for raw in build_context.get("include_dirs", []):
        normalized = _include_dir_text(raw)
        if not normalized:
            continue
        if _is_passthrough_include_dir(normalized):
            append(normalized, None, None, False, "dsp_include")
            continue
        original = (workspace_root / normalized).resolve() if workspace_root.as_posix() and not Path(normalized).is_absolute() else Path(normalized).resolve()
        append(original.as_posix(), None, original, original.exists(), "dsp_include")
    return entries


def _makefile_include_arg(entry: BuildPathEntry) -> str:
    if _is_passthrough_include_dir(entry.raw):
        include_path = entry.raw
    elif Path(entry.raw).is_absolute():
        include_path = entry.raw
    elif entry.workspace_path is not None:
        include_path = (Path("..") / entry.workspace_path).as_posix()
    else:
        include_path = entry.raw
    include_path = include_path.replace("/", "\\")
    return f'/I"{include_path}"'


def _generate_extern_global_definitions(output_root: Path, copied_files: list[WorkspaceFile], diagnostics: list[BuildDiagnostic]) -> list[WorkspaceFile]:
    output_root = Path(output_root).resolve()
    destination = output_root / "generated/stubs/utr_extern_globals.c"
    if destination.exists():
        destination.unlink()

    policy = _load_dependency_policy(output_root)
    object_policies = {
        str(item.get("symbol")): item
        for item in policy.get("external_objects", [])
        if item.get("symbol")
    }
    for symbol, item in object_policies.items():
        if item.get("resolved_mode") == "review_required" or item.get("review_status") == "review_required":
            diagnostics.append(
                BuildDiagnostic(
                    "external_object_binding_review_required",
                    "error",
                    f"External object {symbol} has no safe automatic binding. Review dependency_policy.json.",
                    Path(str(item.get("declaration_header"))) if item.get("declaration_header") else None,
                    None,
                    None,
                )
            )

    source_items = [
        item
        for item in copied_files
        if item.file_kind in {"target_source", "dependency_source", "external_object_source"} and item.exists
    ]
    source_texts = [_workspace_or_source_text(output_root, item) for item in source_items]
    definitions: dict[str, tuple[str, str]] = {}
    matched_fixture_symbols: set[str] = set()
    for header in [item for item in copied_files if item.file_kind == "target_header" and item.exists]:
        header_text = _workspace_or_source_text(output_root, header)
        for prefix, name, array in bwg._extern_variable_declarations(header_text):
            item_policy = object_policies.get(name)
            mode = str(item_policy.get("resolved_mode")) if item_policy else "fixture"
            if mode == "real" or mode == "review_required":
                continue
            if name in definitions:
                matched_fixture_symbols.add(name)
                continue
            if bwg._target_source_defines_name(name, source_texts):
                if item_policy and mode == "fixture":
                    diagnostics.append(BuildDiagnostic("external_object_fixture_conflict", "error", f"Fixture binding for {name} conflicts with a linked product definition.", header.source_path or header.workspace_path, None, None))
                continue
            declaration = bwg._extern_definition_line(prefix, name, array)
            if declaration:
                include_token = str(item_policy.get("declaration_header") or "").replace("\\", "/") if item_policy else ""
                definitions[name] = (declaration, include_token or _include_token_for_header(header))
                matched_fixture_symbols.add(name)

    for symbol, item in object_policies.items():
        if item.get("resolved_mode") == "fixture" and symbol not in matched_fixture_symbols:
            diagnostics.append(
                BuildDiagnostic(
                    "external_object_fixture_declaration_missing",
                    "error",
                    f"Fixture binding for {symbol} could not find a compatible extern declaration in referenced headers.",
                    Path(str(item.get("declaration_header"))) if item.get("declaration_header") else None,
                    None,
                    None,
                )
            )

    if not definitions:
        return []
    relative = Path("generated/stubs/utr_extern_globals.c")
    lines = [
        "/* generated extern data fixtures for function-level build probe */",
        "/* bindings are selected by reports/dependency_policy.json */",
        "",
    ]
    included_headers: list[str] = []
    for _name, (_definition, include_path) in sorted(definitions.items()):
        if include_path not in included_headers:
            included_headers.append(include_path)
            lines.append(f'#include "{include_path}"')
    lines.append("")
    for name, (definition, _include_path) in sorted(definitions.items()):
        lines.append(f"/* fixture for declaration-only external object: {name} */")
        lines.append(definition)
    lines.append("")
    bwg.write_build_text(destination, "\n".join(lines))
    return [WorkspaceFile(relative, "extern_global_source", sha256=bwg.sha256_file(destination), copied=False, generated=True, required=False, exists=True)]

def _workspace_or_source_text(output_root: Path, item: WorkspaceFile) -> str:
    if item.source_path is not None and not item.copied:
        try:
            return bwg.decode_bytes_auto(item.source_path.read_bytes())
        except OSError:
            return ""
    return bwg._workspace_text(output_root, item.workspace_path)


def _include_token_for_header(item: WorkspaceFile) -> str:
    if item.source_path is not None and not item.copied:
        return item.source_path.name
    return bwg._relative_include_from_generated_stubs(item.workspace_path)


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left == right


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
    bwg._copy_target_and_headers = _copy_target_and_headers
    bwg._copy_dependency_sources = _copy_dependency_sources
    bwg._include_dirs = _include_dirs
    bwg._makefile_include_arg = _makefile_include_arg
    bwg._generate_extern_global_definitions = _generate_extern_global_definitions
    bwg._function_level_source_text = _function_level_source_text
