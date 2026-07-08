from __future__ import annotations

from pathlib import Path


READ_ENCODINGS = ("utf-8-sig", "utf-8", "cp932", "shift_jis")
GENERATED_C_ENCODING = "cp932"
GENERATED_C_NEWLINE = "\r\n"


def decode_bytes_with_encoding(
    data: bytes,
    encodings: tuple[str, ...] = READ_ENCODINGS,
    errors: str = "strict",
) -> tuple[str, str, bool]:
    last_error: UnicodeDecodeError | None = None
    for index, encoding in enumerate(encodings):
        try:
            return data.decode(encoding), encoding, index > 0
        except UnicodeDecodeError as exc:
            last_error = exc
    if errors == "strict" and last_error:
        raise last_error
    fallback = encodings[-1] if encodings else "utf-8"
    return data.decode(fallback, errors=errors), fallback, True


def decode_bytes_auto(data: bytes, errors: str = "replace") -> str:
    text, _, _ = decode_bytes_with_encoding(data, errors=errors)
    return text


def read_text_with_encoding(path: Path | str) -> tuple[str, str, bool]:
    return decode_bytes_with_encoding(Path(path).read_bytes())


def read_text_auto(path: Path | str) -> str:
    text, _, _ = read_text_with_encoding(path)
    return text


def normalize_crlf(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\n", GENERATED_C_NEWLINE)


def write_generated_c_text(path: Path | str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(normalize_crlf(text).encode(GENERATED_C_ENCODING))
