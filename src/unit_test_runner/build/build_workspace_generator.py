from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unit_test_runner.encoding import decode_bytes_auto
from unit_test_runner.harness.c90_writer import sha256_file

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
    copied_files = _copy_target_and_headers(output_root, source_path, source_digest, build_context, diagnostics)
    generated_files = _copy_or_verify_generated_files(output_root, harness_report, diagnostics)
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


def _copy_target_and_headers(output_root: Path, source_path: Path, source_digest: dict[str, Any], build_context: dict[str, Any], diagnostics: list[BuildDiagnostic]) -> list[WorkspaceFile]:
    copied: list[WorkspaceFile] = []
    workspace_root = Path(build_context.get("workspace_root") or source_path.parent)
    target_relative = _relative_or_name(source_path, workspace_root)
    target_workspace = Path("extracted") / target_relative
    _copy_file(source_path, output_root / target_workspace, copied, target_workspace, "target_source", diagnostics)
    for include in source_digest.get("preprocessor", {}).get("includes", []):
        candidates = [Path(item) for item in include.get("resolved_candidates", []) if item]
        existing = next((item for item in candidates if item.exists()), None)
        if existing is None:
            continue
        include_relative = _relative_or_name(existing, workspace_root)
        if (include_relative.parts and include_relative.parts[0].lower() == "include") or _is_under_declared_include_dir(include_relative, build_context):
            destination_relative = Path("extracted") / include_relative
        else:
            destination_relative = Path("extracted") / "include" / existing.name
        _copy_file(existing, output_root / destination_relative, copied, destination_relative, "target_header", diagnostics)
    return copied


def _copy_file(source: Path, destination: Path, copied: list[WorkspaceFile], relative_destination: Path, kind: str, diagnostics: list[BuildDiagnostic]) -> None:
    if not source.exists():
        diagnostics.append(BuildDiagnostic("missing_source_file", "error", f"Source file is missing: {source}", source, None, None))
        copied.append(WorkspaceFile(relative_destination, kind, source_path=source, copied=False, generated=False, required=True, exists=False))
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    copied.append(WorkspaceFile(relative_destination, kind, source_path=source, sha256=sha256_file(destination), copied=True, generated=False, required=True, exists=True))


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
    source_files.extend(item.workspace_path for item in generated_files if item.exists and item.file_kind in {"assert_source", "runner_source", "stub_source", "test_source", "target_invocation_source"})
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
    completed = subprocess.run([_cmd_exe(), "/c", "build.bat"], cwd=output_root / "build", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout_seconds, check=False)
    duration_ms = int((time.monotonic() - start_tick) * 1000)
    finished = datetime.now(timezone.utc)
    log_path = output_root / "logs" / "build.log"
    if log_path.exists():
        log_text = decode_bytes_auto(log_path.read_bytes())
    else:
        log_text = _decode_process_output(completed.stdout)
        log_path.write_text(log_text, encoding="utf-8")
    parsed = parse_build_log(log_text, stub_candidates)
    status = "succeeded" if completed.returncode == 0 else "failed"
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
    objects = " ".join(unit.object_file.as_posix().replace("/", "\\") for unit in compile_units)
    lines = ["# generated VC6 build probe Makefile", "CC=cl", "LINK=link", f"CFLAGS={' '.join(compiler_options)} {' '.join('/D\"' + item + '\"' for item in defines)} {' '.join(_makefile_include_arg(item) for item in include_dirs)}", f"OBJS={objects}", "", "all: ..\\bin\\utr_probe.exe", "", "..\\bin\\utr_probe.exe: $(OBJS)", "\t$(LINK) /nologo /OUT:$@ $(OBJS)", ""]
    for unit in compile_units:
        source = unit.source_file.as_posix().replace("/", "\\")
        obj = unit.object_file.as_posix().replace("/", "\\")
        lines.extend([f"{obj}: ..\\{source}", f"\t$(CC) $(CFLAGS) /Fo\"{obj}\" /c \"..\\{source}\"", ""])
    return "\n".join(lines)


def _render_build_bat(vcvars: Path | str | None) -> str:
    lines = ["@echo off", "setlocal", "rem generated build probe script", "rem review required"]
    if vcvars:
        lines.append(f'if exist "{vcvars}" call "{vcvars}"')
    lines.extend(["nmake /f Makefile > ..\\logs\\build.log 2>&1", "set BUILD_EXIT=%ERRORLEVEL%", "exit /b %BUILD_EXIT%"])
    return "\n".join(lines)


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
        include_dir = str(raw).replace("\\", "/").strip("/").lower()
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
