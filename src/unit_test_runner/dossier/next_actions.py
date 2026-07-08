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
    parts = [item.description]
    if item.related_test_cases:
        parts.append("Related test cases: " + ", ".join(_non_empty(item.related_test_cases)) + ".")
    if item.related_artifacts:
        parts.append("Related artifacts: " + ", ".join(_non_empty(item.related_artifacts)) + ".")
    if item.impact:
        parts.append("Impact: " + item.impact)
    if item.suggested_action:
        parts.append("Suggested action: " + item.suggested_action)
    return " ".join(part for part in parts if part).strip()


def _expected_output_for_item(kind: str, item: DossierUnresolvedItem) -> str:
    target = _target_label(item)
    if kind == "review_expected_result":
        return f"Reviewed expected values recorded for {target}; test_case_design updated if needed."
    if kind == "review_stub_behavior":
        return f"Harness or stub decision recorded for {target}; generated files updated if needed."
    if kind == "resolve_pch_issue":
        return f"PCH setting decision recorded for {target}; build workspace regenerated if needed."
    if kind == "add_include_path":
        return f"Include path decision recorded for {target}; build context or workspace updated if needed."
    if kind == "rerun_tests":
        return f"Execution evidence refreshed for {target}; rerun result recorded."
    return f"Human review decision recorded for {target}."


def _target_label(item: DossierUnresolvedItem) -> str:
    test_cases = _non_empty(item.related_test_cases)
    if test_cases:
        return "test case " + ", ".join(test_cases)
    artifacts = _non_empty(item.related_artifacts)
    if artifacts:
        return "artifact " + ", ".join(artifacts)
    if item.source_item:
        return f"{item.source_item} / {item.item_id}"
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
