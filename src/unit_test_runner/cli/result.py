from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .exit_codes import EXIT_NOT_IMPLEMENTED


@dataclass
class CLIResult:
    status: str
    exit_code: int
    command: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    legacy_payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "command": self.command,
            "message": self.message,
            "data": self.data,
            "warnings": self.warnings,
            "errors": self.errors,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    def render_human(self) -> str:
        if self.legacy_payload is not None:
            return json.dumps(self.legacy_payload, indent=2, ensure_ascii=False) + "\n"
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
            lines.extend(f"- {error}" for error in self.errors)
        return "\n".join(lines) + "\n"


def not_implemented(command: str, planned_step: str) -> CLIResult:
    return CLIResult(
        status="not_implemented",
        exit_code=EXIT_NOT_IMPLEMENTED,
        command=command,
        message="This command is defined but not implemented yet.",
        data={"planned_step": planned_step},
    )
