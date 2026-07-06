from __future__ import annotations

import json
from pathlib import Path

from .global_access_models import GlobalAccessReport


def write_global_access(out_dir: Path | str, report: GlobalAccessReport) -> dict[str, Path]:
    reports = Path(out_dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    json_path = reports / "global_access.json"
    markdown_path = reports / "global_access.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_global_access_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def render_global_access_markdown(payload: dict) -> str:
    function = payload["function"]
    lines = [
        "# グローバルアクセスレポート",
        "",
        "## 対象",
        f"- ソース: {payload['source']['path']}",
        f"- 関数: {function['name']}",
        f"- 状態: {function['status']}",
        "",
        "## ファイルスコープ宣言",
        "",
        "| 名前 | スコープ | 型 | 信頼度 |",
        "|---|---|---|---|",
    ]
    for declaration in payload["file_scope_declarations"]:
        lines.append(f"| {declaration['name']} | {declaration['scope']} | {declaration['type_raw']} | {declaration['confidence']} |")
    lines.extend(["", "## グローバルアクセス", "", "| 名前 | スコープ | アクセス | 根拠 | 信頼度 |", "|---|---|---|---|---|"])
    for access in payload["global_accesses"]:
        lines.append(f"| {access['name']} | {access['scope']} | {access['access_kind']} | `{access['evidence']}` | {access['confidence']} |")
    lines.extend(["", "## パラメータ副作用候補", "", "| パラメータ | アクセス | 根拠 | 信頼度 |", "|---|---|---|---|"])
    for effect in payload["side_effect_candidates"]:
        lines.append(f"| {effect['name'] or ''} | {effect['kind']} | `{effect['evidence']}` | {effect['confidence']} |")
    lines.extend(["", "## 警告", ""])
    if payload["warnings"]:
        lines.extend(f"- {warning['code']}: {warning['message']}" for warning in payload["warnings"])
    else:
        lines.append("- なし")
    return "\n".join(lines) + "\n"
