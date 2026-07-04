from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..reports.source_digest_markdown import render_source_digest_markdown
from .masker import mask_source_text
from .preprocessor import scan_preprocessor
from .source_models import SourceDigest
from .source_reader import read_source
from .tokens import extract_tokens


def build_source_digest(source_path: Path | str, build_context: dict[str, Any] | None = None) -> SourceDigest:
    source = read_source(source_path)
    masked = mask_source_text(source.text, source.path)
    directives, includes, macros, preprocessor_warnings = scan_preprocessor(source.text, masked.masked_text, source.path, build_context)
    tokens = extract_tokens(masked.masked_text)
    return SourceDigest(
        source=source,
        masked_source=masked,
        directives=directives,
        includes=includes,
        macros=macros,
        tokens=tokens,
        warnings=source.warnings + masked.warnings + preprocessor_warnings,
    )


def write_source_digest(out_dir: Path | str, digest: SourceDigest) -> dict[str, Path]:
    root = Path(out_dir)
    reports = root / "reports"
    intermediate = root / "intermediate"
    reports.mkdir(parents=True, exist_ok=True)
    intermediate.mkdir(parents=True, exist_ok=True)
    masked_path = intermediate / "masked_source.c"
    digest.masked_source_path = masked_path
    masked_path.write_text(digest.masked_source.masked_text, encoding="utf-8")
    json_path = reports / "source_digest.json"
    markdown_path = reports / "source_digest.md"
    payload = digest.to_dict(include_tokens=True)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_source_digest_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path, "masked_source": masked_path}
