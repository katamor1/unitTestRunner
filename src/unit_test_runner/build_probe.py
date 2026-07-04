from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


def _clean_symbol(symbol: str) -> str:
    symbol = symbol.strip()
    if symbol.startswith("_"):
        symbol = symbol[1:]
    return symbol


def parse_build_log(log_text: str) -> dict[str, Any]:
    missing_includes = []
    pch_warnings = []
    unresolved_symbols = []
    for line in log_text.splitlines():
        include_match = re.search(r"Cannot open include file:\s*'([^']+)'", line)
        if include_match and include_match.group(1) not in missing_includes:
            missing_includes.append(include_match.group(1))
        if "PCH" in line.upper() or "STDAFX" in line.upper() or "D4024" in line:
            pch_warnings.append(line.strip())
        unresolved_match = re.search(r"unresolved external symbol\s+(_?[A-Za-z]\w*)", line)
        if unresolved_match:
            symbol = _clean_symbol(unresolved_match.group(1))
            if symbol not in unresolved_symbols:
                unresolved_symbols.append(symbol)
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


def build_probe(dossier_path: Path | str, vc6_bin: Path | str | None = None, dry_run: bool = False) -> dict[str, Any]:
    dossier_path = Path(dossier_path)
    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
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
    makefile = build_dir / "Makefile"
    makefile.write_text(f"# Generated build probe for {function_name}\nprobe:\n\t{command}\n", encoding="utf-8")
    log_path = root / "reports" / "build_probe.log"
    if dry_run or not vc6_bin:
        log_text = f"DRY RUN\n{command}\n"
        log_path.write_text(log_text, encoding="utf-8")
        return {"command": command, "dry_run": True, "diagnostics": parse_build_log(log_text)}

    completed = subprocess.run(command_parts, cwd=build_dir, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    log_path.write_text(completed.stdout, encoding="utf-8")
    return {"command": command, "dry_run": False, "returncode": completed.returncode, "diagnostics": parse_build_log(completed.stdout)}
