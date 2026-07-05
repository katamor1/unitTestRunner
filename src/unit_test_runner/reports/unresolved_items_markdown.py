from __future__ import annotations

from unit_test_runner.dossier.dossier_models import DossierUnresolvedItem


def render_unresolved_items_markdown(items: list[DossierUnresolvedItem]) -> str:
    lines = ["# Unresolved Items", "", "| Kind | Source Item | Impact | Suggested Action |", "|---|---|---|---|"]
    for item in items:
        lines.append(f"| {item.item_kind} | {item.source_item} | {item.impact} | {item.suggested_action} |")
    return "\n".join(lines) + "\n"
