from __future__ import annotations

import re
from pathlib import Path

from .dsp_models import DspLinkSettings, PathLikeValue
from .dsp_options import tokenize_compiler_options

_MACRO_PATTERNS = (
    re.compile(r"\$\(([^)]+)\)"),
    re.compile(r"\$\{([^}]+)\}"),
    re.compile(r"\(\$([A-Za-z_][A-Za-z0-9_]*)\)"),
    re.compile(r"%([^%]+)%"),
)


def tokenize_linker_options(text: str) -> list[str]:
    return tokenize_compiler_options(text)


def parse_link_settings(tokens: list[str], dsp_dir: Path, workspace_root: Path | None = None) -> DspLinkSettings:
    dsp_dir = Path(dsp_dir).resolve()
    workspace_root = Path(workspace_root or dsp_dir).resolve()
    settings = DspLinkSettings(raw_options=list(tokens))
    index = 0
    while index < len(tokens):
        token = tokens[index]
        lower = token.lower()
        value: str | None = None
        option: str | None = None
        for prefix in ("/libpath", "/out", "/implib"):
            if lower == prefix:
                option = prefix
                if index + 1 < len(tokens):
                    index += 1
                    value = _strip_quotes(tokens[index])
                break
            if lower.startswith(prefix + ":"):
                option = prefix
                value = _strip_quotes(token[len(prefix) + 1 :])
                break
        if option == "/libpath" and value:
            settings.library_dirs.append(_path_like(value, dsp_dir, workspace_root))
        elif option == "/out" and value:
            settings.output_file = _path_like(value, dsp_dir, workspace_root)
        elif option == "/implib" and value:
            settings.import_library = _path_like(value, dsp_dir, workspace_root)
        elif not token.startswith("/") and _strip_quotes(token).lower().endswith(".lib"):
            library = _strip_quotes(token).replace("\\", "/")
            if library not in settings.libraries:
                settings.libraries.append(library)
        index += 1
    _collect_unresolved_macros(settings)
    return settings


def merge_link_settings(target: DspLinkSettings, source: DspLinkSettings) -> None:
    for library in source.libraries:
        if library not in target.libraries:
            target.libraries.append(library)
    target.library_dirs.extend(source.library_dirs)
    for option in source.raw_options:
        if option not in target.raw_options:
            target.raw_options.append(option)
    target.output_file = source.output_file or target.output_file
    target.import_library = source.import_library or target.import_library
    for macro in source.unresolved_macros:
        if macro not in target.unresolved_macros:
            target.unresolved_macros.append(macro)


def path_like_value(raw: str, dsp_dir: Path, workspace_root: Path | None = None) -> PathLikeValue:
    dsp_dir = Path(dsp_dir).resolve()
    workspace_root = Path(workspace_root or dsp_dir).resolve()
    return _path_like(raw, dsp_dir, workspace_root)


def _path_like(raw: str, dsp_dir: Path, workspace_root: Path) -> PathLikeValue:
    del workspace_root
    clean = _strip_quotes(raw)
    normalized = clean.replace("\\", "/")
    macros = _macros(clean)
    if macros:
        return PathLikeValue(raw=raw, normalized=normalized, absolute=None, exists=None, unresolved_macros=macros)
    path = Path(normalized)
    absolute = path.resolve() if path.is_absolute() else (dsp_dir / path).resolve()
    return PathLikeValue(raw=raw, normalized=normalized, absolute=absolute, exists=absolute.exists(), unresolved_macros=[])


def _collect_unresolved_macros(settings: DspLinkSettings) -> None:
    for item in [*settings.library_dirs, settings.output_file, settings.import_library]:
        if item is None:
            continue
        for macro in item.unresolved_macros:
            if macro not in settings.unresolved_macros:
                settings.unresolved_macros.append(macro)
    for library in settings.libraries:
        for macro in _macros(library):
            if macro not in settings.unresolved_macros:
                settings.unresolved_macros.append(macro)


def _macros(value: str) -> list[str]:
    result: list[str] = []
    for pattern in _MACRO_PATTERNS:
        for match in pattern.findall(value):
            if match not in result:
                result.append(match)
    return result


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"')
