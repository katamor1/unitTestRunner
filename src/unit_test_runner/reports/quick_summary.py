from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_quick_summary(out_dir: Path | str, dossier: dict[str, Any], phase: str, status: str) -> dict[str, Path]:
    root = Path(out_dir)
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    payload = quick_summary_payload(root, dossier, phase, status)
    json_path = reports_dir / "quick_summary.json"
    markdown_path = reports_dir / "quick_summary.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_quick_summary_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def quick_summary_payload(out_dir: Path, dossier: dict[str, Any], phase: str, status: str) -> dict[str, Any]:
    target = dossier.get("target", {}) if isinstance(dossier.get("target"), dict) else {}
    diagnostics = dossier.get("diagnostics", []) if isinstance(dossier.get("diagnostics"), list) else []
    return {
        "schema_version": "0.1",
        "status": status,
        "phase": phase,
        "output_root": str(out_dir),
        "target": {
            "source": target.get("source"),
            "function": target.get("function"),
            "configuration": target.get("configuration"),
            "project": target.get("project"),
        },
        "steps": _step_summaries(dossier),
        "diagnostics": {
            "count": len(diagnostics),
            "items": diagnostics[:20],
        },
        "reports": _report_paths(out_dir, dossier),
    }


def render_quick_summary_markdown(payload: dict[str, Any]) -> str:
    target = payload.get("target", {}) if isinstance(payload.get("target"), dict) else {}
    diagnostics = payload.get("diagnostics", {}) if isinstance(payload.get("diagnostics"), dict) else {}
    lines = [
        "# Quick Check Summary",
        "",
        "## 対象",
        f"- 関数: `{_text(target.get('function'))}`",
        f"- ソース: `{_text(target.get('source'))}`",
        f"- 構成: `{_text(target.get('configuration'))}`",
        f"- プロジェクト: `{_text(target.get('project'))}`",
        "",
        "## 結果",
        f"- フェーズ: `{_text(payload.get('phase'))}`",
        f"- ステータス: `{_text(payload.get('status'))}`",
        f"- 出力workspace: `{_text(payload.get('output_root'))}`",
        "",
        "## 生成ステップ",
        "| ステップ | 状態 | レポート |",
        "|---|---|---|",
    ]
    for step in payload.get("steps", []):
        if not isinstance(step, dict):
            continue
        reports = step.get("reports") if isinstance(step.get("reports"), dict) else {}
        report_text = "<br>".join(f"`{key}`: `{value}`" for key, value in reports.items()) if reports else ""
        lines.append(f"| {_text(step.get('label'))} | {_text(step.get('status'))} | {report_text} |")
    lines.extend(["", "## 診断"])
    count = diagnostics.get("count", 0)
    if count:
        lines.append(f"- 診断件数: {count}")
        for item in diagnostics.get("items", []):
            if isinstance(item, dict):
                message = item.get("message") or item.get("code") or item
            else:
                message = item
            lines.append(f"  - {_text(message)}")
    else:
        lines.append("- なし")
    lines.append("")
    return "\n".join(lines)


def _step_summaries(dossier: dict[str, Any]) -> list[dict[str, Any]]:
    definitions = [
        ("source_digest", "ソース解析", {"markdown": "markdown", "json": "json"}),
        ("function_signature", "関数シグネチャ", {"markdown": "markdown", "json": "json"}),
        ("global_access", "グローバルアクセス", {"markdown": "markdown", "json": "json"}),
        ("call_report", "呼び出し解析", {"markdown": "markdown", "json": "json"}),
        ("coverage_design", "カバレッジ設計", {"markdown": "markdown", "json": "json"}),
        ("boundary_equivalence_candidates", "境界値・同値クラス", {"markdown": "markdown", "json": "json"}),
        ("test_case_design", "テストケース設計", {"markdown": "markdown", "json": "json", "csv": "csv"}),
        ("harness_skeleton", "ハーネス生成", {"markdown": "markdown", "json": "json"}),
        ("build_workspace", "ビルドworkspace", {"markdown": "markdown", "json": "json"}),
        ("build_probe", "ビルドプローブ", {"markdown": "markdown", "json": "json"}),
        ("build_completion", "ビルド補完解析", {"plan_markdown": "plan_markdown", "iteration_markdown": "iteration_markdown"}),
        ("test_execution", "テスト実行", {"markdown": "markdown", "json": "json"}),
        ("evidence", "エビデンス", {"package_markdown": "package_markdown", "manifest_json": "manifest_json"}),
    ]
    steps: list[dict[str, Any]] = []
    for key, label, report_keys in definitions:
        value = dossier.get(key)
        if not isinstance(value, dict):
            steps.append({"id": key, "label": label, "status": "not_run", "reports": {}})
            continue
        reports = {name: value.get(source_key) for name, source_key in report_keys.items() if value.get(source_key)}
        steps.append({"id": key, "label": label, "status": value.get("status", "generated"), "reports": reports})
    return steps


def _report_paths(out_dir: Path, dossier: dict[str, Any]) -> dict[str, str]:
    reports = out_dir / "reports"
    result = {
        "quick_summary_json": str(reports / "quick_summary.json"),
        "quick_summary_md": str(reports / "quick_summary.md"),
        "function_dossier_json": str(reports / "function_dossier.json"),
        "function_dossier_md": str(reports / "function_dossier.md"),
    }
    mapping = {
        "test_case_design": {"test_case_design_json": "json", "test_case_design_md": "markdown", "test_case_design_csv": "csv"},
        "function_signature": {"function_signature_json": "json"},
        "global_access": {"global_access_json": "json"},
        "call_report": {"call_report_json": "json"},
        "harness_skeleton": {"harness_skeleton_report_json": "json", "harness_skeleton_report_md": "markdown"},
        "build_probe": {"build_probe_report_md": "markdown"},
        "test_execution": {"test_execution_report_md": "markdown"},
        "evidence": {"evidence_package_md": "package_markdown"},
    }
    for section, keys in mapping.items():
        value = dossier.get(section)
        if not isinstance(value, dict):
            continue
        for report_key, source_key in keys.items():
            source = value.get(source_key)
            if source:
                result[report_key] = str(source)
    return result


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|")
