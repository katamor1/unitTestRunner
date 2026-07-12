from __future__ import annotations

import csv
import json
from pathlib import Path

from unit_test_runner.contracts import ContractMode

from .models import TestSpec
from .repository import canonical_json_bytes, load_test_spec_snapshot


GENERATED_VIEW_NOTICE = "generated view; edits are not imported"


def export_test_spec_views(
    spec: TestSpec,
    out_dir: Path,
    *,
    canonical_path: Path | None = None,
) -> dict[str, Path]:
    out_dir = Path(out_dir)
    canonical_path = canonical_path or out_dir / "test_spec.json"
    if not canonical_path.is_file():
        raise FileNotFoundError(
            "Canonical test_spec.json must be saved before generated views are exported."
        )
    snapshot = load_test_spec_snapshot(
        canonical_path,
        mode=ContractMode.STRICT,
    )
    if canonical_json_bytes(spec) != canonical_json_bytes(snapshot.spec):
        raise ValueError(
            "Caller-supplied test spec does not match the canonical saved snapshot."
        )
    render_spec = snapshot.spec
    canonical_sha = snapshot.sha256
    out_dir.mkdir(parents=True, exist_ok=True)
    markdown = out_dir / "test_spec.md"
    csv_path = out_dir / "test_spec.csv"
    markdown.write_text(
        _render_markdown(render_spec, canonical_sha),
        encoding="utf-8",
        newline="",
    )
    _write_csv(csv_path, render_spec, canonical_sha)
    return {"markdown": markdown, "csv": csv_path}


def _render_markdown(spec: TestSpec, canonical_sha: str) -> str:
    lines = [
        "# テスト仕様（生成ビュー）",
        "",
        f"> **{GENERATED_VIEW_NOTICE}**",
        "",
        f"- spec_id: {spec.spec_id}",
        f"- revision: {spec.revision}",
        f"- canonical_sha256: {canonical_sha}",
        "",
        "| case_id | title | purpose | coverage |",
        "| --- | --- | --- | --- |",
    ]
    for case in spec.test_cases + spec.additional_case_candidates:
        coverage = ", ".join(
            str(item.get("coverage_id") or "")
            for item in case.get("coverage_links") or []
        )
        values = (
            str(case.get("test_case_id") or ""),
            str(case.get("title") or ""),
            str(case.get("purpose") or ""),
            coverage,
        )
        lines.append("| " + " | ".join(_escape_md(item) for item in values) + " |")
    return "\n".join(lines) + "\n"


def _write_csv(path: Path, spec: TestSpec, canonical_sha: str) -> None:
    fields = (
        "notice",
        "spec_id",
        "revision",
        "canonical_sha256",
        "test_case_id",
        "kind",
        "title",
        "purpose",
        "coverage_ids",
        "case_json",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        cases = [
            ("executable", case) for case in spec.test_cases
        ] + [
            ("candidate", case) for case in spec.additional_case_candidates
        ]
        if not cases:
            cases = [("", {})]
        for kind, case in cases:
            writer.writerow(
                {
                    "notice": GENERATED_VIEW_NOTICE,
                    "spec_id": spec.spec_id,
                    "revision": spec.revision,
                    "canonical_sha256": canonical_sha,
                    "test_case_id": case.get("test_case_id", ""),
                    "kind": kind,
                    "title": case.get("title", ""),
                    "purpose": case.get("purpose", ""),
                    "coverage_ids": ";".join(
                        str(item.get("coverage_id") or "")
                        for item in case.get("coverage_links") or []
                    ),
                    "case_json": json.dumps(case, ensure_ascii=False, sort_keys=True),
                }
            )


def _escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
