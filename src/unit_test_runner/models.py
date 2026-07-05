from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BuildConfiguration:
    full_name: str
    defines: list[str] = field(default_factory=list)
    include_dirs: list[str] = field(default_factory=list)
    forced_includes: list[str] = field(default_factory=list)
    precompiled_header: dict[str, Any] = field(default_factory=dict)
    compiler_options: list[str] = field(default_factory=list)
    unresolved_macros: list[str] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "defines": list(self.defines),
            "include_dirs": list(self.include_dirs),
            "forced_includes": list(self.forced_includes),
            "precompiled_header": dict(self.precompiled_header),
            "compiler_options": list(self.compiler_options),
            "unresolved_macros": list(self.unresolved_macros),
            "diagnostics": list(self.diagnostics),
        }


@dataclass
class Project:
    project_name: str
    dsp: str
    sources: list[str] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    configurations: dict[str, BuildConfiguration] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "dsp": self.dsp,
            "sources": list(self.sources),
            "headers": list(self.headers),
            "configurations": {
                name: configuration.to_dict()
                for name, configuration in self.configurations.items()
            },
            "dependencies": list(self.dependencies),
        }


@dataclass
class DswProjectReference:
    project_name: str
    dsp_path: Path
    dsp: str
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "dsp_path": self.dsp_path,
            "dsp": self.dsp,
            "dependencies": list(self.dependencies),
        }
