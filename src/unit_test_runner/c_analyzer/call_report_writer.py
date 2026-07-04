from __future__ import annotations

import json
from pathlib import Path

from .call_models import CallReport


def write_call_report(out_dir: Path | str, report: CallReport) -> dict[str, Path]:
    reports = Path(out_dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    json_path = reports / "call_report.json"
    markdown_path = reports / "call_report.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_call_report_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def render_call_report_markdown(payload: dict) -> str:
    function = payload["function"]
    lines = [
        "# Call Report",
        "",
        "## Target",
        f"- Source: {payload['source']['path']}",
        f"- Function: {function['name']}",
        f"- Status: {function['status']}",
        "",
        "## Calls",
        "",
        "| ID | Name | Target Kind | Return Usage | Evidence | Confidence |",
        "|---|---|---|---|---|---|",
    ]
    for call in payload["calls"]:
        lines.append(f"| {call['call_id']} | {call['name']} | {call['target_kind']} | {call['return_usage']['usage_kind']} | `{call['evidence']}` | {call['confidence']} |")
    lines.extend(["", "## Stub Candidates", "", "| Name | Reason | Return Control | Arg Capture | Side Effect | Tags |", "|---|---|---|---|---|---|"])
    for candidate in payload["stub_candidates"]:
        lines.append(
            f"| {candidate['name']} | {candidate['reason']} | {'yes' if candidate['return_value_control_needed'] else 'no'} | "
            f"{'yes' if candidate['argument_capture_needed'] else 'no'} | {'yes' if candidate['side_effect_control_needed'] else 'no'} | {', '.join(candidate['tags'])} |"
        )
    lines.extend(["", "## Side Effect Candidates", "", "| Call | Kind | Evidence | Confidence |", "|---|---|---|---|"])
    for candidate in payload["side_effect_candidates"]:
        lines.append(f"| {candidate['call_name']} | {candidate['kind']} | `{candidate['evidence']}` | {candidate['confidence']} |")
    lines.extend(["", "## Warnings", ""])
    if payload["warnings"]:
        lines.extend(f"- {warning['code']}: {warning['message']}" for warning in payload["warnings"])
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"
