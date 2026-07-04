from __future__ import annotations

from pathlib import Path


READ_ENCODINGS = ("utf-8-sig", "cp932", "shift_jis")
GENERATED_C_ENCODING = "cp932"
GENERATED_C_NEWLINE = "\r\n"


def read_text_auto(path: Path | str) -> str:
    data = Path(path).read_bytes()
    last_error: UnicodeDecodeError | None = None
    for encoding in READ_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return ""


def normalize_crlf(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\n", GENERATED_C_NEWLINE)


def write_generated_c_text(path: Path | str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(normalize_crlf(text).encode(GENERATED_C_ENCODING))
