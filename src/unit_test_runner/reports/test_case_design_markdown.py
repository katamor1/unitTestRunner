from __future__ import annotations

from .japanese import ja_label, md_cell, md_label_cell


def render_test_case_design_markdown(payload: dict) -> str:
    function = payload["function"]
    summary = payload["coverage_summary"]
    lines = [
        "# テストケース設計レポート",
        "",
        "## 対象",
        f"- ソース: {payload['source']['path']}",
        f"- 関数: {function['name']}",
        f"- 状態: {ja_label(function['status'])}",
        "",
        "## サマリ",
        "",
        "| 項目 | 件数 |",
        "|---|---:|",
        f"| テストケース | {len(payload['test_cases'])} |",
        f"| カバレッジ項目 | {summary['total_coverage_items']} |",
        f"| 設計済みカバレッジ | {summary['covered_by_design_count']} |",
        f"| 未解決項目 | {len(payload['unresolved_items'])} |",
        "",
        "## テストケース",
        "",
    ]
    for case in payload["test_cases"]:
        lines.extend(
            [
                f"### {case['test_case_id']}: {md_cell(case['title'])}",
                "",
                f"- 目的: {md_cell(case['purpose'])}",
                f"- 優先度: {md_label_cell(case['priority'])}",
                f"- 種別: {md_label_cell(case['case_kind'])}",
                f"- レビュー状態: {md_label_cell(case['review_status'])}",
                "",
                "#### 入力",
                "",
                "| 対象 | 値 | 理由 | レビュー要否 |",
                "|---|---|---|---|",
            ]
        )
        if case["input_assignments"]:
            for assignment in case["input_assignments"]:
                lines.append(f"| {assignment['target_name']} | {md_cell(assignment['value_expression'])} | {md_cell(assignment['rationale'])} | {'はい' if assignment['review_required'] else 'いいえ'} |")
        else:
            lines.append("| なし | | | |")
        lines.extend(["", "#### 状態セットアップ", "", "| 変数 | スコープ | 値 | ヒント | レビュー要否 |", "|---|---|---|---|---|"])
        if case["state_setups"]:
            for setup in case["state_setups"]:
                lines.append(f"| {setup['variable_name']} | {md_label_cell(setup['scope'])} | {md_cell(setup['value_expression'])} | {md_cell(setup['setup_method_hint'])} | {'はい' if setup['review_required'] else 'いいえ'} |")
        else:
            lines.append("| なし | | | | |")
        lines.extend(["", "#### スタブ設定", "", "| スタブ | 種別 | 値 | レビュー要否 |", "|---|---|---|---|"])
        if case["stub_setups"]:
            for setup in case["stub_setups"]:
                lines.append(f"| {setup['stub_name']} | {md_label_cell(setup['setup_kind'])} | {md_cell(setup['value_expression'] or setup['call_behavior'] or '')} | {'はい' if setup['review_required'] else 'いいえ'} |")
        else:
            lines.append("| なし | | | |")
        lines.extend(["", "#### 期待観測", "", "| 種別 | 対象 | 期待値 | レビュー要否 |", "|---|---|---|---|"])
        for observation in case["expected_observations"]:
            lines.append(f"| {md_label_cell(observation['observation_kind'])} | {observation['target_name'] or ''} | {md_cell(observation['expected_expression'] or '')} | {'はい' if observation['review_required'] else 'いいえ'} |")
        lines.append("")
    lines.extend(["## 未解決項目", "", "| 種別 | 説明 | 推奨アクション |", "|---|---|---|"])
    if payload["unresolved_items"]:
        for item in payload["unresolved_items"]:
            lines.append(f"| {md_label_cell(item['item_kind'])} | {md_cell(item['description'])} | {md_cell(item['suggested_action'])} |")
    else:
        lines.append("| なし | | |")
    return "\n".join(lines) + "\n"
