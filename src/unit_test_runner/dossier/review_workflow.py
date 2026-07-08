from __future__ import annotations

from typing import Any

from unit_test_runner.reports.japanese import ja_label, ja_text

from .dossier_models import DossierReviewItem, DossierUnresolvedItem


def build_review_items(payloads: dict[str, dict[str, Any]]) -> tuple[list[DossierReviewItem], list[DossierUnresolvedItem]]:
    review_items: list[DossierReviewItem] = []
    unresolved: list[DossierUnresolvedItem] = []
    _from_test_case_design(payloads.get("test_case_design", {}), review_items, unresolved)
    _from_harness(payloads.get("harness_skeleton_report", {}), review_items, unresolved)
    _from_completion(payloads.get("build_completion_plan", {}), review_items, unresolved)
    _from_execution(payloads.get("test_execution_report", {}), review_items, unresolved)
    if not review_items:
        review_items.append(
            DossierReviewItem(
                "REVIEW_FINAL_001",
                "evidence_review",
                "生成dossierの最終確認",
                "承認前に、生成された解析結果、テスト設計、ビルド状態、エビデンスを確認してください。",
                severity="info",
                suggested_reviewer_role="unit_test_lead",
            )
        )
    if not unresolved:
        unresolved.append(
            DossierUnresolvedItem(
                "UNRESOLVED_REVIEW_001",
                "dossier_review_workflow",
                "manual_final_review",
                "最終的な人手レビューが必要です。",
                "dossier生成は承認判断そのものではありません。",
                suggested_action="function_dossier.md を確認し、チェック項目の完了判断をツール外で記録してください。",
            )
        )
    return review_items, unresolved


def _from_test_case_design(payload: dict[str, Any], review_items: list[DossierReviewItem], unresolved: list[DossierUnresolvedItem]) -> None:
    for case in payload.get("test_cases", []):
        test_case_id = case.get("test_case_id") or case.get("id")
        needs_review = case.get("review_status") == "review_required"
        has_tbd = any(str(obs.get("expected_expression", "")).startswith("TBD") or obs.get("expected_expression") is None for obs in case.get("expected_observations", []))
        if needs_review or has_tbd:
            item_id = f"UNRESOLVED_EXPECTED_{len(unresolved) + 1:03d}"
            unresolved.append(
                DossierUnresolvedItem(
                    item_id,
                    "test_case_design_generation",
                    "expected_result_unknown",
                    f"テストケース {test_case_id} の期待結果を確認してください。",
                    "生成テストは、期待値レビューが完了するまで承認済みとして扱えません。",
                    ["test_case_design"],
                    [test_case_id] if test_case_id else [],
                    "関数仕様を確認し、TBD の期待値を置き換えてください。",
                )
            )
            review_items.append(
                DossierReviewItem(
                    f"REVIEW_EXPECTED_{len(review_items) + 1:03d}",
                    "expected_result_review",
                    "期待結果を確認",
                    f"テストケース {test_case_id} の期待値・期待観測を確認してください。",
                    ["test_case_design"],
                    [test_case_id] if test_case_id else [],
                )
            )


def _from_harness(payload: dict[str, Any], review_items: list[DossierReviewItem], unresolved: list[DossierUnresolvedItem]) -> None:
    for placeholder in payload.get("unresolved_placeholders", []):
        test_case_id = placeholder.get("related_test_case_id")
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_PLACEHOLDER_{len(unresolved) + 1:03d}",
                "harness_skeleton_generation",
                "harness_placeholder",
                f"プレースホルダが残っています: {placeholder.get('name')}",
                "生成ハーネスには手動補完が必要です。",
                ["harness_skeleton_report"],
                [test_case_id] if test_case_id else [],
                ja_text(placeholder.get("suggested_action", "生成ハーネスのプレースホルダを確認してください。")),
            )
        )
        review_items.append(DossierReviewItem(f"REVIEW_HARNESS_{len(review_items) + 1:03d}", "stub_behavior_review", "ハーネスのプレースホルダを確認", str(placeholder.get("name")), ["harness_skeleton_report"], [test_case_id] if test_case_id else []))


def _from_completion(payload: dict[str, Any], review_items: list[DossierReviewItem], unresolved: list[DossierUnresolvedItem]) -> None:
    for manual in payload.get("manual_action_items", []):
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_BUILD_{len(unresolved) + 1:03d}",
                "build_completion",
                manual.get("item_kind", "manual_action"),
                ja_text(manual.get("description", "手動でのビルド補完作業が残っています。")),
                ja_text(manual.get("reason", "ビルド補完は完全には自動化できません。")),
                ["build_completion_plan"],
                [],
                ja_text(manual.get("suggested_action", "ビルド補完計画を確認してください。")),
                blocks_readiness=False,
            )
        )
        review_items.append(DossierReviewItem(f"REVIEW_BUILD_{len(review_items) + 1:03d}", "build_review", "ビルド補完項目を確認", ja_text(manual.get("description", "")), ["build_completion_plan"]))


def _from_execution(payload: dict[str, Any], review_items: list[DossierReviewItem], unresolved: list[DossierUnresolvedItem]) -> None:
    status = payload.get("function", {}).get("status") or payload.get("status")
    if status in {"inconclusive", "failed", "blocked", "timeout", "not_run"}:
        status_label = ja_label(status)
        unresolved.append(
            DossierUnresolvedItem(
                f"UNRESOLVED_EXEC_{len(unresolved) + 1:03d}",
                "execution_evidence",
                "execution_inconclusive",
                f"テスト実行状態は「{status_label}」です。",
                "このエビデンスだけでは最終PASS判定にはなりません。",
                ["test_execution_report"],
                [],
                "プレースホルダを解消するか、レビュー後にテストを再実行してください。",
            )
        )
        review_items.append(DossierReviewItem(f"REVIEW_EXEC_{len(review_items) + 1:03d}", "execution_review", "実行エビデンスを確認", f"テスト実行状態は「{status_label}」です。", ["test_execution_report"]))
