from __future__ import annotations

import json
from pathlib import Path

from unit_test_runner.harness.c90_writer import sha256_file, write_c_file
from unit_test_runner.reports.japanese import ja_label, md_cell, md_label_cell
from unit_test_runner.vc6.debug_workspace_response import vc6_cpp_options_path
from unit_test_runner.vc6.debug_workspace_writer import write_vc6_debug_project

from .build_models import BuildDiagnostic, BuildProbeReport, BuildWorkspaceReport, WorkspaceFile


def write_build_reports(output_root: Path, workspace: BuildWorkspaceReport, probe: BuildProbeReport) -> dict[str, Path]:
    reports_dir = output_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    workspace_json = reports_dir / "build_workspace_report.json"
    workspace_md = reports_dir / "build_workspace_report.md"
    probe_json = reports_dir / "build_probe_report.json"
    probe_md = reports_dir / "build_probe_report.md"
    _write_debug_dsp(output_root, workspace)
    workspace_json.write_text(json.dumps(workspace.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    workspace_md.write_text(render_workspace_markdown(workspace), encoding="utf-8")
    probe_json.write_text(json.dumps(probe.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    probe_md.write_text(render_probe_markdown(probe), encoding="utf-8")
    for path, kind in [(workspace_json, "report"), (workspace_md, "report"), (probe_json, "report"), (probe_md, "report")]:
        _record_build_file(output_root, workspace, path, kind)
    workspace_json.write_text(json.dumps(workspace.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"workspace_json": workspace_json, "workspace_markdown": workspace_md, "probe_json": probe_json, "probe_markdown": probe_md}


def write_build_text(path: Path, text: str) -> None:
    write_c_file(path, text, overwrite=True)


def render_workspace_markdown(report: BuildWorkspaceReport) -> str:
    lines = [
        "# ビルドワークスペースレポート",
        "",
        "## 対象",
        f"- 関数: {report.function_name}",
        f"- 状態: {ja_label(report.status)}",
        f"- 出力ルート: {report.output_root.as_posix()}",
        "",
        "## コンパイル単位",
        "| ソース | オブジェクト | 必須 |",
        "|---|---|---|",
    ]
    for unit in report.compile_units:
        lines.append(f"| {unit.source_file.as_posix()} | {unit.object_file.as_posix()} | {'はい' if unit.required else 'いいえ'} |")
    lines.extend(["", "## リンクライブラリ", "| 順序 | ライブラリ | 根拠 | プロジェクト | 解析状態 |", "|---|---|---|---|---|"])
    if report.link_libraries:
        for item in report.link_libraries:
            lines.append(
                f"| {item.link_order} | {md_cell(item.path.as_posix())} | {md_label_cell(item.source)} | "
                f"{md_cell(item.project_name or '')} | {md_label_cell(item.scan_status or '')} |"
            )
    else:
        lines.append("|  | なし |  |  |  |")
    lines.extend(["", "## library path"])
    lines.extend([f"- `{item.as_posix()}`" for item in report.library_dirs] or ["- なし"])
    lines.extend(["", "## includeディレクトリ", "| パス | 根拠 | 存在 |", "|---|---|---|"])
    for item in report.include_dirs:
        lines.append(f"| {item.raw} | {md_label_cell(item.source)} | {'はい' if item.exists else 'いいえ'} |")
    lines.extend(["", "## 診断"])
    if report.diagnostics:
        for diagnostic in report.diagnostics:
            lines.append(f"- {md_label_cell(diagnostic.code)}: {md_cell(diagnostic.message)}")
    else:
        lines.append("- なし")
    return "\n".join(lines) + "\n"


def render_probe_markdown(report: BuildProbeReport) -> str:
    lines = [
        "# ビルドプローブレポート",
        "",
        "## 状態",
        f"- 実行済み: {'はい' if report.executed else 'いいえ'}",
        f"- 状態: {ja_label(report.status)}",
        f"- 終了コード: {report.exit_code if report.exit_code is not None else ''}",
        "",
        "## 不足include",
    ]
    if report.missing_includes:
        lines.extend(["| include | 診断 |", "|---|---|"])
        for item in report.missing_includes:
            lines.append(f"| {item.include_name} | {md_cell(item.diagnostic_raw)} |")
    else:
        lines.append("- なし")
    lines.extend(["", "## 未解決シンボル"])
    if report.unresolved_symbols:
        lines.extend(["| シンボル | 関連呼び出し | スタブ候補 |", "|---|---|---|"])
        for item in report.unresolved_symbols:
            lines.append(f"| {item.symbol_name} | {item.related_call_name or ''} | {'はい' if item.stub_candidate else 'いいえ'} |")
    else:
        lines.append("- なし")
    lines.extend(["", "## PCH課題"])
    lines.extend([f"- {md_label_cell(item.issue_kind)}: {md_cell(item.diagnostic_raw)}" for item in report.pch_issues] or ["- なし"])
    lines.extend(["", "## VC6互換性課題"])
    lines.extend([f"- {md_label_cell(item.issue_kind)}: {md_cell(item.diagnostic_raw)}" for item in report.vc6_compatibility_issues] or ["- なし"])
    lines.extend(["", "## 診断"])
    if report.diagnostics:
        for diagnostic in report.diagnostics:
            lines.append(f"- {md_label_cell(diagnostic.code)}: {md_cell(diagnostic.message)}")
    else:
        lines.append("- なし")
    return "\n".join(lines) + "\n"


def _write_debug_dsp(output_root: Path, report: BuildWorkspaceReport) -> None:
    try:
        dsp_path = write_vc6_debug_project(output_root, report)
    except Exception as exc:  # pragma: no cover - defensive report generation path
        report.diagnostics.append(BuildDiagnostic("vc6_debug_dsp_generation_failed", "warning", f"VC6 debug DSP generation failed: {exc}", None, None, None))
        return
    _record_build_file(output_root, report, dsp_path, "vc6_debug_dsp")
    options_path = vc6_cpp_options_path(dsp_path)
    if options_path.exists():
        _record_build_file(output_root, report, options_path, "vc6_cpp_response")


def _record_build_file(output_root: Path, report: BuildWorkspaceReport, path: Path, kind: str) -> None:
    relative = path.relative_to(output_root)
    if any(item.workspace_path == relative for item in report.generated_build_files):
        return
    report.generated_build_files.append(WorkspaceFile(relative, kind, sha256=sha256_file(path), generated=True, required=True, exists=path.exists()))
