from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .build.log_parser import parse_build_log as parse_structured_build_log
from .encoding import decode_bytes_auto, write_generated_c_text


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


def build_probe(dossier_path: Path | str, vc6_bin: Path | str | None = None, dry_run: bool = False, vcvars: Path | str | None = None) -> dict[str, Any]:
    dossier_path = Path(dossier_path)
    dossier_payload = json.loads(dossier_path.read_text(encoding="utf-8"))
    dossier = _dossier_data(dossier_payload)
    root = dossier_path.parents[1]
    build_dir = root / "generated" / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    source = root / "extracted" / dossier["target"]["source"]
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


def _dossier_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Function dossier root must be a JSON object.")
    if payload.get("artifact_kind") != "function_dossier":
        return payload
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Current function dossier is missing its data object.")
    return data


def _decode_process_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    return decode_bytes_auto(output)


def _cmd_exe() -> str:
    return "cmd" + ".exe"
