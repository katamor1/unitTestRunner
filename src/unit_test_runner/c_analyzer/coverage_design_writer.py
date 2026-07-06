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
        "# カバレッジ設計レポート",
        "",
        "## 対象",
        f"- ソース: {payload['source']['path']}",
        f"- 関数: {function['name']}",
        f"- 状態: {function['status']}",
        "",
        "## 分岐",
        "",
        "| ID | 種別 | 条件 | 関連変数 | 関連呼び出し | 信頼度 |",
        "|---|---|---|---|---|---|",
    ]
    for branch in payload["branches"]:
        condition = branch["condition"]
        lines.append(
            f"| {branch['branch_id']} | {branch['kind']} | `{condition['raw'] if condition else ''}` | "
            f"{', '.join(condition['related_variables']) if condition else ''} | {', '.join(condition['related_calls']) if condition else ''} | {branch['confidence']} |"
        )
    lines.extend(["", "## switch文", "", "| ID | 式 | case数 | default有無 |", "|---|---|---:|---|"])
    for switch in payload["switches"]:
        lines.append(f"| {switch['switch_id']} | `{switch['expression']['raw']}` | {len(switch['cases'])} | {'はい' if switch['has_default'] else 'いいえ'} |")
    lines.extend(["", "## ループ", "", "| ID | 種別 | 条件 | カバレッジヒント |", "|---|---|---|---|"])
    for loop in payload["loops"]:
        lines.append(f"| {loop['loop_id']} | {loop['kind']} | `{loop['condition']['raw'] if loop['condition'] else ''}` | {', '.join(loop['coverage_hints'])} |")
    lines.extend(["", "## 三項演算子", "", "| ID | 条件 | true式 | false式 |", "|---|---|---|---|"])
    for ternary in payload["ternaries"]:
        lines.append(f"| {ternary['ternary_id']} | `{ternary['condition']['raw']}` | `{ternary['true_expression_raw']}` | `{ternary['false_expression_raw']}` |")
    lines.extend(["", "## return経路", "", "| ID | 式 | 種別 | 信頼度 |", "|---|---|---|---|"])
    for path in payload["return_paths"]:
        lines.append(f"| {path['return_id']} | `{path['expression_raw'] or ''}` | {path['return_kind']} | {path['confidence']} |")
    lines.extend(["", "## カバレッジ項目", "", "| ID | 種別 | 対象 | 目的 | レビュー要否 |", "|---|---|---|---|---|"])
    for item in payload["coverage_items"]:
        lines.append(f"| {item['coverage_id']} | {item['coverage_type']} | {item['target_id']} | {item['purpose']} | {'はい' if item['review_required'] else 'いいえ'} |")
    lines.extend(["", "## 警告", ""])
    if payload["warnings"]:
        lines.extend(f"- {warning['code']}: {warning['message']}" for warning in payload["warnings"])
    else:
        lines.append("- なし")
    return "\n".join(lines) + "\n"
