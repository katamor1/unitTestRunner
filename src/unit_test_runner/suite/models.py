from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


SUBJECT_FIELDS = (
    "source_path",
    "source_sha256",
    "function",
    "project",
    "configuration",
)


def normalize_subject(value: Mapping[str, Any]) -> dict[str, str]:
    if set(value) != set(SUBJECT_FIELDS):
        raise ValueError("Suite function subject must contain exactly five identity fields.")
    subject = {field: str(value[field]) for field in SUBJECT_FIELDS}
    if any(not item for item in subject.values()):
        raise ValueError("Suite function subject fields must be non-empty.")
    return subject


def resolve_manifest_workspace(suite_root: Path, value: str) -> Path:
    if not value or "\\" in value:
        raise ValueError("Suite workspace must be a manifest-relative POSIX path.")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("Suite workspace must not be absolute or contain dot traversal.")
    if relative.parts and ":" in relative.parts[0]:
        raise ValueError("Suite workspace must not contain a drive-qualified path.")
    resolved = (suite_root / Path(*relative.parts)).resolve()
    try:
        resolved.relative_to(suite_root.resolve())
    except ValueError as error:
        raise ValueError("Suite workspace escapes the suite output root.") from error
    return resolved


@dataclass
class SuiteEntry:
    entry_id: str
    enabled: bool
    tags: list[str]
    subject: dict[str, str]
    workspace: Path
    workspace_path: str
    test_spec_sha256: str
    harness_sha256: str

    @property
    def function(self) -> dict[str, str]:
        return {
            "name": self.subject["function"],
            "source": self.subject["source_path"],
            "project": self.subject["project"],
            "configuration": self.subject["configuration"],
        }

    @property
    def dossier(self) -> Path:
        return self.workspace / "reports" / "function_dossier.json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "enabled": self.enabled,
            "tags": list(self.tags),
            "subject": dict(self.subject),
            "workspace": self.workspace_path,
            "test_spec_sha256": self.test_spec_sha256,
            "harness_sha256": self.harness_sha256,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], suite_root: Path) -> "SuiteEntry":
        workspace_path = str(payload.get("workspace") or "")
        return cls(
            entry_id=str(payload.get("entry_id") or ""),
            enabled=bool(payload.get("enabled")),
            tags=[str(tag) for tag in payload.get("tags", [])],
            subject=normalize_subject(payload.get("subject", {})),
            workspace=resolve_manifest_workspace(suite_root, workspace_path),
            workspace_path=workspace_path,
            test_spec_sha256=str(payload.get("test_spec_sha256") or ""),
            harness_sha256=str(payload.get("harness_sha256") or ""),
        )


@dataclass
class SuiteManifest:
    suite_id: str
    entries: list[SuiteEntry] = field(default_factory=list)
    schema_version: str = "1.0.0"
    subject: dict[str, str] | None = None
    revision: int = 0

    def to_data(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "revision": self.revision,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def to_dict(self) -> dict[str, Any]:
        if self.subject is None:
            raise ValueError("An empty unregistered suite has no public manifest subject.")
        return {
            "schema_version": "1.0.0",
            "artifact_kind": "suite_manifest",
            "subject": dict(self.subject),
            "data": self.to_data(),
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        suite_root: Path,
        suite_id: str = "default",
    ) -> "SuiteManifest":
        if payload.get("schema_version") != "1.0.0" or payload.get("artifact_kind") != "suite_manifest":
            raise ValueError("Suite manifest must use the public 1.0.0 envelope; regenerate it.")
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ValueError("Suite manifest data must be an object.")
        entries = [
            SuiteEntry.from_dict(item, suite_root)
            for item in data.get("entries", [])
            if isinstance(item, Mapping)
        ]
        entry_ids = [entry.entry_id for entry in entries]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("Suite manifest contains duplicate entry_id values.")
        return cls(
            suite_id=str(data.get("suite_id") or suite_id),
            entries=entries,
            subject=normalize_subject(payload.get("subject", {})),
            revision=int(data.get("revision", 0)),
        )


@dataclass
class SuiteRunPolicy:
    run_tests: bool = False
    dry_run: bool = True
    timeout_seconds: int = 60

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_tests": self.run_tests,
            "dry_run": self.dry_run,
            "timeout_seconds": self.timeout_seconds,
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
    report_path: Path | None
    error: str | None = None
    subject: dict[str, str] | None = None
    workspace_path: str | None = None
    changed_fields: list[str] = field(default_factory=list)
    fingerprints: dict[str, dict[str, str | None]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "entry_id": self.entry_id,
            "function": self.function_name,
            "workspace": self.workspace_path or self.workspace.as_posix(),
            "outcome": self.execution_status,
            "green_status": self.green_status,
            "executed": self.executed,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "inconclusive_tests": self.inconclusive_tests,
            "unresolved_review_count": self.unresolved_review_count,
            "changed_fields": list(self.changed_fields),
            "fingerprints": {
                key: dict(value) for key, value in self.fingerprints.items()
            },
        }
        if self.subject is not None:
            payload["subject"] = dict(self.subject)
        if self.report_path is not None:
            payload["report_path"] = self.report_path.as_posix()
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
    schema_version: str = "1.0.0"
    subject: dict[str, str] | None = None
    manifest_revision: int = 0

    def to_data(self) -> dict[str, Any]:
        return {
            "outcome": self.status,
            "suite_id": self.suite_id,
            "manifest_revision": self.manifest_revision,
            "selector": dict(self.selector),
            "policy": self.policy.to_dict(),
            "summary": dict(self.summary),
            "results": [result.to_dict() for result in self.results],
        }

    def to_dict(self) -> dict[str, Any]:
        """Retain the in-process report projection used by CLI result assembly."""
        return self.to_data()

    def to_envelope(self) -> dict[str, Any]:
        if self.subject is None:
            raise ValueError("suite_run_report requires the manifest anchor subject.")
        return {
            "schema_version": "1.0.0",
            "artifact_kind": "suite_run_report",
            "subject": dict(self.subject),
            "data": self.to_data(),
        }
