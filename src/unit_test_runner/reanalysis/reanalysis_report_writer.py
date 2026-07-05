from __future__ import annotations

import json
from pathlib import Path

from unit_test_runner.reports.change_impact_markdown import render_change_impact_markdown
from unit_test_runner.reports.regression_selection_csv import render_regression_selection_csv
from unit_test_runner.reports.test_case_reconciliation_markdown import render_test_case_reconciliation_markdown

from .reanalysis_models import ChangeImpactReport, RegressionSelection, TestCaseReconciliationReport


def write_reanalysis_reports(
    workspace: Path | str,
    change_impact: ChangeImpactReport,
    reconciliation: TestCaseReconciliationReport,
    selection: RegressionSelection,
    updated_test_case_design: dict | None = None,
) -> dict[str, Path]:
    reports = Path(workspace).resolve() / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    change_payload = change_impact.to_dict()
    reconciliation_payload = reconciliation.to_dict()
    selection_payload = selection.to_dict()
    paths = {
        "change_impact_report_json": reports / "change_impact_report.json",
        "change_impact_report_md": reports / "change_impact_report.md",
        "test_case_reconciliation_report_json": reports / "test_case_reconciliation_report.json",
        "test_case_reconciliation_report_md": reports / "test_case_reconciliation_report.md",
        "regression_selection_json": reports / "regression_selection.json",
        "regression_selection_csv": reports / "regression_selection.csv",
    }
    _write_json(paths["change_impact_report_json"], change_payload)
    paths["change_impact_report_md"].write_text(render_change_impact_markdown(change_payload), encoding="utf-8")
    _write_json(paths["test_case_reconciliation_report_json"], reconciliation_payload)
    paths["test_case_reconciliation_report_md"].write_text(render_test_case_reconciliation_markdown(reconciliation_payload), encoding="utf-8")
    _write_json(paths["regression_selection_json"], selection_payload)
    paths["regression_selection_csv"].write_text(render_regression_selection_csv(selection_payload), encoding="utf-8", newline="")
    if updated_test_case_design is not None:
        paths["updated_test_case_design_json"] = reports / "updated_test_case_design.json"
        _write_json(paths["updated_test_case_design_json"], updated_test_case_design)
    return paths


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
