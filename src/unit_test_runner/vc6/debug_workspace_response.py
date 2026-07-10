from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import debug_workspace_writer as base


# Capture the original functions before vc6.__init__ installs the compatibility
# wrappers. The original suite writer resolves write_vc6_debug_project through
# module globals, so once patched it automatically uses the project wrapper too.
_ORIGINAL_WRITE_PROJECT = base.write_vc6_debug_project
_ORIGINAL_WRITE_SUITE = base.write_vc6_debug_suite
_INCLUDE_OPTION_RE = re.compile(r'/I\s*(?:"[^"]*"|\S+)', re.IGNORECASE)


def vc6_cpp_options_path(dsp_path: Path | str) -> Path:
    return Path(dsp_path).with_suffix(".ini")


def write_vc6_debug_project(
    workspace: Path | str,
    build_workspace_report: Any | None = None,
    project_name: str | None = None,
) -> Path:
    """Generate a VC6 DSP and move bulk /I options into a response file.

    VC6 can silently truncate a very long ``# ADD CPP`` record when the project
    is loaded by the IDE. Keeping one include option per line in ``<project>.ini``
    leaves the DSP with a short ``# ADD CPP @\"<project>.ini\"`` record.
    """

    workspace_path = Path(workspace).resolve()
    dsp_path = _ORIGINAL_WRITE_PROJECT(workspace_path, build_workspace_report, project_name)
    report = base._report_payload(workspace_path, build_workspace_report)
    _rewrite_dsp_with_response_file(workspace_path, dsp_path, report)
    return dsp_path


def write_vc6_debug_suite(suite_path: Path | str, manifest: Any, out: Path | str | None = None):
    # _ORIGINAL_WRITE_SUITE calls the patched project writer through the base
    # module global, so every entry gets its own short DSP and response file.
    return _ORIGINAL_WRITE_SUITE(suite_path, manifest, out)


def _rewrite_dsp_with_response_file(workspace: Path, dsp_path: Path, report: dict[str, Any]) -> None:
    include_options = _include_options(dsp_path.parent, workspace, report)
    response_path = vc6_cpp_options_path(dsp_path)
    if not include_options:
        if response_path.exists():
            response_path.unlink()
        return

    base._write_vc6_text(response_path, "\r\n".join(include_options))
    text = dsp_path.read_text(encoding="cp932", errors="replace")
    response_record = f'# ADD CPP @"{response_path.name}"'
    output: list[str] = []
    inserted = False

    for line in text.splitlines():
        if line.startswith("# ADD CPP") and not line.startswith("# ADD BASE CPP") and _INCLUDE_OPTION_RE.search(line):
            output.append(_strip_include_options(line))
            output.append(response_record)
            inserted = True
        else:
            output.append(line)

    if not inserted:
        for index, line in enumerate(output):
            if line.startswith("# ADD CPP") and not line.startswith("# ADD BASE CPP"):
                output.insert(index + 1, response_record)
                inserted = True
                break

    if inserted:
        base._write_vc6_text(dsp_path, "\r\n".join(output))


def _include_options(dsp_dir: Path, workspace: Path, report: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in report.get("include_dirs", []):
        option = base._dsp_include_arg(dsp_dir, workspace, item)
        key = option.lower()
        if not option or key in seen:
            continue
        seen.add(key)
        result.append(option)
    return result


def _strip_include_options(line: str) -> str:
    stripped = _INCLUDE_OPTION_RE.sub("", line)
    return " ".join(stripped.split())
