from __future__ import annotations

from unit_test_runner.dossier.dossier_models import DossierReviewItem


def render_review_checklist_markdown(items: list[DossierReviewItem]) -> str:
    lines = ["# レビュー確認リスト", "", "| 完了 | 分類 | タイトル | 重要度 |", "|---|---|---|---|"]
    for item in items:
        lines.append(f"| {'x' if item.done else ' '} | {item.category} | {item.title} | {item.severity} |")
    return "\n".join(lines) + "\n"
