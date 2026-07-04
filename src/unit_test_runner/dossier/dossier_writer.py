from __future__ import annotations

import json
from pathlib import Path

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
    payload = dossier.to_dict()
    paths["function_dossier_json"].write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["function_dossier_md"].write_text(render_function_dossier_markdown(dossier), encoding="utf-8")
    paths["dossier_manifest"].write_text(json.dumps({"schema_version": dossier.schema_version, "artifact_index": payload["artifact_index"], "readiness": payload["readiness"]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_dossier_traceability_csv(paths["traceability_matrix"], dossier.traceability)
    paths["review_checklist"].write_text(render_review_checklist_markdown(dossier.review_items), encoding="utf-8")
    paths["unresolved_items"].write_text(render_unresolved_items_markdown(dossier.unresolved_items), encoding="utf-8")
    paths["next_actions"].write_text(render_next_actions_markdown(dossier.next_actions), encoding="utf-8")
    return paths


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

    review_items = [DossierReviewItem(**item) for item in dossier_payload.get("review_items", [])]
    unresolved_items = [DossierUnresolvedItem(**item) for item in dossier_payload.get("unresolved_items", [])]
    next_actions = [DossierNextAction(**item) for item in dossier_payload.get("next_actions", [])]
    traceability = [TraceabilityLink(**item) for item in dossier_payload.get("traceability", [])]
    paths["review_checklist"].write_text(render_review_checklist_markdown(review_items), encoding="utf-8")
    paths["unresolved_items"].write_text(render_unresolved_items_markdown(unresolved_items), encoding="utf-8")
    paths["next_actions"].write_text(render_next_actions_markdown(next_actions), encoding="utf-8")
    write_dossier_traceability_csv(paths["traceability_matrix"], traceability)
    return paths
