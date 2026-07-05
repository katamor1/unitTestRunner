from __future__ import annotations

import json
from pathlib import Path

from unit_test_runner.reports.test_case_design_csv import render_test_case_design_csv
from unit_test_runner.reports.test_case_design_markdown import render_test_case_design_markdown

from .test_case_models import TestCaseDesignReport


def write_test_case_design_report(out_dir: Path | str, report: TestCaseDesignReport) -> dict[str, Path]:
    reports = Path(out_dir)
    if reports.name != "reports":
        reports = reports / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    paths = {
        "json": reports / "test_case_design.json",
        "markdown": reports / "test_case_design.md",
        "csv": reports / "test_case_design.csv",
    }
    paths["json"].write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["markdown"].write_text(render_test_case_design_markdown(payload), encoding="utf-8")
    paths["csv"].write_text(render_test_case_design_csv(payload), encoding="utf-8", newline="")
    return paths


def write_test_case_design_format(target: Path, report: TestCaseDesignReport, output_format: str) -> Path | dict[str, Path]:
    payload = report.to_dict()
    if output_format == "all":
        root = target
        root.mkdir(parents=True, exist_ok=True)
        return {
            "json": _write_text(root / "test_case_design.json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n"),
            "markdown": _write_text(root / "test_case_design.md", render_test_case_design_markdown(payload)),
            "csv": _write_text(root / "test_case_design.csv", render_test_case_design_csv(payload)),
        }
    if output_format == "json":
        return _write_text(target, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    if output_format == "md":
        return _write_text(target, render_test_case_design_markdown(payload))
    if output_format == "csv":
        return _write_text(target, render_test_case_design_csv(payload))
    raise ValueError(f"Unsupported test design format: {output_format}")


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    return path
