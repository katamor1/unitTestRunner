from __future__ import annotations


def render_test_case_reconciliation_markdown(payload: dict) -> str:
    function = payload["function"]
    rows = [
        ("再利用可能", payload["preserved_test_cases"]),
        ("更新が必要", payload["updated_test_cases"]),
        ("廃止候補", payload["obsolete_test_cases"]),
        ("ブロック中", payload["blocked_test_cases"]),
        ("新規作成が必要", payload["new_test_case_candidates"]),
    ]
    lines = [
        "# テストケース照合レポート",
        "",
        "## サマリ",
        "",
        f"- 関数: {function['name']}",
        f"- 状態: {function['status']}",
        "",
        "| 状態 | 件数 |",
        "|---|---:|",
    ]
    for label, cases in rows:
        lines.append(f"| {label} | {len(cases)} |")
    lines.extend(["", "## 既存テストケース", "", "| テストケース | 再利用状態 | 理由 | レビュー対象フィールド |", "|---|---|---|---|"])
    existing = payload["preserved_test_cases"] + payload["updated_test_cases"] + payload["obsolete_test_cases"] + payload["blocked_test_cases"]
    if existing:
        for case in existing:
            lines.append(f"| {case['test_case_id']} | {case['reuse_status']} | {case['reason']} | {', '.join(case['review_required_fields'])} |")
    else:
        lines.append("| なし | | | |")
    lines.extend(["", "## 新規作成が必要なテストケース", "", "| テストケース | カバレッジ | 理由 |", "|---|---|---|"])
    if payload["new_test_case_candidates"]:
        for case in payload["new_test_case_candidates"]:
            lines.append(f"| {case['test_case_id']} | {', '.join(case['current_coverage_ids'])} | {case['reason']} |")
    else:
        lines.append("| なし | | |")
    return "\n".join(lines) + "\n"
