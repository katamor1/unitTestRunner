from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BlockerAction:
    code: str
    label: str
    affected_count: int = 1

    def to_dict(self, *, include_affected_count: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "code": self.code,
            "label": self.label,
        }
        if include_affected_count:
            value["affected_count"] = self.affected_count
        return value


@dataclass(frozen=True)
class ExecutionBlocker:
    blocker_id: str
    code: str
    category: str
    severity: str
    summary: str
    source_artifact: str
    recommended_action: BlockerAction
    next_steps: tuple[str, ...]
    case_id: str | None = None
    item_id: str | None = None
    control_name: str | None = None
    current_value: str | None = None
    source_pointer: str | None = None
    related_file: str | None = None
    line_number: int | None = None
    log_excerpt: str | None = None
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "blocker_id": self.blocker_id,
            "code": self.code,
            "category": self.category,
            "severity": self.severity,
            "summary": self.summary,
            "source_artifact": self.source_artifact,
            "recommended_action": self.recommended_action.to_dict(),
            "next_steps": list(self.next_steps),
            "truncated": self.truncated,
        }
        for name in (
            "case_id",
            "item_id",
            "control_name",
            "current_value",
            "source_pointer",
            "related_file",
            "line_number",
            "log_excerpt",
        ):
            item = getattr(self, name)
            if item is not None:
                value[name] = item
        return value


@dataclass(frozen=True)
class TestExecutionBlockerReport:
    run_id: str
    execution_report_path: str
    execution_report_sha256: str
    primary_action: BlockerAction
    blockers: tuple[ExecutionBlocker, ...]

    @property
    def blocker_count(self) -> int:
        return len(self.blockers)

    def to_data(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "execution_status": "blocked",
            "execution_report": {
                "artifact_kind": "test_execution_report",
                "path": self.execution_report_path,
                "sha256": self.execution_report_sha256,
            },
            "blocker_count": self.blocker_count,
            "primary_action": self.primary_action.to_dict(
                include_affected_count=True
            ),
            "blockers": [item.to_dict() for item in self.blockers],
        }


@dataclass(frozen=True)
class BlockerPublicationDiagnostic:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass(frozen=True)
class BlockerPublicationResult:
    report: TestExecutionBlockerReport | None = None
    run_json: Path | None = None
    run_markdown: Path | None = None
    latest_json: Path | None = None
    latest_markdown: Path | None = None
    diagnostics: tuple[BlockerPublicationDiagnostic, ...] = ()

    @property
    def complete_history_view(self) -> bool:
        return self.run_json is not None and self.run_markdown is not None
