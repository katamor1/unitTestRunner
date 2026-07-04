from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .dsw_parser import parse_dsw as parse_dsw_workspace
from .encoding import read_text_auto
from .models import BuildConfiguration, Project
from .path_utils import normalize_include_dir, normalize_relative, resolve_vc6_path


CFG_RE = re.compile(r'!\s*(?:IF|ELSEIF)\s+"\$\(CFG\)"\s*==\s*"(?P<cfg>[^"]+)"')
NAME_RE = re.compile(r'Name="(?P<name>[^"]+)"')


def _read_text(path: Path) -> str:
    return read_text_auto(path)


def _short_configuration(full_name: str, project_name: str) -> str:
    prefix = project_name + " - "
    if full_name.startswith(prefix):
        return full_name[len(prefix) :]
    if " - " in full_name:
        return full_name.split(" - ", 1)[1]
    return full_name


def parse_dsw(dsw_path: Path) -> dict[str, Any]:
    dsw_path = Path(dsw_path).resolve()
    workspace = parse_dsw_workspace(dsw_path)
    dependency_map: dict[str, list[str]] = {}
    for dependency in workspace.dependencies:
        dependency_map.setdefault(dependency.from_project, []).append(dependency.to_project)
    return {
        "workspace_name": dsw_path.stem,
        "dsw": normalize_relative(dsw_path, dsw_path.parent),
        "projects": [
            {
                "project_name": project.name,
                "dsp_path": project.dsp_path_absolute,
                "dsp": project.dsp_path.as_posix(),
                "dependencies": dependency_map.get(project.name, []),
            }
            for project in workspace.projects
        ],
    }


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _parse_cpp_options(line: str, dsp_dir: Path, workspace_root: Path) -> dict[str, Any]:
    defines: list[str] = []
    include_dirs: list[str] = []
    forced_includes: list[str] = []
    unresolved_macros: list[str] = []
    compiler_options: list[str] = []
    pch = {"enabled": False, "header": None, "mode": None}

    for value in re.findall(r'/D\s*"?([^"\s]+)"?', line):
        _append_unique(defines, value)
    for value in re.findall(r'/I\s*"?([^"\s]+)"?', line):
        normalized, unresolved = normalize_include_dir(dsp_dir, workspace_root, value)
        _append_unique(include_dirs, normalized)
        for macro in unresolved:
            _append_unique(unresolved_macros, macro)
    for value in re.findall(r'/FI\s*"?([^"\s]+)"?', line):
        _append_unique(forced_includes, value.replace("\\", "/"))

    yu = re.search(r'/Yu\s*"?([^"\s]+)"?', line)
    yc = re.search(r'/Yc\s*"?([^"\s]+)"?', line)
    if yu:
        pch = {"enabled": True, "header": yu.group(1), "mode": "use"}
    if yc:
        pch = {"enabled": True, "header": yc.group(1), "mode": "create"}

    for option in re.findall(r'/(?:[A-Za-z][A-Za-z0-9]*)(?:"[^"]*"|[^\s"]*)?', line):
        _append_unique(compiler_options, option)

    return {
        "defines": defines,
        "include_dirs": include_dirs,
        "forced_includes": forced_includes,
        "precompiled_header": pch,
        "compiler_options": compiler_options,
        "unresolved_macros": unresolved_macros,
    }


def _merge_options(target: BuildConfiguration, options: dict[str, Any]) -> None:
    for key in ("defines", "include_dirs", "forced_includes", "compiler_options", "unresolved_macros"):
        items = getattr(target, key)
        for value in options[key]:
            _append_unique(items, value)
    if options["precompiled_header"]["enabled"]:
        target.precompiled_header = options["precompiled_header"]


def _empty_configuration(full_name: str) -> BuildConfiguration:
    return BuildConfiguration(
        full_name=full_name,
        precompiled_header={"enabled": False, "header": None, "mode": None},
    )


def _classify_sources(text: str, dsp_path: Path, workspace_root: Path) -> tuple[list[str], list[str]]:
    sources: list[str] = []
    headers: list[str] = []
    for raw in re.findall(r"^SOURCE=(.+)$", text, flags=re.MULTILINE):
        resolved = resolve_vc6_path(dsp_path.parent, raw)
        relative = normalize_relative(resolved, workspace_root)
        suffix = resolved.suffix.lower()
        if suffix in (".c", ".cpp", ".cxx"):
            _append_unique(sources, relative)
        elif suffix in (".h", ".hpp", ".hxx", ".inc"):
            _append_unique(headers, relative)
    return sources, headers


def parse_dsp(dsp_path: Path, workspace_root: Path) -> dict[str, Any]:
    dsp_path = Path(dsp_path).resolve()
    workspace_root = Path(workspace_root).resolve()
    text = _read_text(dsp_path)
    name_match = NAME_RE.search(text)
    project_name = name_match.group("name") if name_match else dsp_path.stem
    sources, headers = _classify_sources(text, dsp_path, workspace_root)
    configurations: dict[str, BuildConfiguration] = {}
    current_config: str | None = None

    for line in text.splitlines():
        cfg_match = CFG_RE.search(line)
        if cfg_match:
            full_name = cfg_match.group("cfg")
            short_name = _short_configuration(full_name, project_name)
            current_config = short_name
            configurations.setdefault(short_name, _empty_configuration(full_name))
            continue
        if line.startswith("!ENDIF"):
            current_config = None
            continue
        if current_config and line.startswith("# ADD") and " CPP " in line:
            options = _parse_cpp_options(line, dsp_path.parent, workspace_root)
            _merge_options(configurations[current_config], options)

    for config in configurations.values():
        for include_dir in config.include_dirs:
            if "$(" in include_dir:
                config.diagnostics.append({"severity": "warning", "message": f"Unresolved macro in include dir: {include_dir}"})
            else:
                include_path = workspace_root / include_dir
                if not include_path.exists():
                    config.diagnostics.append({"severity": "warning", "message": f"Include dir does not exist: {include_dir}"})

    return Project(
        project_name=project_name,
        dsp=normalize_relative(dsp_path, workspace_root),
        sources=sources,
        headers=headers,
        configurations=configurations,
    ).to_dict()


def discover_workspace(workspace_root: Path | str, dsw_path: Path | str) -> dict[str, Any]:
    workspace_root = Path(workspace_root).resolve()
    dsw = parse_dsw(Path(dsw_path))
    projects = []
    for project_ref in dsw["projects"]:
        parsed = parse_dsp(project_ref["dsp_path"], workspace_root)
        parsed["dependencies"] = project_ref["dependencies"]
        projects.append(parsed)
    return {
        "workspace_name": dsw["workspace_name"],
        "dsw": normalize_relative(Path(dsw_path).resolve(), workspace_root),
        "projects": projects,
    }


def _normalize_source_arg(workspace_root: Path, source: str | Path) -> str:
    source_path = Path(source)
    if source_path.is_absolute():
        return normalize_relative(source_path.resolve(), workspace_root)
    return source.replace("\\", "/")


def map_source_to_projects(
    workspace_root: Path | str,
    dsw_path: Path | str,
    source: str | Path,
    project_name: str | None = None,
) -> list[dict[str, Any]]:
    workspace_root = Path(workspace_root).resolve()
    target = _normalize_source_arg(workspace_root, source)
    workspace = discover_workspace(workspace_root, dsw_path)
    matches: list[dict[str, Any]] = []
    for project in workspace["projects"]:
        if project_name and project["project_name"] != project_name:
            continue
        if target not in project["sources"]:
            continue
        for configuration_name, configuration in project["configurations"].items():
            matches.append(
                {
                    "dsw": workspace["dsw"],
                    "dsp": project["dsp"],
                    "project_name": project["project_name"],
                    "configuration": configuration_name,
                    "configuration_full_name": configuration["full_name"],
                    "source": target,
                }
            )
    return matches


def select_project_context(
    workspace_root: Path | str,
    dsw_path: Path | str,
    source: str | Path,
    configuration: str,
    project_name: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    workspace = discover_workspace(workspace_root, dsw_path)
    source_key = _normalize_source_arg(Path(workspace_root).resolve(), source)
    memberships = map_source_to_projects(workspace_root, dsw_path, source, project_name)
    for project in workspace["projects"]:
        if project_name and project["project_name"] != project_name:
            continue
        if source_key not in project["sources"]:
            continue
        if configuration in project["configurations"]:
            return project, project["configurations"][configuration], memberships
    raise ValueError(f"No project/configuration found for {source_key} ({project_name or 'any project'} / {configuration})")
