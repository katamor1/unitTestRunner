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
        "# 境界値・同値クラス候補レポート",
        "",
        "## 対象",
        f"- ソース: {payload['source']['path']}",
        f"- 関数: {function['name']}",
        f"- 状態: {function['status']}",
        "",
        "## 入力値候補",
        "",
        "| ID | 対象 | 値 | 種別 | 関連カバレッジ | 根拠 | レビュー要否 |",
        "|---|---|---|---|---|---|---|",
    ]
    for candidate in payload["input_candidates"]:
        lines.append(
            f"| {candidate['candidate_id']} | {candidate['target_name']} | {candidate['value_expression']} | {candidate['value_kind']} | "
            f"{', '.join(candidate['related_coverage_ids'])} | `{candidate['evidence']}` | {'はい' if candidate['review_required'] else 'いいえ'} |"
        )
    lines.extend(["", "## 同値クラス", "", "| ID | 対象 | クラス | 代表値 | カバレッジ | レビュー要否 |", "|---|---|---|---|---|---|"])
    for item in payload["equivalence_classes"]:
        lines.append(f"| {item['class_id']} | {item['target_name']} | {item['class_name']} | {', '.join(item['representative_values'])} | {', '.join(item['related_coverage_ids'])} | {'はい' if item['review_required'] else 'いいえ'} |")
    lines.extend(["", "## 状態候補", "", "| ID | 変数 | スコープ | 値 | セットアップヒント | レビュー要否 |", "|---|---|---|---|---|---|"])
    for candidate in payload["state_candidates"]:
        lines.append(f"| {candidate['candidate_id']} | {candidate['variable_name']} | {candidate['scope']} | {candidate['value_expression']} | {candidate['setup_hint']} | {'はい' if candidate['review_required'] else 'いいえ'} |")
    lines.extend(["", "## スタブ戻り値候補", "", "| ID | 呼び出し | 値 | 目的 | カバレッジ | レビュー要否 |", "|---|---|---|---|---|---|"])
    for candidate in payload["stub_return_candidates"]:
        lines.append(f"| {candidate['candidate_id']} | {candidate['call_name']} | {candidate['value_expression']} | {candidate['purpose']} | {', '.join(candidate['related_coverage_ids'])} | {'はい' if candidate['review_required'] else 'いいえ'} |")
    lines.extend(["", "## 警告", ""])
    if payload["warnings"]:
        lines.extend(f"- {warning['code']}: {warning['message']}" for warning in payload["warnings"])
    else:
        lines.append("- なし")
    return "\n".join(lines) + "\n"
