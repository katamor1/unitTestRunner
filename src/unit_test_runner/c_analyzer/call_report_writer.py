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
        "# 呼び出し解析レポート",
        "",
        "## 対象",
        f"- ソース: {payload['source']['path']}",
        f"- 関数: {function['name']}",
        f"- 状態: {function['status']}",
        "",
        "## 呼び出し",
        "",
        "| ID | 名前 | 対象種別 | 戻り値の使われ方 | 根拠 | 信頼度 |",
        "|---|---|---|---|---|---|",
    ]
    for call in payload["calls"]:
        lines.append(f"| {call['call_id']} | {call['name']} | {call['target_kind']} | {call['return_usage']['usage_kind']} | `{call['evidence']}` | {call['confidence']} |")
    lines.extend(["", "## スタブ候補", "", "| 名前 | 理由 | 戻り値制御 | 引数記録 | 副作用制御 | タグ |", "|---|---|---|---|---|---|"])
    for candidate in payload["stub_candidates"]:
        lines.append(
            f"| {candidate['name']} | {candidate['reason']} | {'はい' if candidate['return_value_control_needed'] else 'いいえ'} | "
            f"{'はい' if candidate['argument_capture_needed'] else 'いいえ'} | {'はい' if candidate['side_effect_control_needed'] else 'いいえ'} | {', '.join(candidate['tags'])} |"
        )
    lines.extend(["", "## 副作用候補", "", "| 呼び出し | 種別 | 根拠 | 信頼度 |", "|---|---|---|---|"])
    for candidate in payload["side_effect_candidates"]:
        lines.append(f"| {candidate['call_name']} | {candidate['kind']} | `{candidate['evidence']}` | {candidate['confidence']} |")
    lines.extend(["", "## 警告", ""])
    if payload["warnings"]:
        lines.extend(f"- {warning['code']}: {warning['message']}" for warning in payload["warnings"])
    else:
        lines.append("- なし")
    return "\n".join(lines) + "\n"
