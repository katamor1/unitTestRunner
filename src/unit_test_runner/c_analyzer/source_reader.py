from __future__ import annotations

import hashlib
from pathlib import Path

from ..encoding import read_text_with_encoding
from .source_models import SourceReadResult, SourceWarning


def read_source(path: Path | str) -> SourceReadResult:
    source_path = Path(path).expanduser().resolve()
    data = source_path.read_bytes()
    text, encoding, used_fallback = read_text_with_encoding(source_path)
    warnings = []
    if used_fallback:
        warnings.append(SourceWarning("encoding_fallback", f"Decoded source using fallback encoding: {encoding}"))
    return SourceReadResult(
        path=source_path,
        encoding=encoding,
        text=text,
        newline=_detect_newline(text),
        sha256=hashlib.sha256(data).hexdigest(),
        line_count=len(text.splitlines()) if text else 0,
        warnings=warnings,
    )


def _detect_newline(text: str) -> str | None:
    if "\r\n" in text:
        return "\r\n"
    if "\n" in text:
        return "\n"
    if "\r" in text:
        return "\r"
    return None
