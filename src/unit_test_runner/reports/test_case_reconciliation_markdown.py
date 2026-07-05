from __future__ import annotations


def render_test_case_reconciliation_markdown(payload: dict) -> str:
    function = payload["function"]
    rows = [
        ("Reusable", payload["preserved_test_cases"]),
        ("Needs Update", payload["updated_test_cases"]),
        ("Obsolete", payload["obsolete_test_cases"]),
        ("Blocked", payload["blocked_test_cases"]),
        ("New Required", payload["new_test_case_candidates"]),
    ]
    lines = [
        "# Test Case Reconciliation Report",
        "",
        "## Summary",
        "",
        f"- Function: {function['name']}",
        f"- Status: {function['status']}",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for label, cases in rows:
        lines.append(f"| {label} | {len(cases)} |")
    lines.extend(["", "## Existing Test Cases", "", "| Test Case | Reuse Status | Reason | Review Fields |", "|---|---|---|---|"])
    existing = payload["preserved_test_cases"] + payload["updated_test_cases"] + payload["obsolete_test_cases"] + payload["blocked_test_cases"]
    if existing:
        for case in existing:
            lines.append(f"| {case['test_case_id']} | {case['reuse_status']} | {case['reason']} | {', '.join(case['review_required_fields'])} |")
    else:
        lines.append("| None | | | |")
    lines.extend(["", "## New Required Test Cases", "", "| Test Case | Coverage | Reason |", "|---|---|---|"])
    if payload["new_test_case_candidates"]:
        for case in payload["new_test_case_candidates"]:
            lines.append(f"| {case['test_case_id']} | {', '.join(case['current_coverage_ids'])} | {case['reason']} |")
    else:
        lines.append("| None | | |")
    return "\n".join(lines) + "\n"
