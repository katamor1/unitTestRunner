from __future__ import annotations

import struct
from pathlib import Path

ARCHIVE_MAGIC = b"!<arch>\n"


def archive_member(name: str, payload: bytes) -> bytes:
    encoded_name = (name + "/").encode("ascii")[:16].ljust(16, b" ") if name not in {"/", "//"} else name.encode("ascii").ljust(16, b" ")
    header = (
        encoded_name
        + b"0".ljust(12, b" ")
        + b"0".ljust(6, b" ")
        + b"0".ljust(6, b" ")
        + b"100666".ljust(8, b" ")
        + str(len(payload)).encode("ascii").ljust(10, b" ")
        + b"`\n"
    )
    body = header + payload
    return body + (b"\n" if len(payload) % 2 else b"")


def import_object(symbol: str, dll_name: str = "Product.dll") -> bytes:
    data = symbol.encode("ascii") + b"\0" + dll_name.encode("ascii") + b"\0"
    return struct.pack("<HHHHIIHH", 0, 0xFFFF, 0, 0x14C, 0, len(data), 0, 0) + data


def coff_object(symbol: str) -> bytes:
    encoded = symbol.encode("ascii")
    if len(encoded) <= 8:
        name = encoded.ljust(8, b"\0")
        string_table = struct.pack("<I", 4)
    else:
        name = struct.pack("<II", 0, 4)
        string_table = struct.pack("<I", 4 + len(encoded) + 1) + encoded + b"\0"
    header = struct.pack("<HHIIIHH", 0x14C, 0, 0, 20, 1, 0, 0)
    symbol_entry = name + struct.pack("<IhHBB", 0, 1, 0, 2, 0)
    return header + symbol_entry + string_table


def first_linker_member(symbols: list[tuple[str, int]]) -> bytes:
    return (
        struct.pack(">I", len(symbols))
        + b"".join(struct.pack(">I", offset) for _name, offset in symbols)
        + b"".join(name.encode("ascii") + b"\0" for name, _offset in symbols)
    )


def write_import_library(path: Path, symbol: str) -> None:
    member_payload = import_object(symbol)
    placeholder = archive_member("/", first_linker_member([(symbol, 0)]))
    member_offset = len(ARCHIVE_MAGIC) + len(placeholder)
    linker = archive_member("/", first_linker_member([(symbol, member_offset)]))
    path.write_bytes(ARCHIVE_MAGIC + linker + archive_member("import.obj", member_payload))


def write_object_library_without_linker(path: Path, symbol: str) -> None:
    path.write_bytes(ARCHIVE_MAGIC + archive_member("object.obj", coff_object(symbol)))


def second_linker_member(member_offsets: list[int], symbols: list[tuple[str, int]]) -> bytes:
    return (
        struct.pack("<I", len(member_offsets))
        + b"".join(struct.pack("<I", offset) for offset in member_offsets)
        + struct.pack("<I", len(symbols))
        + b"".join(struct.pack("<H", member_index) for _name, member_index in symbols)
        + b"".join(name.encode("ascii") + b"\0" for name, _member_index in symbols)
    )


def write_library_with_second_linker(path: Path, symbol: str) -> None:
    member_payload = coff_object(symbol)
    first_placeholder = archive_member("/", first_linker_member([]))
    second_placeholder = archive_member("/", second_linker_member([0], [(symbol, 1)]))
    object_offset = len(ARCHIVE_MAGIC) + len(first_placeholder) + len(second_placeholder)
    second = archive_member("/", second_linker_member([object_offset], [(symbol, 1)]))
    path.write_bytes(ARCHIVE_MAGIC + first_placeholder + second + archive_member("second.obj", member_payload))
