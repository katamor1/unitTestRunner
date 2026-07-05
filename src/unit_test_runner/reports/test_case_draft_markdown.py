from __future__ import annotations


def render_test_case_draft_markdown(payload: dict) -> str:
    function = payload["function"]
    summary = payload["coverage_summary"]
    lines = [
        "# Test Case Draft Report",
        "",
        "## Target",
        f"- Source: {payload['source']['path']}",
        f"- Function: {function['name']}",
        f"- Status: {function['status']}",
        "",
        "## Summary",
        "",
        "| Item | Count |",
        "|---|---:|",
        f"| Test Cases | {len(payload['test_cases'])} |",
        f"| Coverage Items | {summary['total_coverage_items']} |",
        f"| Covered by Draft | {summary['covered_by_draft_count']} |",
        f"| Unresolved Items | {len(payload['unresolved_items'])} |",
        "",
        "## Test Cases",
        "",
    ]
    for case in payload["test_cases"]:
        lines.extend(
            [
                f"### {case['test_case_id']}: {case['title']}",
                "",
                f"- Purpose: {case['purpose']}",
                f"- Priority: {case['priority']}",
                f"- Kind: {case['case_kind']}",
                f"- Review Status: {case['review_status']}",
                "",
                "#### Inputs",
                "",
                "| Target | Value | Rationale | Review |",
                "|---|---|---|---|",
            ]
        )
        if case["input_assignments"]:
            for assignment in case["input_assignments"]:
                lines.append(f"| {assignment['target_name']} | {assignment['value_expression']} | {assignment['rationale']} | {'yes' if assignment['review_required'] else 'no'} |")
        else:
            lines.append("| None | | | |")
        lines.extend(["", "#### State Setup", "", "| Variable | Scope | Value | Hint | Review |", "|---|---|---|---|---|"])
        if case["state_setups"]:
            for setup in case["state_setups"]:
                lines.append(f"| {setup['variable_name']} | {setup['scope']} | {setup['value_expression']} | {setup['setup_method_hint']} | {'yes' if setup['review_required'] else 'no'} |")
        else:
            lines.append("| None | | | | |")
        lines.extend(["", "#### Stub Setup", "", "| Stub | Kind | Value | Review |", "|---|---|---|---|"])
        if case["stub_setups"]:
            for setup in case["stub_setups"]:
                lines.append(f"| {setup['stub_name']} | {setup['setup_kind']} | {setup['value_expression'] or setup['call_behavior'] or ''} | {'yes' if setup['review_required'] else 'no'} |")
        else:
            lines.append("| None | | | |")
        lines.extend(["", "#### Expected Observations", "", "| Kind | Target | Expected | Review |", "|---|---|---|---|"])
        for observation in case["expected_observations"]:
            lines.append(f"| {observation['observation_kind']} | {observation['target_name'] or ''} | {observation['expected_expression'] or ''} | {'yes' if observation['review_required'] else 'no'} |")
        lines.append("")
    lines.extend(["## Unresolved Items", "", "| Kind | Description | Suggested Action |", "|---|---|---|"])
    if payload["unresolved_items"]:
        for item in payload["unresolved_items"]:
            lines.append(f"| {item['item_kind']} | {item['description']} | {item['suggested_action']} |")
    else:
        lines.append("| None | | |")
    return "\n".join(lines) + "\n"
