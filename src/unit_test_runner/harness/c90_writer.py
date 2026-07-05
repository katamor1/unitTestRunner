from __future__ import annotations

import hashlib
import re
from pathlib import Path


C_CODE_ENCODING = "cp932"


def sanitize_identifier(value: str | None, fallback: str = "item") -> str:
    raw = value or fallback
    sanitized = re.sub(r"\W+", "_", raw)
    sanitized = sanitized.strip("_")
    if not sanitized:
        sanitized = fallback
    if sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    return sanitized


def include_guard_for(path: Path | str) -> str:
    name = Path(path).as_posix().upper()
    name = re.sub(r"[^A-Z0-9]+", "_", name).strip("_")
    return f"UTR_{name}_"


def write_c_file(path: Path, text: str, overwrite: bool = False) -> tuple[bool, str | None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return False, sha256_file(path)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    with path.open("w", encoding=C_CODE_ENCODING, newline="\r\n") as handle:
        handle.write(normalized)
        if not normalized.endswith("\n"):
            handle.write("\n")
    return True, sha256_file(path)


def write_text_file(path: Path, text: str, encoding: str = "utf-8", overwrite: bool = True) -> tuple[bool, str | None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return False, sha256_file(path)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding=encoding)
    return True, sha256_file(path)


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def is_c90_compatible_text(text: str) -> bool:
    checked = _mask_c_strings_and_block_comments(text)
    forbidden_patterns = [
        r"//",
        r"^\s*#\s*include\s*<\s*(?:stdint|stdbool)\.h\s*>",
        r"\bfor\s*\(\s*(?:const\s+|volatile\s+|signed\s+|unsigned\s+|short\s+|long\s+)*int\b",
        r"\binline\b",
    ]
    return not any(re.search(pattern, checked, flags=re.MULTILINE) for pattern in forbidden_patterns)


def _mask_c_strings_and_block_comments(text: str) -> str:
    result: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        next_char = text[index + 1] if index + 1 < length else ""
        if char in {'"', "'"}:
            quote = char
            result.append(" ")
            index += 1
            while index < length:
                current = text[index]
                result.append("\n" if current == "\n" else " ")
                if current == "\\" and index + 1 < length:
                    escaped = text[index + 1]
                    result.append("\n" if escaped == "\n" else " ")
                    index += 2
                    continue
                index += 1
                if current == quote:
                    break
            continue
        if char == "/" and next_char == "*":
            result.extend([" ", " "])
            index += 2
            while index < length:
                current = text[index]
                following = text[index + 1] if index + 1 < length else ""
                result.append("\n" if current == "\n" else " ")
                index += 1
                if current == "*" and following == "/":
                    result.append(" ")
                    index += 1
                    break
            continue
        result.append(char)
        index += 1
    return "".join(result)
