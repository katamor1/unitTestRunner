from __future__ import annotations

import re
from pathlib import Path

from ..encoding import read_text_with_encoding
from ..path_utils import resolve_vc6_path
from .dsp_link_options import merge_link_settings, parse_link_settings, path_like_value, tokenize_linker_options
from .dsp_models import DspConfiguration, DspFileEntry, DspParseWarning, DspProject
from .dsp_options import merge_build_settings, parse_build_settings, tokenize_compiler_options


PROJECT_NAME_RE = re.compile(r'Project File - Name="(?P<name>[^"]+)"')
FORMAT_RE = re.compile(r"Format Version\s+(?P<version>[0-9.]+)")
TARGET_TYPE_RE = re.compile(r'# TARGTYPE\s+"(?P<type>[^"]+)"')
CFG_RE = re.compile(r'!\s*(?:IF|ELSEIF)\s+"\$\(CFG\)"\s*==\s*"(?P<cfg>[^"]+)"')
NAME_RE = re.compile(r'^#\s+Name\s+"(?P<cfg>[^"]+)"')
GROUP_RE = re.compile(r'^#\s+Begin\s+Group\s+"(?P<group>[^"]+)"')
OUTPUT_DIR_RE = re.compile(r'^#\s+PROP(?:\s+BASE)?\s+Output_Dir\s+"(?P<value>[^"]*)"')
INTERMEDIATE_DIR_RE = re.compile(r'^#\s+PROP(?:\s+BASE)?\s+Intermediate_Dir\s+"(?P<value>[^"]*)"')


def parse_dsp(path: Path | str, workspace_root: Path | str | None = None) -> DspProject:
    dsp_path = Path(path).expanduser().resolve()
    workspace = Path(workspace_root).resolve() if workspace_root is not None else dsp_path.parent
    text, encoding, used_fallback = read_text_with_encoding(dsp_path)
    warnings: list[DspParseWarning] = []
    if used_fallback:
        warnings.append(DspParseWarning("encoding_fallback", f"Decoded DSP using fallback encoding: {encoding}"))

    project_name = _match_first(PROJECT_NAME_RE, text, "name") or dsp_path.stem
    format_version = _match_first(FORMAT_RE, text, "version")
    target_type = _match_first(TARGET_TYPE_RE, text, "type")
    configurations: dict[str, DspConfiguration] = {}
    files: list[DspFileEntry] = []
    current_config: DspConfiguration | None = None
    current_group: str | None = None

    for line_number, line in enumerate(text.splitlines(), start=1):
        cfg_match = CFG_RE.search(line)
        if cfg_match:
            current_config = configurations.setdefault(
                cfg_match.group("cfg"),
                _configuration(cfg_match.group("cfg"), line_number),
            )
            continue
        if line.startswith("!ENDIF"):
            current_config = None
            continue
        name_match = NAME_RE.match(line)
        if name_match:
            configurations.setdefault(name_match.group("cfg"), _configuration(name_match.group("cfg"), line_number))
            continue

        group_match = GROUP_RE.match(line)
        if group_match:
            current_group = group_match.group("group")
            continue
        if line.startswith("# End Group"):
            current_group = None
            continue

        output_match = OUTPUT_DIR_RE.match(line)
        if output_match and current_config is not None:
            current_config.link_settings.output_dir = path_like_value(output_match.group("value"), dsp_path.parent, workspace)
            _merge_path_macros(current_config, current_config.link_settings.output_dir)
            continue
        intermediate_match = INTERMEDIATE_DIR_RE.match(line)
        if intermediate_match and current_config is not None:
            current_config.link_settings.intermediate_dir = path_like_value(intermediate_match.group("value"), dsp_path.parent, workspace)
            _merge_path_macros(current_config, current_config.link_settings.intermediate_dir)
            continue

        if line.startswith("# ADD") and " CPP " in line:
            if current_config is None:
                warnings.append(
                    DspParseWarning(
                        "compiler_options_without_configuration",
                        "Compiler options appeared outside a configuration block.",
                        line_number,
                        line,
                    )
                )
                continue
            is_base = line.startswith("# ADD BASE CPP")
            options_text = line.split(" CPP ", 1)[1]
            tokens = tokenize_compiler_options(options_text)
            if is_base:
                current_config.compiler_base_options.extend(tokens)
            else:
                current_config.compiler_options.extend(tokens)
            settings = parse_build_settings(tokens, dsp_path.parent, workspace)
            merge_build_settings(current_config.build_settings, settings)
            for macro in settings.unresolved_macros:
                warnings.append(DspParseWarning("unresolved_macro", f"Unresolved macro in compiler option: {macro}", line_number, line))
            continue

        link_marker = _link_tool_marker(line)
        if line.startswith("# ADD") and link_marker is not None:
            if current_config is None:
                warnings.append(
                    DspParseWarning(
                        "linker_options_without_configuration",
                        "Linker or librarian options appeared outside a configuration block.",
                        line_number,
                        line,
                    )
                )
                continue
            is_base = line.startswith("# ADD BASE")
            options_text = line.split(link_marker, 1)[1]
            tokens = tokenize_linker_options(options_text)
            if is_base:
                current_config.linker_base_options.extend(tokens)
            else:
                current_config.linker_options.extend(tokens)
            settings = parse_link_settings(tokens, dsp_path.parent, workspace)
            merge_link_settings(current_config.link_settings, settings)
            for macro in settings.unresolved_macros:
                warnings.append(DspParseWarning("unresolved_link_macro", f"Unresolved macro in linker option: {macro}", line_number, line))
            continue

        if line.startswith("SOURCE="):
            raw = line.split("=", 1)[1].strip().strip('"')
            absolute = resolve_vc6_path(dsp_path.parent, raw)
            entry = DspFileEntry(
                source_raw=raw,
                source_path=_normalized_source_path(raw),
                source_path_absolute=absolute,
                file_kind=_file_kind(absolute.suffix.lower()),
                group=current_group,
                exists=absolute.exists() and absolute.is_file(),
                line_number=line_number,
            )
            files.append(entry)
            if not entry.exists:
                warnings.append(DspParseWarning("missing_source_file", f"SOURCE file does not exist: {absolute}", line_number, line))
            continue

        if "Custom Build" in line:
            warnings.append(DspParseWarning("custom_build_step_detected", "Custom build step detected.", line_number, line))

    return DspProject(
        name=project_name,
        path=dsp_path,
        root_dir=dsp_path.parent,
        format_version=format_version,
        target_type=target_type,
        configurations=list(configurations.values()),
        files=files,
        warnings=warnings,
        encoding=encoding,
    )


def _link_tool_marker(line: str) -> str | None:
    for marker in (" LINK32 ", " LIB32 "):
        if marker in line:
            return marker
    return None


def _merge_path_macros(configuration: DspConfiguration, value) -> None:
    for macro in value.unresolved_macros:
        if macro not in configuration.link_settings.unresolved_macros:
            configuration.link_settings.unresolved_macros.append(macro)


def _match_first(pattern: re.Pattern[str], text: str, group: str) -> str | None:
    match = pattern.search(text)
    return match.group(group) if match else None


def _configuration(full_name: str, line_number: int | None) -> DspConfiguration:
    project_name = None
    platform = None
    name = None
    if " - " in full_name:
        project_name, rest = full_name.split(" - ", 1)
        parts = rest.split()
        if parts:
            platform = parts[0]
            name = " ".join(parts[1:]) if len(parts) > 1 else None
    return DspConfiguration(full_name=full_name, project_name=project_name, platform=platform, name=name, line_number=line_number)


def _normalized_source_path(raw: str) -> Path:
    clean = raw.strip().strip('"').replace("\\", "/")
    if clean.startswith("./"):
        clean = clean[2:]
    return Path(clean)


def _file_kind(suffix: str) -> str:
    if suffix in {".c", ".cpp", ".cxx", ".cc"}:
        return "source"
    if suffix in {".h", ".hpp", ".hxx", ".inl", ".inc"}:
        return "header"
    if suffix in {".rc", ".ico", ".bmp", ".cur"}:
        return "resource"
    if suffix == ".def":
        return "def"
    return "other"
