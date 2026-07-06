from __future__ import annotations

from typing import Any


def render_dsw_discovery_markdown(payload: dict[str, Any]) -> str:
    lines = ["# DSWプロジェクト検出レポート", ""]
    workspaces = payload.get("workspaces", [])
    for workspace in workspaces:
        lines.extend(
            [
                "## workspace",
                "",
                f"- パス: {workspace.get('dsw_path', '')}",
                f"- フォーマットバージョン: {workspace.get('format_version') or ''}",
                "",
                "## プロジェクト",
                "",
                "| プロジェクト | DSPパス | 存在 |",
                "|---|---|---|",
            ]
        )
        for project in workspace.get("projects", []):
            exists = "はい" if project.get("exists") else "いいえ"
            lines.append(f"| {project.get('name', '')} | {project.get('dsp_path', '')} | {exists} |")
        lines.extend(
            [
                "",
                "## 依存関係",
                "",
                "| 参照元 | 参照先 |",
                "|---|---|",
            ]
        )
        dependencies = workspace.get("dependencies", [])
        if dependencies:
            for dependency in dependencies:
                lines.append(f"| {dependency.get('from_project', '')} | {dependency.get('to_project', '')} |")
        else:
            lines.append("| なし | なし |")
        lines.extend(["", "## 警告", ""])
        warnings = workspace.get("warnings", [])
        if warnings:
            for warning in warnings:
                location = f" {warning['line_number']}行" if "line_number" in warning else ""
                lines.append(f"- `{warning.get('code', '')}`{location}: {warning.get('message', '')}")
        else:
            lines.append("なし")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
