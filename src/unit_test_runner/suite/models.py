from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _path_text(path: Path | None) -> str:
    return "" if path is None else path.as_posix()


@dataclass
class SuiteEntry:
    entry_id: str
    enabled: bool
    tags: list[str]
    function: dict[str, str]
    workspace: Path
    dossier: Path
    test_execution_report: Path
    registered_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "enabled": self.enabled,
            "tags": list(self.tags),
            "function": dict(self.function),
            "workspace": _path_text(self.workspace),
            "dossier": _path_text(self.dossier),
            "test_execution_report": _path_text(self.test_execution_report),
            "registered_at": self.registered_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SuiteEntry":
        return cls(
            entry_id=str(payload.get("entry_id", "")),
            enabled=bool(payload.get("enabled", True)),
            tags=[str(tag) for tag in payload.get("tags", []) if str(tag)],
            function={str(key): str(value) for key, value in dict(payload.get("function", {})).items()},
            workspace=Path(str(payload.get("workspace", ""))).resolve(),
            dossier=Path(str(payload.get("dossier", ""))).resolve(),
            test_execution_report=Path(str(payload.get("test_execution_report", ""))).resolve(),
            registered_at=str(payload.get("registered_at", "")),
        )


@dataclass
class SuiteManifest:
    suite_id: str
    source_root: Path | None
    dsw_path: Path | None
    entries: list[SuiteEntry] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "suite_id": self.suite_id,
            "source_root": _path_text(self.source_root),
            "dsw_path": _path_text(self.dsw_path),
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any], suite_id: str = "default") -> "SuiteManifest":
        source_root = str(payload.get("source_root") or "")
        dsw_path = str(payload.get("dsw_path") or "")
        return cls(
            suite_id=str(payload.get("suite_id") or suite_id),
            source_root=Path(source_root).resolve() if source_root else None,
            dsw_path=Path(dsw_path).resolve() if dsw_path else None,
            entries=[SuiteEntry.from_dict(item) for item in payload.get("entries", []) if isinstance(item, dict)],
            schema_version=str(payload.get("schema_version") or "0.1"),
        )


@dataclass
class SuiteRunPolicy:
    run_tests: bool = False
    dry_run: bool = True
    timeout_seconds: int = 60
    fail_fast: bool = False
    require_green: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_tests": self.run_tests,
            "dry_run": self.dry_run,
            "timeout_seconds": self.timeout_seconds,
            "fail_fast": self.fail_fast,
            "require_green": self.require_green,
        }


@dataclass
class SuiteRunEntryResult:
    entry_id: str
    function_name: str
    workspace: Path
    execution_status: str
    green_status: str
    executed: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    inconclusive_tests: int
    unresolved_review_count: int
    report_path: Path
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "entry_id": self.entry_id,
            "function": self.function_name,
            "workspace": _path_text(self.workspace),
            "outcome": self.execution_status,
            "green_status": self.green_status,
            "executed": self.executed,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "inconclusive_tests": self.inconclusive_tests,
            "unresolved_review_count": self.unresolved_review_count,
            "report_path": _path_text(self.report_path),
        }
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass
class SuiteRunReport:
    suite_id: str
    status: str
    selector: dict[str, Any]
    policy: SuiteRunPolicy
    results: list[SuiteRunEntryResult]
    summary: dict[str, int]
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcome": self.status,
            "suite_id": self.suite_id,
            "selector": self.selector,
            "policy": self.policy.to_dict(),
            "summary": dict(self.summary),
            "results": [result.to_dict() for result in self.results],
        }
