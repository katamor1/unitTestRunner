from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from unit_test_runner import __version__
from unit_test_runner.contracts import ArtifactKind, RunOutcome, validate_payload
from unit_test_runner.execution.test_result_writer import current_producer_commit

from .artifacts import ExpectedArtifact, ProducedArtifact
from .exit_codes import EXIT_NOT_IMPLEMENTED
from .outcomes import DomainOutcome


@dataclass
class CLIResult:
    status: str
    exit_code: int
    command: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[Any] = field(default_factory=list)
    legacy_payload: dict[str, Any] | None = None
    human_output: str | None = None
    outcome: DomainOutcome | None = None
    artifacts: list[ProducedArtifact] = field(default_factory=list)
    expected_artifacts: list[ExpectedArtifact] = field(default_factory=list)
    diagnostics: list[dict[str, str]] = field(default_factory=list)
    lifecycle: str = "finished"
    invocation_id: str = field(default_factory=lambda: f"inv-{uuid4().hex}")
    producer_commit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.outcome is None:
            raise ValueError("CLI v1 results require an explicit DomainOutcome.")
        outcome = self.outcome
        payload = {
            "artifact_kind": ArtifactKind.CLI_RESULT.value,
            "schema_version": "1.0.0",
            "producer": {
                "name": "unit-test-runner",
                "version": __version__,
                "commit": self.producer_commit or current_producer_commit(),
            },
            "subject": {"invocation_id": self.invocation_id},
            "data": {
                "invocation_id": self.invocation_id,
                "command": self.command,
                "lifecycle": self.lifecycle,
                "outcome_kind": outcome.kind,
                "outcome": outcome.state.value,
                "green": outcome.green,
                "exit_code": self.exit_code,
                "message": self.message,
                "diagnostics": _diagnostics(self.diagnostics, self.warnings),
                "artifacts": [artifact.to_dict() for artifact in self.artifacts],
                "expected_artifacts": [artifact.to_dict() for artifact in self.expected_artifacts],
                "errors": [_error(item) for item in self.errors],
                "details": dict(self.data),
            },
            "extensions": {},
        }
        violations = validate_payload(ArtifactKind.CLI_RESULT, payload)
        if violations:
            detail = "; ".join(
                f"{item.code} at {item.json_path}: {item.message}"
                for item in violations
            )
            raise ValueError(f"Invalid cli_result: {detail}")
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=True) + "\n"

    def render_human(self) -> str:
        if self.human_output is not None:
            return self.human_output if self.human_output.endswith("\n") else self.human_output + "\n"
        if self.legacy_payload is not None:
            return json.dumps(self.legacy_payload, indent=2, ensure_ascii=True) + "\n"
        lines = [
            f"Command: {self.command}",
            f"Status: {self.status}",
            self.message,
        ]
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in self.warnings)
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"- {_error(item)['message']}" for item in self.errors)
        return "\n".join(lines) + "\n"


def not_implemented(command: str, planned_item: str) -> CLIResult:
    return CLIResult(
        status="not_implemented",
        exit_code=EXIT_NOT_IMPLEMENTED,
        command=command,
        message="This command is defined but not implemented yet.",
        data={"planned_item": planned_item},
        outcome=DomainOutcome("command", RunOutcome.ERROR, None),
    )


def _diagnostics(
    diagnostics: list[dict[str, str]],
    warnings: list[str],
) -> list[dict[str, str]]:
    normalized = [
        {
            "code": str(item.get("code") or "diagnostic"),
            "severity": str(item.get("severity") or "info"),
            "message": str(item.get("message") or ""),
        }
        for item in diagnostics
    ]
    normalized.extend(
        {"code": "warning", "severity": "warning", "message": warning}
        for warning in warnings
    )
    return normalized


def _error(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            "code": str(value.get("code") or "error"),
            "message": str(value.get("message") or ""),
        }
    return {"code": "error", "message": str(value)}
