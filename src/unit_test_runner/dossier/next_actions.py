from __future__ import annotations

from .dossier_models import DossierNextAction, DossierUnresolvedItem


def build_next_actions(unresolved_items: list[DossierUnresolvedItem]) -> list[DossierNextAction]:
    actions: list[DossierNextAction] = []
    for index, item in enumerate(unresolved_items, start=1):
        kind = _action_kind(item.item_kind)
        actions.append(
            DossierNextAction(
                action_id=f"NEXT_{index:03d}",
                priority="high" if item.blocks_readiness else "medium",
                action_kind=kind,
                title=_title_for_kind(kind),
                description=item.suggested_action,
                owner_role=_owner_for_kind(kind),
                related_unresolved_items=[item.item_id],
                expected_output="Updated generated workspace artifacts or recorded human review decision.",
            )
        )
    return actions


def _action_kind(item_kind: str) -> str:
    if "expected" in item_kind:
        return "review_expected_result"
    if "stub" in item_kind or "harness" in item_kind:
        return "review_stub_behavior"
    if "pch" in item_kind:
        return "resolve_pch_issue"
    if "include" in item_kind:
        return "add_include_path"
    if "execution" in item_kind:
        return "rerun_tests"
    return "approve_dossier"


def _title_for_kind(kind: str) -> str:
    return {
        "review_expected_result": "Review expected result",
        "review_stub_behavior": "Review stub or harness behavior",
        "resolve_pch_issue": "Resolve PCH issue",
        "add_include_path": "Review include path",
        "rerun_tests": "Rerun or review generated tests",
        "approve_dossier": "Review dossier",
    }.get(kind, "Review dossier")


def _owner_for_kind(kind: str) -> str:
    if kind in {"review_expected_result", "approve_dossier"}:
        return "spec_reviewer"
    if kind in {"review_stub_behavior", "rerun_tests"}:
        return "unit_test_engineer"
    return "build_engineer"
