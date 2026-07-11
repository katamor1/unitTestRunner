from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

from unit_test_runner.c_analyzer.call_models import LinkProvider
from unit_test_runner.dsw_parser import parse_dsw

from .coff_archive import LibrarySymbolCache
from .dsp_models import DspConfiguration, DspProject, PathLikeValue
from .dsp_parser import parse_dsp
from .link_context import LinkContext, LinkContextWarning, ResolvedLinkLibrary

_MACRO_PATTERNS = (
    re.compile(r"\$\(([^)]+)\)"),
    re.compile(r"\$\{([^}]+)\}"),
    re.compile(r"\(\$([A-Za-z_][A-Za-z0-9_]*)\)"),
    re.compile(r"%([^%]+)%"),
)
_MAX_EXPANSION_PASSES = 10


def resolve_link_context(
    workspace_root: Path | str,
    dsw_path: Path | str,
    project_name: str,
    configuration: str,
    *,
    environ: Mapping[str, str] | None = None,
    cache: LibrarySymbolCache | None = None,
) -> LinkContext:
    root = Path(workspace_root).resolve()
    environment = dict(os.environ if environ is None else environ)
    symbol_cache = cache or LibrarySymbolCache()
    workspace = parse_dsw(dsw_path)
    project_refs = {project.name.lower(): project for project in workspace.projects}
    selected_ref = project_refs.get(project_name.lower())
    if selected_ref is None:
        raise ValueError(f"Project not found in DSW: {project_name}")
    if not selected_ref.exists:
        raise FileNotFoundError(f"DSP file does not exist for project {selected_ref.name}: {selected_ref.dsp_path_absolute}")
    selected_project = parse_dsp(selected_ref.dsp_path_absolute, root)
    selected_config = _select_configuration(selected_project, configuration)
    if selected_config is None:
        raise ValueError(f"Configuration not found for {selected_project.name}: {configuration}")

    context = LinkContext()
    explicit_library_dirs = _resolve_library_dirs(selected_project, selected_config, environment, context.warnings)
    context.library_dirs.extend(explicit_library_dirs)
    environment_library_dirs = _environment_library_dirs(environment)
    seen_libraries: set[str] = set()

    for raw_library in selected_config.link_settings.libraries:
        expanded, unresolved = expand_link_path(
            raw_library,
            output_dir=_path_value(selected_config.link_settings.output_dir),
            intermediate_dir=_path_value(selected_config.link_settings.intermediate_dir),
            configuration=selected_config.full_name,
            project_name=selected_project.name,
            environ=environment,
        )
        if expanded is None:
            context.warnings.append(
                LinkContextWarning(
                    "link_library_macro_unresolved",
                    f"Unresolved macro in LINK32 library {raw_library}: {', '.join(unresolved)}",
                    selected_project.name,
                    selected_config.full_name,
                    raw_library,
                )
            )
            continue
        resolved = _resolve_explicit_library(
            expanded,
            selected_project.root_dir,
            explicit_library_dirs,
            environment_library_dirs,
        )
        if resolved is None:
            context.warnings.append(
                LinkContextWarning(
                    "link_library_not_found",
                    f"LINK32 library could not be resolved: {raw_library}",
                    selected_project.name,
                    selected_config.full_name,
                    raw_library,
                )
            )
            continue
        _append_library(context, resolved, "explicit_link32", selected_project.name, selected_config.full_name, seen_libraries)

    direct_dependencies = [dependency for dependency in workspace.dependencies if dependency.from_project.lower() == selected_ref.name.lower()]
    for dependency in direct_dependencies:
        dependency_ref = project_refs.get(dependency.to_project.lower())
        if dependency_ref is None or not dependency_ref.exists:
            context.warnings.append(
                LinkContextWarning(
                    "link_library_not_found",
                    f"Direct dependency project is unavailable: {dependency.to_project}",
                    dependency.to_project,
                    selected_config.full_name,
                    None,
                )
            )
            continue
        dependency_project = parse_dsp(dependency_ref.dsp_path_absolute, root)
        dependency_config = _matching_dependency_configuration(dependency_project, selected_config)
        if dependency_config is None:
            context.warnings.append(
                LinkContextWarning(
                    "dependency_configuration_not_found",
                    f"No matching {selected_config.platform} {selected_config.name} configuration exists for dependency {dependency_project.name}.",
                    dependency_project.name,
                    selected_config.full_name,
                    None,
                )
            )
            continue
        dependency_library = _resolve_dependency_output(
            dependency_project,
            dependency_config,
            environment,
            context.warnings,
        )
        if dependency_library is None:
            continue
        _append_library(
            context,
            dependency_library,
            "direct_dependency_project",
            dependency_project.name,
            dependency_config.full_name,
            seen_libraries,
        )

    _scan_libraries(context, symbol_cache)
    return context


def expand_link_path(
    value: str,
    *,
    output_dir: str | None,
    intermediate_dir: str | None,
    configuration: str,
    project_name: str,
    environ: Mapping[str, str],
) -> tuple[str | None, list[str]]:
    expanded = str(value).strip().strip('"')
    environment = dict(environ)

    def lookup(name: str) -> str | None:
        upper = name.upper()
        if upper == "OUTDIR":
            return output_dir
        if upper == "INTDIR":
            return intermediate_dir
        if upper == "CFG":
            return configuration
        if upper == "NAME":
            return project_name
        if name in environment:
            return environment[name]
        for key, item in environment.items():
            if key.upper() == upper:
                return item
        return None

    for _ in range(_MAX_EXPANSION_PASSES):
        previous = expanded
        for pattern in _MACRO_PATTERNS:
            expanded = pattern.sub(lambda match: lookup(match.group(1)) if lookup(match.group(1)) is not None else match.group(0), expanded)
        if expanded == previous:
            break
    unresolved = _unresolved_macros(expanded)
    if unresolved:
        return None, unresolved
    return expanded.replace("\\", "/"), []


def _resolve_library_dirs(
    project: DspProject,
    configuration: DspConfiguration,
    environ: Mapping[str, str],
    warnings: list[LinkContextWarning],
) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for value in configuration.link_settings.library_dirs:
        expanded, unresolved = expand_link_path(
            value.normalized,
            output_dir=_path_value(configuration.link_settings.output_dir),
            intermediate_dir=_path_value(configuration.link_settings.intermediate_dir),
            configuration=configuration.full_name,
            project_name=project.name,
            environ=environ,
        )
        if expanded is None:
            warnings.append(
                LinkContextWarning(
                    "link_library_macro_unresolved",
                    f"Unresolved macro in /libpath: {', '.join(unresolved)}",
                    project.name,
                    configuration.full_name,
                    value.raw,
                )
            )
            continue
        path = _absolute_from_project(expanded, project.root_dir)
        if not path.exists() or not path.is_dir():
            warnings.append(
                LinkContextWarning(
                    "link_library_not_found",
                    f"Library directory does not exist: {path}",
                    project.name,
                    configuration.full_name,
                    value.raw,
                )
            )
            continue
        key = _path_key(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _environment_library_dirs(environ: Mapping[str, str]) -> list[Path]:
    raw = ""
    for key, value in environ.items():
        if key.upper() == "LIB":
            raw = value
            break
    result: list[Path] = []
    seen: set[str] = set()
    for item in raw.split(";"):
        if not item.strip():
            continue
        path = Path(item.strip().strip('"')).expanduser()
        try:
            path = path.resolve()
        except OSError:
            continue
        if path.exists() and path.is_dir() and _path_key(path) not in seen:
            seen.add(_path_key(path))
            result.append(path)
    return result


def _resolve_explicit_library(raw: str, dsp_dir: Path, library_dirs: list[Path], environment_dirs: list[Path]) -> Path | None:
    path = Path(raw)
    candidates: list[Path]
    if path.is_absolute():
        candidates = [path]
    else:
        candidates = [dsp_dir / path]
        candidates.extend(directory / path for directory in library_dirs)
        candidates.extend(directory / path for directory in environment_dirs)
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists() and resolved.is_file() and resolved.suffix.lower() == ".lib":
            return resolved
    return None


def _resolve_dependency_output(
    project: DspProject,
    configuration: DspConfiguration,
    environ: Mapping[str, str],
    warnings: list[LinkContextWarning],
) -> Path | None:
    stages: list[tuple[str, PathLikeValue | None]] = [
        ("/implib", configuration.link_settings.import_library),
        ("/out", configuration.link_settings.output_file if _path_value(configuration.link_settings.output_file).lower().endswith(".lib") else None),
    ]
    for stage, value in stages:
        if value is None:
            continue
        candidate = _expanded_project_path(project, configuration, value.normalized, environ, warnings)
        if candidate is None:
            continue
        if candidate.exists() and candidate.is_file() and candidate.suffix.lower() == ".lib":
            return candidate
    output_dir = configuration.link_settings.output_dir
    if output_dir is not None:
        expanded, unresolved = expand_link_path(
            output_dir.normalized,
            output_dir=output_dir.normalized,
            intermediate_dir=_path_value(configuration.link_settings.intermediate_dir),
            configuration=configuration.full_name,
            project_name=project.name,
            environ=environ,
        )
        if expanded is None:
            warnings.append(
                LinkContextWarning(
                    "link_library_macro_unresolved",
                    f"Unresolved dependency output macro: {', '.join(unresolved)}",
                    project.name,
                    configuration.full_name,
                    output_dir.raw,
                )
            )
        else:
            directory = _absolute_from_project(expanded, project.root_dir)
            candidate = (directory / f"{project.name}.lib").resolve()
            if candidate.exists() and candidate.is_file():
                return candidate
    warnings.append(
        LinkContextWarning(
            "link_library_not_found",
            f"No existing output library was found for direct dependency {project.name}.",
            project.name,
            configuration.full_name,
            None,
        )
    )
    return None


def _expanded_project_path(
    project: DspProject,
    configuration: DspConfiguration,
    raw: str,
    environ: Mapping[str, str],
    warnings: list[LinkContextWarning],
) -> Path | None:
    expanded, unresolved = expand_link_path(
        raw,
        output_dir=_path_value(configuration.link_settings.output_dir),
        intermediate_dir=_path_value(configuration.link_settings.intermediate_dir),
        configuration=configuration.full_name,
        project_name=project.name,
        environ=environ,
    )
    if expanded is None:
        warnings.append(
            LinkContextWarning(
                "link_library_macro_unresolved",
                f"Unresolved dependency library macro: {', '.join(unresolved)}",
                project.name,
                configuration.full_name,
                raw,
            )
        )
        return None
    return _absolute_from_project(expanded, project.root_dir)


def _append_library(
    context: LinkContext,
    path: Path,
    source: str,
    project_name: str | None,
    configuration: str | None,
    seen: set[str],
) -> None:
    resolved = path.resolve()
    key = _path_key(resolved)
    if key in seen:
        return
    seen.add(key)
    context.libraries.append(
        ResolvedLinkLibrary(
            resolved,
            source,
            len(context.libraries),
            project_name=project_name,
            configuration=configuration,
            exists=True,
        )
    )


def _scan_libraries(context: LinkContext, cache: LibrarySymbolCache) -> None:
    provider_seen: set[tuple[str, str, str, int]] = set()
    for library in context.libraries:
        index = cache.scan(library.path)
        library.scan_status = index.scan_status
        if index.scan_status != "ok":
            context.warnings.append(
                LinkContextWarning(
                    "library_symbol_scan_failed",
                    f"Library symbol scan failed: {library.path}",
                    library.project_name,
                    library.configuration,
                    str(library.path),
                )
            )
            for warning in index.warnings:
                context.warnings.append(
                    LinkContextWarning(
                        warning.code,
                        warning.message,
                        library.project_name,
                        library.configuration,
                        str(library.path),
                    )
                )
            continue
        for warning in index.warnings:
            if warning.code == "linker_member_missing":
                continue
            context.warnings.append(
                LinkContextWarning(
                    warning.code,
                    warning.message,
                    library.project_name,
                    library.configuration,
                    str(library.path),
                )
            )
        for normalized_name, symbols in index.symbols_by_normalized_name.items():
            for symbol in symbols:
                key = (normalized_name, str(library.path), symbol.raw_name, library.link_order)
                if key in provider_seen:
                    continue
                provider_seen.add(key)
                context.providers_by_name.setdefault(normalized_name, []).append(
                    LinkProvider(
                        library=library.path,
                        symbol=symbol.raw_name,
                        provider_kind=symbol.provider_kind,
                        source=library.source,
                        link_order=library.link_order,
                        project_name=library.project_name,
                    )
                )
    for providers in context.providers_by_name.values():
        providers.sort(key=lambda item: item.link_order)


def _select_configuration(project: DspProject, requested: str) -> DspConfiguration | None:
    lowered = requested.strip().lower()
    for configuration in project.configurations:
        short = " ".join(item for item in (configuration.platform, configuration.name) if item)
        if configuration.full_name.lower() == lowered or short.lower() == lowered or (configuration.name or "").lower() == lowered:
            return configuration
    return None


def _matching_dependency_configuration(project: DspProject, target: DspConfiguration) -> DspConfiguration | None:
    target_platform = (target.platform or "").lower()
    target_name = (target.name or "").lower()
    for configuration in project.configurations:
        if (configuration.platform or "").lower() == target_platform and (configuration.name or "").lower() == target_name:
            return configuration
    return None


def _absolute_from_project(value: str, project_dir: Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (project_dir / path).resolve()


def _path_value(value: PathLikeValue | None) -> str:
    return value.normalized if value is not None else ""


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _unresolved_macros(value: str) -> list[str]:
    result: list[str] = []
    for pattern in _MACRO_PATTERNS:
        for name in pattern.findall(value):
            if name not in result:
                result.append(name)
    return result
