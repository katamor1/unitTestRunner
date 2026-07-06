from __future__ import annotations

import json
from pathlib import Path

from .c90_writer import sha256_file, write_text_file
from .harness_models import GeneratedFile, HarnessSkeletonReport


def write_harness_report(output_root: Path, report: HarnessSkeletonReport) -> dict[str, Path]:
    reports_dir = output_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "harness_skeleton_report.json"
    markdown_path = reports_dir / "harness_skeleton_report.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_harness_markdown(report), encoding="utf-8")
    _record_report_file(output_root, report, json_path, "report")
    _record_report_file(output_root, report, markdown_path, "report")
    json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def render_harness_markdown(report: HarnessSkeletonReport) -> str:
    payload = report.to_dict()
    lines = [
        "# ハーネスひな形レポート",
        "",
        "## 対象",
        f"- 関数: {report.function_name}",
        f"- 状態: {report.status}",
        f"- 出力ルート: {report.output_root.as_posix()}",
        "",
        "## 生成ファイル",
        "| ファイル | 種別 | レビュー要否 |",
        "|---|---|---|",
    ]
    for item in payload["generated_files"]:
        review = "はい" if item["review_required"] else "いいえ"
        lines.append(f"| {item['path']} | {item['file_kind']} | {review} |")
    lines.extend(["", "## スタブひな形", "| スタブ | 元関数 | 機能 | 関連呼び出し |", "|---|---|---|---|"])
    for item in payload["stub_skeletons"]:
        lines.append(
            f"| {item['stub_name']} | {item['original_function_name']} | {', '.join(item['capabilities'])} | {', '.join(item['related_call_ids'])} |"
        )
    lines.extend(["", "## テストひな形", "| テストケース | 関数 | プレースホルダ数 |", "|---|---|---|"])
    for item in payload["test_skeletons"]:
        lines.append(f"| {item['test_case_id']} | {item['generated_function_name']} | {item['placeholder_count']} |")
    lines.extend(["", "## 未解決プレースホルダ"])
    if report.unresolved_placeholders:
        lines.extend(["| 種別 | 名前 | 関連テストケース | 理由 |", "|---|---|---|---|"])
        for item in payload["unresolved_placeholders"]:
            lines.append(f"| {item['placeholder_kind']} | {item['name']} | {item['related_test_case_id'] or ''} | {item['reason']} |")
    else:
        lines.append("- なし")
    lines.extend(["", "## ビルドヒント"])
    if report.build_hints:
        lines.extend(["| 種別 | メッセージ | 重要度 |", "|---|---|---|"])
        for item in payload["build_hints"]:
            lines.append(f"| {item['hint_kind']} | {item['message']} | {item['severity']} |")
    else:
        lines.append("- なし")
    lines.extend(["", "## 警告"])
    if report.warnings:
        for warning in payload["warnings"]:
            lines.append(f"- {warning['code']}: {warning['message']}")
    else:
        lines.append("- なし")
    return "\n".join(lines) + "\n"


def _record_report_file(output_root: Path, report: HarnessSkeletonReport, path: Path, kind: str) -> None:
    relative = path.relative_to(output_root)
    if any(item.path == relative for item in report.generated_files):
        return
    report.generated_files.append(
        GeneratedFile(
            path=relative,
            file_kind=kind,
            generated_from=["harness_skeleton_report"],
            sha256=sha256_file(path),
            overwrite=True,
            review_required=False,
        )
    )
