from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
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
    human_output: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "exit_code": self.exit_code,
            "command": self.command,
            "message": self.message,
            "data": self.data,
            "warnings": self.warnings,
            "errors": self.errors,
        }
        reports = _reports_from_data(self.data)
        if reports is not None:
            payload["reports"] = reports
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
            lines.extend(f"- {error}" for error in self.errors)
        return "\n".join(lines) + "\n"


def not_implemented(command: str, planned_item: str) -> CLIResult:
    return CLIResult(
        status="not_implemented",
        exit_code=EXIT_NOT_IMPLEMENTED,
        command=command,
        message="This command is defined but not implemented yet.",
        data={"planned_item": planned_item},
    )


def _reports_from_data(data: dict[str, Any]) -> dict[str, Any] | None:
    direct = data.get("reports")
    if isinstance(direct, dict):
        return direct
    review = data.get("review")
    if isinstance(review, dict):
        nested = review.get("reports")
        if isinstance(nested, dict):
            return nested
    dossier_reports = _reports_from_dossier_path(data.get("dossier"))
    if dossier_reports is not None:
        return dossier_reports
    return None


def _reports_from_dossier_path(value: Any) -> dict[str, str] | None:
    if not isinstance(value, str) or not value:
        return None
    reports = Path(value).parent
    return {
        "function_dossier_json": str(reports / "function_dossier.json"),
        "function_dossier_md": str(reports / "function_dossier.md"),
        "quick_summary_json": str(reports / "quick_summary.json"),
        "quick_summary_md": str(reports / "quick_summary.md"),
        "test_case_design_json": str(reports / "test_case_design.json"),
        "test_case_design_md": str(reports / "test_case_design.md"),
        "test_case_design_csv": str(reports / "test_case_design.csv"),
        "function_signature_json": str(reports / "function_signature.json"),
        "global_access_json": str(reports / "global_access.json"),
        "call_report_json": str(reports / "call_report.json"),
        "harness_skeleton_report_json": str(reports / "harness_skeleton_report.json"),
        "harness_skeleton_report_md": str(reports / "harness_skeleton_report.md"),
        "build_probe_report_md": str(reports / "build_probe_report.md"),
        "test_execution_report_md": str(reports / "test_execution_report.md"),
        "evidence_package_md": str(reports / "evidence_package.md"),
    }
