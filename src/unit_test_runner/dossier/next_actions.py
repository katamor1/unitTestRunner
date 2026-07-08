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
                expected_output="生成workspace成果物の更新、または人手レビュー判断の記録。",
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
        "review_expected_result": "期待結果を確認",
        "review_stub_behavior": "スタブまたはハーネスの挙動を確認",
        "resolve_pch_issue": "PCH課題を解消",
        "add_include_path": "includeパスを確認",
        "rerun_tests": "生成テストを再実行またはレビュー",
        "approve_dossier": "dossierをレビュー",
    }.get(kind, "dossierをレビュー")


def _owner_for_kind(kind: str) -> str:
    if kind in {"review_expected_result", "approve_dossier"}:
        return "spec_reviewer"
    if kind in {"review_stub_behavior", "rerun_tests"}:
        return "unit_test_engineer"
    return "build_engineer"
