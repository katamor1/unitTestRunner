from __future__ import annotations

from pathlib import Path


def as_posix_path(value: str) -> str:
    return value.replace("\\", "/")


def normalize_relative(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
        return as_posix_path(str(relative))
    except ValueError:
        return as_posix_path(str(path))


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
