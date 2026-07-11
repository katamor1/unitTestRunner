from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from unit_test_runner.c_analyzer.call_models import LinkProvider


@dataclass(frozen=True)
class LinkContextWarning:
    code: str
    message: str
    project_name: str | None = None
    configuration: str | None = None
    library_candidate: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "project_name": self.project_name,
            "configuration": self.configuration,
            "library_candidate": self.library_candidate,
        }


@dataclass
class ResolvedLinkLibrary:
    path: Path
    source: str
    link_order: int
    project_name: str | None = None
    configuration: str | None = None
    exists: bool = True
    scan_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path.as_posix(),
            "source": self.source,
            "link_order": self.link_order,
            "project_name": self.project_name,
            "configuration": self.configuration,
            "exists": self.exists,
            "scan_status": self.scan_status,
        }


@dataclass
class LinkContext:
    libraries: list[ResolvedLinkLibrary] = field(default_factory=list)
    library_dirs: list[Path] = field(default_factory=list)
    providers_by_name: dict[str, list[LinkProvider]] = field(default_factory=dict)
    warnings: list[LinkContextWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "libraries": [library.to_dict() for library in self.libraries],
            "library_dirs": [path.as_posix() for path in self.library_dirs],
            "providers_by_name": {
                name: [provider.to_dict() for provider in providers]
                for name, providers in self.providers_by_name.items()
            },
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
