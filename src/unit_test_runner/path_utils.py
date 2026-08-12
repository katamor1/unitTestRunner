from __future__ import annotations

import os
import stat
from pathlib import Path


def as_posix_path(value: str) -> str:
    return value.replace("\\", "/")


def normalize_relative(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
        return as_posix_path(str(relative))
    except ValueError:
        return as_posix_path(str(path))


def resolved_relative_to(path: Path | str, root: Path | str) -> Path:
    return Path(path).resolve(strict=False).relative_to(
        Path(root).resolve(strict=False)
    )


def resolve_vc6_path(base_dir: Path, raw_path: str) -> Path:
    clean = raw_path.strip().strip('"')
    clean = clean.replace("\\", "/")
    return (base_dir / clean).resolve()


def normalize_include_dir(base_dir: Path, workspace_root: Path, raw_path: str) -> tuple[str, list[str]]:
    clean = raw_path.strip().strip('"').replace("\\", "/")
    unresolved = []
    parts = clean.split("$(")
    for part in parts[1:]:
        if ")" in part:
            unresolved.append(part.split(")", 1)[0])
    if unresolved:
        return clean, unresolved
    return normalize_relative((base_dir / clean).resolve(), workspace_root), unresolved


def validate_external_output_root(path: Path | str, source_root: Path | str) -> Path:
    lexical_output = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    lexical_source = Path(os.path.abspath(os.path.expanduser(os.fspath(source_root))))
    if _is_relative_to(lexical_output, lexical_source):
        raise ValueError(f"Output workspace must be outside the source root: {lexical_output}")
    if _has_symlink_or_reparse_component(lexical_output):
        raise ValueError(f"Output workspace must not traverse a symlink or reparse point: {lexical_output}")
    resolved_output = lexical_output.resolve(strict=False)
    resolved_source = lexical_source.resolve(strict=False)
    if _is_relative_to(resolved_output, resolved_source):
        raise ValueError(f"Output workspace must be outside the source root: {resolved_output}")
    return resolved_output


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _has_symlink_or_reparse_component(path: Path) -> bool:
    current = path
    while True:
        if os.path.lexists(current) and _is_symlink_or_reparse(current):
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _is_symlink_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
