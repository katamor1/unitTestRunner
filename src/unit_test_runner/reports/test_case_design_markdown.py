from __future__ import annotations


def render_test_case_design_markdown(payload: dict) -> str:
    function = payload["function"]
    summary = payload["coverage_summary"]
    lines = [
        "# テストケース設計レポート",
        "",
        "## 対象",
        f"- ソース: {payload['source']['path']}",
        f"- 関数: {function['name']}",
        f"- 状態: {function['status']}",
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
                f"### {case['test_case_id']}: {case['title']}",
                "",
                f"- 目的: {case['purpose']}",
                f"- 優先度: {case['priority']}",
                f"- 種別: {case['case_kind']}",
                f"- レビュー状態: {case['review_status']}",
                "",
                "#### 入力",
                "",
                "| 対象 | 値 | 理由 | レビュー要否 |",
                "|---|---|---|---|",
            ]
        )
        if case["input_assignments"]:
            for assignment in case["input_assignments"]:
                lines.append(f"| {assignment['target_name']} | {assignment['value_expression']} | {assignment['rationale']} | {'はい' if assignment['review_required'] else 'いいえ'} |")
        else:
            lines.append("| なし | | | |")
        lines.extend(["", "#### 状態セットアップ", "", "| 変数 | スコープ | 値 | ヒント | レビュー要否 |", "|---|---|---|---|---|"])
        if case["state_setups"]:
            for setup in case["state_setups"]:
                lines.append(f"| {setup['variable_name']} | {setup['scope']} | {setup['value_expression']} | {setup['setup_method_hint']} | {'はい' if setup['review_required'] else 'いいえ'} |")
        else:
            lines.append("| なし | | | | |")
        lines.extend(["", "#### スタブ設定", "", "| スタブ | 種別 | 値 | レビュー要否 |", "|---|---|---|---|"])
        if case["stub_setups"]:
            for setup in case["stub_setups"]:
                lines.append(f"| {setup['stub_name']} | {setup['setup_kind']} | {setup['value_expression'] or setup['call_behavior'] or ''} | {'はい' if setup['review_required'] else 'いいえ'} |")
        else:
            lines.append("| なし | | | |")
        lines.extend(["", "#### 期待観測", "", "| 種別 | 対象 | 期待値 | レビュー要否 |", "|---|---|---|---|"])
        for observation in case["expected_observations"]:
            lines.append(f"| {observation['observation_kind']} | {observation['target_name'] or ''} | {observation['expected_expression'] or ''} | {'はい' if observation['review_required'] else 'いいえ'} |")
        lines.append("")
    lines.extend(["## 未解決項目", "", "| 種別 | 説明 | 推奨アクション |", "|---|---|---|"])
    if payload["unresolved_items"]:
        for item in payload["unresolved_items"]:
            lines.append(f"| {item['item_kind']} | {item['description']} | {item['suggested_action']} |")
    else:
        lines.append("| なし | | |")
    return "\n".join(lines) + "\n"
