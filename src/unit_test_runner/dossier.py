from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

from .c_analyzer import analyze_function
from .path_utils import normalize_relative
from .test_design import generate_test_design
from .vc6 import select_project_context


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _copy_source_tree(workspace_root: Path, source: str, out_dir: Path, project: dict[str, Any]) -> list[str]:
    copied = []
    targets = [source]
    targets.extend(project.get("headers", []))
    for relative in targets:
        src = workspace_root / relative
        if not src.exists():
            continue
        dest = out_dir / "extracted" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(relative)
    return copied


def _markdown_list(items: list[Any], formatter=str) -> str:
    if not items:
        return "- None\n"
    return "".join(f"- {formatter(item)}\n" for item in items)


def _write_markdown_reports(out_dir: Path, dossier: dict[str, Any], copied_files: list[str]) -> None:
    reports = out_dir / "reports"
    function = dossier["function"]
    design = dossier["test_design"]
    md = [
        f"# Function Dossier: {function['name']}",
        "",
        "## Target",
        f"- Source: `{dossier['target']['source']}`",
        f"- Function: `{dossier['target']['function']}`",
        f"- Configuration: `{dossier['target']['configuration']}`",
        "",
        "## Build Context",
        _markdown_list(dossier["build_context"].get("defines", []), lambda item: f"Define: `{item}`"),
        _markdown_list(dossier["build_context"].get("include_dirs", []), lambda item: f"Include: `{item}`"),
        "## Function",
        f"- Return type: `{function['return_type']}`",
        _markdown_list(function.get("parameters", []), lambda item: f"`{item['type']} {item['name']}`"),
        "## Globals",
        _markdown_list(function.get("globals_read", []), lambda item: f"Read: `{item}`"),
        _markdown_list(function.get("globals_written", []), lambda item: f"Write: `{item}`"),
        "## Calls",
        _markdown_list(function.get("external_calls", []), lambda item: f"`{item['name']}` at line {item['line']}"),
        "## Branches",
        _markdown_list(function.get("branches", []), lambda item: f"{item['id']}: `{item['condition']}`"),
        "## Stub Candidates",
        _markdown_list(design.get("stub_candidates", []), lambda item: f"`{item['name']}`"),
    ]
    (reports / "function_dossier.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (reports / "project_membership.md").write_text(
        "# Project Membership\n\n" + _markdown_list(dossier["project_membership"], lambda item: f"{item['project_name']} / {item['configuration']}"),
        encoding="utf-8",
    )
    _write_json(reports / "build_context.json", dossier["build_context"])
    (reports / "source_file_set.md").write_text("# Source File Set\n\n" + _markdown_list(copied_files, lambda item: f"`{item}`"), encoding="utf-8")
    (reports / "global_access_report.md").write_text(
        "# Global Access\n\n## Read\n" + _markdown_list(function.get("globals_read", [])) + "\n## Written\n" + _markdown_list(function.get("globals_written", [])),
        encoding="utf-8",
    )
    (reports / "call_report.md").write_text(
        "# Calls\n\n" + _markdown_list(function.get("external_calls", []), lambda item: f"`{item['name']}` at line {item['line']}"),
        encoding="utf-8",
    )
    (reports / "branch_condition_report.md").write_text(
        "# Branches and Conditions\n\n" + _markdown_list(function.get("branches", []), lambda item: f"{item['id']}: `{item['condition']}`"),
        encoding="utf-8",
    )
    (reports / "coverage_design.md").write_text(
        "# Coverage Design\n\n"
        + _markdown_list(design.get("branch_coverage_items", []), lambda item: f"{item['id']}: {item['description']}")
        + "\n"
        + _markdown_list(design.get("condition_coverage_items", []), lambda item: item["description"]),
        encoding="utf-8",
    )
    (reports / "boundary_equivalence_candidates.md").write_text(
        "# Boundary and Equivalence Candidates\n\n## Boundary\n"
        + _markdown_list(design.get("boundary_value_candidates", []), lambda item: item["value"])
        + "\n## Equivalence\n"
        + _markdown_list(design.get("equivalence_class_candidates", []), lambda item: item["value"]),
        encoding="utf-8",
    )
    (reports / "stub_candidates.md").write_text(
        "# Stub Candidates\n\n" + _markdown_list(design.get("stub_candidates", []), lambda item: f"`{item['name']}`"),
        encoding="utf-8",
    )


def write_test_case_draft(path: Path, dossier: dict[str, Any]) -> None:
    rows = []
    function_name = dossier["target"]["function"]
    for index, branch in enumerate(dossier["test_design"].get("branch_coverage_items", []), start=1):
        rows.append(
            {
                "id": f"TC_{function_name}_{index:03d}",
                "function": function_name,
                "purpose": branch["description"],
                "preconditions": "review required",
                "inputs": "review required",
                "global_initial_values": "review required",
                "stub_settings": "review required",
                "expected_return": "review required",
                "expected_globals": "review required",
                "expected_external_calls": "review required",
                "coverage": branch["id"],
                "judgement": "manual review",
                "review_state": "required",
            }
        )
    if not rows:
        rows.append(
            {
                "id": f"TC_{function_name}_001",
                "function": function_name,
                "purpose": "Baseline function invocation",
                "preconditions": "review required",
                "inputs": "review required",
                "global_initial_values": "review required",
                "stub_settings": "review required",
                "expected_return": "review required",
                "expected_globals": "review required",
                "expected_external_calls": "review required",
                "coverage": "review required",
                "judgement": "manual review",
                "review_state": "required",
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def analyze_function_workflow(
    workspace_root: Path | str,
    dsw_path: Path | str,
    source: str,
    function_name: str,
    configuration: str,
    out_dir: Path | str,
    project_name: str | None = None,
) -> dict[str, Any]:
    workspace_root = Path(workspace_root).resolve()
    out_dir = Path(out_dir).resolve()
    for child in ("input", "extracted", "generated", "reports"):
        (out_dir / child).mkdir(parents=True, exist_ok=True)
    project, config, memberships = select_project_context(workspace_root, dsw_path, source, configuration, project_name)
    source_path = (workspace_root / source).resolve()
    function = analyze_function(source_path, function_name)
    test_design = generate_test_design(function)
    copied_files = _copy_source_tree(workspace_root, source.replace("\\", "/"), out_dir, project)
    request = {
        "workspace": str(workspace_root),
        "dsw": normalize_relative(Path(dsw_path).resolve(), workspace_root),
        "source": source.replace("\\", "/"),
        "function": function_name,
        "configuration": configuration,
        "project": project_name,
        "out": str(out_dir),
    }
    _write_json(out_dir / "input" / "request.json", request)
    dossier = {
        "schema_version": "0.1",
        "target": {
            "source": source.replace("\\", "/"),
            "function": function_name,
            "configuration": configuration,
            "project": project["project_name"],
        },
        "project_membership": memberships,
        "build_context": {
            "defines": config["defines"],
            "include_dirs": config["include_dirs"],
            "compiler_options": config["compiler_options"],
            "forced_includes": config["forced_includes"],
            "precompiled_header": config["precompiled_header"],
            "unresolved_macros": config["unresolved_macros"],
        },
        "function": function,
        "test_design": test_design,
        "diagnostics": config.get("diagnostics", []) + function.get("diagnostics", []),
    }
    _write_json(out_dir / "reports" / "function_dossier.json", dossier)
    _write_markdown_reports(out_dir, dossier, copied_files)
    write_test_case_draft(out_dir / "reports" / "test_case_draft.csv", dossier)
    _write_json(out_dir / "generated" / "prompt_pack.json", {"function_dossier": dossier})
    return dossier


def generate_test_draft_from_dossier(dossier_path: Path | str) -> Path:
    dossier_path = Path(dossier_path)
    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    target = dossier_path.with_name("test_case_draft.csv")
    write_test_case_draft(target, dossier)
    return target
