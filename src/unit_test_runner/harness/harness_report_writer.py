from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from unit_test_runner.reports.japanese import ja_label, ja_text, md_cell, md_label_cell

from .c90_writer import sha256_file
from .harness_models import GeneratedFile, HarnessSkeletonReport


def write_harness_report(output_root: Path, report: HarnessSkeletonReport) -> dict[str, Path]:
    reports_dir = output_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "harness_skeleton_report.json"
    markdown_path = reports_dir / "harness_skeleton_report.md"
    payload = report.to_dict()
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_harness_markdown(report), encoding="utf-8")
    _record_report_file(output_root, report, json_path, "report", hash_file=False)
    _record_report_file(output_root, report, markdown_path, "report")
    json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def render_harness_markdown(report: HarnessSkeletonReport) -> str:
    payload = _localized_report_payload(report)
    lines = [
        "# ハーネスひな形レポート",
        "",
        "## 対象",
        f"- 関数: {report.function_name}",
        f"- 状態: {ja_label(report.status)}",
        f"- 出力ルート: {report.output_root.as_posix()}",
        "",
        "## 生成ファイル",
        "| ファイル | 種別 | レビュー要否 |",
        "|---|---|---|",
    ]
    for item in payload["generated_files"]:
        review = "はい" if item["review_required"] else "いいえ"
        lines.append(f"| {item['path']} | {md_label_cell(item['file_kind'])} | {review} |")
    lines.extend(["", "## スタブひな形", "| スタブ | 元関数 | 機能 | 関連呼び出し |", "|---|---|---|---|"])
    for item in payload["stub_skeletons"]:
        capabilities = ", ".join(md_label_cell(value) for value in item["capabilities"])
        lines.append(
            f"| {item['stub_name']} | {item['original_function_name']} | {capabilities} | {', '.join(item['related_call_ids'])} |"
        )
    lines.extend(["", "## 依存関係ディスパッチ", "| 呼び出し先 | ディスパッチャ | スタブ実体 | 既定モード | real可否 |", "|---|---|---|---|---|"])
    if payload.get("dependency_dispatches"):
        for item in payload["dependency_dispatches"]:
            lines.append(
                f"| {item['callee']} | {item['dispatcher_name']} | {item['stub_invoke_name']} | "
                f"{item['default_mode']} | {'はい' if item['real_available'] else 'いいえ'} |"
            )
    else:
        lines.append("| なし | | | | |")
    lines.extend(["", "## テストひな形", "| テストケース | 関数 | プレースホルダ数 |", "|---|---|---|"])
    for item in payload["test_skeletons"]:
        lines.append(f"| {item['test_case_id']} | {item['generated_function_name']} | {item['placeholder_count']} |")
    lines.extend(["", "## 未解決プレースホルダ"])
    if report.unresolved_placeholders:
        lines.extend(["| 種別 | 名前 | 関連テストケース | 理由 |", "|---|---|---|---|"])
        for item in payload["unresolved_placeholders"]:
            lines.append(f"| {md_label_cell(item['placeholder_kind'])} | {item['name']} | {item['related_test_case_id'] or ''} | {md_cell(item['reason'])} |")
    else:
        lines.append("- なし")
    lines.extend(["", "## ビルドヒント"])
    if report.build_hints:
        lines.extend(["| 種別 | メッセージ | 重要度 |", "|---|---|---|"])
        for item in payload["build_hints"]:
            lines.append(f"| {md_label_cell(item['hint_kind'])} | {md_cell(item['message'])} | {md_label_cell(item['severity'])} |")
    else:
        lines.append("- なし")
    lines.extend(["", "## 警告"])
    if report.warnings:
        for warning in payload["warnings"]:
            lines.append(f"- {md_label_cell(warning['code'])}: {md_cell(warning['message'])}")
    else:
        lines.append("- なし")
    return "\n".join(lines) + "\n"


def _localized_report_payload(report: HarnessSkeletonReport) -> dict[str, Any]:
    payload = report.to_dict()
    for item in payload.get("unresolved_placeholders", []):
        item["placeholder_kind"] = ja_label(item.get("placeholder_kind"))
        item["reason"] = ja_text(item.get("reason"))
        item["suggested_action"] = ja_text(item.get("suggested_action"))
    for item in payload.get("warnings", []):
        item["message"] = ja_text(item.get("message"))
    for item in payload.get("build_hints", []):
        item["hint_kind"] = ja_label(item.get("hint_kind"))
        item["message"] = ja_text(item.get("message"))
        item["severity"] = ja_label(item.get("severity"))
    return payload


def _record_report_file(
    output_root: Path,
    report: HarnessSkeletonReport,
    path: Path,
    kind: str,
    *,
    hash_file: bool = True,
) -> None:
    relative = path.relative_to(output_root)
    digest = sha256_file(path) if hash_file else None
    for item in report.generated_files:
        if item.path == relative:
            item.sha256 = digest
            return
    report.generated_files.append(
        GeneratedFile(
            path=relative,
            file_kind=kind,
            generated_from=["harness_skeleton_report"],
            sha256=digest,
            overwrite=True,
            review_required=False,
        )
    )
