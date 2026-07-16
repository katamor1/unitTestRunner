from __future__ import annotations

import argparse
import os
import json
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any, Literal

from unit_test_runner import __version__
from unit_test_runner.contracts import ArtifactKind, RunOutcome
from unit_test_runner.build_probe import build_probe
from unit_test_runner.build_completion import analyze_build_errors, analyze_build_errors_from_workspace
from unit_test_runner.build_completion.completion_applier import apply_safe_completions
from unit_test_runner.build_completion.completion_models import BuildCompletionIterationReport, BuildCompletionPolicy, CompletionIteration
from unit_test_runner.build_completion.completion_report_writer import write_completion_reports
from unit_test_runner.c_analyzer import list_functions
from unit_test_runner.dsw_parser import discover_dsw_workspaces, parse_dsw as parse_dsw_workspace
from unit_test_runner.execution import (
    prepare_evidence_from_existing_run,
    prepare_test_execution_evidence,
    validate_run_paths_available,
    validate_test_run_preflight,
)
from unit_test_runner.path_utils import normalize_relative
from unit_test_runner.reanalysis import (
    reconcile_test_case_reports,
    reanalyze_function_workflow,
    select_regression_from_reports,
)
from unit_test_runner.suite import (
    SuiteRunPolicy,
    list_entries,
    register_workspace,
    remove_entry,
    run_suite,
    validate_suite_plan,
)
from unit_test_runner.reanalysis.reanalysis_models import ReanalysisPolicy
from unit_test_runner.dossier import (
    analyze_function_workflow,
    finalize_function_dossier,
    generate_build_workspace_from_reports,
    generate_build_workspace_from_workspace,
    generate_harness_skeleton_from_reports,
    generate_test_design_from_dossier_result,
    generate_test_design_from_reports_result,
    prepare_review_from_dossier,
)
from unit_test_runner.dossier.review_assessment import (
    assess_review_decisions,
    discover_review_snapshot,
)
from unit_test_runner.dossier.review_decision_models import ReviewResolution
from unit_test_runner.dossier.review_decision_repository import (
    InvalidReviewDecisionLedgerError,
    ReviewDecisionRepository,
    ReviewDecisionWriteStatus,
)
from unit_test_runner.execution.test_result_writer import current_producer_commit
from unit_test_runner.reports.dsw_markdown import render_dsw_discovery_markdown
from unit_test_runner.reports.source_membership_markdown import render_source_membership_markdown
from unit_test_runner.vc6 import discover_workspace, map_source_to_projects
from unit_test_runner.vc6.dsp_parser import parse_dsp as parse_dsp_project
from unit_test_runner.vc6.source_membership import map_source_membership
from unit_test_runner.test_spec import (
    TestSpecContractError,
    build_current_artifact_context,
    export_test_spec_snapshot_views,
    load_test_spec,
    load_test_spec_snapshot,
    update_test_spec_snapshot,
    validate_test_spec,
)
from unit_test_runner.contracts import ContractMode

from .errors import CLIError
from .artifacts import (
    ExpectedArtifact,
    ProducedArtifact,
    UnclaimableUntypedJsonError,
    build_expected_artifact,
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
    EXIT_TESTS_INCONCLUSIVE,
    EXIT_TESTS_TIMED_OUT,
)
from .outcomes import (
    DomainOutcome,
    classify_domain_state,
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
        "reanalyze-function": handle_reanalyze_function,
        "generate-harness-skeleton": handle_generate_harness_skeleton,
        "build-probe": handle_build_probe,
        "analyze-build-errors": handle_analyze_build_errors,
        "complete-build": handle_complete_build,
        "run-tests": handle_run_tests,
        "prepare-evidence": handle_prepare_evidence,
        "finalize-dossier": handle_finalize_dossier,
        "prepare-review": handle_prepare_review,
        "generate-test-design": handle_generate_test_design,
        "get-test-spec": handle_get_test_spec,
        "update-test-spec": handle_update_test_spec,
        "get-review-status": handle_get_review_status,
        "record-review-decision": handle_record_review_decision,
        "reconcile-test-cases": handle_reconcile_test_cases,
        "select-regression-tests": handle_select_regression_tests,
        "suite-register": handle_suite_register,
        "suite-list": handle_suite_list,
        "suite-remove": handle_suite_remove,
        "suite-run": handle_suite_run,
    }
    return handlers[args.command](args)


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
        data={
            "version": __version__,
            "python": {
                "version": platform.python_version(),
                "supported": supported,
            },
            "os": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
            },
            "cwd": str(Path.cwd()),
            "temp_dir": str(temp_dir),
            "checks": checks,
        },
        warnings=warnings,
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_discover_projects(args: argparse.Namespace) -> CLIResult:
    if args.dsw:
        workspace = _existing_dir(args.workspace, "workspace", args.command)
        dsw = _resolve_dsw(workspace, args.dsw, args.command)
        if args.with_dsp_details:
            result = _with_dsp_details(discover_dsw_workspaces(dsw).to_dict())
            if args.out:
                _write_discovery_report(Path(args.out), result, args.command)
            return CLIResult(
                status="ok",
                exit_code=EXIT_OK,
                command=args.command,
                message="Projects discovered.",
                data=result,
                human_output=_render_discovery_summary(result, Path(args.out) if args.out else None),
                artifacts=_optional_output_artifacts(args.out, ArtifactKind.DSW_DISCOVERY.value),
                outcome=DomainOutcome("command", RunOutcome.PASSED, None),
            )
        result = discover_workspace(workspace, dsw)
        if args.out:
            out = Path(args.out)
            if out.suffix.lower() == ".md":
                discovery = discover_dsw_workspaces(dsw)
                _write_discovery_report(out, discovery.to_dict(), args.command)
            else:
                _write_json(out, result, args.command)
        return CLIResult(
            status="ok",
            exit_code=EXIT_OK,
            command=args.command,
            message="Projects discovered.",
            data=result,
            legacy_payload=result,
            human_output=_render_discovery_summary(
                discover_dsw_workspaces(dsw).to_dict(),
                Path(args.out) if args.out else None,
            ),
            artifacts=_optional_output_artifacts(args.out, ArtifactKind.DSW_DISCOVERY.value),
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
        data=result,
        human_output=_render_discovery_summary(result, Path(args.out) if args.out else None),
        artifacts=_optional_output_artifacts(args.out, ArtifactKind.DSW_DISCOVERY.value),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_map_source(args: argparse.Namespace) -> CLIResult:
    dsw = _existing_file(args.dsw, "dsw", args.command)
    if args.workspace:
        workspace = _workspace_from_args(args.workspace, dsw)
        matches = map_source_to_projects(workspace, dsw, args.source, args.project)
        if args.configuration:
            matches = [match for match in matches if _legacy_configuration_matches(match, args.configuration)]
        payload = {"matches": matches}
        if args.out:
            _write_json(Path(args.out), payload, args.command)
        return CLIResult(
            status="ok",
            exit_code=EXIT_OK,
            command=args.command,
            message="Source mapping completed.",
            data=payload,
            legacy_payload=payload,
            artifacts=_optional_output_artifacts(args.out, ArtifactKind.SOURCE_MEMBERSHIP.value),
            outcome=DomainOutcome("command", RunOutcome.PASSED, None),
        )

    membership = map_source_membership(dsw, args.source, args.project, args.configuration)
    payload = membership.to_dict()
    if args.out:
        _write_source_membership_report(Path(args.out), payload, args.command)
    return CLIResult(
        status=membership.status,
        exit_code=EXIT_OK,
        command=args.command,
        message="Source mapping completed.",
        data=payload,
        human_output=_render_source_membership_summary(payload, Path(args.out) if args.out else None),
        artifacts=_optional_output_artifacts(args.out, ArtifactKind.SOURCE_MEMBERSHIP.value),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_list_functions(args: argparse.Namespace) -> CLIResult:
    source = _existing_file(args.source, "source", args.command)
    payload = {"functions": list_functions(source)}
    return CLIResult(
        status="ok",
        exit_code=EXIT_OK,
        command=args.command,
        message="Functions listed.",
        data=payload,
        legacy_payload=payload,
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_analyze_function(args: argparse.Namespace) -> CLIResult:
    if getattr(args, "reuse_existing_tests", False):
        if args.finalize_dossier or args.run_tests:
            raise CLIError(
                "--reuse-existing-tests cannot be combined with --finalize-dossier or --run-tests.",
                EXIT_INPUT_ERROR,
                args.command,
            )
        return _run_reanalysis(args)
    if args.apply_safe_completions and _phase_rank(args.phase) < _phase_rank("build"):
        raise CLIError("--apply-safe-completions requires --phase build or --phase execution.", EXIT_INPUT_ERROR, args.command)
    if args.run_tests and args.phase != "execution":
        raise CLIError("--run-tests requires --phase execution.", EXIT_INPUT_ERROR, args.command)
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
            apply_safe_completions=args.apply_safe_completions,
            run_tests=args.run_tests,
            phase=args.phase,
        )
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
        "build_workspace",
        "build_probe",
        "build_completion",
        "test_execution",
        "evidence",
        "quick_summary",
    ):
        if key in dossier:
            payload[key] = dossier[key]
    execution_outcome = DomainOutcome("command", RunOutcome.PASSED, None)
    execution_exit = EXIT_OK
    if args.run_tests and isinstance(payload.get("test_execution"), dict):
        execution = payload["test_execution"]
        try:
            state = RunOutcome(str(execution.get("status") or "error"))
        except ValueError:
            state = RunOutcome.ERROR
        execution_outcome, execution_exit = classify_domain_state(
            "test_run",
            state,
            green=(bool(execution.get("green")) if state is RunOutcome.PASSED else False),
        )
        execution["status"] = execution_outcome.state.value
        if isinstance(payload.get("evidence"), dict):
            payload["evidence"]["status"] = execution_outcome.state.value
    if args.finalize_dossier:
        final_dossier = finalize_function_dossier(Path(args.out), function_name=args.function)
        payload["review"] = _dossier_payload(Path(args.out), final_dossier)
        artifacts = _analysis_artifacts(Path(args.out), payload)
        return CLIResult(
            status="dossier_finalized",
            exit_code=execution_exit,
            command=args.command,
            message="Function analysis generated and finalized for dossier review.",
            data=payload,
            legacy_payload=payload,
            outcome=execution_outcome,
            artifacts=artifacts,
        )
    artifacts = _analysis_artifacts(Path(args.out), payload)
    return CLIResult(
        status=_analyze_status_for_phase(args.phase),
        exit_code=execution_exit,
        command=args.command,
        message="Function analysis generated. Use --finalize-dossier or finalize-dossier for dossier review packaging. Use --phase harness, build, or execution to run downstream steps.",
        data=payload,
        legacy_payload=payload,
        outcome=execution_outcome,
        artifacts=artifacts,
    )


def _phase_rank(phase: str) -> int:
    return {"analysis": 1, "design": 2, "harness": 3, "build": 4, "execution": 5}[phase]


def _analyze_status_for_phase(phase: str) -> str:
    if phase == "execution":
        return "evidence_prepared"
    if phase == "build":
        return "build_workspace_generated"
    if phase == "harness":
        return "harness_skeleton_generated"
    return "analysis_completed"


def _artifacts_from_explicit_outputs(
    root: Path,
    outputs: list[tuple[Path, str | None]],
) -> list[ProducedArtifact]:
    resolved_root = root.resolve()
    artifacts: list[ProducedArtifact] = []
    seen: set[Path] = set()
    for raw_path, kind in outputs:
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
        try:
            artifact = build_produced_artifact(
                resolved_root,
                resolved,
                kind=kind,
            )
        except UnclaimableUntypedJsonError:
            continue
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
        [(path, None if path.suffix.lower() == ".json" else kind)],
    )


def _analysis_artifacts(root: Path, payload: dict[str, Any]) -> list[ProducedArtifact]:
    root = root.resolve()
    reports = root / "reports"
    outputs: list[tuple[Path, str | None]] = [
        (root / "input" / "request.json", None),
        (reports / "source_digest.json", None),
        (reports / "source_digest.md", ArtifactKind.SOURCE_DIGEST.value),
        (reports / "function_location.json", None),
        (reports / "function_location.md", ArtifactKind.FUNCTION_LOCATION.value),
        (reports / "function_signature.json", None),
        (reports / "function_signature.md", ArtifactKind.FUNCTION_SIGNATURE.value),
        (reports / "global_access.json", None),
        (reports / "global_access.md", ArtifactKind.GLOBAL_ACCESS.value),
        (reports / "call_report.json", None),
        (reports / "call_report.md", ArtifactKind.CALL_REPORT.value),
        (reports / "dependency_policy.json", None),
        (reports / "dependency_policy.md", ArtifactKind.DEPENDENCY_POLICY.value),
        (reports / "coverage_design.json", None),
        (reports / "coverage_design.md", ArtifactKind.COVERAGE_DESIGN.value),
        (
            reports / "boundary_equivalence_candidates.json",
            None,
        ),
        (
            reports / "boundary_equivalence_candidates.md",
            ArtifactKind.BOUNDARY_CANDIDATES.value,
        ),
        (reports / "build_context.json", None),
        (reports / "function_dossier.json", None),
        (reports / "function_dossier.md", ArtifactKind.FUNCTION_DOSSIER.value),
        (reports / "quick_summary.json", None),
        (reports / "quick_summary.md", ArtifactKind.QUICK_SUMMARY.value),
        (root / "generated" / "prompt_pack.json", None),
    ]
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
        "test_spec": {
            "json": None,
            "markdown": ArtifactKind.TEST_SPEC.value,
            "csv": ArtifactKind.TEST_SPEC.value,
        },
        "harness_skeleton": {
            "json": None,
            "markdown": ArtifactKind.HARNESS_SKELETON_REPORT.value,
        },
        "build_workspace": {
            "json": None,
            "markdown": ArtifactKind.BUILD_WORKSPACE_REPORT.value,
        },
        "build_probe": {
            "json": None,
            "markdown": ArtifactKind.BUILD_PROBE_REPORT.value,
        },
        "build_completion": {
            "plan_json": None,
            "plan_markdown": ArtifactKind.BUILD_COMPLETION_PLAN.value,
            "iteration_json": None,
            "iteration_markdown": ArtifactKind.BUILD_COMPLETION_ITERATION.value,
        },
        "test_execution": {
            "json": ArtifactKind.TEST_EXECUTION_REPORT.value,
            "result_json": ArtifactKind.TEST_RESULT.value,
            "result_csv": ArtifactKind.TEST_RESULT.value,
            "stdout_log": "test_execution_log",
            "stderr_log": "test_execution_log",
            "combined_log": "test_execution_log",
        },
        "evidence": {
            "manifest_json": ArtifactKind.EVIDENCE_MANIFEST.value,
            "package_markdown": "evidence_package",
            "source_run_json": ArtifactKind.EVIDENCE_SOURCE_RUN.value,
        },
    }
    for section_name, fields in section_specs.items():
        section = payload.get(section_name)
        if not isinstance(section, dict):
            continue
        for field, kind in fields.items():
            value = section.get(field)
            if isinstance(value, str) and value:
                if (
                    section_name == "test_execution"
                    and not section.get("run_id")
                    and field in {"json", "result_json"}
                ):
                    kind = None
                if (
                    section_name == "evidence"
                    and not section.get("evidence_id")
                    and field in {"manifest_json", "source_run_json"}
                ):
                    kind = None
                outputs.append((Path(value), kind))
    return outputs


def _review_outputs(reports: dict[str, Any]) -> list[tuple[Path, str | None]]:
    field_kinds = {
        "function_dossier_json": None,
        "function_dossier_md": ArtifactKind.FUNCTION_DOSSIER.value,
        "dossier_manifest": None,
        "traceability_matrix": "review_artifact",
        "review_checklist": "review_artifact",
        "unresolved_items": "review_artifact",
        "next_actions": "review_artifact",
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


def _run_reanalysis(args: argparse.Namespace) -> CLIResult:
    dsw = _existing_file(args.dsw, "dsw", args.command)
    workspace = _workspace_from_args(args.workspace, dsw)
    source = normalize_relative(_existing_source(workspace, args.source, args.command), workspace)
    policy = ReanalysisPolicy(
        generate_updated_test_case_design=args.generate_updated_test_case_design,
        overwrite_test_case_design=args.overwrite_test_case_design,
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
            previous_test_case_design_path=(args.previous_test_spec or args.previous_test_case_design),
            previous_legacy_alias=bool(args.previous_test_case_design),
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
        data=payload,
        legacy_payload=payload,
        artifacts=_artifacts_from_explicit_outputs(
            Path(args.out).resolve(),
            _named_outputs(
                reports,
                {
                    "change_impact_report_json": None,
                    "change_impact_report_md": ArtifactKind.CHANGE_IMPACT.value,
                    "test_case_reconciliation_report_json": None,
                    "test_case_reconciliation_report_md": ArtifactKind.TEST_CASE_RECONCILIATION.value,
                    "regression_selection_json": None,
                    "regression_selection_csv": ArtifactKind.REGRESSION_SELECTION.value,
                    "updated_test_case_design_json": None,
                },
            ),
        ),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_generate_harness_skeleton(args: argparse.Namespace) -> CLIResult:
    spec_argument = args.test_spec or args.test_case_design
    report = generate_harness_skeleton_from_reports(
        _existing_file(args.function_signature, "function-signature", args.command),
        _existing_file(args.global_access, "global-access", args.command),
        _existing_file(args.call_report, "call-report", args.command),
        _existing_file(spec_argument, "test-spec", args.command),
        Path(args.out),
        overwrite=args.overwrite,
        dependency_policy_path=_existing_file(args.dependency_policy, "dependency-policy", args.command) if args.dependency_policy else None,
        allow_legacy_alias=bool(args.test_case_design),
    )
    payload = {
        "harness_skeleton": {
            "json": str(Path(args.out) / "reports" / "harness_skeleton_report.json"),
            "markdown": str(Path(args.out) / "reports" / "harness_skeleton_report.md"),
            "status": report.status,
        },
        "generated_file_count": len(report.generated_files),
    }
    output_root = Path(args.out).resolve()
    harness_outputs = [
        (
            output_root / "reports" / "harness_skeleton_report.json",
            None,
        ),
        (
            output_root / "reports" / "harness_skeleton_report.md",
            ArtifactKind.HARNESS_SKELETON_REPORT.value,
        ),
    ]
    return CLIResult(
        status="harness_skeleton_generated",
        exit_code=EXIT_OK,
        command=args.command,
        message="Harness skeleton generated.",
        data=payload,
        legacy_payload=payload,
        artifacts=_artifacts_from_explicit_outputs(output_root, harness_outputs),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_build_probe(args: argparse.Namespace) -> CLIResult:
    if args.workspace:
        workspace = _existing_dir(args.workspace, "workspace", args.command)
        _require_build_probe_workspace_reports(workspace, args.command)
        workspace_report, probe_report = generate_build_workspace_from_workspace(
            workspace,
            run_probe=args.run,
            dry_run=args.dry_run or not args.run,
            vcvars=args.vcvars,
            timeout_seconds=args.timeout,
            overwrite=args.overwrite,
        )
        return _build_probe_result(args.command, workspace, workspace_report, probe_report)

    explicit_inputs = [args.build_context, args.source_digest, args.harness_report]
    if any(explicit_inputs):
        missing = [
            label
            for label, value in [
                ("--build-context", args.build_context),
                ("--source-digest", args.source_digest),
                ("--harness-report", args.harness_report),
                ("--out", args.out),
            ]
            if not value
        ]
        if missing:
            raise CLIError("build-probe explicit mode requires: " + ", ".join(missing), EXIT_INPUT_ERROR, args.command)
        workspace_report, probe_report = generate_build_workspace_from_reports(
            _existing_file(args.build_context, "build-context", args.command),
            _existing_file(args.source_digest, "source-digest", args.command),
            _existing_file(args.harness_report, "harness-report", args.command),
            Path(args.out),
            run_probe=args.run,
            dry_run=args.dry_run or not args.run,
            vcvars=args.vcvars,
            timeout_seconds=args.timeout,
            overwrite=args.overwrite,
        )
        return _build_probe_result(args.command, Path(args.out), workspace_report, probe_report)

    if args.dossier:
        dossier = _existing_file(args.dossier, "dossier", args.command)
        payload = build_probe(dossier, args.vc6_bin, args.dry_run, args.vcvars)
        if args.out:
            _write_json(Path(args.out), payload, args.command)
        return CLIResult(
            status="build_probe_failed" if payload.get("returncode", 0) not in {0, None} else "ok",
            exit_code=EXIT_BUILD_PROBE_FAILED if payload.get("returncode", 0) not in {0, None} else EXIT_OK,
            command=args.command,
            message="Build probe completed.",
            data=payload,
            legacy_payload=payload,
            artifacts=_optional_output_artifacts(
                args.out,
                ArtifactKind.BUILD_PROBE_REPORT.value,
            ),
            outcome=DomainOutcome(
                "command",
                RunOutcome.FAILED
                if payload.get("returncode", 0) not in {0, None}
                else RunOutcome.PASSED,
                None,
            ),
        )

    raise CLIError("build-probe requires --workspace, --dossier, or explicit report inputs.", EXIT_INPUT_ERROR, args.command)


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
        data=payload,
        errors=errors,
        legacy_payload=payload,
        artifacts=_artifacts_from_explicit_outputs(
            workspace,
            _existing_explicit_outputs(
                [
                    (build_workspace_json, None),
                    (build_workspace_md, ArtifactKind.BUILD_WORKSPACE_REPORT.value),
                    (build_probe_json, None),
                    (build_probe_md, ArtifactKind.BUILD_PROBE_REPORT.value),
                ]
            ),
        ),
        outcome=DomainOutcome(
            "command",
            RunOutcome.PASSED
            if exit_code == EXIT_OK
            else RunOutcome.BLOCKED
            if exit_code == EXIT_ENVIRONMENT_WARNING
            else RunOutcome.FAILED,
            None,
        ),
    )


def handle_analyze_build_errors(args: argparse.Namespace) -> CLIResult:
    if args.workspace:
        workspace = _existing_dir(args.workspace, "workspace", args.command)
        plan, iteration = analyze_build_errors_from_workspace(workspace, source_root=Path(args.source_root) if args.source_root else None)
    else:
        missing = [
            label
            for label, value in [
                ("--build-workspace-report", args.build_workspace_report),
                ("--build-probe-report", args.build_probe_report),
                ("--call-report", args.call_report),
                ("--harness-report", args.harness_report),
                ("--out", args.out),
            ]
            if not value
        ]
        if missing:
            raise CLIError("analyze-build-errors requires --workspace or explicit inputs: " + ", ".join(missing), EXIT_INPUT_ERROR, args.command)
        workspace = Path(args.out).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        plan, iteration = analyze_build_errors(
            _read_json(_existing_file(args.build_workspace_report, "build-workspace-report", args.command)),
            _read_json(_existing_file(args.build_probe_report, "build-probe-report", args.command)),
            _read_json(_existing_file(args.call_report, "call-report", args.command)),
            _read_json(_existing_file(args.harness_report, "harness-report", args.command)),
            workspace,
            Path(args.source_root) if args.source_root else None,
        )
        write_completion_reports(workspace, plan, iteration)
    payload = _completion_payload(workspace, plan, iteration)
    return CLIResult(
        status="completion_plan_generated",
        exit_code=EXIT_OK,
        command=args.command,
        message="Build completion plan generated.",
        data=payload,
        legacy_payload=payload,
        artifacts=_completion_artifacts(workspace),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_complete_build(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    policy = BuildCompletionPolicy(
        apply_safe_completions=args.apply_safe_completions,
        run_probe_after_apply=args.run_probe_after_apply,
        max_iterations=args.max_iterations,
        generate_unknown_symbol_stubs=args.generate_unknown_symbol_stubs,
        overwrite_existing_generated_stubs=args.overwrite_existing_generated_stubs,
    )
    plan, iteration = analyze_build_errors_from_workspace(workspace, source_root=Path(args.source_root) if args.source_root else None, policy=policy)
    apply_result = None
    if args.apply_safe_completions:
        apply_result = apply_safe_completions(workspace, plan)
        first = iteration.iterations[0]
        first.applied_actions = apply_result.applied_actions
        first.skipped_actions = apply_result.skipped_actions
        first.generated_files = apply_result.generated_files
        first.progress = "not_run"
        iteration.warnings.extend(apply_result.warnings)
        iteration.stop_reason = "safe completions applied; build probe rerun is not executed unless explicitly enabled"
        iteration.next_recommended_action = "Run build-probe --workspace with --run when VC6 is available, or review generated stubs."
        write_completion_reports(workspace, plan, iteration)
    payload = _completion_payload(workspace, plan, iteration)
    if apply_result is not None:
        payload["applied_actions"] = apply_result.applied_actions
        payload["generated_files"] = [str(item) for item in apply_result.generated_files]
    return CLIResult(
        status="completion_applied" if args.apply_safe_completions else "completion_plan_generated",
        exit_code=EXIT_OK,
        command=args.command,
        message="Build completion processed.",
        data=payload,
        legacy_payload=payload,
        artifacts=_completion_artifacts(workspace),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def _completion_payload(workspace: Path, plan, iteration) -> dict[str, Any]:
    return {
        "build_completion_plan": {
            "json": str(workspace / "reports" / "build_completion_plan.json"),
            "markdown": str(workspace / "reports" / "build_completion_plan.md"),
            "status": plan.status,
        },
        "build_completion_iteration": {
            "json": str(workspace / "reports" / "build_completion_iteration_report.json"),
            "markdown": str(workspace / "reports" / "build_completion_iteration_report.md"),
            "status": iteration.status,
            "final_build_probe_status": iteration.final_build_probe_status,
        },
    }


def _completion_artifacts(workspace: Path) -> list[ProducedArtifact]:
    reports = workspace / "reports"
    return _artifacts_from_explicit_outputs(
        workspace,
        [
            (reports / "build_completion_plan.json", None),
            (reports / "build_completion_plan.md", ArtifactKind.BUILD_COMPLETION_PLAN.value),
            (reports / "build_completion_iteration_report.json", None),
            (
                reports / "build_completion_iteration_report.md",
                ArtifactKind.BUILD_COMPLETION_ITERATION.value,
            ),
        ],
    )


def handle_generate_test_design(args: argparse.Namespace) -> CLIResult:
    out = Path(args.out) if args.out else None
    if args.dossier:
        dossier = _existing_file(args.dossier, "dossier", args.command)
        design_result = generate_test_design_from_dossier_result(
            dossier,
            args.format,
            out,
        )
    else:
        missing = [
            label
            for label, value in [
                ("--function-signature", args.function_signature),
                ("--global-access", args.global_access),
                ("--call-report", args.call_report),
                ("--coverage-design", args.coverage_design),
                ("--boundary-candidates", args.boundary_candidates),
            ]
            if not value
        ]
        if missing:
            raise CLIError("generate-test-design requires --dossier or all explicit report inputs: " + ", ".join(missing), EXIT_INPUT_ERROR, args.command)
        design_result = generate_test_design_from_reports_result(
            _existing_file(args.function_signature, "function-signature", args.command),
            _existing_file(args.global_access, "global-access", args.command),
            _existing_file(args.call_report, "call-report", args.command),
            _existing_file(args.coverage_design, "coverage-design", args.command),
            _existing_file(args.boundary_candidates, "boundary-candidates", args.command),
            args.format,
            out,
        )
    result = design_result.output
    if isinstance(result, dict):
        design_value: str | dict[str, str] = {key: str(value) for key, value in result.items()}
        resolved_outputs = [Path(value).resolve() for value in result.values()]
        artifact_root = Path(os.path.commonpath([str(path) for path in resolved_outputs])).resolve()
        if artifact_root.is_file() or artifact_root.suffix:
            artifact_root = artifact_root.parent
    else:
        design_value = str(result)
        artifact_root = Path(result).resolve().parent
    canonical_workspace = (
        Path(args.function_signature).resolve().parent.parent
        if design_result.canonical_artifact is not None
        else None
    )
    artifacts = (
        [design_result.canonical_artifact]
        if design_result.canonical_artifact is not None
        else []
    )
    artifacts.extend(
        build_produced_artifact(
            _test_spec_view_artifact_root(
                path,
                canonical_workspace=canonical_workspace,
                fallback_root=artifact_root,
            ),
            path,
            kind=(
                "test_spec_markdown"
                if path.suffix.lower() == ".md"
                else "test_spec_csv"
            ),
        )
        for path in design_result.produced_view_paths
    )
    payload = {"test_spec": design_value}
    if design_result.saved_snapshot is not None:
        payload.update(
            {
                "saved_revision": design_result.saved_snapshot.spec.revision,
                "saved_sha256": design_result.saved_snapshot.sha256,
                "views_written_by_operation": bool(
                    design_result.view_export is not None
                    and design_result.view_export.written
                ),
            }
        )
    return CLIResult(
        status="test_spec_generated",
        exit_code=EXIT_OK,
        command=args.command,
        message="Test design generated.",
        data=payload,
        legacy_payload=payload,
        artifacts=artifacts,
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_get_test_spec(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    path = workspace / "reports" / "test_spec.json"
    try:
        snapshot = load_test_spec_snapshot(path, mode=ContractMode.STRICT)
        spec = snapshot.spec
        context = build_current_artifact_context(workspace, spec)
        violations = validate_test_spec(spec, current_context=context)
        if violations:
            raise TestSpecContractError(violations)
        digest = snapshot.sha256
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise CLIError(str(error), EXIT_INPUT_ERROR, args.command) from error
    return CLIResult(
        status="test_spec_loaded",
        exit_code=EXIT_OK,
        command=args.command,
        message="Canonical test specification loaded and validated.",
        data={
            "workspace": str(workspace),
            "path": "reports/test_spec.json",
            "spec_id": spec.spec_id,
            "revision": spec.revision,
            "sha256": digest,
            "test_spec": spec.to_payload(),
        },
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_update_test_spec(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    path = workspace / "reports" / "test_spec.json"
    patch_path = _existing_file(args.patch, "patch", args.command)
    try:
        current = load_test_spec(path, mode=ContractMode.STRICT)
        context = build_current_artifact_context(workspace, current)
        patch = _read_json(patch_path)
        updated_snapshot, artifact = update_test_spec_snapshot(
            path,
            patch,
            expected_revision=args.expected_revision,
            current_context=context,
        )
        updated = updated_snapshot.spec
        view_export = export_test_spec_snapshot_views(
            updated_snapshot,
            path.parent,
            canonical_path=path,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise CLIError(str(error), EXIT_INPUT_ERROR, args.command) from error
    return CLIResult(
        status="test_spec_updated",
        exit_code=EXIT_OK,
        command=args.command,
        message="Canonical test specification updated.",
        data={
            "workspace": str(workspace),
            "path": artifact.path,
            "spec_id": updated.spec_id,
            "revision": updated.revision,
            "sha256": artifact.sha256,
            "views_written_by_operation": view_export.written,
        },
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
        artifacts=[artifact]
        + (
            [
                build_produced_artifact(
                    workspace,
                    view_export["markdown"],
                    kind="test_spec_markdown",
                ),
                build_produced_artifact(
                    workspace,
                    view_export["csv"],
                    kind="test_spec_csv",
                ),
            ]
            if view_export.written
            else []
        ),
    )


def handle_get_review_status(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    try:
        snapshot = discover_review_snapshot(workspace)
        repository = _review_decision_repository(workspace, snapshot.items)
        decision_set = (
            repository.load().decision_set
            if repository.path.exists()
            else None
        )
        assessment = assess_review_decisions(
            snapshot.items,
            decision_set,
            workspace=workspace,
        )
        readiness = _review_readiness(workspace, assessment.review_complete)
    except (
        InvalidReviewDecisionLedgerError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise CLIError(str(error), EXIT_INPUT_ERROR, args.command) from error

    decisions_by_id = {
        decision.review_id: decision
        for decision in (decision_set.decisions if decision_set is not None else ())
    }
    assessments_by_id = {item.review_id: item for item in assessment.items}
    items: list[dict[str, Any]] = []
    for current_item in snapshot.items.items:
        item_assessment = assessments_by_id[current_item.review_id]
        decision = decisions_by_id.get(current_item.review_id)
        items.append(
            {
                "review_id": current_item.review_id,
                "category": current_item.category,
                "function_id": current_item.function_id,
                "case_id": current_item.case_id,
                "semantic_subject_key": current_item.semantic_subject_key,
                "subject_fingerprint": current_item.subject_fingerprint,
                "subject_artifacts": [
                    subject.to_dict()
                    for subject in current_item.subject_artifacts
                ],
                "status": item_assessment.status.value,
                "resolution": (
                    decision.resolution.value if decision is not None else None
                ),
                "reviewer": decision.reviewer if decision is not None else "",
                "rationale": decision.rationale if decision is not None else "",
                "decided_at": decision.decided_at if decision is not None else None,
                "current": not item_assessment.reasons,
                "blocked_reasons": list(item_assessment.reasons),
            }
        )

    return CLIResult(
        status="review_status_loaded",
        exit_code=EXIT_OK,
        command=args.command,
        message="Current review items, exact guards, decisions, and readiness loaded.",
        data={
            "workspace": str(workspace),
            "ledger_path": "reports/review_decisions.json",
            "ledger_revision": decision_set.revision if decision_set is not None else 0,
            "function_id": snapshot.function_id,
            "source_path": snapshot.source_path,
            "source_sha256": snapshot.source_sha256,
            "items": items,
            "orphaned_decision_ids": list(assessment.orphan_review_ids),
            "review_complete": assessment.review_complete,
            "readiness": readiness,
        },
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_record_review_decision(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    try:
        snapshot = discover_review_snapshot(workspace)
        repository = _review_decision_repository(workspace, snapshot.items)
        result = repository.record(
            review_id=args.review_id,
            resolution=ReviewResolution(args.resolution),
            reviewer=args.reviewer,
            rationale=args.rationale,
            decided_at=args.decided_at,
            expected_revision=args.expected_revision,
            expected_subject_fingerprint=args.expected_subject_fingerprint,
        )
    except (
        InvalidReviewDecisionLedgerError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise CLIError(str(error), EXIT_INPUT_ERROR, args.command) from error

    if result.status is not ReviewDecisionWriteStatus.WRITTEN:
        raise CLIError(
            result.message or f"Review decision was not written: {result.status.value}",
            EXIT_INPUT_ERROR,
            args.command,
        )
    if result.artifact is None or result.snapshot is None:
        raise CLIError(
            "Review decision write completed without an exact artifact snapshot.",
            EXIT_INTERNAL_ERROR,
            args.command,
        )

    return CLIResult(
        status="review_decision_recorded",
        exit_code=EXIT_OK,
        command=args.command,
        message="Review decision recorded against the current exact subjects.",
        data={
            "workspace": str(workspace),
            "ledger_path": result.artifact.path,
            "ledger_revision": result.current_revision,
            "review_id": args.review_id,
            "subject_fingerprint": args.expected_subject_fingerprint,
        },
        artifacts=[result.artifact],
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def _review_decision_repository(workspace: Path, current_items) -> ReviewDecisionRepository:
    return ReviewDecisionRepository(
        workspace,
        current_items=current_items,
        producer_version=__version__,
        producer_commit=current_producer_commit(),
    )


def _review_readiness(workspace: Path, review_complete: bool) -> dict[str, bool]:
    payload = _read_json(workspace / "reports" / "function_dossier.json")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Current function dossier is missing its data object")
    serialized = data.get("readiness")
    if not isinstance(serialized, dict):
        raise ValueError("Current function dossier is missing semantic readiness")
    return {
        "ready_for_review": bool(serialized.get("ready_for_review")),
        "review_complete": review_complete,
        "evidence_ready": bool(serialized.get("evidence_ready")),
        "test_green": bool(serialized.get("test_green")),
    }


def handle_reconcile_test_cases(args: argparse.Namespace) -> CLIResult:
    policy = ReanalysisPolicy(
        generate_updated_test_case_design=args.generate_updated_test_case_design,
        include_low_confidence_matches=args.include_low_confidence_matches,
    )
    try:
        result = reconcile_test_case_reports(
            _existing_file(args.previous_test_spec or args.previous_test_case_design, "previous-test-spec", args.command),
            _existing_file(args.previous_coverage_design, "previous-coverage-design", args.command),
            _existing_file(args.current_test_spec or args.current_test_case_design, "current-test-spec", args.command),
            _existing_file(args.current_coverage_design, "current-coverage-design", args.command),
            _existing_file(args.current_boundary_candidates, "current-boundary-candidates", args.command),
            Path(args.out),
            policy=policy,
            previous_legacy_alias=bool(args.previous_test_case_design),
            current_legacy_alias=bool(args.current_test_case_design),
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
    reports = {"test_case_reconciliation_report_json": str(result["out"])}
    if result.get("updated_test_case_design_path"):
        reports["updated_test_case_design_json"] = str(result["updated_test_case_design_path"])
    payload = {"reports": reports}
    return CLIResult(
        status="test_case_reconciliation_completed",
        exit_code=EXIT_OK,
        command=args.command,
        message="Test case reconciliation completed.",
        data=payload,
        legacy_payload=payload,
        artifacts=_artifacts_from_explicit_outputs(
            Path(args.out).resolve().parent,
            _named_outputs(
                reports,
                {
                    "test_case_reconciliation_report_json": None,
                    "updated_test_case_design_json": None,
                },
            ),
        ),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_select_regression_tests(args: argparse.Namespace) -> CLIResult:
    try:
        result = select_regression_from_reports(
            _existing_file(args.change_impact, "change-impact", args.command),
            _existing_file(args.reconciliation, "reconciliation", args.command),
            Path(args.out),
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
    key = "regression_selection_csv" if Path(args.out).suffix.lower() == ".csv" else "regression_selection_json"
    payload = {"reports": {key: str(result["out"])}}
    return CLIResult(
        status="regression_selection_completed",
        exit_code=EXIT_OK,
        command=args.command,
        message="Regression selection completed.",
        data=payload,
        legacy_payload=payload,
        artifacts=_optional_output_artifacts(args.out, ArtifactKind.REGRESSION_SELECTION.value),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_suite_register(args: argparse.Namespace) -> CLIResult:
    try:
        manifest = register_workspace(
            Path(args.suite),
            Path(args.workspace),
            tags=_split_tags(args.tags),
            source_root=Path(args.source_root) if args.source_root else None,
            dsw_path=Path(args.dsw) if args.dsw else None,
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
        data=payload,
        legacy_payload=payload,
        artifacts=_optional_output_artifacts(args.suite, ArtifactKind.SUITE_MANIFEST.value),
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
        message="Suite entries listed.",
        data=payload,
        legacy_payload=payload,
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_suite_remove(args: argparse.Namespace) -> CLIResult:
    try:
        manifest = remove_entry(Path(args.suite), args.entry_id)
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
        data=payload,
        legacy_payload=payload,
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
        fail_fast=args.fail_fast,
        require_green=args.require_green,
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
        data=payload,
        legacy_payload=payload,
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
        # A custom --out is an independently rooted produced artifact. Keep the
        # lexical parent as the trust boundary so build_produced_artifact still
        # rejects a symlink/reparse redirect that resolves outside that parent.
        return lexical_path.parent
    return lexical_workspace


def _plan_suite_run(
    args: argparse.Namespace,
    suite_path: Path,
    blocker_diagnostics: list[dict[str, str]] | None = None,
) -> CLIResult:
    root = suite_path.parent
    expected = [
        build_expected_artifact(
            root,
            root / "reports" / "suite_run_report.json",
            kind=ArtifactKind.SUITE_RUN_REPORT.value,
        ),
        build_expected_artifact(
            root,
            root / "reports" / "suite_run_report.md",
            kind=ArtifactKind.SUITE_RUN_REPORT.value,
        ),
        build_expected_artifact(
            root,
            root / "reports" / "suite_run_report.csv",
            kind=ArtifactKind.SUITE_RUN_REPORT.value,
        ),
    ]
    diagnostics = list(blocker_diagnostics or [])
    if getattr(args, "dry_run", False):
        diagnostics.append(
            {
                "code": "deprecated_dry_run_alias",
                "severity": "warning",
                "message": "--dry-run is deprecated; use --plan. No suite entries were executed and no reports were written.",
            }
        )
    return CLIResult(
        status=RunOutcome.PLANNED.value,
        exit_code=EXIT_OK,
        command=args.command,
        message="Suite execution plan validated; no entries were executed and no artifacts were written.",
        data={
            "mode": "plan",
            "suite": str(suite_path),
            "selector": _suite_selector_details(args),
            "execution_requested": False,
        },
        outcome=DomainOutcome("suite_run", RunOutcome.PLANNED, None),
        expected_artifacts=expected,
        diagnostics=diagnostics,
    )


def _suite_artifacts(root: Path, paths: dict[str, Path]) -> list[ProducedArtifact]:
    candidates = [
        (paths["json"], None),
        (paths["markdown"], ArtifactKind.SUITE_RUN_REPORT.value),
        (paths["csv"], ArtifactKind.SUITE_RUN_REPORT.value),
    ]
    return [
        build_produced_artifact(root, path, kind=kind)
        for path, kind in candidates
    ]


def _suite_selector_details(args: argparse.Namespace) -> dict[str, Any]:
    if args.all:
        return {"kind": "all"}
    if args.tag:
        return {"kind": "tag", "tag": args.tag}
    return {"kind": "entry_id", "entry_ids": list(args.entry_ids or [])}


def handle_run_tests(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
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
    report, manifest = prepare_test_execution_evidence(
        workspace,
        executable=Path(args.executable) if args.executable else None,
        run_tests=True,
        dry_run=False,
        timeout_seconds=args.timeout,
        allow_placeholder_tests=args.allow_placeholder_tests,
        treat_placeholder_as_inconclusive=args.treat_placeholder_as_inconclusive,
        run_id=getattr(args, "run_id", None),
    )
    payload = _evidence_payload(
        workspace,
        report,
        manifest,
        evidence_paths=getattr(manifest, "evidence_paths", None),
    )
    outcome, exit_code = classify_test_run(report, execution_requested=True)
    payload["test_execution"]["status"] = outcome.state.value
    payload["evidence"]["status"] = outcome.state.value
    return CLIResult(
        status=outcome.state.value,
        exit_code=exit_code,
        command=args.command,
        message="Test execution evidence prepared with the reported terminal outcome.",
        data=payload,
        legacy_payload=payload,
        outcome=outcome,
        artifacts=_run_artifacts(workspace, report, manifest),
    )


def _plan_test_run(
    args: argparse.Namespace,
    workspace: Path,
    blocker_diagnostics: list[dict[str, str]] | None = None,
) -> CLIResult:
    expected: list[ExpectedArtifact] = []
    run_id = getattr(args, "run_id", None)
    if run_id:
        try:
            run_paths = validate_run_paths_available(workspace, run_id)
            expected = [
                build_expected_artifact(
                    workspace,
                    run_paths.execution_report,
                    kind=ArtifactKind.TEST_EXECUTION_REPORT.value,
                ),
                build_expected_artifact(
                    workspace,
                    run_paths.result_json,
                    kind=ArtifactKind.TEST_RESULT.value,
                ),
                build_expected_artifact(
                    workspace,
                    run_paths.result_csv,
                    kind=ArtifactKind.TEST_RESULT.value,
                ),
            ]
        except (OSError, ValueError) as error:
            raise CLIError(str(error), EXIT_INPUT_ERROR, args.command) from error
    diagnostics = list(blocker_diagnostics or [])
    if getattr(args, "dry_run", False):
        diagnostics.append(
            {
                "code": "deprecated_dry_run_alias",
                "severity": "warning",
                "message": "--dry-run is deprecated; use --plan. No execution or evidence artifacts were written.",
            }
        )
    return CLIResult(
        status=RunOutcome.PLANNED.value,
        exit_code=EXIT_OK,
        command=args.command,
        message="Test execution plan validated; no tests were executed and no artifacts were written.",
        data={
            "mode": "plan",
            "workspace": str(workspace),
            "execution_requested": False,
            "requested_run_id": run_id,
        },
        outcome=DomainOutcome("test_run", RunOutcome.PLANNED, None),
        expected_artifacts=expected,
        diagnostics=diagnostics,
    )


def _run_artifacts(workspace: Path, report, manifest) -> list[ProducedArtifact]:
    run_paths = getattr(report, "run_paths", None)
    evidence_paths = getattr(manifest, "evidence_paths", None)
    candidates: list[tuple[Path, str]] = []
    if run_paths is not None:
        candidates.extend(
            [
                (run_paths.execution_report, ArtifactKind.TEST_EXECUTION_REPORT.value),
                (run_paths.result_json, ArtifactKind.TEST_RESULT.value),
                (run_paths.result_csv, ArtifactKind.TEST_RESULT.value),
                (run_paths.stdout_log, "test_execution_log"),
                (run_paths.stderr_log, "test_execution_log"),
                (run_paths.combined_log, "test_execution_log"),
            ]
        )
    if evidence_paths is not None:
        candidates.extend(
            [
                (evidence_paths.source_run, ArtifactKind.EVIDENCE_SOURCE_RUN.value),
                (evidence_paths.evidence_manifest, ArtifactKind.EVIDENCE_MANIFEST.value),
                (evidence_paths.evidence_package, "evidence_package"),
            ]
        )
    return [
        build_produced_artifact(workspace, path, kind=kind)
        for path, kind in candidates
        if path.is_file()
    ]


def legacy_execution_exit(
    status: Literal[
        "planned",
        "not_run",
        "passed",
        "failed",
        "blocked",
        "inconclusive",
        "cancelled",
        "timed_out",
        "timeout",
        "error",
    ],
    executed: bool,
) -> tuple[str, int]:
    normalized = "timed_out" if status == "timeout" else status
    if normalized == "passed" and executed:
        return "tests_passed", EXIT_OK
    if normalized == "failed":
        return "tests_failed", EXIT_TESTS_FAILED
    if normalized == "timed_out":
        return "tests_timed_out", EXIT_TESTS_TIMED_OUT
    if normalized in {"blocked", "inconclusive"}:
        if normalized == "blocked":
            return "tests_blocked", EXIT_TESTS_BLOCKED
        return "tests_blocked", EXIT_TESTS_INCONCLUSIVE
    if normalized == "cancelled":
        return "tests_cancelled", EXIT_TESTS_CANCELLED
    if normalized in {"planned", "not_run"} and not executed:
        return "evidence_prepared", EXIT_OK
    if normalized == "error":
        return "tests_error", EXIT_INTERNAL_ERROR
    return "tests_error", EXIT_INTERNAL_ERROR


def _split_tags(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def handle_prepare_evidence(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    try:
        paths, report, manifest = prepare_evidence_from_existing_run(
            workspace,
            run_id=getattr(args, "run_id", None),
        )
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise CLIError(str(exc), EXIT_INPUT_ERROR, args.command) from exc
    payload = _evidence_payload(workspace, report, manifest, evidence_paths=paths)
    outcome, exit_code = classify_test_run(report, execution_requested=True)
    payload["test_execution"]["status"] = outcome.state.value
    payload["evidence"]["status"] = outcome.state.value
    return CLIResult(
        status=outcome.state.value,
        exit_code=exit_code,
        command=args.command,
        message="Evidence package prepared.",
        data=payload,
        legacy_payload=payload,
        outcome=outcome,
        artifacts=_evidence_artifacts(workspace, paths),
    )


def _evidence_artifacts(workspace: Path, paths) -> list[ProducedArtifact]:
    candidates = [
        (paths.source_run, ArtifactKind.EVIDENCE_SOURCE_RUN.value),
        (paths.evidence_manifest, ArtifactKind.EVIDENCE_MANIFEST.value),
        (paths.evidence_package, "evidence_package"),
    ]
    return [
        build_produced_artifact(workspace, path, kind=kind)
        for path, kind in candidates
        if path.is_file()
    ]


def handle_finalize_dossier(args: argparse.Namespace) -> CLIResult:
    workspace = _existing_dir(args.workspace, "workspace", args.command)
    dossier = finalize_function_dossier(
        workspace,
        function_name=args.function,
        out=Path(args.out) if args.out else None,
        mvp_level=args.mvp_level,
        strict_schema_version=args.strict_schema_version,
    )
    payload = _dossier_payload(workspace, dossier, Path(args.out) if args.out else None)
    artifact_root = Path(args.out).resolve() if args.out else workspace
    return CLIResult(
        status="dossier_finalized",
        exit_code=EXIT_OK,
        command=args.command,
        message="Function dossier finalized.",
        data=payload,
        legacy_payload=payload,
        artifacts=_artifacts_from_explicit_outputs(
            artifact_root,
            _review_outputs(payload["reports"]),
        ),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def handle_prepare_review(args: argparse.Namespace) -> CLIResult:
    dossier = _existing_file(args.dossier, "dossier", args.command)
    paths = prepare_review_from_dossier(dossier, Path(args.out) if args.out else None)
    payload = {"reports": {key: str(value) for key, value in paths.items()}}
    artifact_root = Path(args.out).resolve() if args.out else dossier.parent.parent.resolve()
    return CLIResult(
        status="review_prepared",
        exit_code=EXIT_OK,
        command=args.command,
        message="Review workflow artifacts prepared.",
        data=payload,
        legacy_payload=payload,
        artifacts=_artifacts_from_explicit_outputs(
            artifact_root,
            [
                (Path(path), None if Path(path).suffix.lower() == ".json" else "review_artifact")
                for path in paths.values()
            ],
        ),
        outcome=DomainOutcome("command", RunOutcome.PASSED, None),
    )


def _dossier_payload(workspace: Path, dossier, out: Path | None = None) -> dict[str, Any]:
    reports = out if out else workspace / "reports"
    return {
        "function": dossier.function_name,
        "status": dossier.status,
        "readiness": dossier.readiness.to_dict(),
        "reports": {
            "function_dossier_json": str(reports / "function_dossier.json"),
            "function_dossier_md": str(reports / "function_dossier.md"),
            "dossier_manifest": str(reports / "dossier_manifest.json"),
            "traceability_matrix": str(reports / "traceability_matrix.csv"),
            "review_checklist": str(reports / "review_checklist.md"),
            "unresolved_items": str(reports / "unresolved_items.md"),
            "next_actions": str(reports / "next_actions.md"),
        },
    }


def _evidence_payload(
    workspace: Path,
    report,
    manifest,
    *,
    evidence_paths=None,
) -> dict[str, Any]:
    execution_json = workspace / "reports" / "test_execution_report.json"
    result_json = workspace / "reports" / "test_result.json"
    result_csv = workspace / "reports" / "test_result.csv"
    execution_payload: dict[str, Any] = {
        "json": str(execution_json),
        "markdown": str(workspace / "reports" / "test_execution_report.md"),
        "result_json": str(result_json),
        "result_csv": str(result_csv),
        "status": report.status,
        "executed": report.executed,
    }
    if evidence_paths is not None:
        source_run_id = evidence_paths.source_run_id
        execution_json = (
            workspace / "runs" / source_run_id / "test_execution_report.json"
        )
        execution_payload = {
            "run_id": source_run_id,
            "json": str(execution_json),
            "result_json": str(execution_json.with_name("test_result.json")),
            "result_csv": str(execution_json.with_name("test_result.csv")),
            "status": report.status,
            "executed": report.executed,
        }
    manifest_path = (
        evidence_paths.evidence_manifest
        if evidence_paths is not None
        else workspace / "reports" / "evidence_manifest.json"
    )
    package_path = (
        evidence_paths.evidence_package
        if evidence_paths is not None
        else workspace / "reports" / "evidence_package.md"
    )
    evidence_id = evidence_paths.evidence_id if evidence_paths is not None else None
    return {
        "test_execution": execution_payload,
        "evidence": {
            "evidence_id": evidence_id,
            "manifest_json": str(manifest_path),
            "package_markdown": str(package_path),
            "status": manifest.summary.test_execution_status,
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


def _legacy_configuration_matches(match: dict[str, Any], requested: str) -> bool:
    requested_lower = requested.lower()
    candidates = [
        match.get("configuration"),
        match.get("configuration_full_name"),
    ]
    return any(isinstance(candidate, str) and (candidate == requested or candidate.lower() == requested_lower) for candidate in candidates)


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
