from __future__ import annotations

from unit_test_runner.dossier.dossier_models import DossierNextAction


def render_next_actions_markdown(actions: list[DossierNextAction]) -> str:
    lines = [
        "# 次のアクション",
        "",
        "| ID | 優先度 | アクション | 対応対象・理由 | 担当 | 期待成果物 |",
        "|---|---|---|---|---|---|",
    ]
    for action in actions:
        related = ", ".join(action.related_unresolved_items) if action.related_unresolved_items else "-"
        detail = action.description or related
        if related != "-" and related not in detail:
            detail = f"{related}: {detail}"
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(action.action_id),
                    _markdown_cell(action.priority),
                    _markdown_cell(action.title),
                    _markdown_cell(detail),
                    _markdown_cell(action.owner_role),
                    _markdown_cell(action.expected_output),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _markdown_cell(value: str) -> str:
    text = str(value or "-").replace("\n", "<br>")
    return text.replace("|", "\\|")
