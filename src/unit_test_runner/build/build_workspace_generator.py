from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unit_test_runner.encoding import decode_bytes_auto
from unit_test_runner.harness.c90_writer import sha256_file
from unit_test_runner.process_control import run_process_tree

from .build_models import (
    BuildCommand,
    BuildCommandResult,
    BuildDiagnostic,
    BuildPathEntry,
    BuildProbeReport,
    BuildWorkspaceReport,
    CompileUnit,
    WorkspaceFile,
)
from .build_report_writer import write_build_reports, write_build_text
from .log_parser import parse_build_log
from .verification_toolchain import render_verification_build_info, run_verification_build

_QUOTE_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.MULTILINE)
_EXTERN_VARIABLE_RE = re.compile(r"(?m)^\s*extern\s+(?P<prefix>[^;\n()]*?)(?P<name>[A-Za-z_]\w*)\s*(?P<array>(?:\[[^\]]*\])*)\s*;")


def generate_build_workspace(
    build_context: dict[str, Any],
    source_digest: dict[str, Any],
    harness_report: dict[str, Any],
    output_root: Path | str,
    run_probe: bool = False,
    dry_run: bool = True,
    vcvars: Path | str | None = None,
    timeout_seconds: int = 120,
    overwrite: bool = False,
    toolchain: str | None = None,
    cc: Path | str | None = None,
) -> tuple[BuildWorkspaceReport, BuildProbeReport]:
    del overwrite
    output_root = Path(output_root).resolve()
    toolchain = _normalize_toolchain(toolchain or os.environ.get("UNIT_TEST_RUNNER_BUILD_TOOLCHAIN") or "vc6")
    cc = cc or os.environ.get("UNIT_TEST_RUNNER_CC")
    _ensure_layout(output_root)
    source_path = Path(source_digest.get("source", {}).get("path") or harness_report.get("source", {}).get("path") or "")
    function_name = harness_report.get("function", {}).get("name") or "unknown_function"
    diagnostics: list[BuildDiagnostic] = []
    copied_files = _copy_target_and_headers(output_root, source_path, source_digest, build_context, function_name, diagnostics)
    generated_files = _copy_or_verify_generated_files(output_root, harness_report, diagnostics)
    generated_files.extend(_generate_extern_global_definitions(output_root, copied_files, diagnostics))
    include_dirs = _include_dirs(output_root, build_context)
    defines = _defines(build_context)
    compiler_options = _compiler_options(build_context)
    compile_units = _compile_units(output_root, copied_files, generated_files, include_dirs, defines, compiler_options)
    build_commands = _write_build_files(output_root, compile_units, include_dirs, defines, compiler_options, vcvars, dry_run, toolchain, cc)
    status = "partial" if any(item.severity == "error" for item in diagnostics) else "generated"
    workspace_report = BuildWorkspaceReport(source_path, function_name, status, output_root, copied_files, [], [], compile_units, [unit.object_file for unit in compile_units], include_dirs, defines, compiler_options, build_commands, diagnostics)
    probe_report = _build_probe_report(output_root, source_path, function_name, build_commands, compile_units, include_dirs, defines, compiler_options, harness_report, run_probe, dry_run, timeout_seconds, vcvars, toolchain, cc)
    write_build_reports(output_root, workspace_report, probe_report)
    return workspace_report, probe_report


def _ensure_layout(output_root: Path) -> None:
    for relative in ["build", "obj", "bin", "logs", "extracted", "generated", "reports"]:
        (output_root / relative).mkdir(parents=True, exist_ok=True)


def _copy_target_and_headers(
    output_root: Path,
    source_path: Path,
    source_digest: dict[str, Any],
    build_context: dict[str, Any],
    function_name: str,
    diagnostics: list[BuildDiagnostic],
) -> list[WorkspaceFile]:
    copied: list[WorkspaceFile] = []
    workspace_root = Path(build_context.get("workspace_root") or source_path.parent)
    include_roots = _include_search_roots(workspace_root, build_context)
    target_relative = _relative_or_name(source_path, workspace_root)
    target_workspace = Path("extracted") / target_relative
    _copy_target_source(source_path, output_root / target_workspace, copied, target_workspace, source_digest, function_name, diagnostics)
    header_queue: list[Path] = []
    for include in source_digest.get("preprocessor", {}).get("includes", []):
        candidates = [Path(item) for item in include.get("resolved_candidates", []) if item]
        existing = next((item for item in candidates if item.exists()), None)
        if existing is None:
            continue
        _copy_header(existing, output_root, workspace_root, include_roots, copied, diagnostics, header_queue)
    _copy_transitive_header_includes(output_root, workspace_root, include_roots, copied, diagnostics, header_queue)
    return copied


def _copy_target_source(
    source: Path,
    destination: Path,
    copied: list[WorkspaceFile],
    relative_destination: Path,
    source_digest: dict[str, Any],
    function_name: str,
    diagnostics: list[BuildDiagnostic],
) -> None:
    isolated = _function_level_source_text(source, source_digest, function_name)
    if isolated is None:
        _copy_file(source, destination, copied, relative_destination, "target_source", diagnostics)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(isolated, encoding="cp932", errors="replace")
    copied.append(WorkspaceFile(relative_destination, "target_source", source_path=source, sha256=sha256_file(destination), copied=True, generated=False, required=True, exists=True))


def _function_level_source_text(source: Path, source_digest: dict[str, Any], function_name: str) -> str | None:
    if not source.exists():
        return None
    tokens = _source_tokens(source_digest)
    definitions = _function_definitions_from_tokens(tokens)
    if not definitions or not any(item["name"] == function_name for item in definitions):
        return None
    keep = _reachable_function_names(function_name, definitions, tokens)
    if all(item["name"] in keep for item in definitions):
        return None
    try:
        text = decode_bytes_auto(source.read_bytes())
    except OSError:
        return None
    return _remove_unkept_functions(text, definitions, keep)


def _source_tokens(source_digest: dict[str, Any]) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    for token in source_digest.get("tokens", []):
        if not all(key in token for key in ("kind", "value", "start_offset", "end_offset")):
            continue
        tokens.append(token)
    return sorted(tokens, key=lambda item: int(item.get("start_offset", 0)))


def _function_definitions_from_tokens(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    depths = _brace_depths(tokens)
    definitions: list[dict[str, Any]] = []
    index = 0
    while index < len(tokens) - 2:
        token = tokens[index]
        if token.get("kind") != "identifier" or depths[index] != 0:
            index += 1
            continue
        if _token_value(tokens, index + 1) != "(":
            index += 1
            continue
        close_paren = _matching_token(tokens, index + 1, "(", ")")
        next_index = close_paren + 1 if close_paren != -1 else -1
        if next_index == -1 or next_index >= len(tokens) or _token_value(tokens, next_index) != "{" or depths[next_index] != 0:
            index += 1
            continue
        close_brace = _matching_token(tokens, next_index, "{", "}")
        if close_brace == -1:
            index += 1
            continue
        start_index = _definition_start_index(tokens, depths, index)
        definitions.append(
            {
                "name": str(token.get("value")),
                "start": int(tokens[start_index].get("start_offset", 0)),
                "end": int(tokens[close_brace].get("end_offset", 0)),
                "body_start": int(tokens[next_index].get("end_offset", 0)),
                "body_end": int(tokens[close_brace].get("start_offset", 0)),
            }
        )
        index = close_brace + 1
    return definitions


def _brace_depths(tokens: list[dict[str, Any]]) -> list[int]:
    depths: list[int] = []
    depth = 0
    for token in tokens:
        value = token.get("value")
        depths.append(depth)
        if value == "{":
            depth += 1
        elif value == "}":
            depth = max(0, depth - 1)
    return depths


def _matching_token(tokens: list[dict[str, Any]], start_index: int, open_value: str, close_value: str) -> int:
    depth = 0
    for index in range(start_index, len(tokens)):
        value = _token_value(tokens, index)
        if value == open_value:
            depth += 1
        elif value == close_value:
            depth -= 1
            if depth == 0:
                return index
    return -1


def _definition_start_index(tokens: list[dict[str, Any]], depths: list[int], name_index: int) -> int:
    for index in range(name_index - 1, -1, -1):
        value = _token_value(tokens, index)
        if value == ";" and depths[index] == 0:
            return index + 1
        if value == "}" and depths[index] <= 1:
            return index + 1
    return 0


def _reachable_function_names(function_name: str, definitions: list[dict[str, Any]], tokens: list[dict[str, Any]]) -> set[str]:
    definitions_by_name = {item["name"]: item for item in definitions}
    keep: set[str] = set()
    pending = [function_name]
    while pending:
        name = pending.pop()
        if name in keep:
            continue
        keep.add(name)
        definition = definitions_by_name.get(name)
        if not definition:
            continue
        for called in _called_defined_functions(definition, tokens, set(definitions_by_name)):
            if called not in keep:
                pending.append(called)
    return keep


def _called_defined_functions(definition: dict[str, Any], tokens: list[dict[str, Any]], known_names: set[str]) -> set[str]:
    calls: set[str] = set()
    body_start = int(definition["body_start"])
    body_end = int(definition["body_end"])
    for index, token in enumerate(tokens[:-1]):
        start = int(token.get("start_offset", 0))
        if start < body_start or start >= body_end:
            continue
        name = str(token.get("value"))
        if token.get("kind") == "identifier" and name in known_names and _token_value(tokens, index + 1) == "(":
            calls.add(name)
    return calls


def _remove_unkept_functions(text: str, definitions: list[dict[str, Any]], keep: set[str]) -> str:
    result = text
    for definition in sorted(definitions, key=lambda item: int(item["start"]), reverse=True):
        if definition["name"] in keep:
            continue
        start = int(definition["start"])
        end = int(definition["end"])
        removed = result[start:end]
        result = result[:start] + _removed_function_replacement(definition["name"], removed) + result[end:]
    return result


def _removed_function_replacement(name: str, removed_text: str) -> str:
    newline_count = removed_text.count("\n")
    comment = f"/* unit-test-runner build probe: unused peer function {name} removed for function-level linking. */"
    return comment + ("\n" * max(1, newline_count))


def _token_value(tokens: list[dict[str, Any]], index: int) -> str | None:
    if index < 0 or index >= len(tokens):
        return None
    return str(tokens[index].get("value"))


def _copy_header(source: Path, output_root: Path, workspace_root: Path, include_roots: list[Path], copied: list[WorkspaceFile], diagnostics: list[BuildDiagnostic], queue: list[Path] | None = None) -> None:
    destination_relative = _header_destination_relative(source, workspace_root, include_roots)
    _copy_file(source, output_root / destination_relative, copied, destination_relative, "target_header", diagnostics)
    if queue is not None:
        queue.append(source)


def _copy_transitive_header_includes(output_root: Path, workspace_root: Path, include_roots: list[Path], copied: list[WorkspaceFile], diagnostics: list[BuildDiagnostic], header_queue: list[Path]) -> None:
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
        for include_target in _quote_include_targets(current):
            included = _resolve_quoted_include(current, include_target, include_roots)
            if included is None:
                diagnostics.append(BuildDiagnostic("missing_transitive_include", "warning", f"Header include not found while preparing build workspace: {include_target}", current, None, None))
                continue
            try:
                resolved_included = included.resolve()
            except OSError:
                resolved_included = included
            already_copied = any(item.source_path is not None and item.source_path.resolve() == resolved_included for item in copied if item.exists)
            if not already_copied:
                _copy_header(included, output_root, workspace_root, include_roots, copied, diagnostics, header_queue)
            elif resolved_included not in scanned:
                header_queue.append(included)


def _quote_include_targets(path: Path) -> list[str]:
    try:
        text = decode_bytes_auto(path.read_bytes())
    except OSError:
        return []
    return [match.group(1).strip() for match in _QUOTE_INCLUDE_RE.finditer(text) if match.group(1).strip()]


def _resolve_quoted_include(current: Path, include_target: str, include_roots: list[Path]) -> Path | None:
    target = Path(include_target)
    candidates = [target] if target.is_absolute() else [current.parent / target] + [root / target for root in include_roots]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _include_search_roots(workspace_root: Path, build_context: dict[str, Any]) -> list[Path]:
    roots: list[Path] = []
    try:
        roots.append(workspace_root.resolve())
    except OSError:
        roots.append(workspace_root)
    for raw in build_context.get("include_dirs", []):
        path = _include_dir_path(raw, workspace_root)
        if path is None:
            continue
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved not in roots:
            roots.append(resolved)
    return roots


def _include_dir_path(raw: Any, workspace_root: Path) -> Path | None:
    if isinstance(raw, dict):
        value = raw.get("absolute") or raw.get("normalized") or raw.get("raw") or raw.get("path")
    else:
        value = raw
    if value is None:
        return None
    text = str(value).strip()
    if not text or "$" in text:
        return None
    path = Path(text.replace("\\", "/"))
    return path if path.is_absolute() else workspace_root / path


def _header_destination_relative(source: Path, workspace_root: Path, include_roots: list[Path]) -> Path:
    try:
        return Path("extracted") / source.resolve().relative_to(workspace_root.resolve())
    except (OSError, ValueError):
        pass
    for root in include_roots:
        try:
            return Path("extracted") / "include" / source.resolve().relative_to(root.resolve())
        except (OSError, ValueError):
            continue
    return Path("extracted") / "include" / source.name


def _copy_file(source: Path, destination: Path, copied: list[WorkspaceFile], relative_destination: Path, kind: str, diagnostics: list[BuildDiagnostic]) -> None:
    existing = next((item for item in copied if item.workspace_path == relative_destination), None)
    if existing is not None and destination.exists():
        return
    if not source.exists():
        diagnostics.append(BuildDiagnostic("missing_source_file", "error", f"Source file is missing: {source}", source, None, None))
        copied.append(WorkspaceFile(relative_destination, kind, source_path=source, copied=False, generated=False, required=True, exists=False))
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    copied.append(WorkspaceFile(relative_destination, kind, source_path=source, sha256=sha256_file(destination), copied=True, generated=False, required=True, exists=True))


def _generate_extern_global_definitions(output_root: Path, copied_files: list[WorkspaceFile], diagnostics: list[BuildDiagnostic]) -> list[WorkspaceFile]:
    del diagnostics
    target_sources = [item for item in copied_files if item.file_kind == "target_source" and item.exists]
    target_source_texts = [_workspace_text(output_root, item.workspace_path) for item in target_sources]
    definitions: dict[str, tuple[str, Path]] = {}
    for header in [item for item in copied_files if item.file_kind == "target_header" and item.exists]:
        header_text = _workspace_text(output_root, header.workspace_path)
        for prefix, name, array in _extern_variable_declarations(header_text):
            if name in definitions or _target_source_defines_name(name, target_source_texts):
                continue
            declaration = _extern_definition_line(prefix, name, array)
            if declaration:
                definitions[name] = (declaration, header.workspace_path)
    if not definitions:
        return []
    relative = Path("generated/stubs/utr_extern_globals.c")
    lines = [
        "/* generated extern data placeholders for function-level build probe */",
        "/* review required: replace with product objects when a real integration build is needed */",
        "",
    ]
    included_headers = []
    for _name, (_definition, header_path) in sorted(definitions.items()):
        include_path = _relative_include_from_generated_stubs(header_path)
        if include_path not in included_headers:
            included_headers.append(include_path)
            lines.append(f'#include "{include_path}"')
    lines.append("")
    for name, (definition, _header_path) in sorted(definitions.items()):
        lines.append(f"/* placeholder for unresolved external data symbol: {name} */")
        lines.append(definition)
    lines.append("")
    destination = output_root / relative
    write_build_text(destination, "\n".join(lines))
    return [WorkspaceFile(relative, "extern_global_source", sha256=sha256_file(destination), copied=False, generated=True, required=False, exists=True)]


def _workspace_text(output_root: Path, workspace_path: Path) -> str:
    path = output_root / workspace_path
    try:
        return decode_bytes_auto(path.read_bytes())
    except OSError:
        return ""


def _extern_variable_declarations(text: str) -> list[tuple[str, str, str]]:
    declarations: list[tuple[str, str, str]] = []
    for match in _EXTERN_VARIABLE_RE.finditer(text):
        prefix = " ".join(match.group("prefix").strip().split())
        name = match.group("name").strip()
        array = match.group("array").replace(" ", "")
        if not prefix or prefix in {"typedef"} or name in {"void"}:
            continue
        declarations.append((prefix, name, array))
    return declarations


def _target_source_defines_name(name: str, target_source_texts: list[str]) -> bool:
    pattern = re.compile(rf"(?m)^\s*(?!extern\b)[^;\n()]*\b{re.escape(name)}\b\s*(?:\[[^\]]*\])?\s*(?:=|;)")
    return any(pattern.search(text) for text in target_source_texts)


def _extern_definition_line(prefix: str, name: str, array: str) -> str:
    compact_prefix = prefix.strip()
    if not compact_prefix or "(" in compact_prefix or ")" in compact_prefix:
        return ""
    return f"{compact_prefix} {name}{array} = {{0}};"


def _relative_include_from_generated_stubs(header_workspace_path: Path) -> str:
    return (Path("../..") / header_workspace_path).as_posix()


def _copy_or_verify_generated_files(output_root: Path, harness_report: dict[str, Any], diagnostics: list[BuildDiagnostic]) -> list[WorkspaceFile]:
    files: list[WorkspaceFile] = []
    harness_root = Path(harness_report.get("output_root") or output_root)
    allowed = {"assert_header", "assert_source", "runner_header", "runner_source", "stub_header", "stub_source", "test_header", "test_source", "target_invocation_header", "target_invocation_source"}
    for item in harness_report.get("generated_files", []):
        relative = Path(item.get("path", ""))
        kind = item.get("file_kind", "generated")
        if not relative.as_posix().startswith("generated/") or kind not in allowed:
            continue
        source = harness_root / relative
        destination = output_root / relative
        if not source.exists():
            diagnostics.append(BuildDiagnostic("missing_generated_file", "error", f"Generated file is missing: {relative}", relative, None, None))
            files.append(WorkspaceFile(relative, kind, source_path=source, copied=False, generated=True, required=True, exists=False))
            continue
        if source.resolve() != destination.resolve():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        files.append(WorkspaceFile(relative, kind, source_path=source, sha256=sha256_file(destination), copied=source.resolve() != destination.resolve(), generated=True, required=True, exists=True))
    return files


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
        normalized = str(raw).replace("\\", "/")
        original = (workspace_root / normalized).resolve() if workspace_root.as_posix() else Path(normalized)
        entries.append(BuildPathEntry(normalized, Path("extracted") / normalized, original, original.exists(), "dsp_include"))
    return entries


def _defines(build_context: dict[str, Any]) -> list[str]:
    values = list(dict.fromkeys([str(item).strip('"') for item in build_context.get("defines", []) if str(item).strip()]))
    if "UTR_BUILD_PROBE" not in values:
        values.append("UTR_BUILD_PROBE")
    return values


def _compiler_options(build_context: dict[str, Any]) -> list[str]:
    keep_prefixes = ("/nologo", "/W", "/O", "/Z", "/M", "/G")
    drop_prefixes = ("/Fo", "/Fd", "/Fp", "/Yu", "/Yc", "/I", "/D")
    result = []
    for option in build_context.get("compiler_options", []):
        text = str(option)
        if text.startswith(drop_prefixes):
            continue
        if text.startswith(keep_prefixes) and text not in result:
            result.append(text)
    if "/nologo" not in result:
        result.insert(0, "/nologo")
    if not any(item.startswith("/W") for item in result):
        result.append("/W3")
    if not any(item.lower() == "/gy" for item in result):
        result.append("/Gy")
    return result


def _compile_units(output_root: Path, copied_files: list[WorkspaceFile], generated_files: list[WorkspaceFile], include_dirs: list[BuildPathEntry], defines: list[str], compiler_options: list[str]) -> list[CompileUnit]:
    source_files = [item.workspace_path for item in copied_files if item.file_kind == "target_source" and item.exists]
    source_files.extend(item.workspace_path for item in generated_files if item.exists and item.file_kind in {"assert_source", "runner_source", "stub_source", "test_source", "target_invocation_source", "extern_global_source"})
    units: list[CompileUnit] = []
    used_objects: set[str] = set()
    for index, source in enumerate(source_files):
        object_name = f"{source.stem}.obj"
        if object_name in used_objects:
            object_name = f"{source.stem}_{index}.obj"
        used_objects.add(object_name)
        object_file = Path("obj") / object_name
        command = _compile_command(source, object_file, include_dirs, defines, compiler_options)
        units.append(CompileUnit(source, object_file, include_dirs, defines, compiler_options, command, True))
    return units


def _write_build_files(output_root: Path, compile_units: list[CompileUnit], include_dirs: list[BuildPathEntry], defines: list[str], compiler_options: list[str], vcvars: Path | str | None, dry_run: bool, toolchain: str, cc: Path | str | None) -> list[BuildCommand]:
    write_build_text(output_root / "build" / "Makefile", _render_makefile(compile_units, include_dirs, defines, compiler_options))
    write_build_text(output_root / "build" / "build.bat", _render_build_bat(vcvars))
    write_build_text(output_root / "build" / "clean.bat", "@echo off\nrem generated clean helper; remove obj/bin artifacts manually if needed\n")
    write_build_text(output_root / "build" / "compile_commands.txt", "\n".join(unit.command for unit in compile_units) + "\n")
    if toolchain == "verification":
        write_build_text(output_root / "build" / "verification_build.txt", render_verification_build_info(cc))
        return [BuildCommand("CMD_BUILD_001", "verification_toolchain", Path("."), _verification_command_line(cc), Path("logs/build.log"), dry_run)]
    return [BuildCommand("CMD_BUILD_001", "build_bat", Path("build"), "build.bat", Path("logs/build.log"), dry_run)]


def _build_probe_report(output_root: Path, source_path: Path, function_name: str, build_commands: list[BuildCommand], compile_units: list[CompileUnit], include_dirs: list[BuildPathEntry], defines: list[str], compiler_options: list[str], harness_report: dict[str, Any], run_probe: bool, dry_run: bool, timeout_seconds: int, vcvars: Path | str | None, toolchain: str, cc: Path | str | None) -> BuildProbeReport:
    stub_candidates = {item.get("original_function_name", "") for item in harness_report.get("stub_skeletons", [])}
    if dry_run or not run_probe:
        log_path = output_root / "logs" / "build.log"
        command_line = build_commands[0].command_line if build_commands else "build.bat"
        log_path.write_text(f"DRY RUN\n{command_line}\n", encoding="utf-8")
        return BuildProbeReport(source_path, function_name, "not_run", False, None, [], [], [], [], [], [], [Path("logs/build.log")])
    if toolchain == "verification":
        return _verification_probe_report(output_root, source_path, function_name, build_commands, compile_units, include_dirs, defines, compiler_options, harness_report, timeout_seconds, vcvars, cc, stub_candidates)
    nmake = shutil.which("nmake")
    cl = shutil.which("cl")
    if not nmake and not cl and not vcvars:
        diagnostic = BuildDiagnostic("missing_vc6_environment", "error", "VC6 build tools were not found on PATH.", None, None, None)
        return BuildProbeReport(source_path, function_name, "environment_missing", False, None, [], [diagnostic], [], [], [], [], [])
    started = datetime.now(timezone.utc)
    start_tick = time.monotonic()
    completed = run_process_tree(
        [_cmd_exe(), "/c", "build.bat"],
        cwd=output_root / "build",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout_seconds=timeout_seconds,
    )
    duration_ms = int((time.monotonic() - start_tick) * 1000)
    finished = datetime.now(timezone.utc)
    log_path = output_root / "logs" / "build.log"
    if log_path.exists():
        log_text = decode_bytes_auto(log_path.read_bytes())
    else:
        log_text = _decode_process_output(completed.stdout)
    if completed.timed_out:
        log_text += f"\nCommand timed out after {timeout_seconds} seconds. Process tree terminated.\n"
    log_path.write_text(log_text, encoding="utf-8")
    parsed = parse_build_log(log_text, stub_candidates)
    diagnostics = list(parsed.diagnostics)
    if completed.timed_out:
        diagnostics.append(BuildDiagnostic("build_probe_timeout", "error", f"Build probe timed out after {timeout_seconds} seconds; the process tree was terminated.", None, None, None))
    exit_code = 124 if completed.timed_out else (completed.returncode if completed.returncode is not None else 1)
    status = "succeeded" if exit_code == 0 else "failed"
    return BuildProbeReport(
        source_path=source_path,
        function_name=function_name,
        status=status,
        executed=True,
        exit_code=completed.returncode,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        duration_ms=duration_ms,
        commands=[BuildCommandResult(build_commands[0].command_id if build_commands else "CMD_BUILD_001", "build_bat", "build.bat", completed.returncode, None, None, Path("logs/build.log"), parsed.diagnostics)],
        diagnostics=parsed.diagnostics,
        missing_includes=parsed.missing_includes,
        unresolved_symbols=parsed.unresolved_symbols,
        pch_issues=parsed.pch_issues,
        vc6_compatibility_issues=parsed.vc6_compatibility_issues,
        log_files=[Path("logs/build.log")],
    )


def _verification_probe_report(output_root: Path, source_path: Path, function_name: str, build_commands: list[BuildCommand], compile_units: list[CompileUnit], include_dirs: list[BuildPathEntry], defines: list[str], compiler_options: list[str], harness_report: dict[str, Any], timeout_seconds: int, vcvars: Path | str | None, cc: Path | str | None, stub_candidates: set[str]) -> BuildProbeReport:
    started = datetime.now(timezone.utc)
    start_tick = time.monotonic()
    verification = run_verification_build(output_root, compile_units, include_dirs, defines, compiler_options, cc=cc, timeout_seconds=timeout_seconds, env_setup=vcvars)
    duration_ms = int((time.monotonic() - start_tick) * 1000)
    finished = datetime.now(timezone.utc)
    if not verification.executed:
        return BuildProbeReport(source_path, function_name, "environment_missing", False, None, [], verification.diagnostics, [], [], [], [], [Path("logs/build.log")], started.isoformat(), finished.isoformat(), duration_ms)
    parsed = parse_build_log(verification.log_text, stub_candidates)
    diagnostics = parsed.diagnostics + verification.diagnostics
    status = "succeeded" if verification.exit_code == 0 else "failed"
    command = build_commands[0] if build_commands else BuildCommand("CMD_BUILD_001", "verification_toolchain", Path("."), verification.command_line, Path("logs/build.log"), False)
    return BuildProbeReport(
        source_path,
        function_name,
        status,
        True,
        verification.exit_code,
        [BuildCommandResult(command.command_id, command.command_kind, verification.command_line, verification.exit_code if verification.exit_code is not None else 1, None, None, Path("logs/build.log"), diagnostics)],
        diagnostics,
        parsed.missing_includes,
        parsed.unresolved_symbols,
        parsed.pch_issues,
        parsed.vc6_compatibility_issues,
        [Path("logs/build.log")],
        started.isoformat(),
        finished.isoformat(),
        duration_ms,
    )


def _compile_command(source: Path, object_file: Path, include_dirs: list[BuildPathEntry], defines: list[str], compiler_options: list[str]) -> str:
    include_args = " ".join(f'/I"{entry.raw}"' for entry in include_dirs)
    define_args = " ".join(f'/D"{define}"' for define in defines)
    option_args = " ".join(compiler_options)
    return f'cl {option_args} {define_args} {include_args} /Fo"{object_file.as_posix()}" /c "{source.as_posix()}"'


def _render_makefile(compile_units: list[CompileUnit], include_dirs: list[BuildPathEntry], defines: list[str], compiler_options: list[str]) -> str:
    objects = " ".join(_makefile_workspace_file(unit.object_file) for unit in compile_units)
    lines = [
        "# generated VC6 build probe Makefile",
        "CC=cl",
        "LINK=link",
        f"CFLAGS={' '.join(compiler_options)} {' '.join('/D\"' + item + '\"' for item in defines)} {' '.join(_makefile_include_arg(item) for item in include_dirs)}",
        f"OBJS={objects}",
        "",
        "all: ..\\bin\\utr_probe.exe",
        "",
        "..\\bin\\utr_probe.exe: $(OBJS)",
        "\t$(LINK) /nologo /OPT:REF /OUT:$@ $(OBJS)",
        "",
    ]
    for unit in compile_units:
        source = _makefile_workspace_file(unit.source_file)
        obj = _makefile_workspace_file(unit.object_file)
        lines.extend([f"{obj}: {source}", f"\t$(CC) $(CFLAGS) /Fo\"{obj}\" /c \"{source}\"", ""])
    return "\n".join(lines)


def _render_build_bat(vcvars: Path | str | None) -> str:
    lines = ["@echo off", "setlocal", "rem generated build probe script", "rem review required"]
    if vcvars:
        lines.append(f'if exist "{vcvars}" call "{vcvars}"')
    lines.extend(["nmake /f Makefile > ..\\logs\\build.log 2>&1", "set BUILD_EXIT=%ERRORLEVEL%", "exit /b %BUILD_EXIT%"])
    return "\n".join(lines)


def _makefile_workspace_file(path: Path) -> str:
    return (Path("..") / path).as_posix().replace("/", "\\")


def _makefile_include_arg(entry: BuildPathEntry) -> str:
    if "$(" in entry.raw:
        include_path = entry.raw
    elif Path(entry.raw).is_absolute():
        include_path = entry.raw
    else:
        workspace_path = entry.workspace_path or Path(entry.raw)
        include_path = (Path("..") / workspace_path).as_posix()
    include_path = include_path.replace("/", "\\")
    return f'/I"{include_path}"'


def _relative_or_name(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return Path(path.name)


def _is_under_declared_include_dir(relative_path: Path, build_context: dict[str, Any]) -> bool:
    normalized = relative_path.as_posix().lower()
    for raw in build_context.get("include_dirs", []):
        text = str(raw.get("normalized") or raw.get("raw") or raw.get("path") or raw.get("absolute") if isinstance(raw, dict) else raw)
        include_dir = text.replace("\\", "/").strip("/").lower()
        if include_dir and (normalized == include_dir or normalized.startswith(include_dir + "/")):
            return True
    return False


def _normalize_toolchain(toolchain: str | None) -> str:
    value = (toolchain or "vc6").strip().lower()
    aliases = {"vc6": "vc6", "verification": "verification", "verify": "verification", "host": "verification"}
    if value not in aliases:
        raise ValueError(f"Unsupported build toolchain: {toolchain}")
    return aliases[value]


def _verification_command_line(cc: Path | str | None) -> str:
    args = ["unit-test-runner", "build-probe", "--workspace", ".", "--run", "--toolchain", "verification"]
    if cc:
        args.extend(["--cc", str(cc)])
    return " ".join(args)


def _decode_process_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    return decode_bytes_auto(output)


def _cmd_exe() -> str:
    return "cmd" + ".exe"
