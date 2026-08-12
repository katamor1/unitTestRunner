from __future__ import annotations

from pathlib import Path

from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.workspace_artifacts import write_canonical_artifact

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
        "function_dossier_json": workspace / "reports" / "function_dossier.json",
        "function_dossier_md": reports / "function_dossier.md",
        "traceability_matrix": reports / "traceability_matrix.csv",
        "review_checklist": reports / "review_checklist.md",
        "unresolved_items": reports / "unresolved_items.md",
        "next_actions": reports / "next_actions.md",
    }
    if dossier.schema_version != "1.0.0":
        raise ValueError(
            "function_dossier must be regenerated as schema version 1.0.0."
        )
    data_payload = dossier.to_dict(current=True)
    data_payload.pop("schema_version", None)
    paths["function_dossier_json"] = write_canonical_artifact(
        workspace,
        ArtifactKind.FUNCTION_DOSSIER,
        _current_subject(dossier),
        data_payload,
    )
    paths["function_dossier_md"].write_text(render_function_dossier_markdown(dossier), encoding="utf-8")
    write_dossier_traceability_csv(paths["traceability_matrix"], dossier.traceability)
    paths["review_checklist"].write_text(render_review_checklist_markdown(dossier.review_items), encoding="utf-8")
    paths["unresolved_items"].write_text(render_unresolved_items_markdown(dossier.unresolved_items), encoding="utf-8")
    paths["next_actions"].write_text(render_next_actions_markdown(dossier.next_actions, dossier.unresolved_items, dossier.artifact_index, dossier.function_name), encoding="utf-8")
    return paths


def _current_subject(dossier: FunctionDossier) -> dict[str, str]:
    target = dossier.target
    source_path = str(
        target.get("source")
        or (dossier.source_path.as_posix() if dossier.source_path else "")
    )
    function = str(target.get("function") or dossier.function_name or "")
    project = str(target.get("project") or "")
    configuration = str(target.get("configuration") or "")
    source_sha256 = str(dossier.source_sha256 or "")
    values = {
        "source_path": source_path,
        "source_sha256": source_sha256,
        "function": function,
        "project": project,
        "configuration": configuration,
    }
    if any(not value.strip() for value in values.values()):
        raise ValueError(
            "Current dossier requires exact source, function, project, full "
            "configuration, and source SHA-256 identity."
        )
    return values
