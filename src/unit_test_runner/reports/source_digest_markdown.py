from __future__ import annotations

from collections import Counter
from typing import Any


def render_source_digest_markdown(payload: dict[str, Any]) -> str:
    source = payload.get("source", {})
    range_counts = Counter(item.get("kind", "unknown") for item in payload.get("masking", {}).get("masked_ranges", []))
    lines = [
        "# Source Digest Report",
        "",
        "## Source",
        "",
        f"- Path: {source.get('path', '')}",
        f"- Encoding: {source.get('encoding', '')}",
        f"- Line Count: {source.get('line_count', '')}",
        f"- SHA-256: {source.get('sha256', '')}",
        "",
        "## Masking Summary",
        "",
        "| Kind | Count |",
        "|---|---:|",
    ]
    if range_counts:
        for kind, count in sorted(range_counts.items()):
            lines.append(f"| {kind} | {count} |")
    else:
        lines.append("| (none) | 0 |")
    lines.extend(["", "## Includes", "", "| Line | Target | Style | Exists | Active |", "|---:|---|---|---|---|"])
    for include in payload.get("preprocessor", {}).get("includes", []):
        exists = "yes" if include.get("exists") else "no" if include.get("exists") is False else "unknown"
        lines.append(f"| {include.get('line_number', '')} | {include.get('target', '')} | {include.get('style', '')} | {exists} | {include.get('active_state', '')} |")
    lines.extend(["", "## Macros", "", "| Line | Name | Kind | Active |", "|---:|---|---|---|"])
    for macro in payload.get("preprocessor", {}).get("macros", []):
        kind = "function-like" if macro.get("is_function_like") else "object-like"
        lines.append(f"| {macro.get('line_number', '')} | {macro.get('name', '')} | {kind} | {macro.get('active_state', '')} |")
    lines.extend(["", "## Warnings", ""])
    warnings = payload.get("warnings", [])
    if warnings:
        for warning in warnings:
            lines.append(f"- `{warning.get('code', '')}`: {warning.get('message', '')}")
    else:
        lines.append("(none)")
    return "\n".join(lines) + "\n"
