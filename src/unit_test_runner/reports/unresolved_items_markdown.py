from __future__ import annotations

from unit_test_runner.dossier.dossier_models import DossierUnresolvedItem

from .japanese import md_cell, md_label_cell


def render_unresolved_items_markdown(items: list[DossierUnresolvedItem]) -> str:
    lines = ["# 未解決項目", "", "| 種別 | 元項目 | 影響 | 推奨アクション |", "|---|---|---|---|"]
    for item in items:
        lines.append(f"| {md_label_cell(item.item_kind)} | {md_label_cell(item.source_item)} | {md_cell(item.impact)} | {md_cell(item.suggested_action)} |")
    return "\n".join(lines) + "\n"
