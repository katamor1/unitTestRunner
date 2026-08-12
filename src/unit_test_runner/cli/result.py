from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from unit_test_runner.contracts import RunOutcome, validate_cli_envelope

from .artifacts import ProducedArtifact
from .outcomes import DomainOutcome


@dataclass
class CLIResult:
    status: str
    exit_code: int
    command: str
    message: str
    warnings: list[str] = field(default_factory=list)
    errors: list[Any] = field(default_factory=list)
    human_output: str | None = None
    outcome: DomainOutcome | None = None
    artifacts: list[ProducedArtifact] = field(default_factory=list)
    diagnostics: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if self.outcome is None:
            raise ValueError("CLI results require an explicit outcome.")
        _validate_outcome_exit(self.outcome.state, self.exit_code)
        payload = {
            "command": self.command,
            "outcome": self.outcome.state.value,
            "message": self.message,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "diagnostics": _diagnostics(
                self.diagnostics,
                self.warnings,
                self.errors,
            ),
        }
        violations = validate_cli_envelope(payload)
        if violations:
            detail = "; ".join(
                f"{item.code} at {item.json_path}: {item.message}"
                for item in violations
            )
            raise ValueError(f"Invalid CLI envelope: {detail}")
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=True) + "\n"

    def render_human(self) -> str:
        if self.human_output is not None:
            return self.human_output if self.human_output.endswith("\n") else self.human_output + "\n"
        lines = [
            f"Command: {self.command}",
            f"Outcome: {self.outcome.state.value if self.outcome else 'error'}",
            self.message,
        ]
        diagnostics = _diagnostics(self.diagnostics, self.warnings, self.errors)
        if diagnostics:
            lines.append("Diagnostics:")
            lines.extend(
                f"- [{item['level']}] {item['code']}: {item['message']}"
                for item in diagnostics
            )
        return "\n".join(lines) + "\n"


def _validate_outcome_exit(outcome: RunOutcome, exit_code: int) -> None:
    success = outcome in {RunOutcome.PLANNED, RunOutcome.PASSED}
    if success != (exit_code == 0):
        raise ValueError(
            f"CLI outcome {outcome.value!r} and exit code {exit_code} disagree."
        )


def _diagnostics(
    diagnostics: list[dict[str, str]],
    warnings: list[str],
    errors: list[Any],
) -> list[dict[str, str]]:
    normalized = [
        {
            "code": str(item.get("code") or "diagnostic"),
            "level": str(item.get("level") or item.get("severity") or "info"),
            "message": str(item.get("message") or ""),
        }
        for item in diagnostics
    ]
    normalized.extend(
        {"code": "warning", "level": "warning", "message": str(warning)}
        for warning in warnings
    )
    for value in errors:
        if isinstance(value, dict):
            normalized.append(
                {
                    "code": str(value.get("code") or "error"),
                    "level": "error",
                    "message": str(value.get("message") or ""),
                }
            )
        else:
            normalized.append(
                {"code": "error", "level": "error", "message": str(value)}
            )
    return normalized
