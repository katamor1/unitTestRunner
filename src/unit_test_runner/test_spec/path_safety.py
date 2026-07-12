from __future__ import annotations

import os
import stat
from pathlib import Path


def lexical_absolute(path: Path | str) -> Path:
    return Path(os.path.abspath(Path(path)))


def assert_no_reparse_components(
    path: Path | str,
    root: Path | str,
    *,
    include_root: bool = True,
) -> Path:
    candidate = lexical_absolute(path)
    trusted_root = lexical_absolute(root)
    try:
        relative = candidate.relative_to(trusted_root)
    except ValueError as error:
        raise ValueError(f"Path escapes the trusted root: {candidate}") from error
    current = trusted_root
    if include_root:
        _assert_not_reparse(current)
    for part in relative.parts:
        current = current / part
        _assert_not_reparse(current)
    return candidate


def assert_safe_canonical_test_spec_path(path: Path | str) -> tuple[Path, Path]:
    candidate = lexical_absolute(path)
    if candidate.name != "test_spec.json" or candidate.parent.name != "reports":
        raise ValueError(
            "Canonical TEST_SPEC must be read from workspace reports/test_spec.json."
        )
    workspace = candidate.parent.parent
    expected = workspace / "reports" / "test_spec.json"
    if candidate != expected:
        raise ValueError("Canonical test_spec path is not lexically exact.")
    assert_no_reparse_components(candidate, workspace)
    return candidate, workspace


def _assert_not_reparse(path: Path) -> None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    is_junction = getattr(path, "is_junction", lambda: False)
    if path.is_symlink() or is_junction() or bool(attributes & reparse_flag):
        raise ValueError(f"Symlink or reparse-point path component is not allowed: {path}")
