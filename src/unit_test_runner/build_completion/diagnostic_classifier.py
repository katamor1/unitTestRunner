from __future__ import annotations

from typing import Any

from .completion_models import DiagnosticsSummary


def summarize_diagnostics(build_probe_report: dict[str, Any]) -> DiagnosticsSummary:
    diagnostics = build_probe_report.get("diagnostics", [])
    return DiagnosticsSummary(
        missing_include_count=len(build_probe_report.get("missing_includes", [])),
        unresolved_symbol_count=len(build_probe_report.get("unresolved_symbols", [])),
        pch_issue_count=len(build_probe_report.get("pch_issues", [])),
        vc6_compatibility_issue_count=len(build_probe_report.get("vc6_compatibility_issues", [])),
        compiler_error_count=len([item for item in diagnostics if item.get("severity") == "error"]),
        compiler_warning_count=len([item for item in diagnostics if item.get("severity") == "warning"]),
    )
