from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from unit_test_runner.contracts import ContractMode

from .models import TestSpec
from .path_safety import assert_safe_canonical_test_spec_path, lexical_absolute
from .repository import (
    TestSpecSnapshot,
    _exclusive_lock,
    canonical_json_bytes,
    load_test_spec_snapshot,
)


GENERATED_VIEW_NOTICE = "generated view; edits are not imported"


@dataclass(frozen=True)
class TestSpecViewExport(Mapping[str, Path]):
    markdown: Path
    csv: Path
    written: bool
    revision: int
    canonical_sha256: str

    def __getitem__(self, key: str) -> Path:
        if key == "markdown":
            return self.markdown
        if key == "csv":
            return self.csv
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(("markdown", "csv"))

    def __len__(self) -> int:
        return 2


def export_test_spec_views(
    spec: TestSpec,
    out_dir: Path,
    *,
    canonical_path: Path | None = None,
) -> TestSpecViewExport:
    """Export a caller object only while it is still the current canonical value."""
    out_dir = Path(out_dir)
    canonical_path = Path(canonical_path or out_dir / "test_spec.json")
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
    return _export_snapshot_views(
        snapshot,
        out_dir,
        canonical_path=canonical_path,
        require_current=True,
    )


def export_test_spec_snapshot_views(
    snapshot: TestSpecSnapshot,
    out_dir: Path,
    *,
    canonical_path: Path,
) -> TestSpecViewExport:
    """Render one saved snapshot without substituting a later canonical revision.

    Operation-specific output directories always receive this exact snapshot. Fixed
    ``reports/test_spec.{md,csv}`` views are ordered by the canonical lock; a saved
    snapshot that has already been superseded leaves newer fixed views untouched.
    """
    return _export_snapshot_views(
        snapshot,
        Path(out_dir),
        canonical_path=Path(canonical_path),
        require_current=False,
    )


def _export_snapshot_views(
    snapshot: TestSpecSnapshot,
    out_dir: Path,
    *,
    canonical_path: Path,
    require_current: bool,
) -> TestSpecViewExport:
    if hashlib.sha256(snapshot.raw_bytes).hexdigest() != snapshot.sha256:
        raise ValueError("TestSpec snapshot bytes do not match its SHA-256 digest.")
    canonical_path, _workspace = assert_safe_canonical_test_spec_path(
        canonical_path
    )
    out_dir = lexical_absolute(out_dir)
    paths = {
        "markdown": out_dir / "test_spec.md",
        "csv": out_dir / "test_spec.csv",
    }
    fixed_views = out_dir == canonical_path.parent
    if require_current or fixed_views:
        lock_path = canonical_path.with_name(f".{canonical_path.name}.lock")
        with _exclusive_lock(lock_path):
            current = load_test_spec_snapshot(
                canonical_path,
                mode=ContractMode.STRICT,
            )
            if current.sha256 != snapshot.sha256:
                if require_current:
                    raise ValueError(
                        "Caller-supplied test spec was superseded before view export."
                    )
                return _view_result(paths, snapshot, written=False)
            _write_views_atomically(paths, snapshot)
        return _view_result(paths, snapshot, written=True)
    _write_views_atomically(paths, snapshot)
    return _view_result(paths, snapshot, written=True)


def _view_result(
    paths: dict[str, Path],
    snapshot: TestSpecSnapshot,
    *,
    written: bool,
) -> TestSpecViewExport:
    return TestSpecViewExport(
        markdown=paths["markdown"],
        csv=paths["csv"],
        written=written,
        revision=snapshot.spec.revision,
        canonical_sha256=snapshot.sha256,
    )


def _write_views_atomically(
    paths: dict[str, Path],
    snapshot: TestSpecSnapshot,
) -> None:
    markdown_bytes = _render_markdown(
        snapshot.spec,
        snapshot.sha256,
    ).encode("utf-8")
    csv_bytes = _render_csv(snapshot.spec, snapshot.sha256)
    paths["markdown"].parent.mkdir(parents=True, exist_ok=True)
    temporary_paths = {
        kind: path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        for kind, path in paths.items()
    }
    try:
        _write_temporary(temporary_paths["markdown"], markdown_bytes)
        _write_temporary(temporary_paths["csv"], csv_bytes)
        os.replace(temporary_paths["markdown"], paths["markdown"])
        os.replace(temporary_paths["csv"], paths["csv"])
    finally:
        for temporary in temporary_paths.values():
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _write_temporary(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


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


def _render_csv(spec: TestSpec, canonical_sha: str) -> bytes:
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
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=fields)
    writer.writeheader()
    cases = [("executable", case) for case in spec.test_cases] + [
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
    return text.getvalue().encode("utf-8-sig")


def _escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
