from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath


def normalized_relative_source(value: str) -> str:
    text = str(value).replace("\\", "/")
    path = PurePosixPath(text)
    if (
        not text
        or path.is_absolute()
        or ".." in path.parts
        or re.match(r"^[A-Za-z]:", text)
    ):
        raise ValueError(f"Expected normalized relative source path: {value}")
    return path.as_posix()


def is_absolute_source(value: str) -> bool:
    normalized = str(value).replace("\\", "/")
    return bool(re.match(r"^[A-Za-z]:/", normalized)) or Path(
        normalized
    ).is_absolute()


def resolved_absolute_source(value: Path | str) -> Path:
    return Path(os.path.abspath(Path(value))).resolve(strict=False)


def declared_source_matches_selected(
    declared: str,
    expected_relative: str,
    selected_source: Path,
) -> bool:
    if is_absolute_source(declared):
        return resolved_absolute_source(declared) == resolved_absolute_source(
            selected_source
        )
    try:
        return (
            normalized_relative_source(declared)
            == normalized_relative_source(expected_relative)
        )
    except ValueError:
        return False


def source_declarations_match(
    left: str,
    right: str,
    *,
    request_root: Path | None = None,
    request_relative: str | None = None,
) -> bool:
    left_absolute = is_absolute_source(left)
    right_absolute = is_absolute_source(right)
    if left_absolute and right_absolute:
        return resolved_absolute_source(left) == resolved_absolute_source(right)
    if not left_absolute and not right_absolute:
        try:
            return normalized_relative_source(left) == normalized_relative_source(
                right
            )
        except ValueError:
            return False
    if request_root is None or request_relative is None:
        return False
    try:
        expected_relative = normalized_relative_source(request_relative)
        relative_declaration = right if left_absolute else left
        absolute_declaration = left if left_absolute else right
        if normalized_relative_source(relative_declaration) != expected_relative:
            return False
    except ValueError:
        return False
    expected_absolute = resolved_absolute_source(
        Path(request_root) / Path(expected_relative)
    )
    return resolved_absolute_source(absolute_declaration) == expected_absolute
