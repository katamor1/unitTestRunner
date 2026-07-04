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
        "# Harness Skeleton Report",
        "",
        "## Target",
        f"- Function: {report.function_name}",
        f"- Status: {report.status}",
        f"- Output Root: {report.output_root.as_posix()}",
        "",
        "## Generated Files",
        "| File | Kind | Review Required |",
        "|---|---|---|",
    ]
    for item in payload["generated_files"]:
        review = "yes" if item["review_required"] else "no"
        lines.append(f"| {item['path']} | {item['file_kind']} | {review} |")
    lines.extend(["", "## Stub Skeletons", "| Stub | Original Function | Capabilities | Related Calls |", "|---|---|---|---|"])
    for item in payload["stub_skeletons"]:
        lines.append(
            f"| {item['stub_name']} | {item['original_function_name']} | {', '.join(item['capabilities'])} | {', '.join(item['related_call_ids'])} |"
        )
    lines.extend(["", "## Test Skeletons", "| Test Case | Function | Placeholders |", "|---|---|---|"])
    for item in payload["test_skeletons"]:
        lines.append(f"| {item['test_case_id']} | {item['generated_function_name']} | {item['placeholder_count']} |")
    lines.extend(["", "## Unresolved Placeholders"])
    if report.unresolved_placeholders:
        lines.extend(["| Kind | Name | Related Test Case | Reason |", "|---|---|---|---|"])
        for item in payload["unresolved_placeholders"]:
            lines.append(f"| {item['placeholder_kind']} | {item['name']} | {item['related_test_case_id'] or ''} | {item['reason']} |")
    else:
        lines.append("- None")
    lines.extend(["", "## Build Hints"])
    if report.build_hints:
        lines.extend(["| Kind | Message | Severity |", "|---|---|---|"])
        for item in payload["build_hints"]:
            lines.append(f"| {item['hint_kind']} | {item['message']} | {item['severity']} |")
    else:
        lines.append("- None")
    lines.extend(["", "## Warnings"])
    if report.warnings:
        for warning in payload["warnings"]:
            lines.append(f"- {warning['code']}: {warning['message']}")
    else:
        lines.append("- None")
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
