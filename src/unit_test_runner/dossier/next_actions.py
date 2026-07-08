from __future__ import annotations

from unit_test_runner.reports.japanese import ja_label, ja_text

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
                title=_title_for_item(kind, item),
                description=_description_for_item(item),
                owner_role=_owner_for_kind(kind),
                related_unresolved_items=[item.item_id],
                expected_output=_expected_output_for_item(kind, item),
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


def _title_for_item(kind: str, item: DossierUnresolvedItem) -> str:
    return f"{_title_for_kind(kind)}: {_target_label(item)}"


def _description_for_item(item: DossierUnresolvedItem) -> str:
    parts = [ja_text(item.description)]
    if item.related_test_cases:
        parts.append("関連テストケース: " + ", ".join(_non_empty(item.related_test_cases)) + "。")
    if item.related_artifacts:
        parts.append("関連成果物: " + ", ".join(ja_label(value) for value in _non_empty(item.related_artifacts)) + "。")
    if item.impact:
        parts.append("影響: " + ja_text(item.impact))
    if item.suggested_action:
        parts.append("推奨対応: " + ja_text(item.suggested_action))
    return " ".join(part for part in parts if part).strip()


def _expected_output_for_item(kind: str, item: DossierUnresolvedItem) -> str:
    target = _target_label(item)
    if kind == "review_expected_result":
        return f"{target} の期待値レビュー結果を記録し、必要に応じてテストケース設計を更新する。"
    if kind == "review_stub_behavior":
        return f"{target} のハーネス/スタブ判断を記録し、必要に応じて生成ファイルを更新する。"
    if kind == "resolve_pch_issue":
        return f"{target} のPCH設定判断を記録し、必要に応じてビルドworkspaceを再生成する。"
    if kind == "add_include_path":
        return f"{target} のincludeパス判断を記録し、必要に応じてビルドコンテキストまたはworkspaceを更新する。"
    if kind == "rerun_tests":
        return f"{target} の実行エビデンスを更新し、再実行結果を記録する。"
    return f"{target} の人手レビュー判断を記録する。"


def _target_label(item: DossierUnresolvedItem) -> str:
    test_cases = _non_empty(item.related_test_cases)
    if test_cases:
        return "テストケース " + ", ".join(test_cases)
    artifacts = _non_empty(item.related_artifacts)
    if artifacts:
        return "成果物 " + ", ".join(ja_label(value) for value in artifacts)
    if item.source_item:
        return f"{ja_label(item.source_item)} / {item.item_id}"
    return item.item_id


def _non_empty(values: list[str]) -> list[str]:
    return [str(value) for value in values if str(value).strip()]


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
