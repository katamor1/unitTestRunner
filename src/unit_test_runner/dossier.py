from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

from .build import generate_build_workspace
from .build_completion import analyze_build_errors_from_workspace
from .build_completion.completion_applier import apply_safe_completions as apply_completion_actions
from .build_completion.completion_models import BuildCompletionPolicy
from .build_completion.completion_report_writer import write_completion_reports
from .c_analyzer import analyze_function
from .c_analyzer.boundary_candidate_analyzer import generate_boundary_equivalence_candidates
from .c_analyzer.boundary_candidate_writer import write_boundary_equivalence_candidates
from .c_analyzer.call_analyzer import analyze_calls
from .c_analyzer.call_report_writer import write_call_report
from .c_analyzer.coverage_design_analyzer import analyze_coverage_design
from .c_analyzer.coverage_design_writer import write_coverage_design
from .c_analyzer.function_location_writer import write_function_location
from .c_analyzer.function_locator import locate_function
from .c_analyzer.global_access_analyzer import analyze_global_access
from .c_analyzer.global_access_writer import write_global_access
from .c_analyzer.signature_extractor import extract_signature
from .c_analyzer.signature_writer import write_function_signature
from .c_analyzer.source_digest import build_source_digest, write_source_digest
from .harness import generate_harness_skeleton
from .execution import prepare_test_execution_evidence
from .path_utils import normalize_relative
from .test_design import generate_test_design
from .test_design.test_case_draft_generator import generate_test_case_draft, generate_test_case_draft_from_payloads
from .test_design.test_case_draft_writer import write_test_case_draft_format, write_test_case_draft_report
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


def _source_relative_to_workspace(workspace_root: Path, source: str | Path) -> str:
    source_path = Path(source)
    if source_path.is_absolute():
        absolute = source_path.resolve()
    else:
        absolute = (workspace_root / str(source).replace("\\", "/")).resolve()
    try:
        return absolute.relative_to(workspace_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"source path is outside workspace: {absolute}") from exc


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
    apply_safe_completions: bool = False,
    run_tests: bool = False,
) -> dict[str, Any]:
    workspace_root = Path(workspace_root).resolve()
    source = _source_relative_to_workspace(workspace_root, source)
    out_dir = Path(out_dir).resolve()
    for child in ("input", "extracted", "generated", "reports", "intermediate"):
        (out_dir / child).mkdir(parents=True, exist_ok=True)
    project, config, memberships = select_project_context(workspace_root, dsw_path, source, configuration, project_name)
    source_path = (workspace_root / source).resolve()
    function = analyze_function(source_path, function_name)
    test_design = generate_test_design(function)
    copied_files = _copy_source_tree(workspace_root, source, out_dir, project)
    request = {
        "workspace": str(workspace_root),
        "dsw": normalize_relative(Path(dsw_path).resolve(), workspace_root),
        "source": source,
        "function": function_name,
        "configuration": configuration,
        "project": project_name,
        "out": str(out_dir),
    }
    _write_json(out_dir / "input" / "request.json", request)
    dossier = {
        "schema_version": "0.1",
        "target": {
            "source": source,
            "function": function_name,
            "configuration": configuration,
            "project": project["project_name"],
        },
        "project_membership": memberships,
        "build_context": {
            "workspace_root": str(workspace_root),
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
    digest = build_source_digest(source_path, dossier["build_context"])
    digest_paths = write_source_digest(out_dir, digest)
    location = locate_function(digest, function_name)
    location_paths = write_function_location(out_dir, digest, location)
    signature = extract_signature(digest, location)
    signature_paths = write_function_signature(out_dir, signature)
    global_access = analyze_global_access(digest, location, signature)
    global_access_paths = write_global_access(out_dir, global_access)
    call_report = analyze_calls(digest, location, signature, global_access)
    call_report_paths = write_call_report(out_dir, call_report)
    coverage_design = analyze_coverage_design(digest, location, signature, global_access, call_report)
    coverage_design_paths = write_coverage_design(out_dir, coverage_design)
    boundary_candidates = generate_boundary_equivalence_candidates(signature, global_access, call_report, coverage_design)
    boundary_paths = write_boundary_equivalence_candidates(out_dir, boundary_candidates)
    test_case_draft = generate_test_case_draft(signature, global_access, call_report, coverage_design, boundary_candidates)
    test_case_draft_paths = write_test_case_draft_report(out_dir, test_case_draft)
    harness_skeleton = generate_harness_skeleton(signature, global_access, call_report, test_case_draft, out_dir)
    build_workspace, build_probe = generate_build_workspace(
        dossier["build_context"],
        digest.to_dict(),
        harness_skeleton.to_dict(),
        out_dir,
        run_probe=False,
        dry_run=True,
    )
    completion_policy = BuildCompletionPolicy(apply_safe_completions=apply_safe_completions)
    build_completion_plan, build_completion_iteration = analyze_build_errors_from_workspace(out_dir, source_root=workspace_root, policy=completion_policy)
    if apply_safe_completions:
        apply_result = apply_completion_actions(out_dir, build_completion_plan)
        if build_completion_iteration.iterations:
            first = build_completion_iteration.iterations[0]
            first.applied_actions = apply_result.applied_actions
            first.skipped_actions = apply_result.skipped_actions
            first.generated_files = apply_result.generated_files
            first.progress = "not_run"
        build_completion_iteration.warnings.extend(apply_result.warnings)
        write_completion_reports(out_dir, build_completion_plan, build_completion_iteration)
    test_execution, evidence_manifest = prepare_test_execution_evidence(out_dir, run_tests=run_tests, dry_run=not run_tests)
    dossier["source_digest"] = {
        "json": str(digest_paths["json"]),
        "markdown": str(digest_paths["markdown"]),
        "masked_source": str(digest_paths["masked_source"]),
    }
    dossier["function_location"] = {
        "json": str(location_paths["json"]),
        "markdown": str(location_paths["markdown"]),
        "function_slice": str(location_paths["function_slice"]),
        "status": location.status,
    }
    dossier["function_signature"] = {
        "json": str(signature_paths["json"]),
        "markdown": str(signature_paths["markdown"]),
        "status": signature.status,
        "style": signature.style,
    }
    dossier["global_access"] = {
        "json": str(global_access_paths["json"]),
        "markdown": str(global_access_paths["markdown"]),
        "status": global_access.status,
    }
    dossier["call_report"] = {
        "json": str(call_report_paths["json"]),
        "markdown": str(call_report_paths["markdown"]),
        "status": call_report.status,
    }
    dossier["coverage_design"] = {
        "json": str(coverage_design_paths["json"]),
        "markdown": str(coverage_design_paths["markdown"]),
        "status": coverage_design.status,
    }
    dossier["boundary_equivalence_candidates"] = {
        "json": str(boundary_paths["json"]),
        "markdown": str(boundary_paths["markdown"]),
        "status": boundary_candidates.status,
    }
    dossier["test_case_draft"] = {
        "json": str(test_case_draft_paths["json"]),
        "markdown": str(test_case_draft_paths["markdown"]),
        "csv": str(test_case_draft_paths["csv"]),
        "status": test_case_draft.status,
    }
    dossier["harness_skeleton"] = {
        "json": str(out_dir / "reports" / "harness_skeleton_report.json"),
        "markdown": str(out_dir / "reports" / "harness_skeleton_report.md"),
        "status": harness_skeleton.status,
    }
    dossier["build_workspace"] = {
        "json": str(out_dir / "reports" / "build_workspace_report.json"),
        "markdown": str(out_dir / "reports" / "build_workspace_report.md"),
        "status": build_workspace.status,
    }
    dossier["build_probe"] = {
        "json": str(out_dir / "reports" / "build_probe_report.json"),
        "markdown": str(out_dir / "reports" / "build_probe_report.md"),
        "status": build_probe.status,
        "executed": build_probe.executed,
    }
    dossier["build_completion"] = {
        "plan_json": str(out_dir / "reports" / "build_completion_plan.json"),
        "plan_markdown": str(out_dir / "reports" / "build_completion_plan.md"),
        "iteration_json": str(out_dir / "reports" / "build_completion_iteration_report.json"),
        "iteration_markdown": str(out_dir / "reports" / "build_completion_iteration_report.md"),
        "status": build_completion_plan.status,
        "iteration_status": build_completion_iteration.status,
    }
    dossier["test_execution"] = {
        "json": str(out_dir / "reports" / "test_execution_report.json"),
        "markdown": str(out_dir / "reports" / "test_execution_report.md"),
        "result_json": str(out_dir / "reports" / "test_result.json"),
        "result_csv": str(out_dir / "reports" / "test_result.csv"),
        "status": test_execution.status,
        "executed": test_execution.executed,
    }
    dossier["evidence"] = {
        "manifest_json": str(out_dir / "reports" / "evidence_manifest.json"),
        "package_markdown": str(out_dir / "reports" / "evidence_package.md"),
        "status": evidence_manifest.summary.test_execution_status,
    }
    _write_json(out_dir / "reports" / "function_dossier.json", dossier)
    _write_markdown_reports(out_dir, dossier, copied_files)
    write_function_signature(out_dir, signature)
    write_global_access(out_dir, global_access)
    write_call_report(out_dir, call_report)
    write_coverage_design(out_dir, coverage_design)
    write_boundary_equivalence_candidates(out_dir, boundary_candidates)
    write_test_case_draft_report(out_dir, test_case_draft)
    _write_json(out_dir / "generated" / "prompt_pack.json", {"function_dossier": dossier})
    return dossier


def generate_harness_skeleton_from_reports(
    function_signature_path: Path | str,
    global_access_path: Path | str,
    call_report_path: Path | str,
    test_case_draft_path: Path | str,
    out: Path | str,
    overwrite: bool = False,
):
    report = generate_harness_skeleton(
        _read_json(Path(function_signature_path)),
        _read_json(Path(global_access_path)),
        _read_json(Path(call_report_path)),
        _read_json(Path(test_case_draft_path)),
        Path(out),
        overwrite=overwrite,
    )
    return report


def generate_build_workspace_from_reports(
    build_context_path: Path | str,
    source_digest_path: Path | str,
    harness_report_path: Path | str,
    out: Path | str,
    run_probe: bool = False,
    dry_run: bool = True,
    vcvars: Path | str | None = None,
    timeout_seconds: int = 120,
    overwrite: bool = False,
):
    return generate_build_workspace(
        _read_json(Path(build_context_path)),
        _read_json(Path(source_digest_path)),
        _read_json(Path(harness_report_path)),
        Path(out),
        run_probe=run_probe,
        dry_run=dry_run,
        vcvars=vcvars,
        timeout_seconds=timeout_seconds,
        overwrite=overwrite,
    )


def generate_build_workspace_from_workspace(
    workspace: Path | str,
    run_probe: bool = False,
    dry_run: bool = True,
    vcvars: Path | str | None = None,
    timeout_seconds: int = 120,
    overwrite: bool = False,
):
    workspace = Path(workspace)
    reports = workspace / "reports"
    return generate_build_workspace_from_reports(
        reports / "build_context.json",
        reports / "source_digest.json",
        reports / "harness_skeleton_report.json",
        workspace,
        run_probe=run_probe,
        dry_run=dry_run,
        vcvars=vcvars,
        timeout_seconds=timeout_seconds,
        overwrite=overwrite,
    )


def generate_test_draft_from_dossier(dossier_path: Path | str, output_format: str = "csv", out: Path | str | None = None) -> Path | dict[str, Path]:
    dossier_path = Path(dossier_path)
    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    report = _generate_test_case_report_from_dossier_payload(dossier, dossier_path)
    target = _draft_target(dossier_path.parent, output_format, out)
    return write_test_case_draft_format(target, report, output_format)


def generate_test_draft_from_reports(
    function_signature_path: Path | str,
    global_access_path: Path | str,
    call_report_path: Path | str,
    coverage_design_path: Path | str,
    boundary_candidates_path: Path | str,
    output_format: str = "csv",
    out: Path | str | None = None,
) -> Path | dict[str, Path]:
    paths = [Path(item) for item in (function_signature_path, global_access_path, call_report_path, coverage_design_path, boundary_candidates_path)]
    report = generate_test_case_draft_from_payloads(*[_read_json(path) for path in paths])
    target_root = paths[3].parent
    target = _draft_target(target_root, output_format, out)
    return write_test_case_draft_format(target, report, output_format)


def _generate_test_case_report_from_dossier_payload(dossier: dict[str, Any], dossier_path: Path):
    try:
        paths = [
            Path(dossier["function_signature"]["json"]),
            Path(dossier["global_access"]["json"]),
            Path(dossier["call_report"]["json"]),
            Path(dossier["coverage_design"]["json"]),
            Path(dossier["boundary_equivalence_candidates"]["json"]),
        ]
    except KeyError:
        target = dossier_path.with_name("test_case_draft.csv")
        write_test_case_draft(target, dossier)
        return _legacy_report_from_csv_dossier(dossier, dossier_path)
    return generate_test_case_draft_from_payloads(*[_read_json(path) for path in paths])


def _legacy_report_from_csv_dossier(dossier: dict[str, Any], dossier_path: Path):
    from .test_design.test_case_models import CoverageDraftSummary, TestCaseDraftReport, TestCaseGenerationPolicy

    function_name = dossier.get("target", {}).get("function", "unknown")
    return TestCaseDraftReport(
        source_path=Path(dossier.get("target", {}).get("source", "")),
        source_sha256="",
        function_name=function_name,
        status="partial",
        generation_policy=TestCaseGenerationPolicy(),
        test_cases=[],
        additional_case_candidates=[],
        coverage_summary=CoverageDraftSummary(0, 0, [], {}),
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _draft_target(default_dir: Path, output_format: str, out: Path | str | None) -> Path:
    if out is not None:
        return Path(out)
    if output_format == "all":
        return default_dir
    suffix = "md" if output_format == "md" else output_format
    return default_dir / f"test_case_draft.{suffix}"
