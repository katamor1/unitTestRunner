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
        "# 関数シグネチャレポート",
        "",
        "## 対象",
        f"- ソース: {payload['source']['path']}",
        f"- 関数: {function['name']}",
        f"- 状態: {function['status']}",
        f"- 形式: {function['style']}",
        f"- 信頼度: {function['confidence']}",
        "",
        "## シグネチャ",
        "",
        "```c",
        function["header_text_raw"],
        "```",
        "",
        "## 戻り値型",
        "",
        "| 項目 | 値 |",
        "|---|---|",
        f"| 生表記 | {function['return_type']['raw']} |",
        f"| 基本型 | {function['return_type']['base_type']} |",
        f"| ポインタ階層 | {function['return_type']['pointer_level']} |",
        f"| 修飾子 | {', '.join(function['return_type']['qualifiers']) or 'なし'} |",
        "",
        "## パラメータ",
        "",
        "| 番号 | 名前 | 型表記 | ポインタ | 配列 | 入出力推定 | 信頼度 |",
        "|---:|---|---|---:|---|---|---|",
    ]
    for parameter in function["parameters"]:
        type_info = parameter["type"]
        lines.append(
            f"| {parameter['index']} | {parameter['name'] or ''} | {type_info['raw']} | {type_info['pointer_level']} | "
            f"{'はい' if type_info['is_array'] else 'いいえ'} | {parameter['direction_hint']} | {parameter['confidence']} |"
        )
    if not function["parameters"]:
        lines.append("| | なし | | | | | |")
    lines.extend(["", "## 警告", ""])
    if payload["warnings"]:
        lines.extend(f"- {warning['code']}: {warning['message']}" for warning in payload["warnings"])
    else:
        lines.append("- なし")
    return "\n".join(lines) + "\n"
