from __future__ import annotations

import json
import shutil
from pathlib import Path

from unit_test_runner.reports.test_case_draft_csv import render_test_case_draft_csv
from unit_test_runner.reports.test_case_draft_markdown import render_test_case_draft_markdown

from .test_case_models import TestCaseDraftReport


def write_test_case_draft_report(out_dir: Path | str, report: TestCaseDraftReport) -> dict[str, Path]:
    reports = Path(out_dir)
    if reports.name != "reports":
        reports = reports / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    paths = {
        "json": reports / "test_case_draft.json",
        "markdown": reports / "test_case_draft.md",
        "csv": reports / "test_case_draft.csv",
    }
    paths["json"].write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["markdown"].write_text(render_test_case_draft_markdown(payload), encoding="utf-8")
    paths["csv"].write_text(render_test_case_draft_csv(payload), encoding="utf-8", newline="")
    return paths


def write_test_case_draft_format(target: Path, report: TestCaseDraftReport, output_format: str) -> Path | dict[str, Path]:
    payload = report.to_dict()
    if output_format == "all":
        root = target
        root.mkdir(parents=True, exist_ok=True)
        return {
            "json": _write_text(root / "test_case_draft.json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n"),
            "markdown": _write_text(root / "test_case_draft.md", render_test_case_draft_markdown(payload)),
            "csv": _write_text(root / "test_case_draft.csv", render_test_case_draft_csv(payload)),
        }
    if output_format == "json":
        return _write_text(target, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    if output_format == "md":
        return _write_text(target, render_test_case_draft_markdown(payload))
    if output_format == "csv":
        return _write_text(target, render_test_case_draft_csv(payload))
    raise ValueError(f"Unsupported test draft format: {output_format}")


def copy_existing_draft(source: Path, target: Path, output_format: str) -> Path:
    if output_format != "csv":
        raise ValueError(f"Cannot copy existing CSV draft as {output_format}.")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    return path
