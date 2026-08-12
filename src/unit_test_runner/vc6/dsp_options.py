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


def effective_build_settings(
    base_options: list[str],
    configuration_options: list[str],
    configuration_subtract_options: list[str] = (),
    source_add_options: list[str] = (),
    source_subtract_options: list[str] = (),
    *,
    dsp_dir: Path,
    workspace_root: Path | None = None,
) -> DspBuildSettings:
    """Apply the VC6 compiler layers without inventing settings.

    Developer Studio evaluates project BASE options, configuration ADD/SUBTRACT,
    then source-file ADD/SUBTRACT.  Keeping the ordered token stream here makes
    source selection and the emitted build context use the same semantics.
    """

    options = [*_option_units(base_options), *_option_units(configuration_options)]
    options = _subtract_options(options, _option_units(configuration_subtract_options))
    options.extend(_option_units(source_add_options))
    options = _subtract_options(options, _option_units(source_subtract_options))
    return parse_build_settings(options, dsp_dir, workspace_root)


def _subtract_options(options: list[str], subtract_options: list[str] | tuple[str, ...]) -> list[str]:
    result = list(options)
    for subtract in subtract_options:
        key = _option_identity(subtract)
        for index in range(len(result) - 1, -1, -1):
            if _option_identity(result[index]) == key:
                del result[index]
                break
    return result


def _option_identity(token: str) -> tuple[str, str]:
    text = str(token).strip()
    upper = text.upper()
    for prefix in ("/D", "/I", "/FI", "/YU", "/YC"):
        if upper.startswith(prefix):
            value = _strip_quotes(text[len(prefix) :]).replace("\\", "/")
            return prefix, value.casefold()
    return upper, ""


def _option_units(options: list[str] | tuple[str, ...]) -> list[str]:
    """Join VC6 options whose value is a separate token before layering.

    DSP files commonly spell a define as ``/D "NAME"``.  Treating those as
    two independent tokens makes ``# SUBTRACT CPP /D "NAME"`` remove an
    unrelated ``/D`` marker.  The joined spelling remains accepted by the
    existing parser while giving ADD/SUBTRACT one stable identity.
    """

    result: list[str] = []
    index = 0
    values = list(options)
    while index < len(values):
        token = values[index]
        if token.upper() in {"/D", "/I", "/FI", "/YU", "/YC"} and index + 1 < len(values):
            result.append(f"{token}{values[index + 1]}")
            index += 2
            continue
        result.append(token)
        index += 1
    return result


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
