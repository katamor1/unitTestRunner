from __future__ import annotations

import json
from pathlib import Path

from .boundary_models import BoundaryEquivalenceReport


def write_boundary_equivalence_candidates(out_dir: Path | str, report: BoundaryEquivalenceReport) -> dict[str, Path]:
    reports = Path(out_dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    json_path = reports / "boundary_equivalence_candidates.json"
    markdown_path = reports / "boundary_equivalence_candidates.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_boundary_equivalence_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def render_boundary_equivalence_markdown(payload: dict) -> str:
    function = payload["function"]
    lines = [
        "# Boundary / Equivalence Candidate Report",
        "",
        "## Target",
        f"- Source: {payload['source']['path']}",
        f"- Function: {function['name']}",
        f"- Status: {function['status']}",
        "",
        "## Input Value Candidates",
        "",
        "| ID | Target | Value | Kind | Related Coverage | Evidence | Review |",
        "|---|---|---|---|---|---|---|",
    ]
    for candidate in payload["input_candidates"]:
        lines.append(
            f"| {candidate['candidate_id']} | {candidate['target_name']} | {candidate['value_expression']} | {candidate['value_kind']} | "
            f"{', '.join(candidate['related_coverage_ids'])} | `{candidate['evidence']}` | {'yes' if candidate['review_required'] else 'no'} |"
        )
    lines.extend(["", "## Equivalence Classes", "", "| ID | Target | Class | Representative Values | Coverage | Review |", "|---|---|---|---|---|---|"])
    for item in payload["equivalence_classes"]:
        lines.append(f"| {item['class_id']} | {item['target_name']} | {item['class_name']} | {', '.join(item['representative_values'])} | {', '.join(item['related_coverage_ids'])} | {'yes' if item['review_required'] else 'no'} |")
    lines.extend(["", "## State Candidates", "", "| ID | Variable | Scope | Value | Setup Hint | Review |", "|---|---|---|---|---|---|"])
    for candidate in payload["state_candidates"]:
        lines.append(f"| {candidate['candidate_id']} | {candidate['variable_name']} | {candidate['scope']} | {candidate['value_expression']} | {candidate['setup_hint']} | {'yes' if candidate['review_required'] else 'no'} |")
    lines.extend(["", "## Stub Return Candidates", "", "| ID | Call | Value | Purpose | Coverage | Review |", "|---|---|---|---|---|---|"])
    for candidate in payload["stub_return_candidates"]:
        lines.append(f"| {candidate['candidate_id']} | {candidate['call_name']} | {candidate['value_expression']} | {candidate['purpose']} | {', '.join(candidate['related_coverage_ids'])} | {'yes' if candidate['review_required'] else 'no'} |")
    lines.extend(["", "## Warnings", ""])
    if payload["warnings"]:
        lines.extend(f"- {warning['code']}: {warning['message']}" for warning in payload["warnings"])
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"
