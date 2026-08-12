from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.reports.change_impact_markdown import render_change_impact_markdown
from unit_test_runner.reports.regression_selection_csv import render_regression_selection_csv
from unit_test_runner.reports.test_case_reconciliation_markdown import render_test_case_reconciliation_markdown
from unit_test_runner.workspace_artifacts import load_public_artifact, write_canonical_artifact

from .reanalysis_models import ChangeImpactReport, RegressionSelection, TestCaseReconciliationReport


def write_reanalysis_reports(
    workspace: Path | str,
    change_impact: ChangeImpactReport,
    reconciliation: TestCaseReconciliationReport,
    selection: RegressionSelection,
    updated_test_case_design: dict | None = None,
    *,
    candidate: Mapping[str, Any] | None = None,
) -> dict[str, Path]:
    reports = Path(workspace).resolve() / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    change_payload = change_impact.to_dict()
    reconciliation_payload = reconciliation.to_dict()
    selection_payload = selection.to_dict()
    paths = {
        "reanalysis_report_json": reports / "reanalysis_report.json",
        "change_impact_report_md": reports / "change_impact_report.md",
        "test_case_reconciliation_report_md": reports / "test_case_reconciliation_report.md",
        "regression_selection_csv": reports / "regression_selection.csv",
    }
    public_data = {
        "change_impact": _component_data(change_payload),
        "test_case_reconciliation": _component_data(reconciliation_payload),
        "regression_selection": _component_data(selection_payload),
    }
    if candidate is not None:
        public_data["candidate"] = dict(candidate)
    paths["reanalysis_report_json"] = write_canonical_artifact(
        workspace,
        ArtifactKind.REANALYSIS_REPORT,
        _reanalysis_subject(Path(workspace), change_impact),
        public_data,
    )
    paths["change_impact_report_md"].write_text(render_change_impact_markdown(change_payload), encoding="utf-8")
    paths["test_case_reconciliation_report_md"].write_text(render_test_case_reconciliation_markdown(reconciliation_payload), encoding="utf-8")
    paths["regression_selection_csv"].write_text(render_regression_selection_csv(selection_payload), encoding="utf-8", newline="")
    return paths


def _component_data(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("schema_version", None)
    function = result.pop("function", None)
    if isinstance(function, dict) and function.get("status") is not None:
        result["status"] = function["status"]
    return result


def _reanalysis_subject(workspace: Path, report: ChangeImpactReport) -> dict[str, str]:
    current = report.current_snapshot
    if current.source_path is None or not current.source_sha256:
        raise ValueError("reanalysis_report requires the current source path and SHA-256.")
    dossier_path = workspace.resolve() / "reports" / "function_dossier.json"
    dossier = load_public_artifact(dossier_path, ArtifactKind.FUNCTION_DOSSIER)
    subject = dossier.get("subject")
    subject_fields = {
        "source_path",
        "source_sha256",
        "function",
        "project",
        "configuration",
    }
    if not isinstance(subject, dict) or set(subject) != subject_fields:
        raise ValueError("Reanalysis requires an exact five-field function_dossier subject.")
    resolved = {field: str(subject[field]) for field in subject_fields}
    if any(not value for value in resolved.values()):
        raise ValueError("Reanalysis function_dossier subject fields must be non-empty.")
    stable_identity = {
        "source_path": current.source_path.as_posix(),
        "function": report.function_name,
    }
    if any(resolved[field] != value for field, value in stable_identity.items()):
        raise ValueError("Reanalysis current snapshot does not match the function_dossier subject.")
    resolved["source_sha256"] = current.source_sha256
    return resolved
