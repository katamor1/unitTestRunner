from __future__ import annotations

from typing import Any


def render_function_location_markdown(payload: dict[str, Any]) -> str:
    source = payload.get("source", {})
    function = payload.get("function", {})
    selected = function.get("selected_candidate")
    lines = [
        "# 関数位置レポート",
        "",
        "## 対象",
        "",
        f"- ソース: {source.get('path', '')}",
        f"- 関数: {function.get('name', '')}",
        f"- 状態: {function.get('status', '')}",
        "",
    ]
    if selected:
        context = selected.get("conditional_context") or {}
        lines.extend(
            [
                "## 選択候補",
                "",
                "| 項目 | 値 |",
                "|---|---|",
                f"| 種別 | {selected.get('kind', '')} |",
                f"| 信頼度 | {selected.get('confidence', '')} |",
                f"| storage | {selected.get('storage_class_hint') or ''} |",
                f"| ヘッダ開始 | {selected['header_range']['start']['line']}行 {selected['header_range']['start']['column']}列 |",
                f"| 本体終了 | {selected['body_range']['end']['line']}行 {selected['body_range']['end']['column']}列 |",
                f"| 有効状態 | {context.get('active_state', '')} |",
                "",
                "## シグネチャプレビュー",
                "",
                "```c",
                selected.get("signature_preview", ""),
                "```",
                "",
            ]
        )
    lines.extend(["## 警告", ""])
    warnings = payload.get("warnings", [])
    if warnings:
        for warning in warnings:
            lines.append(f"- `{warning.get('code', '')}`: {warning.get('message', '')}")
    else:
        lines.append("なし")
    return "\n".join(lines) + "\n"
