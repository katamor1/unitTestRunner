from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..build import generate_build_workspace
from ..c_analyzer import analyze_function
from ..c_analyzer.boundary_candidate_analyzer import generate_boundary_equivalence_candidates
from ..c_analyzer.boundary_candidate_writer import write_boundary_equivalence_candidates
from ..c_analyzer.call_analyzer import analyze_calls
from ..c_analyzer.call_models import CallAnalyzerWarning
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
from ..path_utils import normalize_relative, validate_external_output_root
from ..test_design import generate_test_design
from ..test_design.test_case_design_generator import generate_test_case_design
from ..test_spec import (
    artifact_reference,
    build_current_artifact_context,
    create_test_spec_from_design,
    export_test_spec_snapshot_views,
    load_test_spec,
    load_test_spec_snapshot,
    save_test_spec_snapshot,
    test_spec_consumer_payload,
    validate_test_spec,
)
from ..vc6 import select_project_context
from ..vc6.coff_archive import LibrarySymbolCache
from ..vc6.link_context import LinkContext, LinkContextWarning
from ..vc6.link_library_resolver import resolve_link_context
from ..test_spec.path_safety import assert_safe_canonical_test_spec_path


_LIBRARY_SYMBOL_CACHE = LibrarySymbolCache()


class OutputBoundaryError(ValueError):
    """Raised when an analysis output workspace violates the output boundary."""


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
    if phase not in {"analysis", "design", "harness"}:
        raise ValueError(f"Unsupported analysis phase: {phase}")
    return phase


def _analysis_phase_rank(phase: str) -> int:
    return {"analysis": 1, "design": 2, "harness": 3}[phase]


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
        "# プロジェクト所属\n\n"
        + _markdown_list(
            dossier["project_membership"],
            lambda item: f"{item['project_name']} / {', '.join(item['configurations'])}",
        ),
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


def analyze_function_workflow(
    workspace_root: Path | str,
    dsw_path: Path | str,
    source: str,
    function_name: str,
    configuration: str,
    out_dir: Path | str,
    project_name: str | None = None,
    phase: str = "design",
) -> dict[str, Any]:
    phase = _normalize_analysis_phase(phase)
    phase_rank = _analysis_phase_rank(phase)
    workspace_root = Path(workspace_root).resolve()
    source = _source_relative_to_workspace(workspace_root, source)
    try:
        out_dir = validate_external_output_root(out_dir, workspace_root)
    except ValueError as error:
        raise OutputBoundaryError(str(error)) from error
    for child in ("input", "extracted", "generated", "reports", "intermediate"):
        (out_dir / child).mkdir(parents=True, exist_ok=True)
    project, config, memberships = select_project_context(workspace_root, dsw_path, source, configuration, project_name)
    selected_configuration = config.get("full_name") or configuration
    try:
        link_context = resolve_link_context(
            workspace_root,
            dsw_path,
            project["project_name"],
            selected_configuration,
            cache=_LIBRARY_SYMBOL_CACHE,
        )
    except (OSError, ValueError) as error:
        link_context = LinkContext(
            warnings=[
                LinkContextWarning(
                    "link_context_resolution_failed",
                    f"Link context resolution failed: {error}",
                    project["project_name"],
                    selected_configuration,
                )
            ]
        )
    config.setdefault("diagnostics", []).extend(
        {
            "severity": "warning",
            "code": warning.code,
            "message": warning.message,
            "project_name": warning.project_name,
            "configuration": warning.configuration,
            "library_candidate": warning.library_candidate,
        }
        for warning in link_context.warnings
    )
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
        "internal_format": "analysis-state-v1",
        "target": {
            "source": source,
            "function": function_name,
            "configuration": selected_configuration,
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
            "link_libraries": [item.to_dict() for item in link_context.libraries],
            "library_dirs": [path.as_posix() for path in link_context.library_dirs],
            "link_context_warnings": [item.to_dict() for item in link_context.warnings],
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
    call_report = analyze_calls(
        digest,
        location,
        signature,
        global_access,
        link_providers_by_name=link_context.providers_by_name,
        link_warnings=[
            CallAnalyzerWarning(item.code, item.message)
            for item in link_context.warnings
        ],
    )
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
    if phase_rank >= _analysis_phase_rank("design"):
        canonical_test_spec_path = out_dir / "reports" / "test_spec.json"
        existing_spec = (
            load_test_spec(canonical_test_spec_path)
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
            source_relative_path=source,
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
        if phase == "harness" and existing_spec is not None:
            # Harness preparation consumes the reviewed canonical TestSpec.  It
            # must not silently regenerate the document, advance its revision,
            # or discard human inputs.  Current source/provenance validation is
            # still mandatory before any generated code is written.
            context = build_current_artifact_context(out_dir, existing_spec)
            saved_snapshot = load_test_spec_snapshot(
                canonical_test_spec_path,
                current_context=context,
            )
            test_spec = saved_snapshot.spec
        else:
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
            overwrite=True,
            dependency_policy=dependency_policy,
        )
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
    analysis_state_path = out_dir / ".unit-test-runner" / "analysis_state.json"
    analysis_state_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(analysis_state_path, dossier)
    _write_markdown_reports(out_dir, dossier, copied_files)
    write_function_signature(out_dir, signature)
    write_global_access(out_dir, global_access)
    write_call_report(out_dir, call_report)
    write_dependency_policy(out_dir, dependency_policy)
    write_coverage_design(out_dir, coverage_design)
    write_boundary_equivalence_candidates(out_dir, boundary_candidates)
    return dossier


def load_test_spec_for_consumer(
    path: Path | str,
) -> dict[str, Any]:
    path = Path(path)
    if path.suffix.lower() != ".json":
        raise ValueError("Generated Markdown/CSV test-spec views are never accepted as inputs.")
    assert_safe_canonical_test_spec_path(path)
    raw = _read_json(path)
    if raw.get("artifact_kind") == "test_spec":
        spec = load_test_spec(path)
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
    raise ValueError("Expected canonical test_spec 1.0.0; regenerate the workspace.")


def generate_build_workspace_from_reports(
    build_context_path: Path | str,
    source_digest_path: Path | str,
    harness_report_path: Path | str,
    out: Path | str,
    run_probe: bool = False,
    dry_run: bool = True,
    vcvars: Path | str | None = None,
    timeout_seconds: int = 120,
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
    )


def generate_build_workspace_from_workspace(
    workspace: Path | str,
    run_probe: bool = False,
    dry_run: bool = True,
    vcvars: Path | str | None = None,
    timeout_seconds: int = 120,
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
    )


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
