from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Iterable

from unit_test_runner.c_analyzer.type_classifier import (
    CTypeClassification as BridgeType,
    CTypeKind as BridgeTypeKind,
    classify_c_type,
)
from unit_test_runner.encoding import decode_bytes_auto

_QUOTE_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.MULTILINE)


def classify_bridge_type(
    type_text: str,
    defining_headers: Iterable[Path | str],
) -> BridgeType:
    return classify_c_type(type_text, defining_headers)


def _read_text(path: Path) -> str:
    try:
        return decode_bytes_auto(path.read_bytes())
    except OSError:
        return ""


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
        raw_return = str(return_info.get("raw") or return_info.get("normalized") or "")
        return_info["bridge_kind"] = classify_bridge_type(raw_return, defining_paths).kind
    for parameter in function.get("parameters", []):
        type_info = parameter.get("type")
        if isinstance(type_info, dict):
            raw_type = str(type_info.get("raw") or type_info.get("base_type") or "")
            type_info["bridge_kind"] = classify_bridge_type(raw_type, defining_paths).kind
        else:
            raw_type = str(parameter.get("type_raw") or "")
            parameter["bridge_kind"] = classify_bridge_type(raw_type, defining_paths).kind
    payload["bridge_context"] = {
        "defining_headers": [str(path) for path in defining_paths],
        "source_include_tokens": include_tokens,
    }
    return payload
