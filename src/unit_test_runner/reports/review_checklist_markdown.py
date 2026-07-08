from __future__ import annotations

from unit_test_runner.dossier.dossier_models import DossierReviewItem

from .japanese import md_cell, md_label_cell


def render_review_checklist_markdown(items: list[DossierReviewItem]) -> str:
    lines = [
        "# レビュー確認リスト",
        "",
        "| 完了 | ID | 分類 | 対象 | タイトル | 内容 | 重要度 |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in items:
        lines.append(
            f"| {'x' if item.done else ' '} | {md_cell(item.review_id)} | {md_label_cell(item.category)} | {_target_cell(item)} | {md_cell(item.title)} | {md_cell(item.description)} | {md_label_cell(item.severity)} |"
        )
    return "\n".join(lines) + "\n"


def _target_cell(item: DossierReviewItem) -> str:
    targets: list[str] = []
    targets.extend(item.related_test_cases)
    targets.extend(item.related_artifacts)
    if not targets:
        targets.append(item.review_id)
    return md_cell(", ".join(dict.fromkeys(targets)))
