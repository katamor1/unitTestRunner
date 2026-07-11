from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


_DISPATCH_INCLUDE_RE = re.compile(
    r'^\s*#\s*include\s*["<]utr_dependency_dispatch\.h[">]',
    re.MULTILINE,
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_]\w*$")


@dataclass(frozen=True)
class DependencyRewriteIssue:
    call_id: str
    code: str
    message: str
    severity: Literal["error"] = "error"


@dataclass(frozen=True)
class _Edit:
    ordinal: int
    call_id: str
    start: int
    end: int
    replacement: str


def rewrite_dependency_calls(
    source: str,
    dispatches: list[dict[str, Any]],
) -> tuple[str, list[DependencyRewriteIssue]]:
    """Rewrite verified direct dependency calls in an extracted source copy.

    Rewrite coordinates are one-based and the end position is exclusive.  A
    coordinate is only trusted after the referenced text and direct-call shape
    have both been checked against ``source``.
    """

    line_starts = _line_starts(source)
    edits: list[_Edit] = []
    issues_by_ordinal: dict[int, DependencyRewriteIssue] = {}
    ordinal = 0

    for dispatch in dispatches:
        callee = str(dispatch.get("callee") or "")
        dispatcher_name = str(dispatch.get("dispatcher_name") or "")
        for site in dispatch.get("rewrite_sites") or []:
            current_ordinal = ordinal
            ordinal += 1
            call_id = str(site.get("call_id") or f"rewrite_site_{current_ordinal + 1}")
            if not callee or not _IDENTIFIER_RE.fullmatch(dispatcher_name):
                issues_by_ordinal[current_ordinal] = _issue(
                    call_id,
                    "invalid_dispatch",
                    f"{call_id}: dependency rewrite has an invalid callee or dispatcher name.",
                )
                continue
            try:
                start = _position_offset(source, line_starts, site.get("start"))
                end = _position_offset(source, line_starts, site.get("end"))
            except (KeyError, TypeError, ValueError) as exc:
                issues_by_ordinal[current_ordinal] = _issue(
                    call_id,
                    "invalid_position",
                    f"{call_id}: dependency rewrite position is invalid: {exc}",
                )
                continue
            if end <= start or source[start:end] != callee:
                actual = source[start:end] if 0 <= start <= end <= len(source) else ""
                issues_by_ordinal[current_ordinal] = _issue(
                    call_id,
                    "callee_mismatch",
                    f"{call_id}: expected callee {callee!r} at the declared position, found {actual!r}.",
                )
                continue
            if not _is_direct_call(source, start, end):
                issues_by_ordinal[current_ordinal] = _issue(
                    call_id,
                    "not_direct_call",
                    f"{call_id}: declared rewrite site is not an exact direct call to {callee}.",
                )
                continue
            edits.append(_Edit(current_ordinal, call_id, start, end, dispatcher_name))

    overlapping_ordinals = _overlapping_ordinals(edits)
    for edit in edits:
        if edit.ordinal in overlapping_ordinals:
            issues_by_ordinal[edit.ordinal] = _issue(
                edit.call_id,
                "overlapping_rewrite",
                f"{edit.call_id}: dependency rewrite site overlaps another declared site.",
            )

    valid_edits = [edit for edit in edits if edit.ordinal not in issues_by_ordinal]
    rewritten = source
    for edit in sorted(valid_edits, key=lambda item: item.start, reverse=True):
        rewritten = rewritten[: edit.start] + edit.replacement + rewritten[edit.end :]

    if valid_edits and not _DISPATCH_INCLUDE_RE.search(rewritten):
        rewritten = _add_dispatch_include(rewritten)

    issues = [issues_by_ordinal[index] for index in sorted(issues_by_ordinal)]
    return rewritten, issues


def _issue(call_id: str, code: str, message: str) -> DependencyRewriteIssue:
    return DependencyRewriteIssue(call_id=call_id, code=code, message=message)


def _line_starts(source: str) -> list[int]:
    starts = [0]
    starts.extend(index + 1 for index, character in enumerate(source) if character == "\n")
    return starts


def _position_offset(source: str, line_starts: list[int], position: Any) -> int:
    if not isinstance(position, dict):
        raise TypeError("position must be an object")
    line = int(position["line"])
    column = int(position["column"])
    if line < 1 or line > len(line_starts) or column < 1:
        raise ValueError(f"line {line}, column {column} is outside the source")
    offset = line_starts[line - 1] + column - 1
    line_limit = line_starts[line] if line < len(line_starts) else len(source)
    if offset > line_limit:
        raise ValueError(f"line {line}, column {column} is outside the source")
    return offset


def _is_direct_call(source: str, start: int, end: int) -> bool:
    if _is_preprocessor_use(source, start):
        return False
    previous = source[start - 1] if start else ""
    if previous and (previous.isalnum() or previous in "_.>:"):
        return False
    cursor = end
    while cursor < len(source) and source[cursor] in " \t\f\v":
        cursor += 1
    return cursor < len(source) and source[cursor] == "("


def _is_preprocessor_use(source: str, offset: int) -> bool:
    line_start = source.rfind("\n", 0, offset) + 1
    logical_start = line_start
    while logical_start > 0:
        previous_end = logical_start - 1
        if previous_end > 0 and source[previous_end - 1] == "\r":
            previous_end -= 1
        previous_start = source.rfind("\n", 0, previous_end) + 1
        if not source[previous_start:previous_end].rstrip().endswith("\\"):
            break
        logical_start = previous_start
    return source[logical_start:line_start if logical_start != line_start else offset].lstrip().startswith("#")


def _overlapping_ordinals(edits: list[_Edit]) -> set[int]:
    overlapping: set[int] = set()
    ordered = sorted(edits, key=lambda item: (item.start, item.end, item.ordinal))
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if right.start >= left.end:
                break
            overlapping.add(left.ordinal)
            overlapping.add(right.ordinal)
    return overlapping


def _add_dispatch_include(source: str) -> str:
    newline = "\r\n" if "\r\n" in source else ("\r" if "\r" in source and "\n" not in source else "\n")
    include = f'#include "utr_dependency_dispatch.h"{newline}'
    if source.startswith("\ufeff"):
        return "\ufeff" + include + source[1:]
    return include + source
