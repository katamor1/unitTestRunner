from __future__ import annotations

from collections import Counter
from typing import Any


def render_source_digest_markdown(payload: dict[str, Any]) -> str:
    source = payload.get("source", {})
    range_counts = Counter(item.get("kind", "unknown") for item in payload.get("masking", {}).get("masked_ranges", []))
    lines = [
        "# ソースダイジェストレポート",
        "",
        "## ソース",
        "",
        f"- パス: {source.get('path', '')}",
        f"- エンコーディング: {source.get('encoding', '')}",
        f"- 行数: {source.get('line_count', '')}",
        f"- SHA-256: {source.get('sha256', '')}",
        "",
        "## マスク概要",
        "",
        "| 種別 | 件数 |",
        "|---|---:|",
    ]
    if range_counts:
        for kind, count in sorted(range_counts.items()):
            lines.append(f"| {kind} | {count} |")
    else:
        lines.append("| なし | 0 |")
    lines.extend(["", "## include", "", "| 行 | 対象 | 形式 | 存在 | 有効状態 |", "|---:|---|---|---|---|"])
    for include in payload.get("preprocessor", {}).get("includes", []):
        exists = "はい" if include.get("exists") else "いいえ" if include.get("exists") is False else "不明"
        lines.append(f"| {include.get('line_number', '')} | {include.get('target', '')} | {include.get('style', '')} | {exists} | {include.get('active_state', '')} |")
    lines.extend(["", "## マクロ", "", "| 行 | 名前 | 種別 | 有効状態 |", "|---:|---|---|---|"])
    for macro in payload.get("preprocessor", {}).get("macros", []):
        kind = "function-like" if macro.get("is_function_like") else "object-like"
        lines.append(f"| {macro.get('line_number', '')} | {macro.get('name', '')} | {kind} | {macro.get('active_state', '')} |")
    lines.extend(["", "## 警告", ""])
    warnings = payload.get("warnings", [])
    if warnings:
        for warning in warnings:
            lines.append(f"- `{warning.get('code', '')}`: {warning.get('message', '')}")
    else:
        lines.append("なし")
    return "\n".join(lines) + "\n"
