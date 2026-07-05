from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _path_text(path: Path) -> str:
    return str(path).replace("\\", "/")


@dataclass
class DswParseWarning:
    code: str
    message: str
    line_number: int | None = None
    line_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.line_number is not None:
            value["line_number"] = self.line_number
        if self.line_text is not None:
            value["line_text"] = self.line_text
        return value


@dataclass
class DswDependency:
    from_project: str
    to_project: str
    line_number: int
    kind: str = "project_dependency"

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_project": self.from_project,
            "to_project": self.to_project,
            "kind": self.kind,
            "line_number": self.line_number,
        }


@dataclass
class DswProject:
    name: str
    dsp_path_raw: str
    dsp_path: Path
    dsp_path_absolute: Path
    package_owner: str | None
    exists: bool
    line_number: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dsp_path_raw": self.dsp_path_raw,
            "dsp_path": _path_text(self.dsp_path),
            "dsp_path_normalized": _path_text(self.dsp_path),
            "dsp_path_absolute": _path_text(self.dsp_path_absolute),
            "package_owner": self.package_owner,
            "exists": self.exists,
            "line_number": self.line_number,
        }


@dataclass
class DswWorkspace:
    path: Path
    root_dir: Path
    format_version: str | None
    projects: list[DswProject] = field(default_factory=list)
    dependencies: list[DswDependency] = field(default_factory=list)
    warnings: list[DswParseWarning] = field(default_factory=list)
    encoding: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dsw_path": _path_text(self.path),
            "root_dir": _path_text(self.root_dir),
            "format_version": self.format_version,
            "encoding": self.encoding,
            "projects": [project.to_dict() for project in self.projects],
            "dependencies": [dependency.to_dict() for dependency in self.dependencies],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass
class DswParseResult:
    workspaces: list[DswWorkspace]
    status: str = "ok"
    command: str = "discover-projects"
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        warnings = []
        for workspace in self.workspaces:
            for warning in workspace.warnings:
                item = warning.to_dict()
                item["dsw_path"] = _path_text(workspace.path)
                warnings.append(item)
        return {
            "schema_version": self.schema_version,
            "command": self.command,
            "status": self.status,
            "workspaces": [workspace.to_dict() for workspace in self.workspaces],
            "warnings": warnings,
        }
