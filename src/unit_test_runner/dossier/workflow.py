from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..build import generate_build_workspace
from ..build_completion import analyze_build_errors_from_workspace
from ..build_completion.completion_applier import apply_safe_completions as apply_completion_actions
from ..build_completion.completion_models import BuildCompletionPolicy
from ..build_completion.completion_report_writer import write_completion_reports
from ..c_analyzer import analyze_function
from ..c_analyzer.boundary_candidate_analyzer import generate_boundary_equivalence_candidates
from ..c_analyzer.boundary_candidate_writer import write_boundary_equivalence_candidates
from ..c_analyzer.call_analyzer import analyze_calls
from ..c_analyzer.call_report_writer import write_call_report
from ..c_analyzer.coverage_design_analyzer import analyze_coverage_design
from ..c_analyzer.coverage_design_writer import write_coverage_design
from ..c_analyzer.function_location_writer import write_function_location
from ..c_analyzer.function_locator import locate_function
from ..c_analyzer.global_access_analyzer import analyze_global_access
from ..c_analyzer.global_access_writer import write_global_access
from ..c_analyzer.signature_extractor import extract_signature
from ..c_analyzer.signature_writer import write_function_signature
from ..c_analyzer.source_digest import build_source_digest, write_source_digest
from ..harness import generate_harness_skeleton
from ..dependency_policy import analyze_dependency_policy, write_dependency_policy
from ..execution import classify_test_execution, prepare_test_execution_evidence
from ..path_utils import normalize_relative
from ..test_design import generate_test_design
from ..test_design.test_case_design_generator import generate_test_case_design, generate_test_case_design_from_payloads
from ..test_design.test_case_design_writer import write_test_case_design_format, write_test_case_design_payload_format, write_test_case_design_report
from ..contracts import ContractMode
from ..test_spec import (
    artifact_reference,
    assert_safe_legacy_alias_paths,
    bind_test_spec_inputs,
    build_current_artifact_context,
    create_test_spec_from_design,
    export_test_spec_snapshot_views,
    export_test_spec_views,
    load_test_spec,
    load_legacy_test_case_design_view,
    save_test_spec_snapshot,
    test_spec_consumer_payload,
    validate_test_spec,
)
from ..vc6 import select_project_context
from ..test_spec.path_safety import assert_safe_canonical_test_spec_path


@dataclass(frozen=True)
class TestSpecDesignResult:
    output: Path | dict[str, Path]
    saved_snapshot: Any | None = None
    canonical_artifact: Any | None = None
    view_export: Any | None = None
    produced_view_paths: tuple[Path, ...] = ()


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


def _normalize_analysis_phase(phase: str) -> str:
    if phase not in {"analysis", "design", "harness", "build", "execution"}:
        raise ValueError(f"Unsupported analysis phase: {phase}")
    return phase


def _analysis_phase_rank(phase: str) -> int:
    return {"analysis": 1, "design": 2, "harness": 3, "build": 4, "execution": 5}[phase]


def _markdown_list(items: list[Any], formatter=str) -> str:
    if not items:
        return "- なし\n"
    return "".join(f"- {formatter(item)}\n" for item in items)


def _write_markdown_reports(out_dir: Path, dossier: dict[str, Any], copied_files: list[str]) -> None:
    reports = out_dir / "reports"
    function = dossier["function"]
    design = dossier["test_design"]
    md = [
        f"# 関数dossier: {function['name']}",
        "",
        "## 対象",
        f"- ソース: `{dossier['target']['source']}`",
        f"- 関数: `{dossier['target']['function']}`",
        f"- 構成: `{dossier['target']['configuration']}`",
        "",
        "## ビルドコンテキスト",
        _markdown_list(dossier["build_context"].get("defines", []), lambda item: f"define: `{item}`"),
        _markdown_list(dossier["build_context"].get("include_dirs", []), lambda item: f"include: `{item}`"),
        "## 関数",
        f"- 戻り値型: `{function['return_type']}`",
        _markdown_list(function.get("parameters", []), lambda item: f"`{item['type']} {item['name']}`"),
        "## グローバル",
        _markdown_list(function.get("globals_read", []), lambda item: f"読み取り: `{item}`"),
        _markdown_list(function.get("globals_written", []), lambda item: f"書き込み: `{item}`"),
        "## 呼び出し",
        _markdown_list(function.get("external_calls", []), lambda item: f"`{item['name']}` {item['line']}行"),
        "## 分岐",
        _markdown_list(function.get("branches", []), lambda item: f"{item['id']}: `{item['condition']}`"),
        "## スタブ候補",
        _markdown_list(design.get("stub_candidates", []), lambda item: f"`{item['name']}`"),
    ]
    (reports / "function_dossier.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (reports / "project_membership.md").write_text(
        "# プロジェクト所属\n\n" + _markdown_list(dossier["project_membership"], lambda item: f"{item['project_name']} / {item['configuration']}"),
        encoding="utf-8",
    )
    _write_json(reports / "build_context.json", dossier["build_context"])
    (reports / "source_file_set.md").write_text("# ソースファイルセット\n\n" + _markdown_list(copied_files, lambda item: f"`{item}`"), encoding="utf-8")
    (reports / "global_access_report.md").write_text(
        "# グローバルアクセス\n\n## 読み取り\n" + _markdown_list(function.get("globals_read", [])) + "\n## 書き込み\n" + _markdown_list(function.get("globals_written", [])),
        encoding="utf-8",
    )
    (reports / "call_report.md").write_text(
        "# 呼び出し\n\n" + _markdown_list(function.get("external_calls", []), lambda item: f"`{item['name']}` {item['line']}行"),
        encoding="utf-8",
    )
    (reports / "branch_condition_report.md").write_text(
        "# 分岐と条件\n\n" + _markdown_list(function.get("branches", []), lambda item: f"{item['id']}: `{item['condition']}`"),
        encoding="utf-8",
    )
    (reports / "coverage_design.md").write_text(
        "# カバレッジ設計\n\n"
        + _markdown_list(design.get("branch_coverage_items", []), lambda item: f"{item['id']}: {item['description']}")
        + "\n"
        + _markdown_list(design.get("condition_coverage_items", []), lambda item: item["description"]),
        encoding="utf-8",
    )
    (reports / "boundary_equivalence_candidates.md").write_text(
        "# 境界値・同値クラス候補\n\n## 境界値\n"
        + _markdown_list(design.get("boundary_value_candidates", []), lambda item: item["value"])
        + "\n## 同値クラス\n"
        + _markdown_list(design.get("equivalence_class_candidates", []), lambda item: item["value"]),
        encoding="utf-8",
    )
    (reports / "stub_candidates.md").write_text(
        "# スタブ候補\n\n" + _markdown_list(design.get("stub_candidates", []), lambda item: f"`{item['name']}`"),
        encoding="utf-8",
    )


def write_test_case_design(path: Path, dossier: dict[str, Any]) -> None:
    raise ValueError(
        "Legacy CSV test-case-design generation is disabled; export test_spec.csv from the saved canonical TestSpec."
    )


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
    phase: str = "execution",
) -> dict[str, Any]:
    phase = _normalize_analysis_phase(phase)
    phase_rank = _analysis_phase_rank(phase)
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
    existing_dependency_policy = _read_existing_json(out_dir / "reports" / "dependency_policy.json")
    project_sources = [workspace_root / item for item in project.get("sources", [])]
    project_headers = [workspace_root / item for item in project.get("headers", [])]
    dependency_policy = analyze_dependency_policy(
        workspace_root=workspace_root,
        target_source=source_path,
        source_digest=digest,
        function_signature=signature,
        global_access=global_access,
        call_report=call_report,
        project_sources=project_sources,
        project_headers=project_headers,
        existing_policy=existing_dependency_policy,
    )
    dependency_policy_paths = write_dependency_policy(out_dir, dependency_policy)
    coverage_design = analyze_coverage_design(digest, location, signature, global_access, call_report)
    coverage_design_paths = write_coverage_design(out_dir, coverage_design)
    boundary_candidates = generate_boundary_equivalence_candidates(signature, global_access, call_report, coverage_design)
    boundary_paths = write_boundary_equivalence_candidates(out_dir, boundary_candidates)
    test_case_design = None
    test_spec = None
    test_case_design_paths = None
    harness_skeleton = None
    build_workspace = None
    build_probe = None
    build_completion_plan = None
    build_completion_iteration = None
    test_execution = None
    evidence_manifest = None
    if phase_rank >= _analysis_phase_rank("design"):
        canonical_test_spec_path = out_dir / "reports" / "test_spec.json"
        existing_spec = (
            load_test_spec(canonical_test_spec_path, mode=ContractMode.STRICT)
            if canonical_test_spec_path.exists()
            else None
        )
        existing_test_case_design = (
            test_spec_consumer_payload(existing_spec) if existing_spec is not None else None
        )
        test_case_design = generate_test_case_design(
            signature,
            global_access,
            call_report,
            coverage_design,
            boundary_candidates,
            dependency_policy=dependency_policy,
            existing_design=existing_test_case_design,
        )
        provenance = [
            artifact_reference(out_dir, digest_paths["json"], artifact_kind="source_digest"),
            artifact_reference(out_dir, location_paths["json"], artifact_kind="function_location"),
            artifact_reference(out_dir, signature_paths["json"], artifact_kind="function_signature"),
            artifact_reference(out_dir, global_access_paths["json"], artifact_kind="global_access"),
            artifact_reference(out_dir, call_report_paths["json"], artifact_kind="call_report"),
            artifact_reference(out_dir, dependency_policy_paths["json"], artifact_kind="dependency_policy"),
            artifact_reference(out_dir, coverage_design_paths["json"], artifact_kind="coverage_design"),
            artifact_reference(out_dir, boundary_paths["json"], artifact_kind="boundary_candidates"),
        ]
        test_spec = create_test_spec_from_design(
            test_case_design,
            signature.to_dict(),
            source_path=source,
            generated_from=provenance,
            revision=existing_spec.revision if existing_spec is not None else 1,
        )
        context = build_current_artifact_context(out_dir, test_spec)
        saved_snapshot, _test_spec_artifact = save_test_spec_snapshot(
            canonical_test_spec_path,
            test_spec,
            expected_revision=existing_spec.revision if existing_spec is not None else None,
            current_context=context,
        )
        test_spec = saved_snapshot.spec
        view_paths = export_test_spec_snapshot_views(
            saved_snapshot,
            canonical_test_spec_path.parent,
            canonical_path=canonical_test_spec_path,
        )
        test_case_design_paths = {
            "json": canonical_test_spec_path,
            "markdown": view_paths["markdown"],
            "csv": view_paths["csv"],
        }
    if phase_rank >= _analysis_phase_rank("harness"):
        harness_skeleton = generate_harness_skeleton(
            signature,
            global_access,
            call_report,
            test_spec_consumer_payload(test_spec),
            out_dir,
            dependency_policy=dependency_policy,
        )
    if phase_rank >= _analysis_phase_rank("build"):
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
    if phase_rank >= _analysis_phase_rank("execution"):
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
    dossier["dependency_policy"] = {
        "json": str(dependency_policy_paths["json"]),
        "markdown": str(dependency_policy_paths["markdown"]),
        "status": dependency_policy.status,
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
    if test_case_design is not None and test_case_design_paths is not None:
        dossier["test_spec"] = {
            "json": str(test_case_design_paths["json"]),
            "markdown": str(test_case_design_paths["markdown"]),
            "csv": str(test_case_design_paths["csv"]),
            "status": test_case_design.status,
            "saved_revision": test_spec.revision,
            "saved_sha256": saved_snapshot.sha256,
            "views_written_by_operation": view_paths.written,
        }
    if harness_skeleton is not None:
        dossier["harness_skeleton"] = {
            "json": str(out_dir / "reports" / "harness_skeleton_report.json"),
            "markdown": str(out_dir / "reports" / "harness_skeleton_report.md"),
            "status": harness_skeleton.status,
        }
    if build_workspace is not None and build_probe is not None:
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
    if build_completion_plan is not None and build_completion_iteration is not None:
        dossier["build_completion"] = {
            "plan_json": str(out_dir / "reports" / "build_completion_plan.json"),
            "plan_markdown": str(out_dir / "reports" / "build_completion_plan.md"),
            "iteration_json": str(out_dir / "reports" / "build_completion_iteration_report.json"),
            "iteration_markdown": str(out_dir / "reports" / "build_completion_iteration_report.md"),
            "status": build_completion_plan.status,
            "iteration_status": build_completion_iteration.status,
        }
    if test_execution is not None and evidence_manifest is not None:
        execution_state, green = classify_test_execution(
            test_execution,
            execution_requested=run_tests,
        )
        execution_paths = test_execution.run_paths
        evidence_paths = evidence_manifest.evidence_paths
        execution_json = (
            execution_paths.execution_report
            if execution_paths is not None
            else out_dir / "reports" / "test_execution_report.json"
        )
        result_json = (
            execution_paths.result_json
            if execution_paths is not None
            else out_dir / "reports" / "test_result.json"
        )
        result_csv = (
            execution_paths.result_csv
            if execution_paths is not None
            else out_dir / "reports" / "test_result.csv"
        )
        dossier["test_execution"] = {
            "run_id": execution_paths.run_id if execution_paths is not None else None,
            "json": str(execution_json),
            "result_json": str(result_json),
            "result_csv": str(result_csv),
            "stdout_log": str(execution_paths.stdout_log) if execution_paths is not None else None,
            "stderr_log": str(execution_paths.stderr_log) if execution_paths is not None else None,
            "combined_log": str(execution_paths.combined_log) if execution_paths is not None else None,
            "latest_run_pointer": str(out_dir / "reports" / "latest_run.json"),
            "status": execution_state.value,
            "executed": test_execution.executed,
            "green": green,
        }
        dossier["evidence"] = {
            "evidence_id": evidence_paths.evidence_id if evidence_paths is not None else None,
            "manifest_json": str(
                evidence_paths.evidence_manifest
                if evidence_paths is not None
                else out_dir / "reports" / "evidence_manifest.json"
            ),
            "source_run_json": str(evidence_paths.source_run) if evidence_paths is not None else None,
            "package_markdown": str(
                evidence_paths.evidence_package
                if evidence_paths is not None
                else out_dir / "reports" / "evidence_package.md"
            ),
            "latest_evidence_pointer": str(out_dir / "reports" / "latest_evidence.json"),
            "status": execution_state.value,
        }
    _write_json(out_dir / "reports" / "function_dossier.json", dossier)
    _write_markdown_reports(out_dir, dossier, copied_files)
    write_function_signature(out_dir, signature)
    write_global_access(out_dir, global_access)
    write_call_report(out_dir, call_report)
    write_dependency_policy(out_dir, dependency_policy)
    write_coverage_design(out_dir, coverage_design)
    write_boundary_equivalence_candidates(out_dir, boundary_candidates)
    _write_json(out_dir / "generated" / "prompt_pack.json", {"function_dossier": dossier})
    return dossier


def generate_harness_skeleton_from_reports(
    function_signature_path: Path | str,
    global_access_path: Path | str,
    call_report_path: Path | str,
    test_case_design_path: Path | str,
    out: Path | str,
    overwrite: bool = False,
    dependency_policy_path: Path | str | None = None,
    allow_legacy_alias: bool = False,
):
    function_signature_path = Path(function_signature_path)
    global_access_path = Path(global_access_path)
    call_report_path = Path(call_report_path)
    test_case_design_path = Path(test_case_design_path)
    policy_path = Path(dependency_policy_path) if dependency_policy_path else call_report_path.parent / "dependency_policy.json"
    test_payload = _read_json(test_case_design_path)
    consumer_spec = load_test_spec_for_consumer(
        test_case_design_path,
        function_signature_path=function_signature_path,
        allow_legacy_alias=allow_legacy_alias,
    )
    if test_payload.get("artifact_kind") == "test_spec":
        canonical_spec = load_test_spec(
            test_case_design_path,
            mode=ContractMode.STRICT,
        )
        inputs: dict[str, Path] = {
            "function_signature": function_signature_path,
            "global_access": global_access_path,
            "call_report": call_report_path,
        }
        if policy_path.exists():
            inputs["dependency_policy"] = policy_path
        bind_test_spec_inputs(
            test_case_design_path.parent.parent,
            canonical_spec,
            inputs,
        )
    else:
        report_root = function_signature_path.parent.resolve()
        legacy_paths = [global_access_path, call_report_path, test_case_design_path]
        if policy_path.exists():
            legacy_paths.append(policy_path)
        if any(path.parent.resolve() != report_root for path in legacy_paths):
            raise ValueError(
                "Legacy harness inputs must share the signature report directory."
            )
    dependency_policy = _read_json(policy_path) if policy_path.exists() else None
    report = generate_harness_skeleton(
        _read_json(function_signature_path),
        _read_json(global_access_path),
        _read_json(call_report_path),
        consumer_spec,
        Path(out),
        overwrite=overwrite,
        dependency_policy=dependency_policy,
    )
    return report


def load_test_spec_for_consumer(
    path: Path | str,
    *,
    function_signature_path: Path | str | None = None,
    allow_legacy_alias: bool = False,
) -> dict[str, Any]:
    path = Path(path)
    if path.suffix.lower() != ".json":
        raise ValueError("Generated Markdown/CSV test-spec views are never accepted as inputs.")
    if path.name == "test_spec.json":
        assert_safe_canonical_test_spec_path(path)
    elif allow_legacy_alias and function_signature_path is not None:
        assert_safe_legacy_alias_paths(path, function_signature_path)
    else:
        assert_safe_canonical_test_spec_path(path)
    raw = _read_json(path)
    if raw.get("artifact_kind") == "test_spec":
        spec = load_test_spec(
            path,
            mode=ContractMode.COMPATIBLE if allow_legacy_alias else ContractMode.STRICT,
        )
        if path.name != "test_spec.json" or path.parent.name != "reports":
            raise ValueError("Canonical TEST_SPEC must be read from workspace reports/test_spec.json.")
        context = build_current_artifact_context(path.parent.parent, spec)
        violations = validate_test_spec(spec, current_context=context)
        if violations:
            detail = "; ".join(
                f"{item.code} at {item.json_path}: {item.message}"
                for item in violations
            )
            raise ValueError(f"Stale canonical test_spec: {detail}")
        return test_spec_consumer_payload(spec)
    if not allow_legacy_alias or raw.get("schema_version") != "0.1":
        raise ValueError("Expected canonical TEST_SPEC v1.1; only --test-case-design accepts the v0.1 legacy alias.")
    if function_signature_path is None:
        raise ValueError("Legacy test-case-design migration requires an explicit function signature artifact.")
    return load_legacy_test_case_design_view(
        path,
        function_signature_path=Path(function_signature_path),
    )


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


def generate_test_design_from_dossier(dossier_path: Path | str, output_format: str = "csv", out: Path | str | None = None) -> Path | dict[str, Path]:
    return generate_test_design_from_dossier_result(
        dossier_path,
        output_format,
        out,
    ).output


def generate_test_design_from_dossier_result(
    dossier_path: Path | str,
    output_format: str = "csv",
    out: Path | str | None = None,
) -> TestSpecDesignResult:
    dossier_path = Path(dossier_path)
    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    canonical = _dossier_artifact_path(dossier, dossier_path, "test_spec")
    if canonical is None or not canonical.is_file():
        raise ValueError("Dossier has no canonical reports/test_spec.json; regenerate the design phase first.")
    load_test_spec_for_consumer(canonical)
    spec = load_test_spec(canonical, mode=ContractMode.STRICT)
    return _export_test_spec_selection_result(
        spec,
        canonical,
        output_format,
        out,
    )


def generate_test_design_from_reports(
    function_signature_path: Path | str,
    global_access_path: Path | str,
    call_report_path: Path | str,
    coverage_design_path: Path | str,
    boundary_candidates_path: Path | str,
    output_format: str = "csv",
    out: Path | str | None = None,
) -> Path | dict[str, Path]:
    return generate_test_design_from_reports_result(
        function_signature_path,
        global_access_path,
        call_report_path,
        coverage_design_path,
        boundary_candidates_path,
        output_format,
        out,
    ).output


def generate_test_design_from_reports_result(
    function_signature_path: Path | str,
    global_access_path: Path | str,
    call_report_path: Path | str,
    coverage_design_path: Path | str,
    boundary_candidates_path: Path | str,
    output_format: str = "csv",
    out: Path | str | None = None,
) -> TestSpecDesignResult:
    paths = [Path(item) for item in (function_signature_path, global_access_path, call_report_path, coverage_design_path, boundary_candidates_path)]
    report = generate_test_case_design_from_payloads(*[_read_json(path) for path in paths])
    reports = paths[0].parent.resolve()
    if reports.name != "reports":
        raise ValueError("Explicit test-design inputs must come from one workspace reports directory.")
    if any(path.parent.resolve() != reports for path in paths):
        raise ValueError("Explicit test-design inputs must share one reports directory.")
    workspace = reports.parent
    request = _read_json(workspace / "input" / "request.json")
    source_path = str(request.get("source") or "")
    if not source_path:
        raise ValueError("Canonical test-spec generation requires input/request.json source identity.")
    reference_files = (
        ("source_digest", "source_digest.json"),
        ("function_location", "function_location.json"),
        ("function_signature", "function_signature.json"),
        ("global_access", "global_access.json"),
        ("call_report", "call_report.json"),
        ("dependency_policy", "dependency_policy.json"),
        ("coverage_design", "coverage_design.json"),
        ("boundary_candidates", "boundary_equivalence_candidates.json"),
    )
    references = [
        artifact_reference(workspace, reports / filename, artifact_kind=kind)
        for kind, filename in reference_files
        if (reports / filename).is_file()
    ]
    canonical = reports / "test_spec.json"
    existing = load_test_spec(canonical, mode=ContractMode.STRICT) if canonical.exists() else None
    spec = create_test_spec_from_design(
        report,
        _read_json(paths[0]),
        source_path=source_path,
        generated_from=references,
        revision=existing.revision if existing is not None else 1,
    )
    context = build_current_artifact_context(workspace, spec)
    saved_snapshot, test_spec_artifact = save_test_spec_snapshot(
        canonical,
        spec,
        expected_revision=existing.revision if existing is not None else None,
        current_context=context,
    )
    return _export_test_spec_selection_result(
        saved_snapshot.spec,
        canonical,
        output_format,
        out,
        saved_snapshot=saved_snapshot,
        canonical_artifact=test_spec_artifact,
    )


def _export_test_spec_selection_result(
    spec,
    canonical: Path,
    output_format: str,
    out: Path | str | None,
    *,
    saved_snapshot=None,
    canonical_artifact=None,
) -> TestSpecDesignResult:
    canonical = canonical.resolve()
    if output_format == "json":
        if out is not None and Path(out).resolve() != canonical:
            raise ValueError("JSON output is fixed at the sole editable reports/test_spec.json contract.")
        return TestSpecDesignResult(
            output=canonical,
            saved_snapshot=saved_snapshot,
            canonical_artifact=canonical_artifact,
        )
    requested = Path(out) if out is not None else None
    if output_format == "all":
        target_dir = requested or canonical.parent
        views = (
            export_test_spec_snapshot_views(
                saved_snapshot,
                target_dir,
                canonical_path=canonical,
            )
            if saved_snapshot is not None
            else export_test_spec_views(spec, target_dir, canonical_path=canonical)
        )
        return TestSpecDesignResult(
            output={"json": canonical, **views},
            saved_snapshot=saved_snapshot,
            canonical_artifact=canonical_artifact,
            view_export=views,
            produced_view_paths=(
                (views["markdown"], views["csv"])
                if views.written
                else ()
            ),
        )
    if output_format not in {"md", "csv"}:
        raise ValueError(f"Unsupported test design format: {output_format}")
    target_dir = (
        requested.parent
        if requested is not None and requested.suffix
        else requested or canonical.parent
    )
    views = (
        export_test_spec_snapshot_views(
            saved_snapshot,
            target_dir,
            canonical_path=canonical,
        )
        if saved_snapshot is not None
        else export_test_spec_views(spec, target_dir, canonical_path=canonical)
    )
    source_view = views["markdown" if output_format == "md" else "csv"]
    if requested is not None and requested.suffix and requested.resolve() != source_view.resolve():
        requested.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_view, requested)
        return TestSpecDesignResult(
            output=requested,
            saved_snapshot=saved_snapshot,
            canonical_artifact=canonical_artifact,
            view_export=views,
            produced_view_paths=(requested,) if views.written else (),
        )
    return TestSpecDesignResult(
        output=source_view,
        saved_snapshot=saved_snapshot,
        canonical_artifact=canonical_artifact,
        view_export=views,
        produced_view_paths=(source_view,) if views.written else (),
    )


def _dossier_artifact_path(dossier: dict[str, Any], dossier_path: Path, artifact_kind: str) -> Path | None:
    legacy = dossier.get(artifact_kind)
    if isinstance(legacy, dict) and isinstance(legacy.get("json"), str):
        return _resolve_dossier_relative_path(dossier, dossier_path, legacy["json"])

    for artifact in dossier.get("artifact_index", []):
        if not isinstance(artifact, dict):
            continue
        if artifact.get("artifact_kind") != artifact_kind or not artifact.get("exists"):
            continue
        artifact_path = artifact.get("path")
        if isinstance(artifact_path, str):
            return _resolve_dossier_relative_path(dossier, dossier_path, artifact_path)

    fallback = dossier_path.parent / f"{artifact_kind}.json"
    if fallback.exists():
        return fallback
    return None


def _resolve_dossier_relative_path(dossier: dict[str, Any], dossier_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path

    candidates: list[Path] = []
    workspace_root = dossier.get("workspace_root")
    if isinstance(workspace_root, str) and workspace_root:
        candidates.append(Path(workspace_root) / path)
    candidates.append(dossier_path.parent / path)
    candidates.append(dossier_path.parent.parent / path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_existing_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = _read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _test_design_target(default_dir: Path, output_format: str, out: Path | str | None) -> Path:
    if out is not None:
        return Path(out)
    if output_format == "all":
        return default_dir
    suffix = "md" if output_format == "md" else output_format
    return default_dir / f"test_case_design.{suffix}"
