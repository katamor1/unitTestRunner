from __future__ import annotations

from pathlib import Path

from .source_models import LineMapEntry, MaskedRange, MaskedSource, SourceWarning


def mask_source_text(text: str, path: Path | str) -> MaskedSource:
    chars = list(text)
    ranges: list[MaskedRange] = []
    warnings: list[SourceWarning] = []
    line_starts = _line_starts(text)
    index = 0
    state = "normal"
    current_kind: str | None = None
    start_index = 0
    quote = ""
    while index < len(chars):
        current = chars[index]
        nxt = chars[index + 1] if index + 1 < len(chars) else ""
        if state == "normal":
            if current == "/" and nxt == "*":
                current_kind = "block_comment"
                start_index = index
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "block_comment"
                continue
            if current == "/" and nxt == "/":
                current_kind = "line_comment"
                start_index = index
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "line_comment"
                continue
            if current == '"':
                current_kind = "string_literal"
                quote = current
                start_index = index
                chars[index] = " "
                index += 1
                state = "literal"
                continue
            if current == "'":
                current_kind = "char_literal"
                quote = current
                start_index = index
                chars[index] = " "
                index += 1
                state = "literal"
                continue
        elif state == "block_comment":
            if current == "*" and nxt == "/":
                chars[index] = chars[index + 1] = " "
                _append_range(ranges, current_kind or "block_comment", text, start_index, index + 2, line_starts)
                index += 2
                state = "normal"
                current_kind = None
                continue
            if current != "\n":
                chars[index] = " "
        elif state == "line_comment":
            if current == "\n":
                _append_range(ranges, current_kind or "line_comment", text, start_index, index, line_starts)
                state = "normal"
                current_kind = None
            else:
                chars[index] = " "
        elif state == "literal":
            if current == "\\":
                chars[index] = " "
                if index + 1 < len(chars) and chars[index + 1] != "\n":
                    chars[index + 1] = " "
                    index += 2
                    continue
            elif current == quote:
                chars[index] = " "
                _append_range(ranges, current_kind or "string_literal", text, start_index, index + 1, line_starts)
                index += 1
                state = "normal"
                current_kind = None
                continue
            elif current != "\n":
                chars[index] = " "
        index += 1

    if state == "block_comment":
        _append_range(ranges, current_kind or "block_comment", text, start_index, len(text), line_starts)
        line, column = _line_column(line_starts, start_index)
        warnings.append(SourceWarning("unterminated_block_comment", "Block comment was not terminated.", line, column))
    elif state == "literal":
        _append_range(ranges, current_kind or "string_literal", text, start_index, len(text), line_starts)
        line, column = _line_column(line_starts, start_index)
        code = "unterminated_char_literal" if current_kind == "char_literal" else "unterminated_string_literal"
        warnings.append(SourceWarning(code, "Literal was not terminated.", line, column))

    return MaskedSource(
        original_path=Path(path).resolve(),
        original_text=text,
        masked_text="".join(chars),
        line_map=_line_map(text),
        masked_ranges=ranges,
        warnings=warnings,
    )


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _line_map(text: str) -> list[LineMapEntry]:
    return [LineMapEntry(index + 1, index + 1, start, start) for index, start in enumerate(_line_starts(text))]


def _append_range(ranges: list[MaskedRange], kind: str, text: str, start: int, end: int, line_starts: list[int]) -> None:
    start_line, start_column = _line_column(line_starts, start)
    end_line, end_column = _line_column(line_starts, max(start, end - 1))
    ranges.append(MaskedRange(kind, start_line, start_column, end_line, end_column, text[start:end][:80]))


def _line_column(line_starts: list[int], offset: int) -> tuple[int, int]:
    line_index = 0
    for index, start in enumerate(line_starts):
        if start > offset:
            break
        line_index = index
    return line_index + 1, offset - line_starts[line_index] + 1
