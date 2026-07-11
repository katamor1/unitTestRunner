from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import Any

from . import build_workspace_generator as bwg
from .build_models import BuildDiagnostic, LinkLibraryEntry

_ORIGINAL_GENERATE_BUILD_WORKSPACE = bwg.generate_build_workspace
_ORIGINAL_RUN_VERIFICATION_BUILD = bwg.run_verification_build
_LINK_LIBRARIES: ContextVar[tuple[LinkLibraryEntry, ...]] = ContextVar("unit_test_runner_build_link_libraries", default=())
_LIBRARY_DIRS: ContextVar[tuple[Path, ...]] = ContextVar("unit_test_runner_build_library_dirs", default=())
_PATCHED = False


def apply_link_library_build_compat() -> None:
    global _PATCHED
    if _PATCHED:
        return
    bwg.generate_build_workspace = _generate_build_workspace_with_links
    bwg._render_makefile = _render_makefile_with_links
    bwg.run_verification_build = _run_verification_build_with_links
    _PATCHED = True


def _generate_build_workspace_with_links(*args, **kwargs):
    build_context = _argument(args, kwargs, 0, "build_context") or {}
    output_root = Path(_argument(args, kwargs, 3, "output_root")).resolve()
    diagnostics: list[BuildDiagnostic] = []
    link_libraries = _link_libraries(build_context, diagnostics)
    library_dirs = _library_dirs(build_context)
    library_token = _LINK_LIBRARIES.set(tuple(link_libraries))
    directory_token = _LIBRARY_DIRS.set(tuple(library_dirs))
    try:
        workspace_report, probe_report = _ORIGINAL_GENERATE_BUILD_WORKSPACE(*args, **kwargs)
        workspace_report.link_libraries = link_libraries
        workspace_report.library_dirs = library_dirs
        workspace_report.link_units = [unit.object_file for unit in workspace_report.compile_units] + [item.path for item in link_libraries]
        workspace_report.diagnostics.extend(diagnostics)
        bwg.write_build_reports(output_root, workspace_report, probe_report)
        return workspace_report, probe_report
    finally:
        _LINK_LIBRARIES.reset(library_token)
        _LIBRARY_DIRS.reset(directory_token)


def _render_makefile_with_links(compile_units, include_dirs, defines, compiler_options) -> str:
    objects = " ".join(bwg._makefile_workspace_file(unit.object_file) for unit in compile_units)
    library_dirs = list(_LIBRARY_DIRS.get())
    link_libraries = list(_LINK_LIBRARIES.get())
    libpaths = " ".join(f'/LIBPATH:"{_windows_path(path)}"' for path in library_dirs)
    libraries = " ".join(f'"{_windows_path(item.path)}"' for item in link_libraries)
    lines = [
        "# generated VC6 build probe Makefile",
        "CC=cl",
        "LINK=link",
        f"CFLAGS={' '.join(compiler_options)} {' '.join('/D\"' + item + '\"' for item in defines)} {' '.join(bwg._makefile_include_arg(item) for item in include_dirs)}",
        f"OBJS={objects}",
        f"LIBPATHS={libpaths}",
        f"LINK_LIBS={libraries}",
        "",
        "all: ..\\bin\\utr_probe.exe",
        "",
        "..\\bin\\utr_probe.exe: $(OBJS)",
        "\t$(LINK) /nologo /OPT:REF /OUT:$@ $(OBJS) $(LIBPATHS) $(LINK_LIBS)",
        "",
    ]
    for unit in compile_units:
        source = bwg._makefile_workspace_file(unit.source_file)
        obj = bwg._makefile_workspace_file(unit.object_file)
        lines.extend([f"{obj}: {source}", f"\t$(CC) $(CFLAGS) /Fo\"{obj}\" /c \"{source}\"", ""])
    return "\n".join(lines)


def _run_verification_build_with_links(
    output_root,
    compile_units,
    include_dirs,
    defines,
    compiler_options,
    cc=None,
    timeout_seconds=120,
    env_setup=None,
    **kwargs,
):
    return _ORIGINAL_RUN_VERIFICATION_BUILD(
        output_root,
        compile_units,
        include_dirs,
        defines,
        compiler_options,
        cc=cc,
        timeout_seconds=timeout_seconds,
        env_setup=env_setup,
        link_libraries=[item.path for item in _LINK_LIBRARIES.get()],
        library_dirs=list(_LIBRARY_DIRS.get()),
        **kwargs,
    )


def _link_libraries(build_context: dict[str, Any], diagnostics: list[BuildDiagnostic]) -> list[LinkLibraryEntry]:
    values = build_context.get("link_libraries", [])
    ordered = sorted(values, key=_link_order)
    result: list[LinkLibraryEntry] = []
    seen: set[str] = set()
    for index, raw in enumerate(ordered):
        item = _mapping(raw)
        path_text = str(item.get("path") or "").strip()
        if not path_text:
            diagnostics.append(BuildDiagnostic("link_library_not_found", "warning", "Link library path is empty."))
            continue
        path = Path(path_text).expanduser()
        try:
            path = path.resolve()
        except OSError:
            path = Path(path_text)
        declared_exists = bool(item.get("exists", path.exists()))
        if not declared_exists or not path.is_file():
            diagnostics.append(BuildDiagnostic("link_library_not_found", "warning", f"Link library is unavailable: {path}", path))
            continue
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(
            LinkLibraryEntry(
                path=path,
                source=str(item.get("source") or "unknown"),
                link_order=int(item.get("link_order", index)),
                project_name=_optional_text(item.get("project_name")),
                configuration=_optional_text(item.get("configuration")),
                exists=True,
                scan_status=_optional_text(item.get("scan_status")),
            )
        )
    result.sort(key=lambda item: item.link_order)
    return result


def _library_dirs(build_context: dict[str, Any]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for raw in build_context.get("library_dirs", []):
        value = raw.get("path") if isinstance(raw, dict) else raw
        if value is None or not str(value).strip():
            continue
        path = Path(str(value)).expanduser()
        try:
            path = path.resolve()
        except OSError:
            continue
        if not path.is_dir():
            continue
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _argument(args: tuple[Any, ...], kwargs: dict[str, Any], index: int, name: str):
    if len(args) > index:
        return args[index]
    return kwargs.get(name)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        payload = value.to_dict()
        return payload if isinstance(payload, dict) else {}
    return {"path": value}


def _link_order(value: Any) -> int:
    item = _mapping(value)
    try:
        return int(item.get("link_order", 0))
    except (TypeError, ValueError):
        return 0


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _windows_path(path: Path | str) -> str:
    return str(path).replace("/", "\\")
