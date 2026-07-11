from __future__ import annotations

from typing import Any

from . import debug_workspace_writer as base

_ORIGINAL_RENDER_DSP = base._render_dsp
_PATCHED = False


def apply_debug_workspace_link_compat() -> None:
    global _PATCHED
    if _PATCHED:
        return
    base._render_dsp = _render_dsp_with_link_inputs
    _PATCHED = True


def _render_dsp_with_link_inputs(workspace, dsp_path, report: dict[str, Any], project_name: str, function_name: str) -> str:
    text = _ORIGINAL_RENDER_DSP(workspace, dsp_path, report, project_name, function_name)
    additions = [*_dsp_library_path_args(report), *_dsp_link_library_args(report)]
    if not additions:
        return text
    lines: list[str] = []
    inserted = False
    for line in text.splitlines():
        if not inserted and line.startswith("# ADD LINK32") and not line.startswith("# ADD BASE LINK32"):
            lines.append(" ".join([line, *additions]))
            inserted = True
        else:
            lines.append(line)
    return "\r\n".join(lines) + ("\r\n" if text.endswith(("\r\n", "\n")) else "")


def _dsp_link_library_args(report: dict[str, Any]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    libraries = report.get("link_libraries", []) if isinstance(report, dict) else []
    for raw in sorted(libraries, key=_link_order):
        item = raw if isinstance(raw, dict) else raw.to_dict() if hasattr(raw, "to_dict") else {"path": raw}
        path = str(item.get("path") or "").strip().replace("/", "\\")
        if not path or path.lower() in seen:
            continue
        seen.add(path.lower())
        values.append(f'"{base._escape_option(path)}"')
    return values


def _dsp_library_path_args(report: dict[str, Any]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    paths = report.get("library_dirs", []) if isinstance(report, dict) else []
    for raw in paths:
        path = str(raw or "").strip().replace("/", "\\")
        if not path or path.lower() in seen:
            continue
        seen.add(path.lower())
        values.append(f'/libpath:"{base._escape_option(path)}"')
    return values


def _link_order(value: Any) -> int:
    if isinstance(value, dict):
        raw = value.get("link_order", 0)
    else:
        raw = getattr(value, "link_order", 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0
