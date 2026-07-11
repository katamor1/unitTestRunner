from __future__ import annotations

import json
from pathlib import Path

from .models import DependencyPolicyReport


def write_dependency_policy(output_root: Path | str, report: DependencyPolicyReport) -> dict[str, Path]:
    reports = Path(output_root) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    json_path = reports / "dependency_policy.json"
    markdown_path = reports / "dependency_policy.md"
    payload = report.to_dict()
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_dependency_policy_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def render_dependency_policy_markdown(payload: dict) -> str:
    function = payload.get("function", {})
    lines = [
        "# 依存関係ポリシー",
        "",
        "## 対象",
        f"- ソース: {payload.get('source', {}).get('path', '')}",
        f"- 関数: {function.get('name', '')}",
        f"- 状態: {function.get('status', '')}",
        "",
        "## 呼び出し先",
        "",
        "| 呼び出し先 | 設定 | 解決結果 | シグネチャ | 実装 | レビュー |",
        "|---|---|---|---|---|---|",
    ]
    for item in payload.get("dependencies", []):
        signature = item.get("signature", {})
        lines.append(
            f"| {item.get('callee', '')} | {item.get('configured_mode', '')} | {item.get('resolved_mode', '')} | "
            f"{signature.get('resolution', '')} | {item.get('implementation_source') or ''} | {item.get('review_status', '')} |"
        )
        evidence = item.get("evidence", [])
        if evidence:
            lines.append("")
            lines.append(f"### {item.get('callee', '')} の判定根拠")
            for reason in evidence:
                lines.append(f"- {reason.get('kind', '')}: {reason.get('detail', '')} ({reason.get('source', '')}, weight={reason.get('weight', 0)})")
        conflicts = signature.get("conflicts", [])
        if conflicts:
            lines.append("")
            lines.append(f"### {item.get('callee', '')} のシグネチャ競合")
            lines.extend(f"- {conflict}" for conflict in conflicts)
    lines.extend([
        "",
        "## 外部オブジェクト",
        "",
        "| シンボル | 型 | 設定 | 解決結果 | 宣言 | 定義 | レビュー |",
        "|---|---|---|---|---|---|---|",
    ])
    for item in payload.get("external_objects", []):
        lines.append(
            f"| {item.get('symbol', '')} | {item.get('type_raw', '')} | {item.get('configured_mode', '')} | "
            f"{item.get('resolved_mode', '')} | {item.get('declaration_header') or ''} | {item.get('definition_source') or ''} | {item.get('review_status', '')} |"
        )
    lines.extend(["", "## 警告"])
    warnings = payload.get("warnings", [])
    lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append("- なし")
    return "\n".join(lines) + "\n"
