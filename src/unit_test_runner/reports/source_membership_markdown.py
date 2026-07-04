from __future__ import annotations

from typing import Any


def render_source_membership_markdown(payload: dict[str, Any]) -> str:
    source = payload.get("source", {})
    lines = [
        "# Source Membership Report",
        "",
        "## Source",
        "",
        f"- Input: {source.get('input', '')}",
        f"- Absolute: {source.get('absolute', '')}",
        "",
        "## Matches",
        "",
        "| Project | DSP | Configuration Count |",
        "|---|---|---:|",
    ]
    matches = payload.get("matches", [])
    if matches:
        for match in matches:
            lines.append(f"| {match.get('project_name', '')} | {match.get('dsp_path', '')} | {len(match.get('configurations', []))} |")
    else:
        lines.append("| (none) | (none) | 0 |")
    lines.extend(["", "## Warnings", ""])
    warnings = payload.get("warnings", [])
    if warnings:
        for warning in warnings:
            lines.append(f"- `{warning.get('code', '')}`: {warning.get('message', '')}")
    else:
        lines.append("(none)")
    return "\n".join(lines) + "\n"
