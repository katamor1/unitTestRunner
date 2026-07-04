from __future__ import annotations

import json
from pathlib import Path

from unit_test_runner.harness.c90_writer import sha256_file, write_c_file

from .build_models import BuildProbeReport, BuildWorkspaceReport, WorkspaceFile


def write_build_reports(output_root: Path, workspace: BuildWorkspaceReport, probe: BuildProbeReport) -> dict[str, Path]:
    reports_dir = output_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    workspace_json = reports_dir / "build_workspace_report.json"
    workspace_md = reports_dir / "build_workspace_report.md"
    probe_json = reports_dir / "build_probe_report.json"
    probe_md = reports_dir / "build_probe_report.md"
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
        "# Build Workspace Report",
        "",
        "## Target",
        f"- Function: {report.function_name}",
        f"- Status: {report.status}",
        f"- Output Root: {report.output_root.as_posix()}",
        "",
        "## Compile Units",
        "| Source | Object | Required |",
        "|---|---|---|",
    ]
    for unit in report.compile_units:
        lines.append(f"| {unit.source_file.as_posix()} | {unit.object_file.as_posix()} | {'yes' if unit.required else 'no'} |")
    lines.extend(["", "## Include Dirs", "| Path | Source | Exists |", "|---|---|---|"])
    for item in report.include_dirs:
        lines.append(f"| {item.raw} | {item.source} | {'yes' if item.exists else 'no'} |")
    lines.extend(["", "## Diagnostics"])
    if report.diagnostics:
        for diagnostic in report.diagnostics:
            lines.append(f"- {diagnostic.code}: {diagnostic.message}")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def render_probe_markdown(report: BuildProbeReport) -> str:
    lines = [
        "# Build Probe Report",
        "",
        "## Status",
        f"- Executed: {'yes' if report.executed else 'no'}",
        f"- Status: {report.status}",
        f"- Exit Code: {report.exit_code if report.exit_code is not None else ''}",
        "",
        "## Missing Includes",
    ]
    if report.missing_includes:
        lines.extend(["| Include | Diagnostic |", "|---|---|"])
        for item in report.missing_includes:
            lines.append(f"| {item.include_name} | {item.diagnostic_raw} |")
    else:
        lines.append("- None")
    lines.extend(["", "## Unresolved Symbols"])
    if report.unresolved_symbols:
        lines.extend(["| Symbol | Related Call | Stub Candidate |", "|---|---|---|"])
        for item in report.unresolved_symbols:
            lines.append(f"| {item.symbol_name} | {item.related_call_name or ''} | {'yes' if item.stub_candidate else 'no'} |")
    else:
        lines.append("- None")
    lines.extend(["", "## PCH Issues"])
    lines.extend([f"- {item.issue_kind}: {item.diagnostic_raw}" for item in report.pch_issues] or ["- None"])
    lines.extend(["", "## VC6 Compatibility Issues"])
    lines.extend([f"- {item.issue_kind}: {item.diagnostic_raw}" for item in report.vc6_compatibility_issues] or ["- None"])
    return "\n".join(lines) + "\n"


def _record_build_file(output_root: Path, report: BuildWorkspaceReport, path: Path, kind: str) -> None:
    relative = path.relative_to(output_root)
    if any(item.workspace_path == relative for item in report.generated_build_files):
        return
    report.generated_build_files.append(WorkspaceFile(relative, kind, sha256=sha256_file(path), generated=True, required=True, exists=path.exists()))
