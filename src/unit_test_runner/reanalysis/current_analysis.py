from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from unit_test_runner.c_analyzer.boundary_candidate_analyzer import generate_boundary_equivalence_candidates
from unit_test_runner.c_analyzer.call_analyzer import analyze_calls
from unit_test_runner.c_analyzer.coverage_design_analyzer import analyze_coverage_design
from unit_test_runner.c_analyzer.function_locator import locate_function
from unit_test_runner.c_analyzer.global_access_analyzer import analyze_global_access
from unit_test_runner.c_analyzer.signature_extractor import extract_signature
from unit_test_runner.c_analyzer.source_digest import build_source_digest
from unit_test_runner.test_design.test_case_design_generator import generate_test_case_design
from unit_test_runner.vc6 import select_project_context


def build_current_reanalysis(
    workspace_root: Path | str,
    dsw_path: Path | str,
    source: str | Path,
    function_name: str,
    configuration: str,
    out_dir: Path | str,
    project_name: str | None = None,
) -> dict[str, dict[str, Any]]:
    workspace_root = Path(workspace_root).resolve()
    source_relative = _source_relative_to_workspace(workspace_root, source)
    source_path = (workspace_root / source_relative).resolve()
    out_dir = Path(out_dir).resolve()
    current_reports = out_dir / "reports" / "reanalysis" / "current"
    current_reports.mkdir(parents=True, exist_ok=True)
    project, config, memberships = select_project_context(workspace_root, dsw_path, source_relative, configuration, project_name)
    build_context = {
        "workspace_root": str(workspace_root),
        "defines": config["defines"],
        "include_dirs": config["include_dirs"],
        "compiler_options": config["compiler_options"],
        "forced_includes": config["forced_includes"],
        "precompiled_header": config["precompiled_header"],
        "unresolved_macros": config["unresolved_macros"],
        "project": project["project_name"],
        "configuration": configuration,
    }
    digest = build_source_digest(source_path, build_context)
    location = locate_function(digest, function_name)
    signature = extract_signature(digest, location)
    global_access = analyze_global_access(digest, location, signature)
    call_report = analyze_calls(digest, location, signature, global_access)
    coverage_design = analyze_coverage_design(digest, location, signature, global_access, call_report)
    boundary_candidates = generate_boundary_equivalence_candidates(signature, global_access, call_report, coverage_design)
    test_case_design = generate_test_case_design(signature, global_access, call_report, coverage_design, boundary_candidates)
    payloads = {
        "source_digest": digest.to_dict(include_tokens=True),
        "function_location": location.to_dict(),
        "function_signature": signature.to_dict(),
        "global_access": global_access.to_dict(),
        "call_report": call_report.to_dict(),
        "coverage_design": coverage_design.to_dict(),
        "boundary_equivalence_candidates": boundary_candidates.to_dict(),
        "test_case_design": test_case_design.to_dict(),
        "build_context": {"schema_version": "0.1", "build_context": build_context},
        "project_membership": {"schema_version": "0.1", "project_membership": memberships},
    }
    for kind, payload in payloads.items():
        filename = "test_case_design.generated.json" if kind == "test_case_design" else f"{kind}.json"
        _write_json(current_reports / filename, payload)
    return payloads


def _source_relative_to_workspace(workspace_root: Path, source: str | Path) -> str:
    source_path = Path(source)
    absolute = source_path.resolve() if source_path.is_absolute() else (workspace_root / str(source).replace("\\", "/")).resolve()
    try:
        return absolute.relative_to(workspace_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"source path is outside workspace: {absolute}") from exc


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
