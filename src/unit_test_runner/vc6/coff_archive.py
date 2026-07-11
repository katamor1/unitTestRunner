from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

_ARCHIVE_MAGIC = b"!<arch>\n"
_MEMBER_HEADER_SIZE = 60
_MAX_MEMBERS = 100_000
_MAX_SYMBOLS = 1_000_000
_MAX_NAME_BYTES = 16_384


@dataclass(frozen=True)
class LibrarySymbol:
    raw_name: str
    normalized_name: str
    provider_kind: str
    member_name: str | None = None


@dataclass(frozen=True)
class LibraryScanWarning:
    code: str
    message: str
    member_name: str | None = None


@dataclass
class LibrarySymbolIndex:
    library_path: Path
    scan_status: str
    symbols_by_normalized_name: dict[str, list[LibrarySymbol]] = field(default_factory=dict)
    warnings: list[LibraryScanWarning] = field(default_factory=list)


@dataclass(frozen=True)
class _ArchiveMember:
    name: str
    header_offset: int
    payload_offset: int
    payload_size: int


def normalize_c_link_symbol(raw_name: str) -> str | None:
    value = raw_name.strip()
    if not value or value.startswith("?"):
        return None
    if value.startswith("__imp__"):
        value = value[len("__imp__") :]
    elif value.startswith("__imp_"):
        value = value[len("__imp_") :]
    if value.startswith("_"):
        value = value[1:]
    value = re.sub(r"@\d+$", "", value)
    return value if re.fullmatch(r"[A-Za-z_]\w*", value) else None


class LibrarySymbolCache:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, int, int], LibrarySymbolIndex] = {}

    def scan(self, path: Path | str) -> LibrarySymbolIndex:
        library = Path(path).resolve()
        try:
            stat = library.stat()
        except OSError as exc:
            return LibrarySymbolIndex(library, "failed", warnings=[LibraryScanWarning("library_stat_failed", str(exc))])
        key = (str(library), stat.st_size, stat.st_mtime_ns)
        cached = self._entries.get(key)
        if cached is not None:
            return cached
        index = scan_library_symbols(library)
        self._entries[key] = index
        return index


def scan_library_symbols(path: Path | str) -> LibrarySymbolIndex:
    library = Path(path).resolve()
    warnings: list[LibraryScanWarning] = []
    try:
        data = library.read_bytes()
    except OSError as exc:
        return LibrarySymbolIndex(library, "failed", warnings=[LibraryScanWarning("library_read_failed", str(exc))])
    if not data.startswith(_ARCHIVE_MAGIC):
        return LibrarySymbolIndex(library, "failed", warnings=[LibraryScanWarning("invalid_archive_signature", "File is not a Microsoft COFF archive.")])
    try:
        members = list(_iter_members(data, warnings))
    except ValueError as exc:
        warnings.append(LibraryScanWarning("malformed_archive", str(exc)))
        return LibrarySymbolIndex(library, "failed", warnings=warnings)
    by_header = {member.header_offset: member for member in members}
    symbols: list[LibrarySymbol] = []
    valid_linker_index = False
    fallback_scanned = False
    linker_members = [member for member in members if member.name == "/"]
    for position, member in enumerate(linker_members[:2]):
        payload = data[member.payload_offset : member.payload_offset + member.payload_size]
        try:
            entries = _parse_first_linker_member(payload) if position == 0 else _parse_second_linker_member(payload)
        except ValueError as exc:
            warnings.append(LibraryScanWarning("linker_member_invalid", str(exc), member.name))
            continue
        member_symbols: list[LibrarySymbol] = []
        invalid_offsets = False
        for raw_name, header_offset in entries:
            target = by_header.get(header_offset)
            if target is None or target.name in {"/", "//"}:
                invalid_offsets = True
                warnings.append(LibraryScanWarning("linker_member_offset_invalid", f"Symbol {raw_name} refers to invalid archive member offset {header_offset}.", member.name))
                continue
            normalized = normalize_c_link_symbol(raw_name)
            if normalized is None:
                continue
            target_payload = data[target.payload_offset : target.payload_offset + target.payload_size]
            provider_kind = "import_library" if _is_import_object(target_payload) else "static_library"
            member_symbols.append(LibrarySymbol(raw_name, normalized, provider_kind, target.name))
        if not invalid_offsets:
            valid_linker_index = True
        symbols.extend(member_symbols)
    if not valid_linker_index:
        warnings.append(LibraryScanWarning("linker_member_missing", "No usable linker-member symbol index was found; scanning COFF members."))
        for member in members:
            if member.name in {"/", "//"}:
                continue
            payload = data[member.payload_offset : member.payload_offset + member.payload_size]
            if _is_import_object(payload):
                try:
                    symbol = _parse_import_object(payload, member.name)
                except ValueError as exc:
                    warnings.append(LibraryScanWarning("import_object_invalid", str(exc), member.name))
                    continue
                fallback_scanned = True
                if symbol is not None:
                    symbols.append(symbol)
                continue
            try:
                symbols.extend(_parse_coff_object(payload, member.name))
                fallback_scanned = True
            except ValueError as exc:
                warnings.append(LibraryScanWarning("unsupported_coff_member", str(exc), member.name))
    by_name: dict[str, list[LibrarySymbol]] = {}
    seen: set[tuple[str, str, str, str | None]] = set()
    for symbol in symbols:
        key = (symbol.normalized_name, symbol.raw_name, symbol.provider_kind, symbol.member_name)
        if key in seen:
            continue
        seen.add(key)
        by_name.setdefault(symbol.normalized_name, []).append(symbol)
    status = "ok" if valid_linker_index or fallback_scanned else "failed"
    if status == "failed" and not warnings:
        warnings.append(LibraryScanWarning("library_symbol_scan_failed", "No scannable archive members were found."))
    return LibrarySymbolIndex(library, status, by_name, warnings)


def _iter_members(data: bytes, warnings: list[LibraryScanWarning]):
    offset = len(_ARCHIVE_MAGIC)
    member_count = 0
    long_names = b""
    while offset < len(data):
        if member_count >= _MAX_MEMBERS:
            raise ValueError(f"Archive exceeds member limit {_MAX_MEMBERS}.")
        if len(data) - offset < _MEMBER_HEADER_SIZE:
            raise ValueError(f"Truncated archive member header at offset {offset}.")
        header = data[offset : offset + _MEMBER_HEADER_SIZE]
        if header[58:60] != b"`\n":
            raise ValueError(f"Invalid archive member trailer at offset {offset}.")
        size_field = header[48:58].decode("ascii", errors="strict").strip()
        if not size_field.isdigit():
            raise ValueError(f"Invalid archive member size at offset {offset}: {size_field!r}.")
        payload_size = int(size_field)
        payload_offset = offset + _MEMBER_HEADER_SIZE
        payload_end = payload_offset + payload_size
        if payload_end > len(data):
            raise ValueError(f"Archive member at offset {offset} extends past end of file.")
        raw_name = header[:16].decode("ascii", errors="replace").rstrip()
        name = _resolve_member_name(raw_name, long_names)
        member = _ArchiveMember(name, offset, payload_offset, payload_size)
        yield member
        if name == "//":
            long_names = data[payload_offset:payload_end]
        offset = payload_end + (payload_size & 1)
        member_count += 1
    if offset != len(data):
        warnings.append(LibraryScanWarning("archive_padding_invalid", "Archive ended inside a member padding byte."))


def _resolve_member_name(raw_name: str, long_names: bytes) -> str:
    value = raw_name.strip()
    if value in {"/", "//"}:
        return value
    if value.startswith("/") and value[1:].isdigit() and long_names:
        start = int(value[1:])
        if start < len(long_names):
            end = long_names.find(b"/\n", start)
            if end == -1:
                end = long_names.find(b"\0", start)
            if end == -1:
                end = len(long_names)
            return long_names[start:end].decode("utf-8", errors="replace")
    return value.rstrip("/")


def _parse_first_linker_member(payload: bytes) -> list[tuple[str, int]]:
    if len(payload) < 4:
        raise ValueError("First linker member is shorter than its symbol count.")
    count = struct.unpack_from(">I", payload, 0)[0]
    if count > _MAX_SYMBOLS:
        raise ValueError(f"First linker member exceeds symbol limit {_MAX_SYMBOLS}.")
    offsets_end = 4 + count * 4
    if offsets_end > len(payload):
        raise ValueError("First linker member offset table is truncated.")
    offsets = list(struct.unpack_from(f">{count}I", payload, 4)) if count else []
    names = _read_null_names(payload, offsets_end, count)
    return list(zip(names, offsets))


def _parse_second_linker_member(payload: bytes) -> list[tuple[str, int]]:
    if len(payload) < 4:
        raise ValueError("Second linker member is shorter than its member count.")
    member_count = struct.unpack_from("<I", payload, 0)[0]
    if member_count > _MAX_MEMBERS:
        raise ValueError(f"Second linker member exceeds member limit {_MAX_MEMBERS}.")
    member_offsets_end = 4 + member_count * 4
    if member_offsets_end + 4 > len(payload):
        raise ValueError("Second linker member member-offset table is truncated.")
    member_offsets = list(struct.unpack_from(f"<{member_count}I", payload, 4)) if member_count else []
    symbol_count = struct.unpack_from("<I", payload, member_offsets_end)[0]
    if symbol_count > _MAX_SYMBOLS:
        raise ValueError(f"Second linker member exceeds symbol limit {_MAX_SYMBOLS}.")
    indices_start = member_offsets_end + 4
    indices_end = indices_start + symbol_count * 2
    if indices_end > len(payload):
        raise ValueError("Second linker member symbol-index table is truncated.")
    indices = list(struct.unpack_from(f"<{symbol_count}H", payload, indices_start)) if symbol_count else []
    names = _read_null_names(payload, indices_end, symbol_count)
    result: list[tuple[str, int]] = []
    for name, member_index in zip(names, indices):
        if member_index == 0 or member_index > len(member_offsets):
            raise ValueError(f"Second linker member contains invalid 1-based member index {member_index}.")
        result.append((name, member_offsets[member_index - 1]))
    return result


def _read_null_names(payload: bytes, start: int, count: int) -> list[str]:
    names: list[str] = []
    cursor = start
    for _ in range(count):
        if cursor >= len(payload):
            raise ValueError("Linker member symbol-name table is truncated.")
        end = payload.find(b"\0", cursor)
        if end == -1:
            raise ValueError("Linker member symbol name is not null-terminated.")
        if end - cursor > _MAX_NAME_BYTES:
            raise ValueError(f"Linker member symbol name exceeds {_MAX_NAME_BYTES} bytes.")
        names.append(payload[cursor:end].decode("ascii", errors="replace"))
        cursor = end + 1
    return names


def _is_import_object(payload: bytes) -> bool:
    return len(payload) >= 20 and payload[:4] == b"\0\0\xff\xff"


def _parse_import_object(payload: bytes, member_name: str) -> LibrarySymbol | None:
    if not _is_import_object(payload):
        raise ValueError("Member is not a Microsoft import object.")
    size_of_data = struct.unpack_from("<I", payload, 12)[0]
    data_start = 20
    data_end = data_start + size_of_data
    if data_end > len(payload):
        raise ValueError("Import-object data extends past the member payload.")
    terminator = payload.find(b"\0", data_start, data_end)
    if terminator == -1:
        raise ValueError("Import-object symbol name is not null-terminated.")
    if terminator - data_start > _MAX_NAME_BYTES:
        raise ValueError(f"Import-object symbol name exceeds {_MAX_NAME_BYTES} bytes.")
    raw_name = payload[data_start:terminator].decode("ascii", errors="replace")
    normalized = normalize_c_link_symbol(raw_name)
    if normalized is None:
        return None
    return LibrarySymbol(raw_name, normalized, "import_library", member_name)


def _parse_coff_object(payload: bytes, member_name: str) -> list[LibrarySymbol]:
    if len(payload) < 20:
        raise ValueError("COFF member is shorter than the file header.")
    if _is_import_object(payload):
        symbol = _parse_import_object(payload, member_name)
        return [symbol] if symbol is not None else []
    _machine, _sections, _timestamp, symbol_pointer, symbol_count, optional_size, _characteristics = struct.unpack_from("<HHIIIHH", payload, 0)
    if optional_size and 20 + optional_size > len(payload):
        raise ValueError("COFF optional header extends past the member payload.")
    if symbol_count > _MAX_SYMBOLS:
        raise ValueError(f"COFF member exceeds symbol limit {_MAX_SYMBOLS}.")
    symbol_table_end = symbol_pointer + symbol_count * 18
    if symbol_pointer < 20 or symbol_table_end > len(payload):
        raise ValueError("COFF symbol table is outside the member payload.")
    if symbol_table_end + 4 > len(payload):
        raise ValueError("COFF string table length is missing.")
    string_table_size = struct.unpack_from("<I", payload, symbol_table_end)[0]
    if string_table_size < 4 or symbol_table_end + string_table_size > len(payload):
        raise ValueError("COFF string table is invalid or truncated.")
    result: list[LibrarySymbol] = []
    index = 0
    while index < symbol_count:
        entry_offset = symbol_pointer + index * 18
        entry = payload[entry_offset : entry_offset + 18]
        raw_name = _coff_symbol_name(entry[:8], payload, symbol_table_end, string_table_size)
        _value, section_number, _type, storage_class, aux_count = struct.unpack_from("<IhHBB", entry, 8)
        if index + aux_count >= symbol_count and aux_count:
            raise ValueError("COFF auxiliary symbol count extends past the symbol table.")
        if storage_class == 2 and section_number > 0 and raw_name:
            normalized = normalize_c_link_symbol(raw_name)
            if normalized is not None:
                result.append(LibrarySymbol(raw_name, normalized, "static_library", member_name))
        index += 1 + aux_count
    return result


def _coff_symbol_name(name_field: bytes, payload: bytes, string_table_start: int, string_table_size: int) -> str:
    if name_field[:4] == b"\0\0\0\0":
        offset = struct.unpack_from("<I", name_field, 4)[0]
        if offset < 4 or offset >= string_table_size:
            raise ValueError(f"COFF string-table name offset {offset} is invalid.")
        start = string_table_start + offset
        end_limit = string_table_start + string_table_size
        end = payload.find(b"\0", start, end_limit)
        if end == -1:
            raise ValueError("COFF long symbol name is not null-terminated.")
        if end - start > _MAX_NAME_BYTES:
            raise ValueError(f"COFF symbol name exceeds {_MAX_NAME_BYTES} bytes.")
        return payload[start:end].decode("ascii", errors="replace")
    return name_field.split(b"\0", 1)[0].decode("ascii", errors="replace")
