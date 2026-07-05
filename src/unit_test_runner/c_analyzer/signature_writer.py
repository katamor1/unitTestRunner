from __future__ import annotations

import json
from pathlib import Path

from .signature_models import FunctionSignature


def write_function_signature(out_dir: Path | str, signature: FunctionSignature) -> dict[str, Path]:
    reports = Path(out_dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    payload = signature.to_dict()
    json_path = reports / "function_signature.json"
    markdown_path = reports / "function_signature.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_function_signature_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def render_function_signature_markdown(payload: dict) -> str:
    function = payload["function"]
    lines = [
        "# Function Signature Report",
        "",
        "## Target",
        f"- Source: {payload['source']['path']}",
        f"- Function: {function['name']}",
        f"- Status: {function['status']}",
        f"- Style: {function['style']}",
        f"- Confidence: {function['confidence']}",
        "",
        "## Signature",
        "",
        "```c",
        function["header_text_raw"],
        "```",
        "",
        "## Return Type",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Raw | {function['return_type']['raw']} |",
        f"| Base Type | {function['return_type']['base_type']} |",
        f"| Pointer Level | {function['return_type']['pointer_level']} |",
        f"| Qualifiers | {', '.join(function['return_type']['qualifiers']) or 'None'} |",
        "",
        "## Parameters",
        "",
        "| Index | Name | Raw Type | Pointer | Array | Direction Hint | Confidence |",
        "|---:|---|---|---:|---|---|---|",
    ]
    for parameter in function["parameters"]:
        type_info = parameter["type"]
        lines.append(
            f"| {parameter['index']} | {parameter['name'] or ''} | {type_info['raw']} | {type_info['pointer_level']} | "
            f"{'yes' if type_info['is_array'] else 'no'} | {parameter['direction_hint']} | {parameter['confidence']} |"
        )
    if not function["parameters"]:
        lines.append("| | None | | | | | |")
    lines.extend(["", "## Warnings", ""])
    if payload["warnings"]:
        lines.extend(f"- {warning['code']}: {warning['message']}" for warning in payload["warnings"])
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"
