from __future__ import annotations

from pathlib import Path
from typing import Any

from ..path_utils import normalize_relative
from .dsp_models import DspBuildSettings, DspConfiguration, DspProject
from .dsp_parser import effective_source_build_settings, parse_dsp
from .source_membership import map_source_membership


class ProjectContextSelectionError(ValueError):
    def __init__(self, message: str, candidates: list[dict[str, Any]]):
        super().__init__(message)
        self.status = "blocked"
        self.candidates = candidates


def select_project_context(
    workspace_root: Path | str,
    dsw_path: Path | str,
    source: str | Path,
    configuration: str,
    project_name: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    root = Path(workspace_root).resolve()
    membership = map_source_membership(
        dsw_path,
        source,
        project_name=project_name,
        configuration=configuration,
    )
    candidates = [
        {
            "project_name": match.project_name,
            "dsp_path": normalize_relative(match.dsp_path.resolve(), root),
            "configuration": selected.full_name,
            "source": normalize_relative(
                match.source_entry.source_path_absolute.resolve(),
                root,
            ),
        }
        for match in membership.matches
        for selected in match.configurations
    ]
    if len(candidates) != 1:
        source_key = _normalize_source_arg(root, source)
        reason = "No" if not candidates else "Multiple"
        raise ProjectContextSelectionError(
            f"{reason} unique project/configuration/source selection for {source_key} "
            f"({project_name or 'any project'} / {configuration}).",
            candidates,
        )

    selected_match = membership.matches[0]
    selected_configuration = selected_match.configurations[0]
    project = parse_dsp(selected_match.dsp_path, root)
    configuration_model = next(
        item
        for item in project.configurations
        if item.full_name == selected_configuration.full_name
    )
    source_entry = next(
        item
        for item in project.files
        if item.line_number == selected_match.source_entry.line_number
        and item.source_path_absolute.resolve()
        == selected_match.source_entry.source_path_absolute.resolve()
    )
    settings = effective_source_build_settings(
        project,
        configuration_model,
        source_entry,
    )
    return (
        _project_context(project, root),
        _configuration_context(configuration_model, settings, root),
        [match.to_dict() for match in membership.matches],
    )


def _project_context(project: DspProject, workspace_root: Path) -> dict[str, Any]:
    return {
        "project_name": project.name,
        "dsp": normalize_relative(project.path, workspace_root),
        "sources": [
            normalize_relative(entry.source_path_absolute, workspace_root)
            for entry in project.files
            if entry.file_kind == "source"
        ],
        "headers": [
            normalize_relative(entry.source_path_absolute, workspace_root)
            for entry in project.files
            if entry.file_kind == "header"
        ],
    }


def _configuration_context(
    configuration: DspConfiguration,
    settings: DspBuildSettings,
    workspace_root: Path,
) -> dict[str, Any]:
    diagnostics: list[dict[str, str]] = []
    include_dirs: list[str] = []
    for include_dir in settings.include_dirs:
        if include_dir.absolute is None:
            include_dirs.append(include_dir.normalized)
            diagnostics.append(
                {
                    "severity": "warning",
                    "message": f"Unresolved macro in include dir: {include_dir.raw}",
                }
            )
        else:
            include_dirs.append(
                normalize_relative(include_dir.absolute, workspace_root)
            )
            if include_dir.exists is False:
                diagnostics.append(
                    {
                        "severity": "warning",
                        "message": f"Include dir does not exist: {include_dir.normalized}",
                    }
                )
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


def _normalize_source_arg(workspace_root: Path, source: str | Path) -> str:
    source_path = Path(source)
    if source_path.is_absolute():
        return normalize_relative(source_path.resolve(), workspace_root)
    return str(source).replace("\\", "/")
