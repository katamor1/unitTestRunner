from __future__ import annotations


_LABELS = {
    "add_include_path": "includeパス確認",
    "approve_dossier": "dossierレビュー",
    "artifact_older_than_request": "入力より古い成果物",
    "blocked": "ブロック中",
    "build_completion": "ビルド補完",
    "build_engineer": "ビルド担当",
    "build_not_successful": "ビルド未成功",
    "build_probe_not_successful": "ビルドプローブ未成功",
    "build_review": "ビルドレビュー",
    "dossier_review_workflow": "dossierレビューワークフロー",
    "error": "エラー",
    "evidence_ready": "エビデンス準備完了",
    "evidence_review": "エビデンスレビュー",
    "execution_evidence": "実行エビデンス",
    "execution_inconclusive": "テスト実行未確定",
    "execution_review": "実行結果レビュー",
    "executable_not_found": "実行ファイル未検出",
    "expected_result_review": "期待結果レビュー",
    "expected_result_unknown": "期待結果未確認",
    "failed": "失敗",
    "function_name_mismatch": "関数名不一致",
    "generated": "生成済み",
    "harness_placeholder": "ハーネス未完了",
    "harness_skeleton_generation": "ハーネス雛形生成",
    "high": "高",
    "inconclusive": "未確定",
    "info": "情報",
    "low": "低",
    "manual_action": "手動対応",
    "manual_final_review": "最終レビュー未完了",
    "medium": "中",
    "missing_artifact": "成果物不足",
    "not_found_in_output": "実行結果未確認",
    "not_green": "未GREEN",
    "not_run": "未実行",
    "partial": "一部生成",
    "passed": "成功",
    "placeholder_expected_value": "期待値プレースホルダ",
    "ready_for_review": "レビュー準備完了",
    "rerun_tests": "テスト再実行",
    "resolve_pch_issue": "PCH課題対応",
    "review_expected_result": "期待結果確認",
    "review_stub_behavior": "スタブ/ハーネス確認",
    "source_path_mismatch": "ソースパス不一致",
    "spec_reviewer": "仕様レビュー担当",
    "stub_behavior_review": "スタブ/ハーネス挙動レビュー",
    "succeeded": "成功",
    "test_case_design": "テストケース設計",
    "test_case_design_generation": "テストケース設計生成",
    "test_execution_report": "テスト実行レポート",
    "timeout": "タイムアウト",
    "unit_test_engineer": "単体テスト担当",
    "unit_test_lead": "単体テスト責任者",
    "unknown": "不明",
    "warning": "警告",
}

_TEXTS = {
    "Build completion cannot be fully automated.": "ビルド補完は完全には自動化できません。",
    "Confirm generated analysis, test design, build status, and evidence before approval.": "承認前に、生成された解析結果、テスト設計、ビルド状態、エビデンスを確認してください。",
    "Dossier generation is not an approval decision.": "dossier生成は承認判断そのものではありません。",
    "Evidence is not a final pass result.": "このエビデンスだけでは最終PASS判定にはなりません。",
    "Expected observation is not finalized.": "期待値の確認が未完了です。",
    "Final human review is still required.": "最終的な人手レビューが必要です。",
    "Generated harness needs manual completion.": "生成ハーネスには手動補完が必要です。",
    "Review dossier": "dossierをレビュー",
    "Review expected result": "期待結果を確認",
    "Review function_dossier.md and mark checklist items outside this tool.": "function_dossier.md を確認し、チェック項目の完了判断をツール外で記録してください。",
    "Review function specification and replace TBD expected value.": "関数仕様を確認し、TBD の期待値を置き換えてください。",
    "Review function specification and replace TBD expected values.": "関数仕様を確認し、TBD の期待値を置き換えてください。",
    "Review generated harness placeholders.": "生成ハーネスのプレースホルダを確認してください。",
    "Review generated test and replace TBD expected values.": "生成テストを確認し、TBD の期待値を置き換えてください。",
    "Review generated test expected values.": "生成テストの期待値を確認してください。",
    "Review stub or harness behavior": "スタブまたはハーネスの挙動を確認",
    "Review include path": "includeパスを確認",
    "Resolve PCH issue": "PCH課題を解消",
    "Resolve placeholders or rerun tests after review.": "プレースホルダを解消するか、レビュー後にテストを再実行してください。",
    "Rerun or review generated tests": "生成テストを再実行またはレビュー",
    "Test execution was not run": "テストは未実行です。",
    "test execution was not run": "テストは未実行です。",
    "Updated generated workspace artifacts or recorded human review decision.": "生成workspace成果物の更新、または人手レビュー判断の記録。",
}


def ja_label(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    return _LABELS.get(text, text)


def ja_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if text in _TEXTS:
        return _TEXTS[text]
    if text.startswith("Expected result requires review for "):
        target = text.removeprefix("Expected result requires review for ").rstrip(".")
        return f"テストケース {target} の期待結果を確認してください。"
    if text.startswith("Confirm expected observations for "):
        target = text.removeprefix("Confirm expected observations for ").rstrip(".")
        return f"テストケース {target} の期待値・期待観測を確認してください。"
    if text.startswith("Execution status is "):
        status = text.removeprefix("Execution status is ").rstrip(".")
        return f"テスト実行状態は「{ja_label(status)}」です。"
    if text.startswith("Placeholder remains: "):
        name = text.removeprefix("Placeholder remains: ")
        return f"プレースホルダが残っています: {name}"
    if text.startswith("Test execution status is "):
        status = text.removeprefix("Test execution status is ").rstrip(".")
        return f"テスト実行状態は「{ja_label(status)}」です。"
    return text


def md_cell(value: object) -> str:
    text = ja_text(value)
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def md_label_cell(value: object) -> str:
    return md_cell(ja_label(value))
