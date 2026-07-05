from __future__ import annotations

import json
from pathlib import Path

from ..reports.function_location_markdown import render_function_location_markdown
from .function_models import FunctionLocation
from .source_models import SourceDigest


def write_function_location(out_dir: Path | str, digest: SourceDigest, location: FunctionLocation) -> dict[str, Path]:
    root = Path(out_dir)
    reports = root / "reports"
    intermediate = root / "intermediate"
    reports.mkdir(parents=True, exist_ok=True)
    intermediate.mkdir(parents=True, exist_ok=True)
    json_path = reports / "function_location.json"
    markdown_path = reports / "function_location.md"
    slice_path = intermediate / "function_slice.c"
    payload = location.to_dict()
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_function_location_markdown(payload), encoding="utf-8")
    if location.selected_candidate:
        start = location.selected_candidate.full_range.start.offset
        end = location.selected_candidate.full_range.end.offset
        slice_path.write_text(digest.source.text[start:end], encoding="utf-8")
    else:
        slice_path.write_text("", encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path, "function_slice": slice_path}
