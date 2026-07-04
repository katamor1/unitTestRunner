from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .artifact_collector import collect_artifacts
from .dossier_models import DossierGenerationPolicy, FunctionDossier
from .dossier_validator import validate_artifacts
from .dossier_writer import write_dossier_reports, write_review_files_from_payload
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
    strict_schema_version: bool = False,
    policy: DossierGenerationPolicy | None = None,
) -> FunctionDossier:
    workspace = Path(workspace).resolve()
    policy = policy or DossierGenerationPolicy(require_schema_version_match=strict_schema_version)
    analysis_dossier = _read_existing_dossier(workspace / "reports" / "function_dossier.json")
    artifacts, payloads, collection_warnings = collect_artifacts(workspace)
    function_name, source_path, validation_warnings, blocked_reasons = validate_artifacts(
        artifacts,
        payloads,
        function_name,
        strict_schema_version=policy.require_schema_version_match,
    )
    function_name = function_name or "unknown_function"
    summaries = build_summaries(payloads)
    traceability = build_traceability(payloads)
    review_items, unresolved_items = build_review_items(payloads)
    readiness = assess_readiness(artifacts, blocked_reasons, unresolved_items)
    if mvp_level != "auto" and not readiness.blocked:
        readiness.mvp_level = mvp_level
    next_actions = build_next_actions(unresolved_items)
    status = _status_from_readiness(readiness)
    contract_fields = _contract_fields(
        analysis_dossier,
        function_name=function_name,
        source_path=source_path,
        diagnostics=collection_warnings + validation_warnings,
    )
    dossier = FunctionDossier(
        function_name=function_name,
        source_path=source_path,
        workspace_root=workspace,
        status=status,
        created_at=datetime.now(timezone.utc).isoformat(),
        artifact_index=artifacts,
        summaries=summaries,
        traceability=traceability,
        review_items=review_items,
        unresolved_items=unresolved_items,
        next_actions=next_actions,
        readiness=readiness,
        warnings=collection_warnings + validation_warnings,
        target=contract_fields["target"],
        project_membership=contract_fields["project_membership"],
        build_context=contract_fields["build_context"],
        function=contract_fields["function"],
        test_design=contract_fields["test_design"],
        diagnostics=contract_fields["diagnostics"],
    )
    write_dossier_reports(workspace, dossier, out)
    return dossier


def prepare_review_from_dossier(dossier_path: Path | str, out: Path | str | None = None) -> dict[str, Path]:
    dossier_path = Path(dossier_path).resolve()
    payload = json.loads(dossier_path.read_text(encoding="utf-8"))
    target = Path(out).resolve() if out else dossier_path.parent
    return write_review_files_from_payload(payload, target)


def _status_from_readiness(readiness) -> str:
    if readiness.blocked:
        return "blocked"
    if readiness.evidence_ready:
        return "evidence_ready"
    if readiness.ready_for_review:
        return "ready_for_review"
    return "partial"


def _read_existing_dossier(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _dict_field(payload: dict, key: str) -> dict:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _list_field(payload: dict, key: str) -> list:
    value = payload.get(key)
    return list(value) if isinstance(value, list) else []


def _contract_fields(
    analysis_dossier: dict,
    function_name: str,
    source_path: Path | None,
    diagnostics,
) -> dict:
    target = _dict_field(analysis_dossier, "target")
    target.setdefault("source", source_path.as_posix() if source_path else "")
    target.setdefault("function", function_name)
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
