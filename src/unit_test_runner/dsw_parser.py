from __future__ import annotations

import re
from pathlib import Path

from .dsw_models import DswDependency, DswParseResult, DswParseWarning, DswProject, DswWorkspace
from .encoding import read_text_with_encoding
from .path_utils import resolve_vc6_path


FORMAT_RE = re.compile(r"Format Version\s+(?P<version>[0-9.]+)")
PROJECT_RE = re.compile(
    r'^Project:\s+"(?P<name>.+?)"\s*=\s*(?P<path>.+?)\s+-\s+Package\s+Owner=<(?P<owner>[^>]+)>\s*$'
)
DEP_RE = re.compile(r"^\s*Project_Dep_Name\s+(?P<name>.+?)\s*$")


def parse_dsw(path: Path | str) -> DswWorkspace:
    dsw_path = Path(path).expanduser().resolve()
    text, encoding, used_fallback = read_text_with_encoding(dsw_path)
    root_dir = dsw_path.parent
    warnings: list[DswParseWarning] = []
    if used_fallback:
        warnings.append(
            DswParseWarning(
                code="encoding_fallback",
                message=f"Decoded DSW using fallback encoding: {encoding}",
            )
        )

    format_version: str | None = None
    projects: list[DswProject] = []
    dependencies: list[DswDependency] = []
    current_project: str | None = None

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if format_version is None:
            version_match = FORMAT_RE.search(line)
            if version_match:
                format_version = version_match.group("version")

        if not stripped:
            continue

        if stripped.startswith("Project:"):
            match = PROJECT_RE.match(line)
            if not match:
                warnings.append(
                    DswParseWarning(
                        code="malformed_project_line",
                        message="Project line could not be parsed.",
                        line_number=line_number,
                        line_text=line,
                    )
                )
                current_project = None
                continue
            raw_path = match.group("path").strip()
            absolute = resolve_vc6_path(root_dir, raw_path)
            relative = _normalized_relative_path(raw_path)
            project = DswProject(
                name=match.group("name"),
                dsp_path_raw=raw_path,
                dsp_path=relative,
                dsp_path_absolute=absolute,
                package_owner=match.group("owner"),
                exists=absolute.exists() and absolute.is_file(),
                line_number=line_number,
            )
            projects.append(project)
            current_project = project.name
            if not project.exists:
                warnings.append(
                    DswParseWarning(
                        code="missing_dsp_file",
                        message=f"DSP file referenced by project {project.name} does not exist: {absolute}",
                        line_number=line_number,
                        line_text=line,
                    )
                )
            continue

        dep_match = DEP_RE.match(line)
        if dep_match:
            if current_project is None:
                warnings.append(
                    DswParseWarning(
                        code="dependency_without_project",
                        message="Project dependency was found outside a project block.",
                        line_number=line_number,
                        line_text=line,
                    )
                )
                continue
            dependencies.append(
                DswDependency(
                    from_project=current_project,
                    to_project=dep_match.group("name").strip(),
                    line_number=line_number,
                )
            )
            continue

        if stripped == "Global:":
            current_project = None
            continue

        if current_project is not None and not _is_known_ignored_line(stripped):
            warnings.append(
                DswParseWarning(
                    code="unknown_line",
                    message="Unknown line inside project block.",
                    line_number=line_number,
                    line_text=line,
                )
            )

    project_names = {project.name for project in projects}
    for dependency in dependencies:
        if dependency.to_project not in project_names:
            warnings.append(
                DswParseWarning(
                    code="dependency_unknown_project",
                    message=f"Dependency target project is not defined: {dependency.to_project}",
                    line_number=dependency.line_number,
                )
            )

    return DswWorkspace(
        path=dsw_path,
        root_dir=root_dir,
        format_version=format_version,
        projects=projects,
        dependencies=dependencies,
        warnings=warnings,
        encoding=encoding,
    )


def discover_dsw_workspaces(path: Path | str) -> DswParseResult:
    candidates = find_dsw_files(path)
    if not candidates:
        raise FileNotFoundError(f"No .dsw files found under {Path(path)}")
    return DswParseResult(workspaces=[parse_dsw(candidate) for candidate in candidates])


def find_dsw_files(path: Path | str) -> list[Path]:
    root = Path(path).expanduser()
    if root.is_file():
        return [root.resolve()] if root.suffix.lower() == ".dsw" else []
    if not root.exists() or not root.is_dir():
        return []
    candidates = [item.resolve() for item in root.rglob("*") if item.is_file() and item.suffix.lower() == ".dsw"]
    return sorted(candidates, key=lambda item: str(item).lower())


def _normalized_relative_path(raw_path: str) -> Path:
    clean = raw_path.strip().strip('"').replace("\\", "/")
    if clean.startswith("./"):
        clean = clean[2:]
    return Path(clean)


def _is_known_ignored_line(stripped: str) -> bool:
    if stripped.startswith("#"):
        return True
    if stripped.startswith("Microsoft Developer Studio Workspace File"):
        return True
    if stripped.startswith("Package=<"):
        return True
    return stripped in {
        "{{{",
        "}}}",
        "Begin Project Dependency",
        "End Project Dependency",
    }
