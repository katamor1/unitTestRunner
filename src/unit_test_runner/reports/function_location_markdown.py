from __future__ import annotations

from typing import Any


def render_function_location_markdown(payload: dict[str, Any]) -> str:
    source = payload.get("source", {})
    function = payload.get("function", {})
    selected = function.get("selected_candidate")
    lines = [
        "# Function Location Report",
        "",
        "## Target",
        "",
        f"- Source: {source.get('path', '')}",
        f"- Function: {function.get('name', '')}",
        f"- Status: {function.get('status', '')}",
        "",
    ]
    if selected:
        context = selected.get("conditional_context") or {}
        lines.extend(
            [
                "## Selected Candidate",
                "",
                "| Item | Value |",
                "|---|---|",
                f"| Kind | {selected.get('kind', '')} |",
                f"| Confidence | {selected.get('confidence', '')} |",
                f"| Storage | {selected.get('storage_class_hint') or ''} |",
                f"| Header Start | line {selected['header_range']['start']['line']}, column {selected['header_range']['start']['column']} |",
                f"| Body End | line {selected['body_range']['end']['line']}, column {selected['body_range']['end']['column']} |",
                f"| Active State | {context.get('active_state', '')} |",
                "",
                "## Signature Preview",
                "",
                "```c",
                selected.get("signature_preview", ""),
                "```",
                "",
            ]
        )
    lines.extend(["## Warnings", ""])
    warnings = payload.get("warnings", [])
    if warnings:
        for warning in warnings:
            lines.append(f"- `{warning.get('code', '')}`: {warning.get('message', '')}")
    else:
        lines.append("(none)")
    return "\n".join(lines) + "\n"
