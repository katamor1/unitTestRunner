from __future__ import annotations

from unit_test_runner.dossier.dossier_models import DossierNextAction

from .japanese import md_cell, md_label_cell


def render_next_actions_markdown(actions: list[DossierNextAction]) -> str:
    lines = ["# 次のアクション", "", "| 優先度 | アクション | 担当 | 期待成果物 |", "|---|---|---|---|"]
    for action in actions:
        lines.append(f"| {md_label_cell(action.priority)} | {md_cell(action.title)} | {md_label_cell(action.owner_role)} | {md_cell(action.expected_output)} |")
    return "\n".join(lines) + "\n"
