from __future__ import annotations

import re

from .source_models import LexToken


KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do", "double", "else",
    "enum", "extern", "float", "for", "goto", "if", "int", "long", "register", "return",
    "short", "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while",
}
TOKEN_RE = re.compile(r"[A-Za-z_]\w*|0[xX][0-9A-Fa-f]+|\d+(?:\.\d+)?|==|!=|<=|>=|->|\+\+|--|&&|\|\||[{}()\[\];,.*&=+\-/%<>!:?]")


def extract_tokens(masked_text: str) -> list[LexToken]:
    tokens: list[LexToken] = []
    offset = 0
    for line_number, line in enumerate(masked_text.splitlines(keepends=True), start=1):
        if line.lstrip().startswith("#"):
            offset += len(line)
            continue
        for match in TOKEN_RE.finditer(line):
            value = match.group(0)
            tokens.append(LexToken(_kind(value), value, line_number, match.start() + 1, offset + match.start(), offset + match.end()))
        offset += len(line)
    return tokens


def _kind(value: str) -> str:
    if re.match(r"[A-Za-z_]\w*$", value):
        return "keyword" if value in KEYWORDS else "identifier"
    if re.match(r"\d", value):
        return "number"
    if value in "{}()[];,.":
        return "punctuation"
    if value in {"*", "&", "=", "+", "-", "/", "%", "<", ">", "!", ":", "?", "==", "!=", "<=", ">=", "->", "++", "--", "&&", "||"}:
        return "operator"
    return "unknown"
