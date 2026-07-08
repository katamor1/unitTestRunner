from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from unit_test_runner.harness.c90_writer import sanitize_identifier


@dataclass
class Vc6DebugProject:
    entry_id: str | None
    function_name: str
    workspace: Path
    dsp_path: Path
    project_name: str

    def to_dict(self) -> dict[str, str]:
        return {
            "entry_id": self.entry_id or "",
            "function": self.function_name,
            "workspace": self.workspace.as_posix(),
            "dsp": self.dsp_path.as_posix(),
            "project_name": self.project_name,
        }


@dataclass
class Vc6DebugSuiteResult:
    dsw_path: Path
    projects: list[Vc6DebugProject]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dsw": self.dsw_path.as_posix(),
            "projects": [project.to_dict() for project in self.projects],
            "warnings": list(self.warnings),
        }


def write_vc6_debug_project(workspace: Path | str, build_workspace_report: Any | None = None, project_name: str | None = None) -> Path:
    workspace = Path(workspace).resolve()
    report = _report_payload(workspace, build_workspace_report)
    function_name = _function_name(report)
    safe_project = _safe_project_name(project_name or f"UTR_{function_name}")
    dsp_path = workspace / "build" / f"{safe_project}.dsp"
    dsp_text = _render_dsp(workspace, dsp_path, report, safe_project, function_name)
    _write_vc6_text(dsp_path, dsp_text)
    return dsp_path


def write_vc6_debug_suite(suite_path: Path | str, manifest: Any, out: Path | str | None = None) -> Vc6DebugSuiteResult:
    suite_path = Path(suite_path).resolve()
    dsw_path = Path(out).resolve() if out else suite_path.parent / "vc6_debug_suite.dsw"
    projects: list[Vc6DebugProject] = []
    warnings: list[str] = []
    used_names: set[str] = set()
    for index, entry in enumerate(getattr(manifest, "entries", []), start=1):
        if not getattr(entry, "enabled", True):
            continue
        function_payload = getattr(entry, "function", {})
        function_name = function_payload.get("name") if isinstance(function_payload, dict) else None
        function_name = function_name or f"Entry_{index}"
        project_name = _unique_project_name(_safe_project_name(f"UTR_{function_name}"), used_names, index)
        try:
            dsp_path = write_vc6_debug_project(entry.workspace, project_name=project_name)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            warnings.append(f"{entry.entry_id}: VC6 DSP生成をスキップしました: {exc}")
            continue
        projects.append(
            Vc6DebugProject(
                entry_id=entry.entry_id,
                function_name=function_name,
                workspace=entry.workspace,
                dsp_path=dsp_path,
                project_name=project_name,
            )
        )
    _write_vc6_text(dsw_path, _render_dsw(dsw_path, projects))
    return Vc6DebugSuiteResult(dsw_path=dsw_path, projects=projects, warnings=warnings)


def _report_payload(workspace: Path, build_workspace_report: Any | None) -> dict[str, Any]:
    if build_workspace_report is None:
        report_path = workspace / "reports" / "build_workspace_report.json"
        if not report_path.exists():
            raise FileNotFoundError(f"build workspace report not found: {report_path}")
        return json.loads(report_path.read_text(encoding="utf-8"))
    if hasattr(build_workspace_report, "to_dict"):
        return build_workspace_report.to_dict()
    if isinstance(build_workspace_report, dict):
        return build_workspace_report
    raise TypeError(f"Unsupported build workspace report type: {type(build_workspace_report)!r}")


def _render_dsp(workspace: Path, dsp_path: Path, report: dict[str, Any], project_name: str, function_name: str) -> str:
    configuration = f"{project_name} - Win32 Debug"
    include_args = " ".join(_dsp_include_arg(dsp_path.parent, workspace, item) for item in report.get("include_dirs", []))
    define_args = " ".join(f'/D "{_escape_option(str(item))}"' for item in report.get("defines", []))
    compiler_options = " ".join(_dsp_compiler_options(report.get("compiler_options", [])))
    source_files = _source_files(report)
    header_files = _header_files(workspace, report)
    lines = [
        "# Microsoft Developer Studio Project File - Name=\"" + project_name + "\" - Package Owner=<4>",
        "# Microsoft Developer Studio Generated Build File, Format Version 6.00",
        "# ** この .dsp は unit-test-runner が VC6 デバッグ用に生成しました。**",
        "# TARGTYPE \"Win32 (x86) Console Application\" 0x0103",
        "",
        "CFG=" + configuration,
        "!MESSAGE This is not a valid makefile. To build this project using NMAKE,",
        "!MESSAGE use the Export Makefile command and run",
        "!MESSAGE ",
        "!MESSAGE NMAKE /f \"" + project_name + ".mak\".",
        "!MESSAGE ",
        "!MESSAGE You can specify a configuration when running NMAKE",
        "!MESSAGE by defining the macro CFG on the command line.",
        "!MESSAGE ",
        "!MESSAGE Possible choices for configuration are:",
        "!MESSAGE ",
        "!MESSAGE \"" + configuration + "\" (based on \"Win32 (x86) Console Application\")",
        "!MESSAGE ",
        "",
        "# Begin Project",
        "# PROP AllowPerConfigDependencies 0",
        "# PROP Scc_ProjName \"\"",
        "# PROP Scc_LocalPath \"\"",
        "CPP=cl.exe",
        "RSC=rc.exe",
        "",
        "!IF  \"$(CFG)\" == \"" + configuration + "\"",
        "",
        "# PROP BASE Use_MFC 0",
        "# PROP BASE Use_Debug_Libraries 1",
        "# PROP BASE Output_Dir \"..\\bin\"",
        "# PROP BASE Intermediate_Dir \"..\\obj\"",
        "# PROP BASE Target_Dir \"\"",
        "# PROP Use_MFC 0",
        "# PROP Use_Debug_Libraries 1",
        "# PROP Output_Dir \"..\\bin\"",
        "# PROP Intermediate_Dir \"..\\obj\"",
        "# PROP Target_Dir \"\"",
        "# ADD BASE CPP /nologo /W3 /Gm /ZI /Od /D \"WIN32\" /D \"_DEBUG\" /D \"_CONSOLE\" /c",
        f"# ADD CPP {compiler_options} {define_args} /D \"_CONSOLE\" {include_args} /Fo\"..\\obj\\\" /Fd\"..\\obj\\\" /c".strip(),
        "# ADD BASE RSC /l 0x411 /d \"_DEBUG\"",
        "# ADD RSC /l 0x411 /d \"_DEBUG\"",
        "BSC32=bscmake.exe",
        "# ADD BASE BSC32 /nologo",
        "# ADD BSC32 /nologo",
        "LINK32=link.exe",
        "# ADD BASE LINK32 /nologo /subsystem:console /debug /machine:I386",
        "# ADD LINK32 /nologo /subsystem:console /debug /machine:I386 /out:\"..\\bin\\utr_probe.exe\" /pdb:\"..\\bin\\utr_probe.pdb\"",
        "",
        "!ENDIF ",
        "",
        "# Begin Target",
        "",
        "# Name \"" + configuration + "\"",
        _render_group("Source Files", "cpp;c;cxx;rc;def;r;odl;idl;hpj;bat", dsp_path.parent, workspace, source_files),
        _render_group("Header Files", "h;hpp;hxx;hm;inl", dsp_path.parent, workspace, header_files),
        "# End Target",
        "# End Project",
        "",
    ]
    return "\r\n".join(lines)


def _render_group(title: str, default_filter: str, dsp_dir: Path, workspace: Path, files: list[Path]) -> str:
    lines = [f"# Begin Group \"{title}\"", "", f"# PROP Default_Filter \"{default_filter}\""]
    for file_path in files:
        lines.extend(["# Begin Source File", "", "SOURCE=" + _dsp_source_path(dsp_dir, workspace / file_path), "# End Source File"])
    lines.append("# End Group")
    return "\r\n".join(lines)


def _source_files(report: dict[str, Any]) -> list[Path]:
    result: list[Path] = []
    for unit in report.get("compile_units", []):
        source = unit.get("source_file") if isinstance(unit, dict) else getattr(unit, "source_file", None)
        if source:
            result.append(Path(str(source)))
    return _unique_paths(result)


def _header_files(workspace: Path, report: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for key in ("copied_files", "generated_build_files", "referenced_files"):
        for item in report.get(key, []):
            path = item.get("workspace_path") if isinstance(item, dict) else getattr(item, "workspace_path", None)
            kind = item.get("file_kind", "") if isinstance(item, dict) else getattr(item, "file_kind", "")
            if path and (str(path).lower().endswith((".h", ".hpp", ".hxx")) or "header" in str(kind)):
                paths.append(Path(str(path)))
    for root in (workspace / "generated", workspace / "extracted"):
        if root.exists():
            for suffix in ("*.h", "*.hpp", "*.hxx"):
                for header in root.rglob(suffix):
                    try:
                        paths.append(header.relative_to(workspace))
                    except ValueError:
                        pass
    return _unique_paths(paths)


def _dsp_compiler_options(options: list[Any]) -> list[str]:
    values = [str(item) for item in options if str(item).strip()]
    if not any(item.lower() == "/nologo" for item in values):
        values.insert(0, "/nologo")
    if not any(item.upper().startswith("/W") for item in values):
        values.append("/W3")
    if not any(item.upper().startswith("/Z") for item in values):
        values.append("/ZI")
    if not any(item.upper().startswith("/O") for item in values):
        values.append("/Od")
    return values


def _dsp_include_arg(dsp_dir: Path, workspace: Path, item: dict[str, Any]) -> str:
    workspace_path = item.get("workspace_path") if isinstance(item, dict) else getattr(item, "workspace_path", None)
    raw = item.get("raw") if isinstance(item, dict) else getattr(item, "raw", None)
    if workspace_path:
        path = _relative_windows(dsp_dir, workspace / Path(str(workspace_path)))
    else:
        path = str(raw or "").replace("/", "\\")
    return f'/I "{_escape_option(path)}"' if path else ""


def _render_dsw(dsw_path: Path, projects: list[Vc6DebugProject]) -> str:
    lines = ["Microsoft Developer Studio Workspace File, Format Version 6.00", "", "###############################################################################", ""]
    for project in projects:
        relative_dsp = _relative_windows(dsw_path.parent, project.dsp_path)
        lines.extend(
            [
                f'Project: "{project.project_name}"={_quote_if_needed(relative_dsp)} - Package Owner=<4>',
                "",
                "Package=<5>",
                "{{{",
                "}}}",
                "",
                "Package=<4>",
                "{{{",
                "}}}",
                "",
                "###############################################################################",
                "",
            ]
        )
    lines.extend(["Global:", "", "Package=<5>", "{{{", "}}}", "", "Package=<3>", "{{{", "}}}", "", "###############################################################################", ""])
    return "\r\n".join(lines)


def _function_name(report: dict[str, Any]) -> str:
    function = report.get("function") if isinstance(report.get("function"), dict) else {}
    return str(function.get("name") or report.get("function_name") or "unit_test")


def _safe_project_name(value: str) -> str:
    sanitized = sanitize_identifier(value, "UTR_Project")
    return sanitized[:80]


def _unique_project_name(base: str, used: set[str], index: int) -> str:
    candidate = base
    if candidate not in used:
        used.add(candidate)
        return candidate
    candidate = f"{base}_{index:03d}"
    counter = index
    while candidate in used:
        counter += 1
        candidate = f"{base}_{counter:03d}"
    used.add(candidate)
    return candidate


def _dsp_source_path(dsp_dir: Path, path: Path) -> str:
    return _quote_if_needed(_relative_windows(dsp_dir, path))


def _relative_windows(base: Path, path: Path) -> str:
    try:
        relative = os.path.relpath(path.resolve(), base.resolve())
    except (OSError, ValueError):
        relative = str(path)
    return relative.replace("/", "\\")


def _quote_if_needed(path: str) -> str:
    if " " in path or "\t" in path:
        return f'"{path}"'
    return path


def _escape_option(value: str) -> str:
    return str(value).replace('"', '\\"')


def _unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = path.as_posix().lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _write_vc6_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    with path.open("w", encoding="cp932", newline="\r\n") as handle:
        handle.write(normalized)
        if not normalized.endswith("\n"):
            handle.write("\n")
