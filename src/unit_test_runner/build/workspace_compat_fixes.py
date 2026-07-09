from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import build_workspace_generator as bwg
from .build_models import BuildPathEntry

_ENV_INCLUDE_RE = re.compile(r"%[^%]+%")
_EXTERN_OR_EXTERN_MACRO_RE = re.compile(
    r"(?m)^\s*(?:extern|EXTERN)\s+(?P<prefix>[^;\n()]*?)(?P<name>[A-Za-z_]\w*)\s*(?P<array>(?:\[[^\]]*\])*)\s*;"
)


def _include_dir_text(raw: Any) -> str:
    if isinstance(raw, dict):
        value = raw.get("normalized") or raw.get("raw") or raw.get("path") or raw.get("absolute")
    else:
        value = raw
    if value is None:
        return ""
    return str(value).strip().strip('"').replace("\\", "/")


def _is_passthrough_include_dir(text: str) -> bool:
    return "$" in text or _ENV_INCLUDE_RE.search(text) is not None


def _include_dir_path(raw: Any, workspace_root: Path) -> Path | None:
    text = _include_dir_text(raw)
    if not text or _is_passthrough_include_dir(text):
        return None
    path = Path(text.replace("\\", "/"))
    return path if path.is_absolute() else workspace_root / path


def _include_dirs(output_root: Path, build_context: dict[str, Any]) -> list[BuildPathEntry]:
    entries = [
        BuildPathEntry("generated/include", Path("generated/include"), output_root / "generated" / "include", (output_root / "generated" / "include").exists(), "generated_include"),
        BuildPathEntry("generated/harness", Path("generated/harness"), output_root / "generated" / "harness", (output_root / "generated" / "harness").exists(), "generated_include"),
        BuildPathEntry("generated/stubs", Path("generated/stubs"), output_root / "generated" / "stubs", (output_root / "generated" / "stubs").exists(), "generated_include"),
        BuildPathEntry("generated/tests", Path("generated/tests"), output_root / "generated" / "tests", (output_root / "generated" / "tests").exists(), "generated_include"),
        BuildPathEntry("extracted/include", Path("extracted/include"), output_root / "extracted" / "include", (output_root / "extracted" / "include").exists(), "extracted_include"),
    ]
    workspace_root = Path(build_context.get("workspace_root") or "")
    for raw in build_context.get("include_dirs", []):
        normalized = _include_dir_text(raw)
        if not normalized:
            continue
        if _is_passthrough_include_dir(normalized):
            entries.append(BuildPathEntry(normalized, None, None, False, "dsp_include"))
            continue
        original = (workspace_root / normalized).resolve() if workspace_root.as_posix() else Path(normalized)
        entries.append(BuildPathEntry(normalized, Path("extracted") / normalized, original, original.exists(), "dsp_include"))
    return entries


def _makefile_include_arg(entry: BuildPathEntry) -> str:
    if _is_passthrough_include_dir(entry.raw):
        include_path = entry.raw
    elif Path(entry.raw).is_absolute():
        include_path = entry.raw
    else:
        workspace_path = entry.workspace_path or Path(entry.raw)
        include_path = (Path("..") / workspace_path).as_posix()
    include_path = include_path.replace("/", "\\")
    return f'/I"{include_path}"'


def apply_build_probe_compat_fixes() -> None:
    bwg._EXTERN_VARIABLE_RE = _EXTERN_OR_EXTERN_MACRO_RE
    bwg._include_dir_text = _include_dir_text
    bwg._is_passthrough_include_dir = _is_passthrough_include_dir
    bwg._include_dir_path = _include_dir_path
    bwg._include_dirs = _include_dirs
    bwg._makefile_include_arg = _makefile_include_arg
