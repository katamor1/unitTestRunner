from __future__ import annotations

import copy
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .build.log_parser import parse_build_log as parse_structured_build_log
from .contracts import ArtifactKind, ConsumerContractError, normalize_consumer_data
from .encoding import decode_bytes_auto, write_generated_c_text


_CURRENT_DOSSIER_VERSION = "1.1.0"
_CURRENT_ENVELOPE_KEYS = ("producer", "subject", "data", "extensions")


def parse_build_log(log_text: str) -> dict[str, Any]:
    parsed = parse_structured_build_log(log_text)
    missing_includes = [item.include_name for item in parsed.missing_includes]
    pch_warnings = [item.diagnostic_raw for item in parsed.pch_issues]
    unresolved_symbols = []
    for symbol in parsed.unresolved_symbols:
        if symbol.symbol_name not in unresolved_symbols:
            unresolved_symbols.append(symbol.symbol_name)
    return {
        "missing_includes": missing_includes,
        "pch_warnings": pch_warnings,
        "unresolved_symbols": unresolved_symbols,
    }


def _quote(value: Path | str) -> str:
    return f'"{value}"'


def _resolve_extracted_include(root: Path, include_dir: str) -> str:
    extracted = root / "extracted" / include_dir
    if extracted.exists():
        return str(extracted)
    return include_dir


def _load_probe_dossier(dossier_path: Path) -> dict[str, Any]:
    try:
        document = json.loads(dossier_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConsumerContractError(f"Could not load function dossier: {error}") from error
    if not isinstance(document, Mapping):
        raise ConsumerContractError("Function dossier root must be an object.")

    if _is_current_dossier_shape(document):
        dossier = _normalize_current_dossier(document)
    else:
        dossier = _normalize_legacy_dossier(document)
    _validate_probe_fields(dossier)
    return dossier


def _is_current_dossier_shape(document: Mapping[str, Any]) -> bool:
    version = str(document.get("schema_version") or "")
    return any(key in document for key in _CURRENT_ENVELOPE_KEYS) or version not in {
        "",
        "0.1",
    }


def _normalize_current_dossier(document: Mapping[str, Any]) -> dict[str, Any]:
    declared_kind = document.get("artifact_kind")
    if declared_kind != ArtifactKind.FUNCTION_DOSSIER.value:
        raise ConsumerContractError(
            "Expected function_dossier; "
            f"received {declared_kind!r}."
        )
    version = str(document.get("schema_version") or "")
    if version != _CURRENT_DOSSIER_VERSION:
        raise ConsumerContractError(
            "Function dossier build probe requires schema version "
            f"{_CURRENT_DOSSIER_VERSION}; received {version or '<missing>'}."
        )
    if not isinstance(document.get("data"), Mapping):
        raise ConsumerContractError("Function dossier data must be an object.")

    validated_envelope = copy.deepcopy(dict(document))
    validated_envelope.pop("target", None)
    validated_envelope.pop("build_context", None)
    return normalize_consumer_data(
        validated_envelope,
        expected_kind=ArtifactKind.FUNCTION_DOSSIER,
    )


def _normalize_legacy_dossier(document: Mapping[str, Any]) -> dict[str, Any]:
    version = document.get("schema_version")
    if version not in (None, "0.1"):
        raise ConsumerContractError(
            f"Unsupported legacy function dossier version: {version!r}."
        )
    declared_kind = document.get("artifact_kind")
    if declared_kind not in (None, ArtifactKind.FUNCTION_DOSSIER.value):
        raise ConsumerContractError(
            "Expected function_dossier; "
            f"received {declared_kind!r}."
        )
    return copy.deepcopy(dict(document))


def _validate_probe_fields(dossier: Mapping[str, Any]) -> None:
    target = dossier.get("target")
    if not isinstance(target, Mapping):
        raise ConsumerContractError("Function dossier target must be an object.")
    source = target.get("source")
    function_name = target.get("function")
    if not isinstance(source, str) or not source.strip():
        raise ConsumerContractError("Function dossier target.source must be non-empty.")
    if not isinstance(function_name, str) or not function_name.strip():
        raise ConsumerContractError("Function dossier target.function must be non-empty.")

    build_context = dossier.get("build_context", {})
    if not isinstance(build_context, Mapping):
        raise ConsumerContractError("Function dossier build_context must be an object.")
    for field in ("include_dirs", "defines"):
        values = build_context.get(field, [])
        if not isinstance(values, list) or any(
            not isinstance(value, str) for value in values
        ):
            raise ConsumerContractError(
                f"Function dossier build_context.{field} must be a string array."
            )


def _resolve_extracted_source(root: Path, source: str) -> Path:
    windows_path = PureWindowsPath(source)
    posix_path = PurePosixPath(source.replace("\\", "/"))
    if (
        windows_path.drive
        or windows_path.root
        or posix_path.is_absolute()
        or ".." in windows_path.parts
        or ".." in posix_path.parts
    ):
        raise ConsumerContractError(
            "Function dossier target.source must be a relative path without '..'."
        )

    extracted_root = (root / "extracted").resolve()
    resolved_source = extracted_root.joinpath(*posix_path.parts).resolve()
    if not resolved_source.is_relative_to(extracted_root):
        raise ConsumerContractError(
            "Function dossier target.source must remain inside extracted/."
        )
    return resolved_source


def build_probe(dossier_path: Path | str, vc6_bin: Path | str | None = None, dry_run: bool = False, vcvars: Path | str | None = None) -> dict[str, Any]:
    dossier_path = Path(dossier_path)
    dossier = _load_probe_dossier(dossier_path)
    root = dossier_path.parents[1]
    source = _resolve_extracted_source(root, dossier["target"]["source"])
    build_dir = root / "generated" / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    function_name = dossier["target"]["function"]
    build_context = dossier.get("build_context", {})
    include_args = [f"/I{_quote(_resolve_extracted_include(root, include_dir))}" for include_dir in build_context.get("include_dirs", [])]
    define_args = [f"/D{_quote(define)}" for define in build_context.get("defines", [])]
    cl_exe = str(Path(vc6_bin) / "cl.exe") if vc6_bin else "cl"
    command_parts = [cl_exe, "/nologo", "/W3", *define_args, *include_args, "/c", str(source)]
    command = " ".join(_quote(part) if " " in part and not part.startswith(("/I", "/D")) else part for part in command_parts)
    if vcvars:
        command = f"call {_quote(vcvars)} && {command}"
    makefile = build_dir / "Makefile"
    write_generated_c_text(makefile, f"# Generated build probe for {function_name}\nprobe:\n\t{command}\n")
    log_path = root / "reports" / "build_probe.log"
    if dry_run or (not vc6_bin and not vcvars):
        log_text = f"DRY RUN\n{command}\n"
        log_path.write_text(log_text, encoding="utf-8")
        return {"command": command, "dry_run": True, "diagnostics": parse_build_log(log_text)}

    run_args = [_cmd_exe(), "/c", command] if vcvars else command_parts
    completed = subprocess.run(run_args, cwd=build_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    log_text = _decode_process_output(completed.stdout)
    log_path.write_text(log_text, encoding="utf-8")
    return {"command": command, "dry_run": False, "returncode": completed.returncode, "diagnostics": parse_build_log(log_text)}


def _decode_process_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    return decode_bytes_auto(output)


def _cmd_exe() -> str:
    return "cmd" + ".exe"
