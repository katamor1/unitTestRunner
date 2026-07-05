from __future__ import annotations


def render_change_impact_markdown(payload: dict) -> str:
    function = payload["function"]
    lines = [
        "# Change Impact Report",
        "",
        "## Summary",
        "",
        f"- Function: {function['name']}",
        f"- Status: {function['status']}",
        f"- Interface changes: {len(payload['interface_changes'])}",
        f"- Dependency changes: {len(payload['dependency_changes'])}",
        f"- Coverage changes: {len(payload['coverage_changes'])}",
        "",
        "## Interface Changes",
        "",
        "| Kind | Target | Impact | Suggested Action |",
        "|---|---|---|---|",
    ]
    if payload["interface_changes"]:
        for item in payload["interface_changes"]:
            lines.append(f"| {item['change_kind']} | {item['target_name']} | {item['impact_level']} | {item['suggested_action']} |")
    else:
        lines.append("| None | | | |")
    lines.extend(["", "## Dependency Changes", "", "| Kind | Name | Impact | Suggested Action |", "|---|---|---|---|"])
    if payload["dependency_changes"]:
        for item in payload["dependency_changes"]:
            lines.append(f"| {item['change_kind']} | {item['name']} | {item['impact_level']} | {item['suggested_action']} |")
    else:
        lines.append("| None | | | |")
    lines.extend(["", "## Coverage Changes", "", "| Kind | Previous | Current | Similarity | Suggested Action |", "|---|---|---|---:|---|"])
    if payload["coverage_changes"]:
        for item in payload["coverage_changes"]:
            similarity = "" if item["similarity"] is None else f"{item['similarity']:.2f}"
            lines.append(f"| {item['change_kind']} | {item['old_coverage_id'] or ''} | {item['new_coverage_id'] or ''} | {similarity} | {item['suggested_action']} |")
    else:
        lines.append("| None | | | | |")
    return "\n".join(lines) + "\n"
