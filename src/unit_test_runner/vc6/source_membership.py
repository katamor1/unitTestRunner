from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..dsw_parser import parse_dsw
from ..path_utils import normalize_relative
from .dsp_models import DspConfiguration, DspFileEntry, DspParseWarning
from .dsp_parser import parse_dsp


@dataclass
class SourceMembershipMatch:
    dsw_path: Path | None
    dsp_path: Path
    project_name: str
    source_entry: DspFileEntry
    configurations: list[DspConfiguration]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dsw_path": str(self.dsw_path).replace("\\", "/") if self.dsw_path else None,
            "dsp_path": str(self.dsp_path).replace("\\", "/"),
            "project_name": self.project_name,
            "source_entry": self.source_entry.to_dict(),
            "configurations": [_short_configuration(configuration) for configuration in self.configurations],
            "configuration_details": [configuration.to_dict() for configuration in self.configurations],
        }


@dataclass
class SourceMembership:
    source_input: str
    source_absolute: Path
    matches: list[SourceMembershipMatch] = field(default_factory=list)
    warnings: list[DspParseWarning] = field(default_factory=list)
    candidate_projects: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = "0.1"
    command: str = "map-source"

    @property
    def status(self) -> str:
        if len(self.matches) > 1:
            return "multiple_matches"
        if len(self.matches) == 1:
            return "ok"
        return "not_found"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "command": self.command,
            "status": self.status,
            "source": {
                "input": self.source_input,
                "absolute": str(self.source_absolute).replace("\\", "/"),
            },
            "matches": [match.to_dict() for match in self.matches],
            "candidate_projects": list(self.candidate_projects),
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


def map_source_membership(
    dsw_path: Path | str,
    source: str | Path,
    project_name: str | None = None,
    configuration: str | None = None,
) -> SourceMembership:
    dsw = parse_dsw(dsw_path)
    source_absolute = _source_absolute(dsw.root_dir, source)
    result = SourceMembership(source_input=str(source), source_absolute=source_absolute)
    for project_ref in dsw.projects:
        if project_name and project_ref.name != project_name:
            continue
        result.candidate_projects.append(
            {
                "name": project_ref.name,
                "dsp_path": project_ref.dsp_path.as_posix(),
                "dsp_path_absolute": str(project_ref.dsp_path_absolute).replace("\\", "/"),
                "exists": project_ref.exists,
            }
        )
        if not project_ref.exists:
            continue
        dsp_project = parse_dsp(project_ref.dsp_path_absolute, dsw.root_dir)
        result.warnings.extend(dsp_project.warnings)
        matching_entries = [entry for entry in dsp_project.files if _same_path(entry.source_path_absolute, source_absolute)]
        if not matching_entries:
            continue
        configs = _filter_configurations(dsp_project.configurations, configuration)
        for entry in matching_entries:
            result.matches.append(
                SourceMembershipMatch(
                    dsw_path=dsw.path,
                    dsp_path=dsp_project.path,
                    project_name=dsp_project.name,
                    source_entry=entry,
                    configurations=configs,
                )
            )
    return result


def membership_to_legacy_matches(membership: SourceMembership, workspace_root: Path | str) -> list[dict[str, Any]]:
    root = Path(workspace_root).resolve()
    matches: list[dict[str, Any]] = []
    for match in membership.matches:
        for configuration in match.configurations:
            matches.append(
                {
                    "dsw": normalize_relative(match.dsw_path.resolve(), root) if match.dsw_path else None,
                    "dsp": normalize_relative(match.dsp_path.resolve(), root),
                    "project_name": match.project_name,
                    "configuration": _short_configuration(configuration),
                    "configuration_full_name": configuration.full_name,
                    "source": normalize_relative(match.source_entry.source_path_absolute.resolve(), root),
                }
            )
    return matches


def _source_absolute(root_dir: Path, source: str | Path) -> Path:
    source_path = Path(source)
    if source_path.is_absolute():
        return source_path.resolve()
    return (root_dir / str(source).replace("\\", "/")).resolve()


def _same_path(left: Path, right: Path) -> bool:
    return str(left.resolve()).lower() == str(right.resolve()).lower()


def _filter_configurations(configurations: list[DspConfiguration], configuration: str | None) -> list[DspConfiguration]:
    if configuration is None:
        return configurations
    return [
        item
        for item in configurations
        if item.full_name == configuration
        or item.name == configuration
        or _short_configuration(item) == configuration
        or (item.name and item.name.lower() == configuration.lower())
        or _short_configuration(item).lower() == configuration.lower()
    ]


def _short_configuration(configuration: DspConfiguration) -> str:
    if configuration.project_name and configuration.full_name.startswith(configuration.project_name + " - "):
        return configuration.full_name[len(configuration.project_name) + 3 :]
    return configuration.name or configuration.full_name
