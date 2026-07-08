from __future__ import annotations

from unit_test_runner.dossier.dossier_models import DossierReviewItem

from .japanese import md_cell, md_label_cell


def render_review_checklist_markdown(items: list[DossierReviewItem]) -> str:
    lines = ["# レビュー確認リスト", "", "| 完了 | 分類 | タイトル | 重要度 |", "|---|---|---|---|"]
    for item in items:
        lines.append(f"| {'x' if item.done else ' '} | {md_label_cell(item.category)} | {md_cell(item.title)} | {md_label_cell(item.severity)} |")
    return "\n".join(lines) + "\n"
