from __future__ import annotations

from unit_test_runner.dossier.dossier_models import FunctionDossier


def render_function_dossier_markdown(dossier: FunctionDossier) -> str:
    payload = dossier.to_dict()
    lines = [
        f"# Function Dossier: {dossier.function_name}",
        "",
        "## Summary",
        f"- Source: {payload['function'].get('source_path') or ''}",
        f"- Status: {dossier.status}",
        f"- MVP Level: {dossier.readiness.mvp_level}",
        f"- Ready For Review: {'yes' if dossier.readiness.ready_for_review else 'no'}",
        "",
        "## Function Interface",
        f"- Signature: {dossier.summaries.get('function_summary', {}).get('signature', '')}",
        f"- Parameters: {dossier.summaries.get('function_summary', {}).get('parameter_count', 0)}",
        "",
        "## Dependencies",
        f"- Global reads: {dossier.summaries.get('dependency_summary', {}).get('global_read_count', 0)}",
        f"- Global writes: {dossier.summaries.get('dependency_summary', {}).get('global_write_count', 0)}",
        f"- External calls: {dossier.summaries.get('dependency_summary', {}).get('external_call_count', 0)}",
        f"- Stub candidates: {dossier.summaries.get('dependency_summary', {}).get('stub_candidate_count', 0)}",
        "",
        "## Coverage And Tests",
        f"- Coverage items: {dossier.summaries.get('coverage_summary', {}).get('coverage_item_count', 0)}",
        f"- Test cases: {dossier.summaries.get('coverage_summary', {}).get('test_case_design_count', 0)}",
        "",
        "## Build And Execution",
        f"- Build probe: {dossier.summaries.get('build_summary', {}).get('build_probe_status', 'unknown')}",
        f"- Test execution: {dossier.summaries.get('execution_summary', {}).get('status', 'unknown')}",
        "",
        "## Traceability",
        "See `traceability_matrix.csv`.",
        "",
        "## Unresolved Items",
        "| Item | Impact | Suggested Action |",
        "|---|---|---|",
    ]
    for item in dossier.unresolved_items:
        lines.append(f"| {item.item_kind} | {item.impact} | {item.suggested_action} |")
    lines.extend(["", "## Next Actions", "| Priority | Action | Owner Role |", "|---|---|---|"])
    for action in dossier.next_actions:
        lines.append(f"| {action.priority} | {action.title} | {action.owner_role} |")
    return "\n".join(lines) + "\n"
