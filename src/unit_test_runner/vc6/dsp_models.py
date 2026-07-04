from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _path_text(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


@dataclass
class PathLikeValue:
    raw: str
    normalized: str
    absolute: Path | None
    exists: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "normalized": self.normalized,
            "absolute": _path_text(self.absolute),
            "exists": self.exists,
        }


@dataclass
class DspParseWarning:
    code: str
    message: str
    line_number: int | None = None
    line_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.line_number is not None:
            value["line_number"] = self.line_number
        if self.line_text is not None:
            value["line_text"] = self.line_text
        return value


@dataclass
class DspBuildSettings:
    defines: list[str] = field(default_factory=list)
    include_dirs: list[PathLikeValue] = field(default_factory=list)
    forced_includes: list[str] = field(default_factory=list)
    pch_mode: str | None = None
    pch_header: str | None = None
    runtime_library: str | None = None
    warning_level: str | None = None
    optimization: str | None = None
    debug_info: str | None = None
    raw_options: list[str] = field(default_factory=list)
    unresolved_macros: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "defines": list(self.defines),
            "include_dirs": [item.to_dict() for item in self.include_dirs],
            "forced_includes": list(self.forced_includes),
            "precompiled_header": {
                "mode": self.pch_mode,
                "header": self.pch_header,
                "enabled": self.pch_mode is not None,
            },
            "pch_mode": self.pch_mode,
            "pch_header": self.pch_header,
            "runtime_library": self.runtime_library,
            "warning_level": self.warning_level,
            "optimization": self.optimization,
            "debug_info": self.debug_info,
            "raw_options": list(self.raw_options),
            "unresolved_macros": list(self.unresolved_macros),
        }


@dataclass
class DspConfiguration:
    full_name: str
    project_name: str | None
    platform: str | None
    name: str | None
    compiler_base_options: list[str] = field(default_factory=list)
    compiler_options: list[str] = field(default_factory=list)
    build_settings: DspBuildSettings = field(default_factory=DspBuildSettings)
    line_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "project_name": self.project_name,
            "platform": self.platform,
            "name": self.name,
            "compiler_base_options": list(self.compiler_base_options),
            "compiler_options": list(self.compiler_options),
            "build_settings": self.build_settings.to_dict(),
            "line_number": self.line_number,
        }


@dataclass
class DspFileEntry:
    source_raw: str
    source_path: Path
    source_path_absolute: Path
    file_kind: str
    group: str | None
    exists: bool
    line_number: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_raw": self.source_raw,
            "source_path": self.source_path.as_posix(),
            "source_path_absolute": _path_text(self.source_path_absolute),
            "file_kind": self.file_kind,
            "group": self.group,
            "exists": self.exists,
            "line_number": self.line_number,
        }


@dataclass
class DspProject:
    name: str
    path: Path
    root_dir: Path
    format_version: str | None
    target_type: str | None
    configurations: list[DspConfiguration] = field(default_factory=list)
    files: list[DspFileEntry] = field(default_factory=list)
    warnings: list[DspParseWarning] = field(default_factory=list)
    encoding: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": _path_text(self.path),
            "root_dir": _path_text(self.root_dir),
            "format_version": self.format_version,
            "target_type": self.target_type,
            "encoding": self.encoding,
            "configurations": [configuration.to_dict() for configuration in self.configurations],
            "files": [file_entry.to_dict() for file_entry in self.files],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
