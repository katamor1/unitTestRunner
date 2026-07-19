from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .models import FormSuggestion, TestInputFormError


UNRESOLVED_PREFIXES = ("TBD", "TODO", "UNKNOWN", "UNRESOLVED")
MAX_C_EXPRESSION_LENGTH = 4096
MAX_MULTILINE_LENGTH = 16384
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NON_C90_RE = re.compile(r"\b(?:true|false|nullptr)\b|//|\b0[bB][01]+\b")


def _validation_error(message: str) -> TestInputFormError:
    return TestInputFormError("test_input_validation", message)


def is_unresolved(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text.upper().startswith(UNRESOLVED_PREFIXES)


def normalize_c_expression(value: Any) -> str:
    if not isinstance(value, str):
        raise _validation_error("C expression must be a string.")
    if "\x00" in value:
        raise _validation_error("C expression must not contain NUL.")
    if "\r" in value or "\n" in value:
        raise _validation_error("C expression must be a single line.")
    normalized = value.strip()
    if len(normalized) > MAX_C_EXPRESSION_LENGTH:
        raise _validation_error(
            f"C expression must contain at most {MAX_C_EXPRESSION_LENGTH} Unicode code points."
        )
    return normalized


def normalize_multiline(value: Any) -> str:
    if not isinstance(value, str):
        raise _validation_error("Multiline value must be a string.")
    if "\x00" in value:
        raise _validation_error("Multiline value must not contain NUL.")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized) > MAX_MULTILINE_LENGTH:
        raise _validation_error(
            f"Multiline value must contain at most {MAX_MULTILINE_LENGTH} Unicode code points."
        )
    return normalized


def normalize_enum(value: Any, allowed: frozenset[str]) -> str:
    if not isinstance(value, str):
        raise _validation_error("Enum value must be a string.")
    if not _IDENTIFIER_RE.fullmatch(value) or not value.isascii():
        raise _validation_error("Enum value must be an exact ASCII token.")
    if value not in allowed:
        raise _validation_error(
            f"Enum value must be one of: {', '.join(sorted(allowed))}."
        )
    return value


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": "warning", "message": message}


def _suggestion_values(suggestions: Iterable[Any]) -> frozenset[str]:
    values: set[str] = set()
    for suggestion in suggestions:
        if isinstance(suggestion, FormSuggestion):
            values.add(suggestion.value)
        elif isinstance(suggestion, Mapping) and isinstance(suggestion.get("value"), str):
            values.add(str(suggestion["value"]))
        elif isinstance(suggestion, str):
            values.add(suggestion)
    return frozenset(values)


def _balanced_expression(value: str) -> bool:
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    quote: str | None = None
    escaped = False
    for character in value:
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
            continue
        if character in "([{":
            stack.append(character)
            continue
        if character in pairs:
            if not stack or stack.pop() != pairs[character]:
                return False
    return quote is None and not stack


def _pointer_expected(type_hint: Mapping[str, Any]) -> bool:
    pointer_level = type_hint.get("pointer_level")
    return (
        isinstance(pointer_level, int)
        and not isinstance(pointer_level, bool)
        and pointer_level > 0
    ) or bool(type_hint.get("is_pointer")) or str(type_hint.get("type_category") or "") == "pointer"


def _scalar_expected(type_hint: Mapping[str, Any]) -> bool:
    category = str(type_hint.get("type_category") or "").lower()
    if category in {"scalar", "integer", "floating", "enum", "boolean"}:
        return True
    pointer_level = type_hint.get("pointer_level")
    return isinstance(pointer_level, int) and not isinstance(pointer_level, bool) and pointer_level == 0


def _plausible_pointer_expression(value: str, suggested: frozenset[str]) -> bool:
    if value in suggested or value in {"NULL", "0", "((void *)0)"}:
        return True
    if value.startswith("&") or value.startswith("("):
        return True
    if _IDENTIFIER_RE.fullmatch(value):
        return True
    return False


def c_expression_warnings(
    value: Any,
    type_hint: Mapping[str, Any] | None,
    suggestions: Iterable[Any],
) -> tuple[dict[str, str], ...]:
    if value is None:
        return (
            _warning("unresolved_value", "A concrete C expression is required."),
            *(
                ()
                if type_hint
                else (
                    _warning(
                        "missing_type_evidence",
                        "Type evidence is unavailable; validate this expression during build.",
                    ),
                )
            ),
        )
    text = str(value).strip()
    suggestion_values = _suggestion_values(suggestions)
    warnings: list[dict[str, str]] = []
    unresolved = is_unresolved(text)
    if unresolved:
        warnings.append(
            _warning("unresolved_value", "A concrete C expression is required.")
        )
    if text and not _balanced_expression(text):
        warnings.append(
            _warning(
                "unbalanced_expression",
                "Parentheses, brackets, braces, or quotes appear unbalanced.",
            )
        )
    if not type_hint:
        warnings.append(
            _warning(
                "missing_type_evidence",
                "Type evidence is unavailable; validate this expression during build.",
            )
        )
    else:
        if _scalar_expected(type_hint) and '"' in text:
            warnings.append(
                _warning(
                    "scalar_string_mismatch",
                    "A string literal was entered for a scalar-looking target.",
                )
            )
        if _pointer_expected(type_hint) and text and not unresolved:
            if not _plausible_pointer_expression(text, suggestion_values):
                warnings.append(
                    _warning(
                        "pointer_expression_suspect",
                        "The expression does not look like NULL, an address, or a pointer identifier.",
                    )
                )
    if text and _NON_C90_RE.search(text):
        warnings.append(
            _warning(
                "possible_non_c90_expression",
                "The expression may use syntax or constants unavailable in C90/VC6.",
            )
        )
    if (
        text
        and not unresolved
        and _IDENTIFIER_RE.fullmatch(text)
        and text not in suggestion_values
        and text not in {"NULL"}
    ):
        warnings.append(
            _warning(
                "unknown_identifier",
                "The identifier is not present in the current suggestion evidence.",
            )
        )
    if text and not unresolved and suggestion_values and text not in suggestion_values:
        warnings.append(
            _warning(
                "outside_suggestions",
                "The free-form value differs from the current evidence-backed suggestions.",
            )
        )
    # Preserve first occurrence if multiple heuristics reach the same code.
    unique: dict[str, dict[str, str]] = {}
    for warning in warnings:
        unique.setdefault(warning["code"], warning)
    return tuple(unique.values())
