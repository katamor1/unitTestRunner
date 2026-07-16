from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from unit_test_runner import __version__
from unit_test_runner.contracts import ArtifactKind, validate_payload
from unit_test_runner.execution.test_result_writer import current_producer_commit

from unit_test_runner.reports.function_dossier_markdown import render_function_dossier_markdown
from unit_test_runner.reports.next_actions_markdown import render_next_actions_markdown
from unit_test_runner.reports.review_checklist_markdown import render_review_checklist_markdown
from unit_test_runner.reports.traceability_csv import write_dossier_traceability_csv
from unit_test_runner.reports.unresolved_items_markdown import render_unresolved_items_markdown

from .dossier_models import FunctionDossier


def write_dossier_reports(workspace: Path | str, dossier: FunctionDossier, out: Path | str | None = None) -> dict[str, Path]:
    workspace = Path(workspace).resolve()
    reports = Path(out).resolve() if out else workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    paths = {
        "function_dossier_json": reports / "function_dossier.json",
        "function_dossier_md": reports / "function_dossier.md",
        "dossier_manifest": reports / "dossier_manifest.json",
        "traceability_matrix": reports / "traceability_matrix.csv",
        "review_checklist": reports / "review_checklist.md",
        "unresolved_items": reports / "unresolved_items.md",
        "next_actions": reports / "next_actions.md",
    }
    current = dossier.schema_version == "1.1.0"
    data_payload = dossier.to_dict(current=current)
    if current:
        dossier_payload = _current_dossier_payload(dossier, data_payload)
        manifest_payload = _current_manifest_payload(dossier, data_payload)
    else:
        dossier_payload = data_payload
        manifest_payload = {
            "schema_version": dossier.schema_version,
            "artifact_index": data_payload["artifact_index"],
            "readiness": data_payload["readiness"],
        }
    _atomic_json_write(paths["function_dossier_json"], dossier_payload)
    paths["function_dossier_md"].write_text(render_function_dossier_markdown(dossier), encoding="utf-8")
    _atomic_json_write(paths["dossier_manifest"], manifest_payload)
    write_dossier_traceability_csv(paths["traceability_matrix"], dossier.traceability)
    paths["review_checklist"].write_text(render_review_checklist_markdown(dossier.review_items), encoding="utf-8")
    paths["unresolved_items"].write_text(render_unresolved_items_markdown(dossier.unresolved_items), encoding="utf-8")
    paths["next_actions"].write_text(render_next_actions_markdown(dossier.next_actions, dossier.unresolved_items, dossier.artifact_index, dossier.function_name), encoding="utf-8")
    return paths


def _current_dossier_payload(
    dossier: FunctionDossier,
    dossier_data: Mapping[str, Any],
) -> dict[str, Any]:
    subject = _current_subject(dossier)
    data = dict(dossier_data)
    data.pop("schema_version", None)
    payload = {
        "artifact_kind": ArtifactKind.FUNCTION_DOSSIER.value,
        "schema_version": "1.1.0",
        "producer": _producer(),
        "subject": subject,
        "data": data,
        "extensions": {},
    }
    _validate_current_payload(ArtifactKind.FUNCTION_DOSSIER, payload)
    return payload


def _current_manifest_payload(
    dossier: FunctionDossier,
    dossier_data: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "artifact_kind": ArtifactKind.DOSSIER_MANIFEST.value,
        "schema_version": "1.1.0",
        "producer": _producer(),
        "subject": _current_subject(dossier),
        "data": {
            "artifact_index": dossier_data["artifact_index"],
            "readiness": dossier_data["readiness"],
        },
        "extensions": {},
    }
    _validate_current_payload(ArtifactKind.DOSSIER_MANIFEST, payload)
    return payload


def _current_subject(dossier: FunctionDossier) -> dict[str, str]:
    if not dossier.function_id or dossier.source_path is None or not dossier.source_sha256:
        raise ValueError("Current dossier requires exact function/source identity.")
    return {
        "function_id": dossier.function_id,
        "source_path": dossier.source_path.as_posix(),
        "source_sha256": dossier.source_sha256,
    }


def _producer() -> dict[str, str]:
    return {
        "name": "unit-test-runner",
        "version": __version__,
        "commit": current_producer_commit(),
    }


def _validate_current_payload(kind: ArtifactKind, payload: Mapping[str, Any]) -> None:
    violations = validate_payload(kind, payload)
    if violations:
        detail = "; ".join(
            f"{item.code} at {item.json_path}: {item.message}" for item in violations
        )
        raise ValueError(f"Invalid current {kind.value}: {detail}")


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    final_bytes = (
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(final_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_review_files_from_payload(dossier_payload: dict, out: Path | str) -> dict[str, Path]:
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "review_checklist": out / "review_checklist.md",
        "unresolved_items": out / "unresolved_items.md",
        "next_actions": out / "next_actions.md",
        "traceability_matrix": out / "traceability_matrix.csv",
    }
    from .dossier_models import DossierNextAction, DossierReviewItem, DossierUnresolvedItem, TraceabilityLink

    data = dossier_payload.get("data")
    if (
        dossier_payload.get("artifact_kind") == ArtifactKind.FUNCTION_DOSSIER.value
        and isinstance(data, dict)
    ):
        dossier_payload = data
    review_items = [DossierReviewItem(**item) for item in dossier_payload.get("review_items", [])]
    unresolved_items = [DossierUnresolvedItem(**item) for item in dossier_payload.get("unresolved_items", [])]
    next_actions = [DossierNextAction(**item) for item in dossier_payload.get("next_actions", [])]
    traceability = [TraceabilityLink(**item) for item in dossier_payload.get("traceability", [])]
    function_name = dossier_payload.get("function", {}).get("name") or dossier_payload.get("target", {}).get("function")
    paths["review_checklist"].write_text(render_review_checklist_markdown(review_items), encoding="utf-8")
    paths["unresolved_items"].write_text(render_unresolved_items_markdown(unresolved_items), encoding="utf-8")
    paths["next_actions"].write_text(render_next_actions_markdown(next_actions, unresolved_items, dossier_payload.get("artifact_index", []), function_name), encoding="utf-8")
    write_dossier_traceability_csv(paths["traceability_matrix"], traceability)
    return paths
