from __future__ import annotations

from typing import Any


def render_source_membership_markdown(payload: dict[str, Any]) -> str:
    source = payload.get("source", {})
    lines = [
        "# ソース所属レポート",
        "",
        "## ソース",
        "",
        f"- 入力: {source.get('input', '')}",
        f"- 絶対パス: {source.get('absolute', '')}",
        "",
        "## 一致プロジェクト",
        "",
        "| プロジェクト | DSP | 構成数 |",
        "|---|---|---:|",
    ]
    matches = payload.get("matches", [])
    if matches:
        for match in matches:
            lines.append(f"| {match.get('project_name', '')} | {match.get('dsp_path', '')} | {len(match.get('configurations', []))} |")
    else:
        lines.append("| なし | なし | 0 |")
    lines.extend(["", "## 警告", ""])
    warnings = payload.get("warnings", [])
    if warnings:
        for warning in warnings:
            lines.append(f"- `{warning.get('code', '')}`: {warning.get('message', '')}")
    else:
        lines.append("なし")
    return "\n".join(lines) + "\n"
