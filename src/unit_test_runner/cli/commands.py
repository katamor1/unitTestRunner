from __future__ import annotations

import argparse
import os
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unit_test_runner.contracts import ArtifactKind, RunOutcome
from unit_test_runner.workspace_artifacts import (
    apply_reanalysis_candidate,
    is_current_review_approved,
    load_public_artifact,
    set_review_record,
)
from unit_test_runner.c_analyzer import list_functions
from unit_test_runner.dsw_parser import discover_dsw_workspaces, parse_dsw as parse_dsw_workspace
from unit_test_runner.execution import (
    execute_test_run,
    select_test_case_ids,
    validate_run_paths_available,
    validate_test_run_preflight,
)
from unit_test_runner.execution.execution_models import TestRunRequest
from unit_test_runner.path_utils import normalize_relative, resolved_relative_to
from unit_test_runner.reanalysis import (
    reanalyze_function_workflow,
)
from unit_test_runner.suite import (
    SuiteRunPolicy,
    list_entries,
    register_workspace,
    remove_entry,
    run_suite,
    update_entry,
    validate_suite_plan,
)
from unit_test_runner.reanalysis.reanalysis_models import ReanalysisPolicy
from unit_test_runner.dossier import (
    OutputBoundaryError,
    analyze_function_workflow,
    finalize_function_dossier,
    generate_build_workspace_from_workspace,
)
from unit_test_runner.reports.dsw_markdown import render_dsw_discovery_markdown
from unit_test_runner.reports.source_membership_markdown import render_source_membership_markdown
from unit_test_runner.vc6.dsp_parser import parse_dsp as parse_dsp_project
from unit_test_runner.vc6 import ProjectContextSelectionError
from unit_test_runner.vc6.source_membership import map_source_membership
from unit_test_runner.test_input_form import (
    TestInputFormError,
    apply_test_input_form,
    build_test_input_form,
    parse_test_input_change_request,
)
from unit_test_runner.test_spec import (
    TestSpecContractError,
    build_current_artifact_context,
    export_test_spec_snapshot_views,
    load_test_spec,
)
from .errors import CLIError
from .artifacts import (
    ProducedArtifact,
    build_produced_artifact,
)
from .exit_codes import (
    EXIT_BUILD_PROBE_FAILED,
    EXIT_ENVIRONMENT_WARNING,
    EXIT_INPUT_ERROR,
    EXIT_INTERNAL_ERROR,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_OUTPUT_ERROR,
    EXIT_TESTS_BLOCKED,
    EXIT_TESTS_CANCELLED,
    EXIT_TESTS_FAILED,
    EXIT_TESTS_TIMED_OUT,
)
from .outcomes import (
    DomainOutcome,
    classify_suite_run,
    classify_test_run,
)
from .result import CLIResult


def dispatch(args: argparse.Namespace) -> CLIResult:
    handlers = {
        "doctor": handle_doctor,
        "discover-projects": handle_discover_projects,
        "map-source": handle_map_source,
        "list-functions": handle_list_functions,
        "analyze-function": handle_analyze_function,
        "finalize-dossier": handle_finalize_dossier,
        "review-set": handle_review_set,
        "get-test-input-form": handle_get_test_input_form,
        "apply-test-input-form": handle_apply_test_input_form,
        "build-probe": handle_build_probe,
        "run-tests": handle_run_tests,
        "reanalyze-function": handle_reanalyze_function,
        "apply-reanalysis": handle_apply_reanalysis,
        "suite-register": handle_suite_register,
        "suite-update": handle_suite_update,
        "suite-list": handle_suite_list,
        "suite-remove": handle_suite_remove,
        "suite-run": handle_suite_run,
    }
    return handlers[args.command](args)


def handle_review_set(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    try:
        reviewed_kind = ArtifactKind(args.artifact_kind)
    except ValueError as error:
        raise CLIError(
            f"Unsupported public artifact kind: {args.artifact_kind!r}",
            EXIT_INPUT_ERROR,
            args.command,
        ) from error
    if reviewed_kind is ArtifactKind.REVIEW_RECORD:
        raise CLIError(
            "A review_record cannot review itself.",
            EXIT_INPUT_ERROR,
            args.command,
        )
    try:
        path = set_review_record(
            workspace,
            artifact_kind=reviewed_kind,
            artifact_sha256_value=args.artifact_sha256,
            decision=args.decision,
            reviewer=args.reviewer,
            reviewed_at=(
                args.reviewed_at
                or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            ),
            comment=args.comment,
        )
        artifact = build_produced_artifact(
            workspace,
            path,
            kind=ArtifactKind.REVIEW_RECORD.value,
        )
    except (OSError, ValueError) as error:
        raise CLIError(str(error), EXIT_INPUT_ERROR, args.command) from error
    return CLIResult(
        status="ok",
        exit_code=EXIT_OK,
        command=args.command,
        message=f"Recorded {args.decision} for {reviewed_kind.value}.",
        outcome=DomainOutcome("command", RunOutcome.PASSED, True),
        artifacts=[artifact],
    )


def handle_doctor(args: argparse.Namespace) -> CLIResult:
    supported = sys.version_info >= (3, 12)
    temp_dir = Path(tempfile.gettempdir())
    temp_writable = _is_writable_directory(temp_dir)
    checks = [
        {
            "id": "python_version",
            "status": "ok" if supported else "error",
            "message": "Python version is supported." if supported else "Python 3.12 or later is required.",
        },
        {
            "id": "temp_dir_writable",
            "status": "ok" if temp_writable else "error",
            "message": f"Temporary directory is writable: {temp_dir}" if temp_writable else f"Temporary directory is not writable: {temp_dir}",
        },
        {
            "id": "dependencies",
            "status": "ok",
            "message": "Runtime uses the Python standard library only.",
        },
    ]
    warnings = [] if supported and temp_writable else ["One or more doctor checks require attention."]
    return CLIResult(
        status="ok" if not warnings else "warning",
        exit_code=EXIT_OK,
        command="doctor",
        message="Environment check completed.",
        diagnostics=[
            {
                "code": str(check["id"]),
                "level": "info" if check["status"] == "ok" else "error",
                "message": str(check["message"]),
            }
            for check in checks
        ],
        warnings=warnings,
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_discover_projects(args: argparse.Namespace) -> CLIResult:
    if args.dsw:
        workspace = _existing_dir(args.workspace, "workspace", args.command)
        dsw = _resolve_dsw(workspace, args.dsw, args.command)
        result = discover_dsw_workspaces(dsw).to_dict()
        if args.with_dsp_details:
            result = _with_dsp_details(result)
        if args.out:
            _write_discovery_report(Path(args.out), result, args.command)
        return CLIResult(
            status="ok",
            exit_code=EXIT_OK,
            command=args.command,
            message="Projects discovered.",
            human_output=_render_discovery_summary(result, Path(args.out) if args.out else None),
            artifacts=[],
            outcome=DomainOutcome("command", RunOutcome.PASSED, None),
        )

    workspace_arg = _existing_path(args.workspace, "workspace", args.command)
    try:
        discovery = discover_dsw_workspaces(workspace_arg)
    except FileNotFoundError as exc:
        raise CLIError(str(exc), EXIT_NOT_FOUND, args.command) from exc
    result = discovery.to_dict()
    if args.with_dsp_details:
        result = _with_dsp_details(result)
    if args.out:
        _write_discovery_report(Path(args.out), result, args.command)
    return CLIResult(
        status="ok",
        exit_code=EXIT_OK,
        command=args.command,
        message="Projects discovered.",
        human_output=_render_discovery_summary(result, Path(args.out) if args.out else None),
        artifacts=[],
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_map_source(args: argparse.Namespace) -> CLIResult:
    dsw = _existing_file(args.dsw, "dsw", args.command)
    if args.workspace:
        _workspace_from_args(args.workspace, dsw)
    membership = map_source_membership(dsw, args.source, args.project, args.configuration)
    payload = membership.to_dict()
    if membership.status != "ok":
        candidates = _source_membership_candidates(payload)
        return CLIResult(
            status=membership.status,
            exit_code=EXIT_TESTS_BLOCKED,
            command=args.command,
            message="Source mapping requires exactly one project membership.",
            human_output=_render_source_membership_summary(payload, None),
            diagnostics=[
                {
                    "code": "source_membership_candidates",
                    "level": "error",
                    "message": json.dumps(candidates, ensure_ascii=True, sort_keys=True),
                }
            ],
            artifacts=[],
            outcome=DomainOutcome("command", RunOutcome.BLOCKED, None),
        )
    if args.out:
        _write_source_membership_report(Path(args.out), payload, args.command)
    return CLIResult(
        status=membership.status,
        exit_code=EXIT_OK,
        command=args.command,
        message="Source mapping completed.",
        human_output=_render_source_membership_summary(payload, Path(args.out) if args.out else None),
        artifacts=[],
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_list_functions(args: argparse.Namespace) -> CLIResult:
    source = _existing_file(args.source, "source", args.command)
    payload = {"functions": list_functions(source)}
    names = [
        str(item.get("name"))
        for item in payload["functions"]
        if isinstance(item, dict) and item.get("name")
    ]
    return CLIResult(
        status="ok",
        exit_code=EXIT_OK,
        command=args.command,
        message="Functions listed.",
        human_output="\n".join(names) if names else "No functions found.",
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_analyze_function(args: argparse.Namespace) -> CLIResult:
    dsw = _existing_file(args.dsw, "dsw", args.command)
    workspace = _workspace_from_args(args.workspace, dsw)
    source = normalize_relative(_existing_source(workspace, args.source, args.command), workspace)
    try:
        dossier = analyze_function_workflow(
            workspace,
            dsw,
            source,
            args.function,
            args.configuration,
            args.out,
            args.project,
            phase=args.phase,
        )
    except OutputBoundaryError as exc:
        raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
    except ProjectContextSelectionError as exc:
        raise CLIError(
            _project_context_selection_message(exc),
            EXIT_TESTS_BLOCKED,
            args.command,
            code="project_context_selection_blocked",
        ) from exc
    except ValueError as exc:
        raise CLIError(str(exc), EXIT_NOT_FOUND, args.command) from exc
    payload = {
        "phase": args.phase,
        "dossier": str(Path(args.out) / "reports" / "function_dossier.json"),
        "target": dossier["target"],
    }
    for key in (
        "source_digest",
        "function_location",
        "function_signature",
        "global_access",
        "call_report",
        "coverage_design",
        "boundary_equivalence_candidates",
        "test_spec",
        "harness_skeleton",
    ):
        if key in dossier:
            payload[key] = dossier[key]
    execution_outcome = DomainOutcome("command", RunOutcome.PASSED, None)
    execution_exit = EXIT_OK
    final_dossier = finalize_function_dossier(
        Path(args.out),
        function_name=args.function,
    )
    payload["review"] = _dossier_payload(Path(args.out), final_dossier)
    artifacts = _analysis_artifacts(Path(args.out), payload)
    return CLIResult(
        status=_analyze_status_for_phase(args.phase),
        exit_code=execution_exit,
        command=args.command,
        message="Function analysis and canonical dossier generated.",
        outcome=execution_outcome,
        artifacts=artifacts,
    )


def _analyze_status_for_phase(phase: str) -> str:
    if phase == "harness":
        return "harness_skeleton_generated"
    return "analysis_completed"


def _source_membership_candidates(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "matches": payload.get("matches", []),
        "candidate_projects": payload.get("candidate_projects", []),
    }


def _project_context_selection_message(error: ProjectContextSelectionError) -> str:
    return (
        f"{error} Candidates: "
        f"{json.dumps(error.candidates, ensure_ascii=True, sort_keys=True)}"
    )


def _artifacts_from_explicit_outputs(
    root: Path,
    outputs: list[tuple[Path, str | None]],
) -> list[ProducedArtifact]:
    resolved_root = root.resolve()
    artifacts: list[ProducedArtifact] = []
    seen: set[Path] = set()
    for raw_path, kind in outputs:
        if kind is None or raw_path.suffix.lower() != ".json":
            continue
        try:
            ArtifactKind(kind)
        except ValueError:
            continue
        candidate = (
            raw_path
            if raw_path.is_absolute()
            else raw_path.resolve()
            if raw_path.exists()
            else resolved_root / raw_path
        )
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        artifact = build_produced_artifact(
            resolved_root,
            resolved,
            kind=kind,
        )
        artifacts.append(artifact)
    return artifacts


def _existing_explicit_outputs(
    outputs: list[tuple[Path, str | None]],
) -> list[tuple[Path, str | None]]:
    return [(path, kind) for path, kind in outputs if path.is_file()]


def _optional_output_artifacts(
    output: str | Path | None,
    kind: str,
) -> list[ProducedArtifact]:
    if output is None:
        return []
    path = Path(output)
    return _artifacts_from_explicit_outputs(
        path.resolve().parent,
        [(path, kind)],
    )


def _analysis_artifacts(root: Path, payload: dict[str, Any]) -> list[ProducedArtifact]:
    root = root.resolve()
    reports = root / "reports"
    outputs: list[tuple[Path, str | None]] = []
    dossier_path = reports / "function_dossier.json"
    if dossier_path.is_file():
        try:
            dossier_header = json.loads(dossier_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Function dossier output is unreadable.") from error
        declared_kind = (
            dossier_header.get("artifact_kind")
            if isinstance(dossier_header, dict)
            else None
        )
        if declared_kind is not None:
            if declared_kind != ArtifactKind.FUNCTION_DOSSIER.value:
                raise ValueError("Function dossier output has the wrong artifact kind.")
            load_public_artifact(dossier_path, ArtifactKind.FUNCTION_DOSSIER)
            outputs.append(
                (dossier_path, ArtifactKind.FUNCTION_DOSSIER.value)
            )
    outputs.extend(_analysis_phase_outputs(payload))
    review = payload.get("review")
    if isinstance(review, dict):
        review_reports = review.get("reports")
        if isinstance(review_reports, dict):
            outputs.extend(_review_outputs(review_reports))
    return _artifacts_from_explicit_outputs(
        root,
        _existing_explicit_outputs(outputs),
    )


def _analysis_phase_outputs(payload: dict[str, Any]) -> list[tuple[Path, str | None]]:
    outputs: list[tuple[Path, str | None]] = []
    section_specs: dict[str, dict[str, str | None]] = {
        "test_spec": {"json": ArtifactKind.TEST_SPEC.value},
        "build_probe": {"json": ArtifactKind.BUILD_PROBE_REPORT.value},
    }
    for section_name, fields in section_specs.items():
        section = payload.get(section_name)
        if not isinstance(section, dict):
            continue
        for field, kind in fields.items():
            value = section.get(field)
            if isinstance(value, str) and value:
                outputs.append((Path(value), kind))
    return outputs


def _review_outputs(reports: dict[str, Any]) -> list[tuple[Path, str | None]]:
    field_kinds = {
        "function_dossier_json": ArtifactKind.FUNCTION_DOSSIER.value,
    }
    return [
        (Path(reports[field]), kind)
        for field, kind in field_kinds.items()
        if isinstance(reports.get(field), str) and reports[field]
    ]


def _named_outputs(
    values: dict[str, Any],
    field_kinds: dict[str, str | None],
) -> list[tuple[Path, str | None]]:
    return [
        (Path(values[field]), kind)
        for field, kind in field_kinds.items()
        if isinstance(values.get(field), str) and values[field]
    ]


def handle_reanalyze_function(args: argparse.Namespace) -> CLIResult:
    return _run_reanalysis(args)


def handle_apply_reanalysis(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    candidate = _existing_file(args.candidate, "candidate", args.command)
    try:
        applied, revision = apply_reanalysis_candidate(
            workspace,
            candidate,
            candidate_sha256=args.candidate_sha256,
            expected_revision=args.expected_revision,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise CLIError(str(error), EXIT_INPUT_ERROR, args.command) from error
    return CLIResult(
        status="reanalysis_applied",
        exit_code=EXIT_OK,
        command=args.command,
        message=f"Reanalysis candidate applied as TestSpec revision {revision}.",
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
        artifacts=[
            build_produced_artifact(
                workspace,
                applied,
                kind=ArtifactKind.TEST_SPEC.value,
            )
        ],
    )


def _run_reanalysis(args: argparse.Namespace) -> CLIResult:
    dsw = _existing_file(args.dsw, "dsw", args.command)
    workspace = _workspace_from_args(args.workspace, dsw)
    source = normalize_relative(_existing_source(workspace, args.source, args.command), workspace)
    policy = ReanalysisPolicy(
        generate_updated_test_case_design=True,
        overwrite_test_case_design=False,
        include_low_confidence_matches=args.include_low_confidence_matches,
    )
    try:
        result = reanalyze_function_workflow(
            workspace,
            dsw,
            source,
            args.function,
            args.configuration,
            args.out,
            project_name=args.project,
            previous_dossier_path=args.previous_dossier,
            previous_test_case_design_path=args.previous_test_spec,
            policy=policy,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
    reports = {key: str(value) for key, value in result["reports"].items()}
    payload = {
        "function": args.function,
        "status": result["status"],
        "reports": reports,
        "previous_dossier": str(result["previous_dossier"]),
        "previous_test_spec": str(result["previous_test_case_design"]),
    }
    return CLIResult(
        status="reanalysis_completed",
        exit_code=EXIT_OK,
        command=args.command,
        message="Function reanalysis completed.",
        artifacts=_artifacts_from_explicit_outputs(
            Path(args.out).resolve(),
            _named_outputs(
                reports,
                {
                    "reanalysis_report_json": ArtifactKind.REANALYSIS_REPORT.value,
                    "candidate_test_spec_json": ArtifactKind.TEST_SPEC.value,
                },
            ),
        ),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )




def handle_build_probe(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    _require_build_probe_workspace_reports(workspace, args.command)
    workspace_report, probe_report = generate_build_workspace_from_workspace(
        workspace,
        run_probe=args.run,
        dry_run=args.dry_run or not args.run,
        vcvars=args.vcvars,
        timeout_seconds=args.timeout,
    )
    return _build_probe_result(args.command, workspace, workspace_report, probe_report)


def _require_build_probe_workspace_reports(workspace: Path, command: str) -> None:
    reports = workspace / "reports"
    required = [
        reports / "build_context.json",
        reports / "source_digest.json",
        reports / "harness_skeleton_report.json",
    ]
    missing = [path.relative_to(workspace).as_posix() for path in required if not path.is_file()]
    if not missing:
        return
    hint = "Run analyze-function with --phase harness or --phase execution before build-probe --workspace."
    raise CLIError("build-probe --workspace requires generated reports: " + ", ".join(missing) + ". " + hint, EXIT_INPUT_ERROR, command)


def _build_probe_result(command: str, workspace: Path, workspace_report, probe_report) -> CLIResult:
    build_workspace_json = workspace / "reports" / "build_workspace_report.json"
    build_workspace_md = workspace / "reports" / "build_workspace_report.md"
    build_probe_json = workspace / "reports" / "build_probe_report.json"
    build_probe_md = workspace / "reports" / "build_probe_report.md"
    payload = {
        "build_workspace": {
            "json": str(build_workspace_json),
            "markdown": str(build_workspace_md),
            "status": workspace_report.status,
        },
        "build_probe": {
            "json": str(build_probe_json),
            "markdown": str(build_probe_md),
            "status": probe_report.status,
            "executed": probe_report.executed,
        },
        "reports": {
            "build_workspace_report_json": str(build_workspace_json),
            "build_workspace_report_md": str(build_workspace_md),
            "build_probe_report_json": str(build_probe_json),
            "build_probe_report_md": str(build_probe_md),
        },
    }
    exit_code = EXIT_OK
    errors = []
    if probe_report.status == "failed":
        exit_code = EXIT_BUILD_PROBE_FAILED
    elif probe_report.status == "environment_missing":
        exit_code = EXIT_ENVIRONMENT_WARNING
    elif probe_report.status == "blocked":
        exit_code = EXIT_TESTS_BLOCKED
    if exit_code != EXIT_OK:
        errors = [diagnostic.message for diagnostic in probe_report.diagnostics if diagnostic.severity == "error"]
    status = "build_workspace_generated"
    if probe_report.status == "environment_missing":
        status = "build_probe_environment_missing"
    elif probe_report.executed:
        status = f"build_probe_{probe_report.status}"
    message = "Build workspace generated."
    if errors:
        message = errors[0]
    return CLIResult(
        status=status,
        exit_code=exit_code,
        command=command,
        message=message,
        errors=errors,
        artifacts=_artifacts_from_explicit_outputs(
            workspace,
            _existing_explicit_outputs(
                [
                    (build_workspace_json, None),
                    (build_workspace_md, None),
                    (build_probe_json, ArtifactKind.BUILD_PROBE_REPORT.value),
                    (build_probe_md, None),
                ]
            ),
        ),
        outcome=DomainOutcome(
            "command",
            RunOutcome.PASSED
            if exit_code == EXIT_OK
            else RunOutcome.BLOCKED
            if exit_code in {EXIT_ENVIRONMENT_WARNING, EXIT_TESTS_BLOCKED}
            else RunOutcome.FAILED,
            None,
        ),
    )
















MAX_TEST_INPUT_REQUEST_BYTES = 4 * 1024 * 1024


def handle_get_test_input_form(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    try:
        document = build_test_input_form(
            workspace,
            summary_only=bool(args.summary_only),
        )
    except TestInputFormError as error:
        raise CLIError(
            error.message,
            EXIT_INPUT_ERROR,
            args.command,
            code=error.code,
        ) from error
    form_path = workspace / "reports" / "test_input_form.json"
    _write_json(form_path, document.to_dict(), args.command)
    return CLIResult(
        status="test_input_form_loaded",
        exit_code=EXIT_OK,
        command=args.command,
        message=(
            "Test input form written to reports/test_input_form.json; edit the "
            "referenced canonical TestSpec through apply-test-input-form."
        ),
        artifacts=[
            build_produced_artifact(
                workspace,
                workspace / "reports" / "test_spec.json",
                kind=ArtifactKind.TEST_SPEC.value,
            )
        ],
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_apply_test_input_form(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    input_path = _existing_file(args.input, "input", args.command)
    try:
        if input_path.stat().st_size > MAX_TEST_INPUT_REQUEST_BYTES:
            raise TestInputFormError(
                "test_input_form_invalid",
                f"Test input change request exceeds {MAX_TEST_INPUT_REQUEST_BYTES} bytes.",
            )
        parsed = json.loads(input_path.read_text(encoding="utf-8-sig"))
        request = parse_test_input_change_request(parsed)
        applied = apply_test_input_form(
            workspace,
            request,
            args.expected_revision,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CLIError(
            str(error),
            EXIT_INPUT_ERROR,
            args.command,
            code="test_input_form_invalid",
        ) from error
    except TestInputFormError as error:
        raise CLIError(
            error.message,
            EXIT_INPUT_ERROR,
            args.command,
            code=error.code,
        ) from error
    return CLIResult(
        status="test_input_form_applied",
        exit_code=EXIT_OK,
        command=args.command,
        message="Test input form changes applied.",
        diagnostics=[dict(item) for item in applied.warnings],
        artifacts=list(applied.artifacts),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )














def handle_suite_register(args: argparse.Namespace) -> CLIResult:
    try:
        manifest = register_workspace(
            Path(args.suite),
            Path(args.workspace),
            tags=_split_tags(args.tags),
            expected_revision=args.expected_revision,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
    entry = manifest.entries[-1]
    payload = {
        "suite": str(Path(args.suite).resolve()),
        "entry": entry.to_dict(),
        "entry_count": len(manifest.entries),
    }
    return CLIResult(
        status="suite_registered",
        exit_code=EXIT_OK,
        command=args.command,
        message="Suite entry registered.",
        artifacts=_optional_output_artifacts(args.suite, ArtifactKind.SUITE_MANIFEST.value),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_suite_update(args: argparse.Namespace) -> CLIResult:
    try:
        manifest = update_entry(
            Path(args.suite),
            args.entry_id,
            expected_revision=args.expected_revision,
            workspace=Path(args.workspace) if args.workspace else None,
            tags=_split_tags(args.tags),
            enabled=(
                None
                if args.enabled is None
                else args.enabled == "true"
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
    payload = {
        "suite": str(Path(args.suite).resolve()),
        "entry_id": args.entry_id,
        "entry_count": len(manifest.entries),
    }
    return CLIResult(
        status="suite_updated",
        exit_code=EXIT_OK,
        command=args.command,
        message="Suite entry updated.",
        artifacts=_optional_output_artifacts(
            args.suite,
            ArtifactKind.SUITE_MANIFEST.value,
        ),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_suite_list(args: argparse.Namespace) -> CLIResult:
    try:
        entries = list_entries(Path(args.suite), tag=args.tag)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
    payload = {
        "suite": str(Path(args.suite).resolve()),
        "entries": [entry.to_dict() for entry in entries],
        "entry_count": len(entries),
    }
    return CLIResult(
        status="suite_listed",
        exit_code=EXIT_OK,
        command=args.command,
        message=(
            f"Suite entries listed ({len(entries)}): "
            + (", ".join(entry.entry_id for entry in entries) or "none")
        ),
        artifacts=_optional_output_artifacts(
            args.suite,
            ArtifactKind.SUITE_MANIFEST.value,
        ),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_suite_remove(args: argparse.Namespace) -> CLIResult:
    try:
        manifest = remove_entry(
            Path(args.suite),
            args.entry_id,
            expected_revision=args.expected_revision,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
    payload = {
        "suite": str(Path(args.suite).resolve()),
        "removed_entry_id": args.entry_id,
        "entry_count": len(manifest.entries),
    }
    return CLIResult(
        status="suite_removed",
        exit_code=EXIT_OK,
        command=args.command,
        message="Suite entry removed.",
        artifacts=_optional_output_artifacts(args.suite, ArtifactKind.SUITE_MANIFEST.value),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_suite_run(args: argparse.Namespace) -> CLIResult:
    suite_path = _existing_file(args.suite, "suite", args.command)
    if not getattr(args, "run", False):
        try:
            _, plan_diagnostics = validate_suite_plan(
                suite_path,
                entry_ids=args.entry_ids,
                tag=args.tag,
                all_entries=args.all,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
        return _plan_suite_run(args, suite_path, plan_diagnostics)
    policy = SuiteRunPolicy(
        run_tests=True,
        dry_run=False,
        timeout_seconds=args.timeout,
    )
    try:
        report, paths = run_suite(
            suite_path,
            entry_ids=args.entry_ids,
            tag=args.tag,
            all_entries=args.all,
            policy=policy,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
    payload = report.to_dict()
    payload["reports"] = {
        "suite_run_report_json": str(paths["json"]),
        "suite_run_report_md": str(paths["markdown"]),
        "suite_run_report_csv": str(paths["csv"]),
    }
    outcome, exit_code = classify_suite_run(report, execution_requested=True)
    payload["outcome"] = outcome.state.value
    artifacts = _suite_artifacts(suite_path.parent, paths)
    return CLIResult(
        status=outcome.state.value,
        exit_code=exit_code,
        command=args.command,
        message="Suite run completed.",
        outcome=outcome,
        artifacts=artifacts,
    )


def _test_spec_view_artifact_root(
    path: Path,
    *,
    canonical_workspace: Path | None,
    fallback_root: Path,
) -> Path:
    if canonical_workspace is None:
        return fallback_root
    lexical_path = Path(os.path.abspath(path))
    lexical_workspace = Path(os.path.abspath(canonical_workspace))
    try:
        lexical_path.relative_to(lexical_workspace)
    except ValueError:
        try:
            resolved_relative_to(lexical_path, lexical_workspace)
        except ValueError:
            # A genuine external --out remains independently rooted. The
            # artifact builder still rejects a reparse redirect outside it.
            return lexical_path.parent
    return lexical_workspace


def _plan_suite_run(
    args: argparse.Namespace,
    suite_path: Path,
    blocker_diagnostics: list[dict[str, str]] | None = None,
) -> CLIResult:
    diagnostics = list(blocker_diagnostics or [])
    return CLIResult(
        status=RunOutcome.PLANNED.value,
        exit_code=EXIT_OK,
        command=args.command,
        message="Suite execution plan validated; no entries were executed and no artifacts were written.",
        outcome=DomainOutcome("suite_run", RunOutcome.PLANNED, None),
        diagnostics=diagnostics,
    )


def _suite_artifacts(root: Path, paths: dict[str, Path]) -> list[ProducedArtifact]:
    return [
        build_produced_artifact(
            root,
            paths["json"],
            kind=ArtifactKind.SUITE_RUN_REPORT.value,
        )
    ]


def _suite_selector_details(args: argparse.Namespace) -> dict[str, Any]:
    if args.all:
        return {"kind": "all"}
    if args.tag:
        return {"kind": "tag", "tag": args.tag}
    return {"kind": "entry_id", "entry_ids": list(args.entry_ids or [])}


def handle_run_tests(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    test_spec = load_public_artifact(
        workspace / "reports" / "test_spec.json",
        ArtifactKind.TEST_SPEC,
    )
    selector_kind, selector_values = _test_selector(args)
    try:
        selected_case_ids = select_test_case_ids(
            dict(test_spec["data"]), selector_kind, selector_values
        )
    except ValueError as error:
        raise CLIError(str(error), EXIT_INPUT_ERROR, args.command) from error
    if not getattr(args, "run", False):
        try:
            warnings, review_items = validate_test_run_preflight(
                workspace,
                Path(args.executable) if args.executable else None,
                allow_placeholder_tests=args.allow_placeholder_tests,
            )
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
        blocker_diagnostics = [
            {
                "code": warning.code,
                "severity": "warning",
                "message": warning.message,
            }
            for warning in warnings
        ]
        blocker_diagnostics.extend(
            {
                "code": item.item_kind,
                "severity": item.severity if item.severity in {"info", "warning", "error"} else "warning",
                "message": item.description,
            }
            for item in review_items
        )
        return _plan_test_run(args, workspace, blocker_diagnostics)
    if not is_current_review_approved(workspace, ArtifactKind.TEST_SPEC):
        raise CLIError(
            "Current test_spec requires an approved review_record before execution.",
            EXIT_TESTS_BLOCKED,
            args.command,
        )
    try:
        warnings, review_items = validate_test_run_preflight(
            workspace,
            Path(args.executable) if args.executable else None,
            allow_placeholder_tests=False,
        )
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
    if review_items:
        raise CLIError(
            "Test execution is blocked until all review-required items are resolved.",
            EXIT_TESTS_BLOCKED,
            args.command,
        )
    try:
        report = execute_test_run(
            TestRunRequest(
                workspace=workspace,
                executable=Path(args.executable) if args.executable else None,
                timeout_seconds=args.timeout,
                allow_placeholder_tests=False,
                run_id=getattr(args, "run_id", None),
                selector_kind="case_id",
                selector_values=tuple(selected_case_ids),
            )
        )
    except (FileNotFoundError, OSError, PermissionError, ValueError) as exc:
        raise CLIError(str(exc), EXIT_TESTS_BLOCKED, args.command) from exc
    outcome, exit_code = classify_test_run(report, execution_requested=True)
    if report.run_paths is None:
        raise CLIError(
            "Test run did not publish its report path.",
            EXIT_INTERNAL_ERROR,
            args.command,
        )
    artifact = build_produced_artifact(
        workspace,
        report.run_paths.public_report,
        kind=ArtifactKind.TEST_RUN_REPORT.value,
    )
    return CLIResult(
        status=outcome.state.value,
        exit_code=exit_code,
        command=args.command,
        message="Test execution completed with the reported terminal outcome.",
        outcome=outcome,
        artifacts=[artifact],
        diagnostics=[
            {"code": item.code, "level": "warning", "message": item.message}
            for item in warnings
        ],
    )


def _test_selector(args: argparse.Namespace) -> tuple[str, list[str]]:
    if getattr(args, "all", False):
        return "all", []
    tag = getattr(args, "tag", None)
    if tag is not None:
        return "tag", [tag]
    return "case_id", list(getattr(args, "case_ids", None) or [])


def _plan_test_run(
    args: argparse.Namespace,
    workspace: Path,
    blocker_diagnostics: list[dict[str, str]] | None = None,
) -> CLIResult:
    run_id = getattr(args, "run_id", None)
    if run_id:
        try:
            validate_run_paths_available(workspace, run_id)
        except (OSError, ValueError) as error:
            raise CLIError(str(error), EXIT_INPUT_ERROR, args.command) from error
    diagnostics = list(blocker_diagnostics or [])
    return CLIResult(
        status=RunOutcome.PLANNED.value,
        exit_code=EXIT_OK,
        command=args.command,
        message="Test execution plan validated; no tests were executed and no artifacts were written.",
        outcome=DomainOutcome("test_run", RunOutcome.PLANNED, None),
        diagnostics=diagnostics,
    )






def _split_tags(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]






def handle_finalize_dossier(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    dossier = finalize_function_dossier(
        workspace,
        function_name=args.function,
        out=Path(args.out) if args.out else None,
        mvp_level=args.mvp_level,
    )
    payload = _dossier_payload(workspace, dossier, Path(args.out) if args.out else None)
    return CLIResult(
        status="dossier_finalized",
        exit_code=EXIT_OK,
        command=args.command,
        message="Function dossier finalized.",
        artifacts=_artifacts_from_explicit_outputs(
            workspace,
            _review_outputs(payload["reports"]),
        ),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )




def _dossier_payload(workspace: Path, dossier, out: Path | None = None) -> dict[str, Any]:
    canonical_reports = workspace / "reports"
    views = out if out else canonical_reports
    return {
        "function": dossier.function_name,
        "status": dossier.status,
        "readiness": dossier.readiness.to_dict(),
        "reports": {
            "function_dossier_json": str(canonical_reports / "function_dossier.json"),
            "function_dossier_md": str(views / "function_dossier.md"),
            "traceability_matrix": str(views / "traceability_matrix.csv"),
            "review_checklist": str(views / "review_checklist.md"),
            "unresolved_items": str(views / "unresolved_items.md"),
            "next_actions": str(views / "next_actions.md"),
        },
    }




def _is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, delete=True):
            return True
    except OSError:
        return False


def _existing_file(value: str | Path, label: str, command: str) -> Path:
    path = Path(value).expanduser()
    if not path.exists() or not path.is_file():
        raise CLIError(f"{label} file not found: {path}", EXIT_NOT_FOUND, command)
    return path.resolve()


def _existing_dir(value: str | Path, label: str, command: str) -> Path:
    path = Path(value).expanduser()
    if not path.exists() or not path.is_dir():
        raise CLIError(f"{label} directory not found: {path}", EXIT_NOT_FOUND, command)
    return path.resolve()


def _existing_path(value: str | Path, label: str, command: str) -> Path:
    path = Path(value).expanduser()
    if not path.exists():
        raise CLIError(f"{label} path not found: {path}", EXIT_NOT_FOUND, command)
    return path.resolve()


def _existing_source(workspace: Path, source: str, command: str) -> Path:
    path = Path(source)
    if not path.is_absolute():
        path = workspace / source
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError as exc:
        raise CLIError(f"source path is outside workspace: {resolved}", EXIT_INPUT_ERROR, command) from exc
    return _existing_file(resolved, "source", command)


def _workspace_from_args(workspace: str | None, dsw: Path) -> Path:
    if workspace:
        return _existing_dir(workspace, "workspace", "workspace")
    return dsw.parent.resolve()


def _resolve_dsw(workspace: Path, value: str | None, command: str) -> Path:
    if value:
        path = Path(value)
        if not path.is_absolute():
            path = workspace / value
        return _existing_file(path, "dsw", command)
    candidates = sorted(workspace.glob("*.dsw"))
    if len(candidates) != 1:
        raise CLIError(f"Expected exactly one .dsw under workspace, found {len(candidates)}.", EXIT_NOT_FOUND, command)
    return candidates[0].resolve()


def _write_json(path: Path, value: dict[str, Any], command: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        raise CLIError(f"Failed to write output file {path}: {exc}", EXIT_OUTPUT_ERROR, command) from exc


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_discovery_report(path: Path, value: dict[str, Any], command: str) -> None:
    if path.suffix.lower() == ".md":
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_dsw_discovery_markdown(value), encoding="utf-8")
        except OSError as exc:
            raise CLIError(f"Failed to write output file {path}: {exc}", EXIT_OUTPUT_ERROR, command) from exc
        return
    _write_json(path, value, command)


def _write_source_membership_report(path: Path, value: dict[str, Any], command: str) -> None:
    if path.suffix.lower() == ".md":
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_source_membership_markdown(value), encoding="utf-8")
        except OSError as exc:
            raise CLIError(f"Failed to write output file {path}: {exc}", EXIT_OUTPUT_ERROR, command) from exc
        return
    _write_json(path, value, command)


def _render_discovery_summary(value: dict[str, Any], output_path: Path | None) -> str:
    lines: list[str] = []
    for workspace in value.get("workspaces", []):
        lines.extend(
            [
                f"DSW parsed: {workspace.get('dsw_path', '')}",
                f"Projects: {len(workspace.get('projects', []))}",
                f"Dependencies: {len(workspace.get('dependencies', []))}",
                f"Warnings: {len(workspace.get('warnings', []))}",
            ]
        )
    if output_path is not None:
        lines.append(f"Output: {output_path}")
    return "\n".join(lines) + "\n"


def _render_source_membership_summary(value: dict[str, Any], output_path: Path | None) -> str:
    matches = value.get("matches", [])
    lines = [
        f"Source mapped: {value.get('source', {}).get('input', '')}",
        f"Matches: {len(matches)}",
    ]
    if len(matches) == 1:
        lines.append(f"Project: {matches[0].get('project_name', '')}")
        lines.append(f"Configurations: {len(matches[0].get('configurations', []))}")
    elif len(matches) > 1:
        lines.append("Multiple projects contain this source. Specify --project or --configuration.")
    lines.append(f"Warnings: {len(value.get('warnings', []))}")
    if output_path is not None:
        lines.append(f"Output: {output_path}")
    return "\n".join(lines) + "\n"


def _with_dsp_details(value: dict[str, Any]) -> dict[str, Any]:
    for workspace in value.get("workspaces", []):
        for project in workspace.get("projects", []):
            absolute = project.get("dsp_path_absolute")
            if not absolute:
                continue
            try:
                dsp = parse_dsp_project(Path(absolute), Path(workspace["root_dir"]))
            except OSError as exc:
                project["dsp_summary"] = {"error": str(exc)}
                continue
            files = dsp.files
            source_count = len([item for item in files if item.file_kind == "source"])
            header_count = len([item for item in files if item.file_kind == "header"])
            resource_count = len([item for item in files if item.file_kind == "resource"])
            defines = sorted({define for cfg in dsp.configurations for define in cfg.build_settings.defines})
            include_dirs = sorted({item.normalized for cfg in dsp.configurations for item in cfg.build_settings.include_dirs})
            project["dsp_summary"] = {
                "project_name": dsp.name,
                "configurations": [configuration.full_name for configuration in dsp.configurations],
                "source_file_count": source_count,
                "header_file_count": header_count,
                "resource_file_count": resource_count,
                "defines": defines,
                "include_dirs": include_dirs,
                "warnings": [warning.to_dict() for warning in dsp.warnings],
            }
    return value
