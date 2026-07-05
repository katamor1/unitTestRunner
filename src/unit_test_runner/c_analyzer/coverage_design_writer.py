from __future__ import annotations

import json
from pathlib import Path

from .coverage_models import CoverageDesignReport


def write_coverage_design(out_dir: Path | str, report: CoverageDesignReport) -> dict[str, Path]:
    reports = Path(out_dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    json_path = reports / "coverage_design.json"
    markdown_path = reports / "coverage_design.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_coverage_design_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def render_coverage_design_markdown(payload: dict) -> str:
    function = payload["function"]
    lines = [
        "# Coverage Design Report",
        "",
        "## Target",
        f"- Source: {payload['source']['path']}",
        f"- Function: {function['name']}",
        f"- Status: {function['status']}",
        "",
        "## Branches",
        "",
        "| ID | Kind | Condition | Related Variables | Related Calls | Confidence |",
        "|---|---|---|---|---|---|",
    ]
    for branch in payload["branches"]:
        condition = branch["condition"]
        lines.append(
            f"| {branch['branch_id']} | {branch['kind']} | `{condition['raw'] if condition else ''}` | "
            f"{', '.join(condition['related_variables']) if condition else ''} | {', '.join(condition['related_calls']) if condition else ''} | {branch['confidence']} |"
        )
    lines.extend(["", "## Switches", "", "| ID | Expression | Cases | Default |", "|---|---|---:|---|"])
    for switch in payload["switches"]:
        lines.append(f"| {switch['switch_id']} | `{switch['expression']['raw']}` | {len(switch['cases'])} | {'yes' if switch['has_default'] else 'no'} |")
    lines.extend(["", "## Loops", "", "| ID | Kind | Condition | Coverage Hints |", "|---|---|---|---|"])
    for loop in payload["loops"]:
        lines.append(f"| {loop['loop_id']} | {loop['kind']} | `{loop['condition']['raw'] if loop['condition'] else ''}` | {', '.join(loop['coverage_hints'])} |")
    lines.extend(["", "## Ternaries", "", "| ID | Condition | True Expression | False Expression |", "|---|---|---|---|"])
    for ternary in payload["ternaries"]:
        lines.append(f"| {ternary['ternary_id']} | `{ternary['condition']['raw']}` | `{ternary['true_expression_raw']}` | `{ternary['false_expression_raw']}` |")
    lines.extend(["", "## Return Paths", "", "| ID | Expression | Kind | Confidence |", "|---|---|---|---|"])
    for path in payload["return_paths"]:
        lines.append(f"| {path['return_id']} | `{path['expression_raw'] or ''}` | {path['return_kind']} | {path['confidence']} |")
    lines.extend(["", "## Coverage Items", "", "| ID | Type | Target | Purpose | Review Required |", "|---|---|---|---|---|"])
    for item in payload["coverage_items"]:
        lines.append(f"| {item['coverage_id']} | {item['coverage_type']} | {item['target_id']} | {item['purpose']} | {'yes' if item['review_required'] else 'no'} |")
    lines.extend(["", "## Warnings", ""])
    if payload["warnings"]:
        lines.extend(f"- {warning['code']}: {warning['message']}" for warning in payload["warnings"])
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"
