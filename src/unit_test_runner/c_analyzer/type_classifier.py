from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from unit_test_runner.encoding import decode_bytes_auto


CTypeKind = Literal["scalar", "aggregate", "pointer", "unresolved"]

_QUALIFIER_RE = re.compile(r"\b(?:const|volatile|register)\b")
_SCALAR_TYPES = {
    "char", "signed char", "unsigned char", "short", "short int",
    "signed short", "signed short int", "unsigned short", "unsigned short int",
    "int", "signed", "signed int", "unsigned", "unsigned int", "long",
    "long int", "signed long", "signed long int", "unsigned long",
    "unsigned long int", "float", "double", "long double", "void", "_Bool",
}
_KNOWN_SCALAR_TYPEDEFS = {
    "BOOL", "BYTE", "CHAR", "DWORD", "INT", "LONG", "SHORT", "UCHAR",
    "UINT", "ULONG", "USHORT", "WORD",
}


@dataclass(frozen=True)
class CTypeClassification:
    type_text: str
    kind: CTypeKind
    defining_headers: tuple[Path, ...] = ()


def classify_c_type(
    type_text: str,
    defining_files: Iterable[Path | str] = (),
) -> CTypeClassification:
    paths = _existing_paths(defining_files)
    texts = [(path, _read_text(path)) for path in paths]
    return _classify(str(type_text or "").strip(), texts, set())


def _classify(
    type_text: str,
    definitions: list[tuple[Path, str]],
    seen: set[str],
) -> CTypeClassification:
    compact = _compact(type_text)
    if not compact:
        return CTypeClassification(type_text, "unresolved")
    if "*" in compact or "[" in compact:
        return CTypeClassification(type_text, "pointer")
    if compact in _SCALAR_TYPES or compact in _KNOWN_SCALAR_TYPEDEFS or compact.startswith("enum "):
        return CTypeClassification(type_text, "scalar")
    if compact in seen:
        return CTypeClassification(type_text, "unresolved")
    next_seen = {*seen, compact}

    explicit_aggregate = re.fullmatch(r"(struct|union)\s+([A-Za-z_]\w*)", compact)
    if explicit_aggregate:
        kind, tag = explicit_aggregate.groups()
        hits = tuple(path for path, text in definitions if re.search(rf"\b{kind}\s+{re.escape(tag)}\s*\{{", text))
        return CTypeClassification(type_text, "aggregate" if hits else "unresolved", hits)

    if re.fullmatch(r"[A-Za-z_]\w*", compact):
        aggregate_hits = tuple(path for path, text in definitions if _defines_complete_aggregate_typedef(text, compact))
        if aggregate_hits:
            return CTypeClassification(type_text, "aggregate", aggregate_hits)
        for path, text in definitions:
            base = _typedef_base(text, compact)
            if base is None:
                continue
            base_result = _classify(base, definitions, next_seen)
            if base_result.kind != "unresolved":
                headers = tuple(dict.fromkeys((path, *base_result.defining_headers)))
                return CTypeClassification(type_text, base_result.kind, headers)
        tagged_hits = tuple(path for path, text in definitions if _defines_complete_tagged_typedef(text, compact))
        if tagged_hits:
            return CTypeClassification(type_text, "aggregate", tagged_hits)
    return CTypeClassification(type_text, "unresolved")


def _defines_complete_aggregate_typedef(text: str, name: str) -> bool:
    return bool(re.search(rf"\btypedef\s+(?:struct|union)\b[\s\S]*?\{{[\s\S]*?\}}\s*{re.escape(name)}\s*;", text))


def _defines_complete_tagged_typedef(text: str, name: str) -> bool:
    match = re.search(rf"\btypedef\s+(struct|union)\s+([A-Za-z_]\w*)\s+{re.escape(name)}\s*;", text)
    if not match:
        return False
    kind, tag = match.groups()
    return bool(re.search(rf"\b{kind}\s+{re.escape(tag)}\s*\{{", text))


def _typedef_base(text: str, name: str) -> str | None:
    match = re.search(rf"\btypedef\s+([^;{{}}()]+?)\s+{re.escape(name)}\s*;", text)
    return match.group(1).strip() if match else None


def _compact(type_text: str) -> str:
    return " ".join(_QUALIFIER_RE.sub(" ", type_text).split())


def _existing_paths(values: Iterable[Path | str]) -> list[Path]:
    result: list[Path] = []
    for value in values:
        path = Path(value)
        if path.is_file() and path not in result:
            result.append(path)
    return result


def _read_text(path: Path) -> str:
    try:
        return decode_bytes_auto(path.read_bytes())
    except OSError:
        return ""
