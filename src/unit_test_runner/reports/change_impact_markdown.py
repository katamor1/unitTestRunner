from __future__ import annotations


def render_change_impact_markdown(payload: dict) -> str:
    function = payload["function"]
    lines = [
        "# 変更影響レポート",
        "",
        "## サマリ",
        "",
        f"- 関数: {function['name']}",
        f"- 状態: {function['status']}",
        f"- インターフェース変更: {len(payload['interface_changes'])}",
        f"- 依存関係変更: {len(payload['dependency_changes'])}",
        f"- カバレッジ変更: {len(payload['coverage_changes'])}",
        "",
        "## インターフェース変更",
        "",
        "| 種別 | 対象 | 影響 | 推奨アクション |",
        "|---|---|---|---|",
    ]
    if payload["interface_changes"]:
        for item in payload["interface_changes"]:
            lines.append(f"| {item['change_kind']} | {item['target_name']} | {item['impact_level']} | {item['suggested_action']} |")
    else:
        lines.append("| なし | | | |")
    lines.extend(["", "## 依存関係変更", "", "| 種別 | 名前 | 影響 | 推奨アクション |", "|---|---|---|---|"])
    if payload["dependency_changes"]:
        for item in payload["dependency_changes"]:
            lines.append(f"| {item['change_kind']} | {item['name']} | {item['impact_level']} | {item['suggested_action']} |")
    else:
        lines.append("| なし | | | |")
    lines.extend(["", "## カバレッジ変更", "", "| 種別 | 変更前 | 変更後 | 類似度 | 推奨アクション |", "|---|---|---|---:|---|"])
    if payload["coverage_changes"]:
        for item in payload["coverage_changes"]:
            similarity = "" if item["similarity"] is None else f"{item['similarity']:.2f}"
            lines.append(f"| {item['change_kind']} | {item['old_coverage_id'] or ''} | {item['new_coverage_id'] or ''} | {similarity} | {item['suggested_action']} |")
    else:
        lines.append("| なし | | | | |")
    return "\n".join(lines) + "\n"
