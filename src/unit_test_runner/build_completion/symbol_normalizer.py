from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class NormalizedSymbol:
    raw_symbol: str
    function_name_candidate: str
    decoration_kind: str

    def to_dict(self) -> dict[str, str]:
        return {
            "raw_symbol": self.raw_symbol,
            "function_name_candidate": self.function_name_candidate,
            "decoration_kind": self.decoration_kind,
        }


def normalize_link_symbol(symbol: str) -> NormalizedSymbol:
    raw = str(symbol or "").strip()
    candidate = raw[1:] if raw.startswith("_") else raw
    decoration = "leading_underscore" if raw.startswith("_") else "none"
    stdcall = re.match(r"^([A-Za-z]\w*)@\d+$", candidate)
    if stdcall:
        candidate = stdcall.group(1)
        decoration = "stdcall_decorated"
    return NormalizedSymbol(raw, candidate, decoration)
