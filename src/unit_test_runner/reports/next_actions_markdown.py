from __future__ import annotations

from unit_test_runner.dossier.dossier_models import DossierNextAction


def render_next_actions_markdown(actions: list[DossierNextAction]) -> str:
    lines = ["# 次のアクション", "", "| 優先度 | アクション | 担当 | 期待成果物 |", "|---|---|---|---|"]
    for action in actions:
        lines.append(f"| {action.priority} | {action.title} | {action.owner_role} | {action.expected_output} |")
    return "\n".join(lines) + "\n"
