from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.test_spec.repository import resolve_workspace_subject_context
from unit_test_runner.workspace_artifacts import (
    WorkspaceRegenerationRequired,
    canonical_artifact_path,
    is_current_review_approved,
    load_public_artifact,
)

from .artifact_collector import collect_artifacts
from .dossier_models import FunctionDossier
from .dossier_validator import validate_artifacts
from .dossier_writer import write_dossier_reports
from .next_actions import build_next_actions
from .readiness import assess_readiness
from .review_workflow import build_review_items
from .summary_builder import build_summaries
from .traceability import build_traceability


def finalize_function_dossier(
    workspace: Path | str,
    function_name: str | None = None,
    out: Path | str | None = None,
    mvp_level: str = "auto",
) -> FunctionDossier:
    workspace = Path(workspace).resolve()
    analysis_dossier, existing_subject = _read_existing_dossier(workspace)
    artifacts, payloads, collection_warnings = collect_artifacts(workspace)
    function_name, source_path, validation_warnings, blocked_reasons = validate_artifacts(
        artifacts,
        payloads,
        function_name,
    )
    function_name = (
        function_name
        or _existing_function_name(analysis_dossier)
        or _optional_text(existing_subject.get("function"))
        or "unknown_function"
    )
    source_path = (
        source_path
        or _existing_source_path(analysis_dossier)
        or _optional_path(existing_subject.get("source_path"))
    )
    summaries = build_summaries(payloads)
    traceability = build_traceability(payloads)
    review_items, unresolved_items = build_review_items(payloads, artifacts)
    next_actions = build_next_actions(unresolved_items)
    contract_fields = _contract_fields(
        analysis_dossier,
        function_name=function_name,
        source_path=source_path,
        diagnostics=collection_warnings + validation_warnings,
        workspace=workspace,
        existing_subject=existing_subject,
    )
    execution_outcome = None
    provisional_readiness = assess_readiness(
        artifacts,
        blocked_reasons,
        unresolved_items,
        execution_outcome=execution_outcome,
    )
    _apply_mvp_override(provisional_readiness, mvp_level)
    dossier = FunctionDossier(
        function_name=function_name,
        source_path=source_path,
        workspace_root=workspace,
        status=_status_from_readiness(provisional_readiness),
        created_at=datetime.now(timezone.utc).isoformat(),
        artifact_index=artifacts,
        summaries=summaries,
        traceability=traceability,
        review_items=review_items,
        unresolved_items=unresolved_items,
        next_actions=next_actions,
        readiness=provisional_readiness,
        warnings=collection_warnings + validation_warnings,
        target=contract_fields["target"],
        project_membership=contract_fields["project_membership"],
        build_context=contract_fields["build_context"],
        function=contract_fields["function"],
        test_design=contract_fields["test_design"],
        diagnostics=contract_fields["diagnostics"],
        function_id=None,
        source_sha256=_dossier_source_sha256(
            workspace,
            existing_subject,
        ),
        schema_version="1.0.0",
    )
    # The workspace-only review check intentionally happens after this strict
    # current dossier exists. A crash here remains fail-closed.
    write_dossier_reports(workspace, dossier, out)
    final_readiness = _assess_current_workspace(
        workspace,
        artifacts,
        blocked_reasons,
        unresolved_items,
        execution_outcome=execution_outcome,
    )
    _apply_mvp_override(final_readiness, mvp_level)
    dossier.readiness = final_readiness
    dossier.status = _status_from_readiness(final_readiness)
    write_dossier_reports(workspace, dossier, out)
    return dossier


def _status_from_readiness(readiness) -> str:
    if readiness.blocked:
        return "blocked"
    if readiness.evidence_ready:
        return "evidence_ready"
    if readiness.ready_for_review:
        return "ready_for_review"
    return "partial"


def _read_existing_dossier(workspace: Path) -> tuple[dict, dict]:
    analysis_path = workspace / ".unit-test-runner" / "analysis_state.json"
    analysis_dossier: dict = {}
    if analysis_path.is_file():
        try:
            analysis_payload = json.loads(analysis_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise WorkspaceRegenerationRequired(
                "Workspace analysis state is unreadable; regenerate the workspace for v0.1."
            ) from error
        if (
            not isinstance(analysis_payload, dict)
            or analysis_payload.get("internal_format") != "analysis-state-v1"
        ):
            raise WorkspaceRegenerationRequired(
                "Workspace analysis state is invalid; regenerate the workspace for v0.1."
            )
        analysis_dossier = dict(analysis_payload)

    path = workspace / "reports" / "function_dossier.json"
    if not path.exists():
        return analysis_dossier, {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WorkspaceRegenerationRequired(
            "Workspace function_dossier is unreadable; regenerate the workspace for v0.1."
        ) from error
    if not isinstance(payload, dict):
        raise WorkspaceRegenerationRequired(
            "Workspace function_dossier root is invalid; regenerate the workspace for v0.1."
        )
    declared_kind = payload.get("artifact_kind")
    if declared_kind is not None:
        if declared_kind != ArtifactKind.FUNCTION_DOSSIER.value:
            raise WorkspaceRegenerationRequired(
                "Workspace function_dossier has the wrong artifact kind; "
                "regenerate the workspace for v0.1."
            )
        if payload.get("schema_version") != "1.0.0":
            raise WorkspaceRegenerationRequired(
                "Workspace function_dossier uses schema "
                f"{payload.get('schema_version')!r}; regenerate the workspace for v0.1."
            )
        current = load_public_artifact(path, ArtifactKind.FUNCTION_DOSSIER)
        data = current.get("data")
        subject = current.get("subject")
        if not isinstance(data, dict) or not isinstance(subject, dict):
            raise WorkspaceRegenerationRequired(
                "Workspace function_dossier is incomplete; regenerate the workspace for v0.1."
            )
        return analysis_dossier or dict(data), dict(subject)
    raise WorkspaceRegenerationRequired(
        "Workspace function_dossier uses the removed legacy shape; "
        "regenerate the workspace for v0.1."
    )


def _dict_field(payload: dict, key: str) -> dict:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _list_field(payload: dict, key: str) -> list:
    value = payload.get(key)
    return list(value) if isinstance(value, list) else []


def _existing_function_name(payload: dict) -> str | None:
    function = _dict_field(payload, "function")
    target = _dict_field(payload, "target")
    value = function.get("name") or target.get("function")
    return value if isinstance(value, str) and value else None


def _existing_source_path(payload: dict) -> Path | None:
    target = _dict_field(payload, "target")
    function = _dict_field(payload, "function")
    value = target.get("source") or function.get("source_path")
    return Path(value) if isinstance(value, str) and value else None


def _contract_fields(
    analysis_dossier: dict,
    function_name: str,
    source_path: Path | None,
    diagnostics,
    workspace: Path,
    existing_subject: dict,
) -> dict:
    target = _dict_field(analysis_dossier, "target")
    target.setdefault("source", source_path.as_posix() if source_path else "")
    target.setdefault("function", function_name)
    resolved_subject = resolve_workspace_subject_context(workspace)
    if resolved_subject is None:
        project = _optional_text(existing_subject.get("project"))
        configuration = _optional_text(existing_subject.get("configuration"))
        resolved_subject = (
            (project, configuration)
            if project is not None and configuration is not None
            else None
        )
    if resolved_subject is None:
        raise WorkspaceRegenerationRequired(
            "Cannot bind function_dossier project and full configuration; "
            "regenerate the workspace for v0.1."
        )
    target["project"], target["configuration"] = resolved_subject
    function = _dict_field(analysis_dossier, "function")
    function.setdefault("name", function_name)
    if source_path is not None:
        function.setdefault("source_path", source_path.as_posix())
    existing_diagnostics = _list_field(analysis_dossier, "diagnostics")
    if existing_diagnostics:
        diagnostic_payload = existing_diagnostics
    else:
        diagnostic_payload = [warning.to_dict() for warning in diagnostics]
    return {
        "target": target,
        "project_membership": _list_field(analysis_dossier, "project_membership"),
        "build_context": _dict_field(analysis_dossier, "build_context"),
        "function": function,
        "test_design": _dict_field(analysis_dossier, "test_design"),
        "diagnostics": diagnostic_payload,
    }


def _assess_current_workspace(
    workspace: Path,
    artifacts,
    blocked_reasons,
    unresolved_items,
    *,
    execution_outcome,
):
    load_public_artifact(
        canonical_artifact_path(workspace, ArtifactKind.FUNCTION_DOSSIER),
        ArtifactKind.FUNCTION_DOSSIER,
    )
    test_spec_path = canonical_artifact_path(workspace, ArtifactKind.TEST_SPEC)
    if test_spec_path.is_file():
        load_public_artifact(test_spec_path, ArtifactKind.TEST_SPEC)
    readiness = assess_readiness(
        artifacts,
        blocked_reasons,
        unresolved_items,
        execution_outcome=execution_outcome,
    )
    readiness.review_complete = is_current_review_approved(
        workspace,
        ArtifactKind.TEST_SPEC,
    )
    readiness.ready_for_execution = (
        readiness.ready_for_execution and readiness.review_complete
    )
    readiness.evidence_ready = (
        readiness.evidence_ready and readiness.review_complete
    )
    return readiness


def _apply_mvp_override(readiness, mvp_level: str) -> None:
    if mvp_level != "auto" and not readiness.blocked:
        readiness.mvp_level = mvp_level


def _dossier_source_sha256(
    workspace: Path,
    existing_subject: dict,
) -> str | None:
    source_digest_path = workspace / "reports" / "source_digest.json"
    if source_digest_path.is_file():
        try:
            payload = json.loads(source_digest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise WorkspaceRegenerationRequired(
                "Workspace source_digest is unreadable; regenerate the workspace for v0.1."
            ) from error
        if not isinstance(payload, dict):
            raise WorkspaceRegenerationRequired(
                "Workspace source_digest root is invalid; regenerate the workspace for v0.1."
            )
        data = payload.get("data") if "artifact_kind" in payload else payload
        source = data.get("source") if isinstance(data, dict) else None
        digest = source.get("sha256") if isinstance(source, dict) else None
        digest_text = _optional_text(digest)
        if digest_text is None:
            raise WorkspaceRegenerationRequired(
                "Workspace source_digest has no source SHA-256; regenerate the workspace for v0.1."
            )
        return digest_text

    spec_path = canonical_artifact_path(workspace, ArtifactKind.TEST_SPEC)
    if spec_path.is_file():
        spec = load_public_artifact(spec_path, ArtifactKind.TEST_SPEC)
        spec_sha256 = _optional_text(spec["subject"].get("source_sha256"))
        if spec_sha256 is not None:
            return spec_sha256

    return _optional_text(existing_subject.get("source_sha256"))


def _optional_text(value) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_path(value) -> Path | None:
    text = _optional_text(value)
    return Path(text) if text is not None else None
