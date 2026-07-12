from __future__ import annotations

import json
from pathlib import Path

from unit_test_runner.reports.test_case_design_csv import render_test_case_design_csv
from unit_test_runner.reports.test_case_design_markdown import render_test_case_design_markdown

from .test_case_models import TestCaseDesignReport


def write_test_case_design_report(out_dir: Path | str, report: TestCaseDesignReport) -> dict[str, Path]:
    raise ValueError(
        "Legacy test_case_design writers are read-only compatibility APIs; save reports/test_spec.json through the test_spec repository and export views from it."
    )


def write_test_case_design_format(target: Path, report: TestCaseDesignReport, output_format: str) -> Path | dict[str, Path]:
    raise ValueError(
        "Legacy test_case_design writers cannot create alternate editable or generated contracts."
    )


def write_test_case_design_payload_format(target: Path, payload: dict, output_format: str) -> Path | dict[str, Path]:
    raise ValueError(
        "Legacy test_case_design writers cannot create alternate editable or generated contracts."
    )


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    return path
