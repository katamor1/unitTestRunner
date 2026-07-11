from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from unit_test_runner.encoding import decode_bytes_auto


BridgeTypeKind = Literal["scalar", "aggregate", "pointer", "unresolved"]

_QUALIFIER_RE = re.compile(r"\b(?:const|volatile|register)\b")
_QUOTE_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.MULTILINE)
_SCALAR_TYPES = {
    "char",
    "signed char",
    "unsigned char",
    "short",
    "short int",
    "signed short",
    "signed short int",
    "unsigned short",
    "unsigned short int",
    "int",
    "signed",
    "signed int",
    "unsigned",
    "unsigned int",
    "long",
    "long int",
    "signed long",
    "signed long int",
    "unsigned long",
    "unsigned long int",
    "float",
    "double",
    "long double",
    "void",
}
_KNOWN_SCALAR_TYPEDEFS = {
    "BOOL",
    "BYTE",
    "CHAR",
    "DWORD",
    "INT",
    "LONG",
    "SHORT",
    "UCHAR",
    "UINT",
    "ULONG",
    "USHORT",
    "WORD",
}


@dataclass(frozen=True)
class BridgeType:
    type_text: str
    kind: BridgeTypeKind
    defining_headers: tuple[Path, ...] = ()


def classify_bridge_type(
    type_text: str,
    defining_headers: Iterable[Path | str],
) -> BridgeType:
    paths = _existing_paths(defining_headers)
    texts = [(path, _read_text(path)) for path in paths]
    return _classify(str(type_text or "").strip(), texts, set())


def enrich_signature_bridge_types(signature: dict) -> dict:
    payload = copy.deepcopy(signature)
    source_path = Path(str(payload.get("source", {}).get("path") or ""))
    include_tokens: list[str] = []
    defining_paths: list[Path] = []
    if source_path.is_file():
        defining_paths.append(source_path)
        source_text = _read_text(source_path)
        for match in _QUOTE_INCLUDE_RE.finditer(source_text):
            token = match.group(1).strip().replace("\\", "/")
            if token and token not in include_tokens:
                include_tokens.append(token)
            candidate = source_path.parent / token
            if candidate.is_file() and candidate not in defining_paths:
                defining_paths.append(candidate)

    function = payload.get("function", {})
    return_info = function.get("return_type")
    if isinstance(return_info, dict):
        raw_return = str(return_info.get("raw") or return_info.get("normalized") or "int")
        return_info["bridge_kind"] = classify_bridge_type(raw_return, defining_paths).kind
    for parameter in function.get("parameters", []):
        type_info = parameter.get("type")
        if isinstance(type_info, dict):
            raw_type = str(type_info.get("raw") or type_info.get("base_type") or "int")
            type_info["bridge_kind"] = classify_bridge_type(raw_type, defining_paths).kind
        else:
            raw_type = str(parameter.get("type_raw") or "int")
            parameter["bridge_kind"] = classify_bridge_type(raw_type, defining_paths).kind
    payload["bridge_context"] = {
        "defining_headers": [str(path) for path in defining_paths],
        "source_include_tokens": include_tokens,
    }
    return payload


def _classify(
    type_text: str,
    definitions: list[tuple[Path, str]],
    seen: set[str],
) -> BridgeType:
    compact = _compact(type_text)
    if not compact:
        return BridgeType(type_text, "unresolved")
    if "*" in compact or "[" in compact:
        return BridgeType(type_text, "pointer")
    if compact in _SCALAR_TYPES or compact in _KNOWN_SCALAR_TYPEDEFS or compact.startswith("enum "):
        return BridgeType(type_text, "scalar")
    if compact in seen:
        return BridgeType(type_text, "unresolved")
    next_seen = {*seen, compact}

    explicit_aggregate = re.fullmatch(r"(struct|union)\s+([A-Za-z_]\w*)", compact)
    if explicit_aggregate:
        kind, tag = explicit_aggregate.groups()
        hits = tuple(
            path
            for path, text in definitions
            if re.search(rf"\b{kind}\s+{re.escape(tag)}\s*\{{", text)
        )
        return BridgeType(type_text, "aggregate" if hits else "unresolved", hits)

    if re.fullmatch(r"[A-Za-z_]\w*", compact):
        aggregate_hits = tuple(
            path
            for path, text in definitions
            if _defines_complete_aggregate_typedef(text, compact)
        )
        if aggregate_hits:
            return BridgeType(type_text, "aggregate", aggregate_hits)
        for path, text in definitions:
            base = _scalar_typedef_base(text, compact)
            if base is None:
                continue
            base_result = _classify(base, definitions, next_seen)
            if base_result.kind == "scalar":
                headers = tuple(dict.fromkeys((path, *base_result.defining_headers)))
                return BridgeType(type_text, "scalar", headers)
        tagged_hits = tuple(
            path
            for path, text in definitions
            if _defines_complete_tagged_typedef(text, compact)
        )
        if tagged_hits:
            return BridgeType(type_text, "aggregate", tagged_hits)
    return BridgeType(type_text, "unresolved")


def _defines_complete_aggregate_typedef(text: str, name: str) -> bool:
    return bool(
        re.search(
            rf"\btypedef\s+(?:struct|union)\b[\s\S]*?\{{[\s\S]*?\}}\s*{re.escape(name)}\s*;",
            text,
        )
    )


def _defines_complete_tagged_typedef(text: str, name: str) -> bool:
    match = re.search(
        rf"\btypedef\s+(struct|union)\s+([A-Za-z_]\w*)\s+{re.escape(name)}\s*;",
        text,
    )
    if not match:
        return False
    kind, tag = match.groups()
    return bool(re.search(rf"\b{kind}\s+{re.escape(tag)}\s*\{{", text))


def _scalar_typedef_base(text: str, name: str) -> str | None:
    match = re.search(
        rf"\btypedef\s+([^;{{}}()]+?)\s+{re.escape(name)}\s*;",
        text,
    )
    return match.group(1).strip() if match else None


def _compact(type_text: str) -> str:
    without_qualifiers = _QUALIFIER_RE.sub(" ", type_text)
    return " ".join(without_qualifiers.split())


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
