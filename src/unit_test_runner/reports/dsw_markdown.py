from __future__ import annotations

from typing import Any


def render_dsw_discovery_markdown(payload: dict[str, Any]) -> str:
    lines = ["# DSW Project Discovery Report", ""]
    workspaces = payload.get("workspaces", [])
    for workspace in workspaces:
        lines.extend(
            [
                "## Workspace",
                "",
                f"- Path: {workspace.get('dsw_path', '')}",
                f"- Format Version: {workspace.get('format_version') or ''}",
                "",
                "## Projects",
                "",
                "| Project | DSP Path | Exists |",
                "|---|---|---|",
            ]
        )
        for project in workspace.get("projects", []):
            exists = "yes" if project.get("exists") else "no"
            lines.append(f"| {project.get('name', '')} | {project.get('dsp_path', '')} | {exists} |")
        lines.extend(
            [
                "",
                "## Dependencies",
                "",
                "| From | To |",
                "|---|---|",
            ]
        )
        dependencies = workspace.get("dependencies", [])
        if dependencies:
            for dependency in dependencies:
                lines.append(f"| {dependency.get('from_project', '')} | {dependency.get('to_project', '')} |")
        else:
            lines.append("| (none) | (none) |")
        lines.extend(["", "## Warnings", ""])
        warnings = workspace.get("warnings", [])
        if warnings:
            for warning in warnings:
                location = f" line {warning['line_number']}" if "line_number" in warning else ""
                lines.append(f"- `{warning.get('code', '')}`{location}: {warning.get('message', '')}")
        else:
            lines.append("(none)")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
