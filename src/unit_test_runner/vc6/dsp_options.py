from __future__ import annotations

import re
from pathlib import Path

from .dsp_models import DspBuildSettings, PathLikeValue


def append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def tokenize_compiler_options(option_text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(option_text):
        while index < len(option_text) and option_text[index].isspace():
            index += 1
        if index >= len(option_text):
            break
        start = index
        in_quote = False
        while index < len(option_text):
            char = option_text[index]
            if char == '"':
                in_quote = not in_quote
            elif char.isspace() and not in_quote:
                break
            index += 1
        tokens.append(option_text[start:index].strip())
    return tokens


def parse_build_settings(tokens: list[str], dsp_dir: Path, workspace_root: Path | None = None) -> DspBuildSettings:
    workspace_root = Path(workspace_root or dsp_dir).resolve()
    dsp_dir = Path(dsp_dir).resolve()
    settings = DspBuildSettings(raw_options=list(tokens))
    index = 0
    while index < len(tokens):
        token = tokens[index]
        option = token
        value: str | None = None
        upper = option.upper()

        for prefix in ("/D", "/I", "/FI", "/YU", "/YC"):
            if upper == prefix:
                if index + 1 < len(tokens):
                    value = _strip_quotes(tokens[index + 1])
                    index += 1
                option = prefix
                break
            if upper.startswith(prefix) and len(option) > len(prefix):
                value = _strip_quotes(option[len(prefix) :])
                option = prefix
                break

        if option == "/D" and value is not None:
            append_unique(settings.defines, value)
        elif option == "/I" and value is not None:
            settings.include_dirs.append(_path_like(value, dsp_dir, workspace_root))
            for macro in _macros(value):
                append_unique(settings.unresolved_macros, macro)
        elif option == "/FI" and value is not None:
            append_unique(settings.forced_includes, value.replace("\\", "/"))
        elif option == "/YU" and value is not None:
            settings.pch_mode = "use"
            settings.pch_header = value
        elif option == "/YC" and value is not None:
            settings.pch_mode = "create"
            settings.pch_header = value
        elif upper == "/YX":
            settings.pch_mode = settings.pch_mode or "automatic"
        elif upper in {"/ML", "/MLD", "/MT", "/MTD", "/MD", "/MDD"}:
            settings.runtime_library = token
        elif re.match(r"(?i)^/W[0-4]$", token):
            settings.warning_level = token
        elif upper in {"/OD", "/O1", "/O2", "/OX"}:
            settings.optimization = token
        elif upper in {"/ZI", "/ZD"}:
            settings.debug_info = token
        index += 1
    return settings


def merge_build_settings(target: DspBuildSettings, source: DspBuildSettings) -> None:
    for value in source.defines:
        append_unique(target.defines, value)
    target.include_dirs.extend(source.include_dirs)
    for value in source.forced_includes:
        append_unique(target.forced_includes, value)
    for value in source.raw_options:
        append_unique(target.raw_options, value)
    for value in source.unresolved_macros:
        append_unique(target.unresolved_macros, value)
    if source.pch_mode:
        target.pch_mode = source.pch_mode
        target.pch_header = source.pch_header
    if source.runtime_library:
        target.runtime_library = source.runtime_library
    if source.warning_level:
        target.warning_level = source.warning_level
    if source.optimization:
        target.optimization = source.optimization
    if source.debug_info:
        target.debug_info = source.debug_info


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"')


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


def _macros(value: str) -> list[str]:
    macros: list[str] = []
    patterns = [
        r"\$\(([^)]+)\)",
        r"\$\{([^}]+)\}",
        r"\(\$([A-Za-z_][A-Za-z0-9_]*)\)",
        r"%([^%]+)%",
    ]
    for pattern in patterns:
        for macro in re.findall(pattern, value):
            append_unique(macros, macro)
    return macros
