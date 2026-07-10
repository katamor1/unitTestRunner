from __future__ import annotations

from pathlib import Path
from typing import Any

from ..dsw_parser import parse_dsw as parse_dsw_workspace
from ..models import Project
from ..path_utils import normalize_relative
from .dsp_models import DspConfiguration, DspProject
from .dsp_parser import parse_dsp as parse_dsp_project
from .source_membership import map_source_membership, membership_to_legacy_matches


def parse_dsw(dsw_path: Path | str) -> dict[str, Any]:
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


def parse_dsp(dsp_path: Path | str, workspace_root: Path | str) -> dict[str, Any]:
    project = parse_dsp_project(dsp_path, workspace_root)
    return _project_to_legacy(project, Path(workspace_root).resolve())


def discover_workspace(workspace_root: Path | str, dsw_path: Path | str) -> dict[str, Any]:
    workspace_root = Path(workspace_root).resolve()
    dsw = parse_dsw(dsw_path)
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


def map_source_to_projects(
    workspace_root: Path | str,
    dsw_path: Path | str,
    source: str | Path,
    project_name: str | None = None,
) -> list[dict[str, Any]]:
    membership = map_source_membership(dsw_path, source, project_name=project_name)
    return membership_to_legacy_matches(membership, workspace_root)


def select_project_context(
    workspace_root: Path | str,
    dsw_path: Path | str,
    source: str | Path,
    configuration: str,
    project_name: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    workspace = discover_workspace(workspace_root, dsw_path)
    memberships = map_source_to_projects(workspace_root, dsw_path, source, project_name)
    source_key = _normalize_source_arg(Path(workspace_root).resolve(), source)
    for project in workspace["projects"]:
        if project_name and project["project_name"] != project_name:
            continue
        if source_key not in project["sources"]:
            continue
        selected_configuration = _select_legacy_configuration(project["configurations"], configuration)
        if selected_configuration is not None:
            return project, selected_configuration, memberships
    raise ValueError(f"No project/configuration found for {source_key} ({project_name or 'any project'} / {configuration})")


def _project_to_legacy(project: DspProject, workspace_root: Path) -> dict[str, Any]:
    configurations = {}
    for configuration in project.configurations:
        key = _short_configuration(configuration)
        configurations[key] = _configuration_to_legacy(configuration, workspace_root)
    return Project(
        project_name=project.name,
        dsp=normalize_relative(project.path, workspace_root),
        sources=[normalize_relative(entry.source_path_absolute, workspace_root) for entry in project.files if entry.file_kind == "source"],
        headers=[normalize_relative(entry.source_path_absolute, workspace_root) for entry in project.files if entry.file_kind == "header"],
        configurations={},
    ).to_dict() | {"configurations": configurations}


def _configuration_to_legacy(configuration: DspConfiguration, workspace_root: Path) -> dict[str, Any]:
    settings = configuration.build_settings
    diagnostics = []
    include_dirs = []
    for include_dir in settings.include_dirs:
        if include_dir.absolute is None:
            include_dirs.append(include_dir.normalized)
            diagnostics.append({"severity": "warning", "message": f"Unresolved macro in include dir: {include_dir.raw}"})
        else:
            include_dirs.append(normalize_relative(include_dir.absolute, workspace_root))
            if include_dir.exists is False:
                diagnostics.append({"severity": "warning", "message": f"Include dir does not exist: {include_dir.normalized}"})
    return {
        "full_name": configuration.full_name,
        "defines": list(settings.defines),
        "include_dirs": include_dirs,
        "forced_includes": list(settings.forced_includes),
        "precompiled_header": {
            "enabled": settings.pch_mode is not None,
            "header": settings.pch_header,
            "mode": settings.pch_mode,
        },
        "compiler_options": list(settings.raw_options),
        "unresolved_macros": list(settings.unresolved_macros),
        "diagnostics": diagnostics,
    }


def _select_legacy_configuration(configurations: dict[str, Any], requested: str) -> dict[str, Any] | None:
    if requested in configurations:
        return configurations[requested]
    requested_lower = requested.lower()
    for key, value in configurations.items():
        full_name = value.get("full_name") if isinstance(value, dict) else None
        candidates = [key, full_name]
        if any(isinstance(candidate, str) and candidate.lower() == requested_lower for candidate in candidates):
            return value
    return None


def _normalize_source_arg(workspace_root: Path, source: str | Path) -> str:
    source_path = Path(source)
    if source_path.is_absolute():
        return normalize_relative(source_path.resolve(), workspace_root)
    return str(source).replace("\\", "/")


def _short_configuration(configuration: DspConfiguration) -> str:
    if configuration.project_name and configuration.full_name.startswith(configuration.project_name + " - "):
        return configuration.full_name[len(configuration.project_name) + 3 :]
    return configuration.name or configuration.full_name


# Keep the core writer small and apply the legacy-IDE response-file workaround
# as a compatibility layer, matching the build/harness compatibility pattern.
from . import debug_workspace_writer as _debug_workspace_writer  # noqa: E402
from .debug_workspace_response import (  # noqa: E402
    write_vc6_debug_project as _write_vc6_debug_project,
    write_vc6_debug_suite as _write_vc6_debug_suite,
)

_debug_workspace_writer.write_vc6_debug_project = _write_vc6_debug_project
_debug_workspace_writer.write_vc6_debug_suite = _write_vc6_debug_suite
