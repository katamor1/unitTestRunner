from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .build_models import BuildDiagnostic, MissingInclude, PchIssue, UnresolvedSymbol, VC6CompatibilityIssue


@dataclass
class BuildLogParseResult:
    diagnostics: list[BuildDiagnostic] = field(default_factory=list)
    missing_includes: list[MissingInclude] = field(default_factory=list)
    unresolved_symbols: list[UnresolvedSymbol] = field(default_factory=list)
    pch_issues: list[PchIssue] = field(default_factory=list)
    vc6_compatibility_issues: list[VC6CompatibilityIssue] = field(default_factory=list)


def parse_build_log(log_text: str, stub_candidates: set[str] | None = None) -> BuildLogParseResult:
    stub_candidates = stub_candidates or set()
    result = BuildLogParseResult()
    seen_includes: set[str] = set()
    seen_symbols: set[tuple[str, str]] = set()
    for line in log_text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        file_path, line_number = _location(raw)
        include_match = re.search(r"Cannot open include file:\s*'([^']+)'", raw)
        if include_match:
            include_name = include_match.group(1)
            if include_name not in seen_includes:
                result.missing_includes.append(MissingInclude(include_name, file_path, line_number, raw))
                seen_includes.add(include_name)
            result.diagnostics.append(BuildDiagnostic("c1083_include_not_found", "error", f"Missing include: {include_name}", file_path, line_number, raw))
            if include_name.lower() in {"stdint.h", "stdbool.h"}:
                result.vc6_compatibility_issues.append(
                    VC6CompatibilityIssue("unsupported_c99_header", file_path, line_number, raw, "Remove C99 header dependency from generated VC6 skeleton.")
                )
            continue
        unresolved_match = re.search(r"(LNK2001|LNK2019): unresolved external symbol\s+(_?[A-Za-z]\w*(?:@\d+)?)", raw)
        if unresolved_match:
            code = unresolved_match.group(1)
            symbol = _clean_symbol(unresolved_match.group(2))
            referenced = None
            referenced_match = re.search(r"referenced in function\s+(_?[A-Za-z]\w*)", raw)
            if referenced_match:
                referenced = _clean_symbol(referenced_match.group(1))
            key = (code, symbol)
            if key not in seen_symbols:
                result.unresolved_symbols.append(UnresolvedSymbol(symbol, referenced, code, raw, symbol in stub_candidates, symbol if symbol in stub_candidates else None))
                seen_symbols.add(key)
            result.diagnostics.append(BuildDiagnostic(code.lower() + "_unresolved_symbol", "error", f"Unresolved external symbol: {symbol}", file_path, line_number, raw))
            continue
        if "C1010" in raw or "C1853" in raw or "precompiled header" in raw.lower() or "stdafx" in raw.lower():
            result.pch_issues.append(PchIssue("pch_required_or_mismatch", None, raw, "Review /Yu, /Yc, forced include, and stdafx.h handling in Step 15."))
            result.diagnostics.append(BuildDiagnostic("pch_required", "warning", "Precompiled header issue detected.", file_path, line_number, raw))
            continue
        if _looks_like_vc6_syntax_issue(raw):
            result.vc6_compatibility_issues.append(
                VC6CompatibilityIssue("possible_vc6_incompatible_syntax", file_path, line_number, raw, "Inspect generated C90 skeleton for C99 or unsupported syntax.")
            )
            result.diagnostics.append(BuildDiagnostic("vc6_incompatible_syntax", "error", "Possible VC6 incompatible syntax.", file_path, line_number, raw))
            continue
        warning_match = re.search(r"\bwarning\s+(C\d+|LNK\d+)", raw, re.IGNORECASE)
        if warning_match:
            result.diagnostics.append(BuildDiagnostic("compiler_warning", "warning", raw, file_path, line_number, raw))
            continue
        error_match = re.search(r"\berror\s+(C\d+|LNK\d+)", raw, re.IGNORECASE)
        if error_match:
            result.diagnostics.append(BuildDiagnostic("compiler_error", "error", raw, file_path, line_number, raw))
    return result


def _clean_symbol(symbol: str) -> str:
    symbol = symbol.strip()
    return symbol[1:] if symbol.startswith("_") else symbol


def _location(line: str) -> tuple[Path | None, int | None]:
    match = re.match(r"^(.+?)\((\d+)\)\s*:", line)
    if not match:
        return None, None
    return Path(match.group(1)), int(match.group(2))


def _looks_like_vc6_syntax_issue(line: str) -> bool:
    lower = line.lower()
    if "generated" in lower and ("c2143" in lower or "c2065" in lower):
        return True
    if "for" in lower and ("c2065" in lower or "c2143" in lower):
        return True
    if "inline" in lower and ("c2065" in lower or "c2143" in lower):
        return True
    if "stdint.h" in lower or "stdbool.h" in lower:
        return True
    return False
