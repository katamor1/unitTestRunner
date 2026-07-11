# DSP/LIB Linked Function Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the actual `.lib` files selected by a VC6 DSP/DSW configuration, confirm exported C symbols from Microsoft COFF archives, classify matching calls as `linked_library_function`, omit their generated stubs, and link the real libraries from generated Makefiles and VC6 DSPs.

**Architecture:** Extend the DSP parser with configuration-scoped linker settings, resolve explicit and direct-dependency libraries into a `LinkContext`, index their COFF/import symbols with an in-process cache, and pass a normalized provider map into call analysis before test design and harness generation. Persist the resolved link inputs in `build_context.json`, then carry them through build-workspace models, VC6 Makefile generation, verification linking, VC6 debug DSP generation, and existing reports.

**Tech Stack:** Python 3.12+, standard library only (`dataclasses`, `pathlib`, `struct`, `os`, `re`), pytest/unittest-compatible tests, VC6 DSP/DSW text formats, Microsoft COFF archive format.

## Global Constraints

- Use only the Python standard library; do not add runtime dependencies.
- Only an existing `.lib` may be added to the resolved link context.
- A function is excluded from stub generation only when a successfully scanned library contains a matching normalized C symbol.
- C symbol normalization supports `Foo`, `_Foo`, `_Foo@8`, `Foo@8`, `__imp__Foo`, and `__imp__Foo@8`; C++ names beginning with `?` are not normalized.
- Analyze explicit libraries from the selected DSP configuration first, preserving DSP order.
- Analyze only direct DSW dependency projects after explicit libraries; do not traverse transitive dependencies.
- A dependency project must use the same platform and short configuration name, compared case-insensitively.
- Resolve dependency output libraries in this order: `/implib:`, `.lib` `/out:`, then `Output_Dir/ProjectName.lib`.
- Link resolved libraries by original absolute path; do not copy them into generated workspaces.
- Accept both static COFF libraries and DLL import libraries.
- Prefer linker-member symbol indexes; scan regular COFF objects only when linker members are absent or unusable.
- Cache symbol indexes only inside one CLI process; do not create persistent cache files.
- When library scanning fails, retain the library as a link input, retain normal stub candidacy, and emit `library_symbol_scan_failed`.
- When multiple libraries provide one normalized function, preserve link order, use the first provider as `link_provider`, retain all providers in `link_providers`, and emit `multiple_library_symbol_providers`.
- Keep `analyze_calls` backward compatible by making link-provider input optional.
- Preserve all existing CRT `standard_library` classifications before linked-library classification.

---

## File Structure

### New production files

- `src/unit_test_runner/vc6/dsp_link_options.py` — tokenize and parse `LINK32` options into structured settings.
- `src/unit_test_runner/vc6/coff_archive.py` — safe Microsoft COFF archive/import-object indexing and per-process cache.
- `src/unit_test_runner/vc6/link_context.py` — resolved-link data models and warning models.
- `src/unit_test_runner/vc6/link_library_resolver.py` — DSP/DSW configuration selection, macro expansion, path resolution, dependency output resolution, symbol-provider map construction.

### Modified production files

- `src/unit_test_runner/vc6/dsp_models.py` — add `DspLinkSettings` and configuration linker fields.
- `src/unit_test_runner/vc6/dsp_parser.py` — parse `LINK32`, `Output_Dir`, and `Intermediate_Dir` per configuration.
- `src/unit_test_runner/c_analyzer/call_models.py` — add `LinkProvider` and provider fields on `FunctionCall`.
- `src/unit_test_runner/c_analyzer/call_analyzer.py` — consume optional providers and classify `linked_library_function`.
- `src/unit_test_runner/c_analyzer/call_report_writer.py` — render provider details and warnings.
- `src/unit_test_runner/dossier/workflow.py` — construct link context before call analysis and persist it into build context.
- `src/unit_test_runner/build/build_models.py` — represent link libraries in workspace reports.
- `src/unit_test_runner/build/build_workspace_generator.py` — add libraries and library directories to generated links.
- `src/unit_test_runner/build/verification_toolchain.py` — include resolved link inputs for MSVC-flavored verification builds.
- `src/unit_test_runner/build/build_report_writer.py` — report effective libraries and library directories.
- `src/unit_test_runner/vc6/debug_workspace_writer.py` — emit effective libraries and `/libpath:` values in generated `LINK32` lines.
- `src/unit_test_runner/reports/quick_summary.py` — summarize resolved libraries, linked functions, and link-analysis warnings.

### New and modified tests

- `tests/test_vc6_dsp_link_settings.py`
- `tests/coff_fixture.py`
- `tests/test_vc6_coff_archive.py`
- `tests/test_linked_library_call_analysis.py`
- `tests/test_vc6_link_library_resolver.py`
- `tests/test_dossier_link_context_integration.py`
- `tests/test_build_workspace_link_libraries.py`
- `tests/test_vc6_debug_workspace_writer.py`
- `tests/test_quick_summary_generation.py`
- `tests/test_linked_library_end_to_end.py`

---

### Task 1: Parse VC6 DSP linker settings

**Files:**
- Create: `src/unit_test_runner/vc6/dsp_link_options.py`
- Modify: `src/unit_test_runner/vc6/dsp_models.py:48-104`
- Modify: `src/unit_test_runner/vc6/dsp_parser.py:14-116`
- Test: `tests/test_vc6_dsp_link_settings.py`

**Interfaces:**
- Consumes: `PathLikeValue`, DSP directory, workspace root, raw `LINK32` option text.
- Produces: `DspLinkSettings`, `tokenize_linker_options(text: str) -> list[str]`, `parse_link_settings(tokens, dsp_dir, workspace_root) -> DspLinkSettings`, `merge_link_settings(target, source) -> None`.

- [ ] **Step 1: Write parser tests for configuration-scoped LINK32 and PROP values**

Create `tests/test_vc6_dsp_link_settings.py` with these focused cases:

```python
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.vc6.dsp_parser import parse_dsp


class Vc6DspLinkSettingsTests(unittest.TestCase):
    def test_link32_libraries_paths_and_outputs_are_configuration_scoped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dsp = root / "App.dsp"
            dsp.write_text(
                '# Microsoft Developer Studio Project File - Name="App" - Package Owner=<4>\n'
                '# TARGTYPE "Win32 (x86) Console Application" 0x0103\n'
                '!IF  "$(CFG)" == "App - Win32 Debug"\n'
                '# PROP Output_Dir "Debug"\n'
                '# PROP Intermediate_Dir "Debug\\obj"\n'
                '# ADD BASE LINK32 base.lib /libpath:"..\\base"\n'
                '# ADD LINK32 first.lib "..\\third party\\second.lib" /libpath:"..\\lib" '
                '/out:"Debug\\App.exe" /implib:"Debug\\AppImport.lib"\n'
                '!ENDIF\n'
                '!IF  "$(CFG)" == "App - Win32 Release"\n'
                '# PROP Output_Dir "Release"\n'
                '# ADD LINK32 release.lib /out:"Release\\App.exe"\n'
                '!ENDIF\n',
                encoding="cp932",
            )

            project = parse_dsp(dsp, root)
            debug = next(item for item in project.configurations if item.full_name.endswith("Win32 Debug"))
            release = next(item for item in project.configurations if item.full_name.endswith("Win32 Release"))

            self.assertEqual(["base.lib", "first.lib", "../third party/second.lib"], debug.link_settings.libraries)
            self.assertEqual(["../base", "../lib"], [item.normalized for item in debug.link_settings.library_dirs])
            self.assertEqual("Debug/App.exe", debug.link_settings.output_file.normalized)
            self.assertEqual("Debug/AppImport.lib", debug.link_settings.import_library.normalized)
            self.assertEqual("Debug", debug.link_settings.output_dir.normalized)
            self.assertEqual("Debug/obj", debug.link_settings.intermediate_dir.normalized)
            self.assertEqual(["release.lib"], release.link_settings.libraries)
            self.assertEqual("Release/App.exe", release.link_settings.output_file.normalized)

    def test_link_macros_are_preserved_for_the_resolver(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dsp = root / "MacroLib.dsp"
            dsp.write_text(
                '# Microsoft Developer Studio Project File - Name="MacroLib" - Package Owner=<4>\n'
                '!IF  "$(CFG)" == "MacroLib - Win32 Debug"\n'
                '# PROP Output_Dir "$(CFG)\\out"\n'
                '# ADD LINK32 "%PRODUCT_LIB%\\Product.lib" /libpath:"($SDK_ROOT)\\lib"\n'
                '!ENDIF\n',
                encoding="cp932",
            )

            project = parse_dsp(dsp, root)
            settings = project.configurations[0].link_settings

            self.assertEqual(["%PRODUCT_LIB%/Product.lib"], settings.libraries)
            self.assertEqual(["SDK_ROOT"], settings.library_dirs[0].unresolved_macros)
            self.assertIn("CFG", settings.output_dir.unresolved_macros)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new parser tests and verify they fail**

Run:

```bash
python -m pytest tests/test_vc6_dsp_link_settings.py -q
```

Expected: failures because `DspConfiguration` has no `link_settings` and the parser ignores `LINK32`/`PROP` linker fields.

- [ ] **Step 3: Add the linker settings model**

Add this model to `src/unit_test_runner/vc6/dsp_models.py` and add `linker_base_options`, `linker_options`, and `link_settings` to `DspConfiguration`:

```python
@dataclass
class DspLinkSettings:
    libraries: list[str] = field(default_factory=list)
    library_dirs: list[PathLikeValue] = field(default_factory=list)
    output_file: PathLikeValue | None = None
    import_library: PathLikeValue | None = None
    output_dir: PathLikeValue | None = None
    intermediate_dir: PathLikeValue | None = None
    raw_options: list[str] = field(default_factory=list)
    unresolved_macros: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "libraries": list(self.libraries),
            "library_dirs": [item.to_dict() for item in self.library_dirs],
            "output_file": self.output_file.to_dict() if self.output_file else None,
            "import_library": self.import_library.to_dict() if self.import_library else None,
            "output_dir": self.output_dir.to_dict() if self.output_dir else None,
            "intermediate_dir": self.intermediate_dir.to_dict() if self.intermediate_dir else None,
            "raw_options": list(self.raw_options),
            "unresolved_macros": list(self.unresolved_macros),
        }
```

Update `DspConfiguration` exactly as follows:

```python
linker_base_options: list[str] = field(default_factory=list)
linker_options: list[str] = field(default_factory=list)
link_settings: DspLinkSettings = field(default_factory=DspLinkSettings)
```

Include all three fields in `DspConfiguration.to_dict()`.

- [ ] **Step 4: Implement LINK32 tokenization and parsing**

Create `src/unit_test_runner/vc6/dsp_link_options.py` with these public functions and parsing rules:

```python
from __future__ import annotations

import re
from pathlib import Path

from .dsp_models import DspLinkSettings, PathLikeValue
from .dsp_options import tokenize_compiler_options

_MACRO_PATTERNS = (
    re.compile(r"\$\(([^)]+)\)"),
    re.compile(r"\$\{([^}]+)\}"),
    re.compile(r"\(\$([A-Za-z_][A-Za-z0-9_]*)\)"),
    re.compile(r"%([^%]+)%"),
)


def tokenize_linker_options(text: str) -> list[str]:
    return tokenize_compiler_options(text)


def parse_link_settings(tokens: list[str], dsp_dir: Path, workspace_root: Path) -> DspLinkSettings:
    settings = DspLinkSettings(raw_options=list(tokens))
    index = 0
    while index < len(tokens):
        token = tokens[index]
        lower = token.lower()
        value = None
        option = None
        for prefix in ("/libpath", "/out", "/implib"):
            if lower == prefix:
                option = prefix
                if index + 1 < len(tokens):
                    index += 1
                    value = _strip_quotes(tokens[index])
                break
            if lower.startswith(prefix + ":"):
                option = prefix
                value = _strip_quotes(token[len(prefix) + 1 :])
                break
        if option == "/libpath" and value:
            settings.library_dirs.append(_path_like(value, dsp_dir, workspace_root))
        elif option == "/out" and value:
            settings.output_file = _path_like(value, dsp_dir, workspace_root)
        elif option == "/implib" and value:
            settings.import_library = _path_like(value, dsp_dir, workspace_root)
        elif not token.startswith("/") and _strip_quotes(token).lower().endswith(".lib"):
            settings.libraries.append(_strip_quotes(token).replace("\\", "/"))
        index += 1
    for item in [*settings.library_dirs, settings.output_file, settings.import_library]:
        if item is None:
            continue
        for macro in item.unresolved_macros:
            if macro not in settings.unresolved_macros:
                settings.unresolved_macros.append(macro)
    return settings


def merge_link_settings(target: DspLinkSettings, source: DspLinkSettings) -> None:
    for library in source.libraries:
        if library not in target.libraries:
            target.libraries.append(library)
    target.library_dirs.extend(source.library_dirs)
    target.raw_options.extend(item for item in source.raw_options if item not in target.raw_options)
    target.output_file = source.output_file or target.output_file
    target.import_library = source.import_library or target.import_library
    for macro in source.unresolved_macros:
        if macro not in target.unresolved_macros:
            target.unresolved_macros.append(macro)


def path_like_value(raw: str, dsp_dir: Path, workspace_root: Path) -> PathLikeValue:
    return _path_like(raw, dsp_dir, workspace_root)


def _path_like(raw: str, dsp_dir: Path, workspace_root: Path) -> PathLikeValue:
    clean = _strip_quotes(raw)
    normalized = clean.replace("\\", "/")
    macros = _macros(clean)
    if macros:
        return PathLikeValue(raw=raw, normalized=normalized, absolute=None, exists=None, unresolved_macros=macros)
    absolute = (dsp_dir / normalized).resolve() if not Path(normalized).is_absolute() else Path(normalized).resolve()
    return PathLikeValue(raw=raw, normalized=normalized, absolute=absolute, exists=absolute.exists(), unresolved_macros=[])


def _macros(value: str) -> list[str]:
    result: list[str] = []
    for pattern in _MACRO_PATTERNS:
        for match in pattern.findall(value):
            if match not in result:
                result.append(match)
    return result


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"')
```

Add `unresolved_macros: list[str] = field(default_factory=list)` to `PathLikeValue` and include it in `to_dict()`. Update existing `PathLikeValue(...)` construction in `dsp_options.py` to pass `unresolved_macros=_macros(clean)` for macro paths and `[]` for resolved paths.

- [ ] **Step 5: Extend the DSP parser**

In `src/unit_test_runner/vc6/dsp_parser.py`:

1. Import `merge_link_settings`, `parse_link_settings`, `path_like_value`, and `tokenize_linker_options`.
2. Add regexes:

```python
OUTPUT_DIR_RE = re.compile(r'^#\s+PROP(?:\s+BASE)?\s+Output_Dir\s+"(?P<value>[^"]*)"')
INTERMEDIATE_DIR_RE = re.compile(r'^#\s+PROP(?:\s+BASE)?\s+Intermediate_Dir\s+"(?P<value>[^"]*)"')
```

3. Inside each active configuration, parse `# PROP Output_Dir`, `# PROP Intermediate_Dir`, `# ADD BASE LINK32`, and `# ADD LINK32`.
4. Preserve BASE and non-BASE token arrays separately, while merging their effective settings in encounter order.
5. Emit `linker_options_without_configuration` if a `LINK32` line appears outside a configuration block.

Use this structure for the LINK32 branch:

```python
if line.startswith("# ADD") and " LINK32 " in line:
    if current_config is None:
        warnings.append(DspParseWarning("linker_options_without_configuration", "Linker options appeared outside a configuration block.", line_number, line))
        continue
    is_base = line.startswith("# ADD BASE LINK32")
    options_text = line.split(" LINK32 ", 1)[1]
    tokens = tokenize_linker_options(options_text)
    if is_base:
        current_config.linker_base_options.extend(tokens)
    else:
        current_config.linker_options.extend(tokens)
    merge_link_settings(current_config.link_settings, parse_link_settings(tokens, dsp_path.parent, workspace))
    continue
```

Set `output_dir` and `intermediate_dir` with `path_like_value()` when their PROP lines are encountered.

- [ ] **Step 6: Run parser tests and existing DSP tests**

Run:

```bash
python -m pytest tests/test_vc6_dsp_link_settings.py tests/test_vc6_dsp_parser.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add src/unit_test_runner/vc6/dsp_models.py src/unit_test_runner/vc6/dsp_link_options.py src/unit_test_runner/vc6/dsp_options.py src/unit_test_runner/vc6/dsp_parser.py tests/test_vc6_dsp_link_settings.py
git commit -m "Parse VC6 DSP linker settings"
```

---

### Task 2: Index Microsoft COFF archives and import libraries

**Files:**
- Create: `src/unit_test_runner/vc6/coff_archive.py`
- Create: `tests/coff_fixture.py`
- Create: `tests/test_vc6_coff_archive.py`

**Interfaces:**
- Produces: `normalize_c_link_symbol(raw_name: str) -> str | None`, `LibrarySymbol`, `LibraryScanWarning`, `LibrarySymbolIndex`, `LibrarySymbolCache.scan(path: Path) -> LibrarySymbolIndex`.
- Safety limits: 1,000,000 symbols, 100,000 archive members, 16,384-byte maximum symbol name.

- [ ] **Step 1: Create reusable synthetic COFF archive fixtures**

Create `tests/coff_fixture.py` with deterministic archive builders:

```python
from __future__ import annotations

import struct
from pathlib import Path

ARCHIVE_MAGIC = b"!<arch>\n"


def archive_member(name: str, payload: bytes) -> bytes:
    encoded_name = (name + "/").encode("ascii")[:16].ljust(16, b" ")
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
    linker_placeholder = archive_member("/", first_linker_member([(symbol, 0)]))
    member_offset = len(ARCHIVE_MAGIC) + len(linker_placeholder)
    linker = archive_member("/", first_linker_member([(symbol, member_offset)]))
    path.write_bytes(ARCHIVE_MAGIC + linker + archive_member("import.obj", member_payload))


def write_object_library_without_linker(path: Path, symbol: str) -> None:
    path.write_bytes(ARCHIVE_MAGIC + archive_member("object.obj", coff_object(symbol)))
```

- [ ] **Step 2: Write symbol normalization, import-object, linker-member, fallback, cache, and malformed-file tests**

Create `tests/test_vc6_coff_archive.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from tests.coff_fixture import write_import_library, write_object_library_without_linker
from unit_test_runner.vc6.coff_archive import LibrarySymbolCache, normalize_c_link_symbol


class Vc6CoffArchiveTests(unittest.TestCase):
    def test_vc6_c_symbol_decorations_normalize_to_one_name(self):
        for raw in ["Foo", "_Foo", "_Foo@8", "Foo@8", "__imp__Foo", "__imp__Foo@8"]:
            with self.subTest(raw=raw):
                self.assertEqual("Foo", normalize_c_link_symbol(raw))
        self.assertIsNone(normalize_c_link_symbol("?Foo@@YAHH@Z"))

    def test_import_library_uses_linker_member_and_reports_import_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            library = Path(temp_dir) / "Product.lib"
            write_import_library(library, "__imp__ProductCalc@8")

            index = LibrarySymbolCache().scan(library)

            self.assertEqual("ok", index.scan_status)
            symbols = index.symbols_by_normalized_name["ProductCalc"]
            self.assertEqual(["__imp__ProductCalc@8"], [item.raw_name for item in symbols])
            self.assertEqual(["import_library"], [item.provider_kind for item in symbols])

    def test_missing_linker_member_falls_back_to_coff_symbol_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            library = Path(temp_dir) / "Static.lib"
            write_object_library_without_linker(library, "_StaticCalc")

            index = LibrarySymbolCache().scan(library)

            self.assertEqual("ok", index.scan_status)
            self.assertEqual("static_library", index.symbols_by_normalized_name["StaticCalc"][0].provider_kind)
            self.assertTrue(any(item.code == "linker_member_missing" for item in index.warnings))

    def test_cache_returns_same_index_instance_for_unchanged_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            library = Path(temp_dir) / "Cached.lib"
            write_import_library(library, "_Cached")
            cache = LibrarySymbolCache()

            first = cache.scan(library)
            second = cache.scan(library)

            self.assertIs(first, second)

    def test_malformed_archive_fails_without_raising(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            library = Path(temp_dir) / "Broken.lib"
            library.write_bytes(b"not an archive")

            index = LibrarySymbolCache().scan(library)

            self.assertEqual("failed", index.scan_status)
            self.assertTrue(any(item.code == "invalid_archive_signature" for item in index.warnings))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the COFF tests and verify they fail**

Run:

```bash
python -m pytest tests/test_vc6_coff_archive.py -q
```

Expected: import failure because `unit_test_runner.vc6.coff_archive` does not exist.

- [ ] **Step 4: Implement safe archive models and symbol normalization**

Create `src/unit_test_runner/vc6/coff_archive.py` with these public models:

```python
@dataclass(frozen=True)
class LibrarySymbol:
    raw_name: str
    normalized_name: str
    provider_kind: str
    member_name: str | None


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
```

Use this exact normalization order:

```python
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
```

- [ ] **Step 5: Implement archive iteration, linker-member parsing, import-object parsing, and COFF fallback**

Implement these internal units with explicit bounds checks before every slice or integer unpack:

```python
_ARCHIVE_MAGIC = b"!<arch>\n"
_MEMBER_HEADER_SIZE = 60
_MAX_MEMBERS = 100_000
_MAX_SYMBOLS = 1_000_000
_MAX_NAME_BYTES = 16_384

@dataclass(frozen=True)
class _ArchiveMember:
    name: str
    header_offset: int
    payload_offset: int
    payload_size: int
```

Required behavior:

1. `_iter_members(data)` validates the 60-byte header, decimal size field, payload range, and even-byte padding.
2. `_parse_first_linker_member(payload)` reads big-endian count, count offsets, then count null-terminated names.
3. `_parse_second_linker_member(payload)` reads member count and offsets in little-endian, symbol count and 1-based member indexes in little-endian, then symbol names.
4. `_parse_import_object(payload, member_name)` recognizes `Sig1 == 0` and `Sig2 == 0xFFFF`, reads the first null-terminated string after the 20-byte header, and returns an `import_library` symbol.
5. `_parse_coff_object(payload, member_name)` reads the COFF file header, symbol-table pointer/count, 18-byte symbol entries, auxiliary-symbol skips, short names, string-table names, external storage class `2`, and positive section numbers.
6. `scan_library_symbols(path)` trusts linker-member names only after validating their referenced member offsets. It inspects referenced members to label import objects. If no valid linker-member index exists, it scans regular object members.
7. A malformed member adds a warning and never performs an out-of-range read.

- [ ] **Step 6: Implement the process-local cache**

Use a caller-owned cache object rather than module-global state:

```python
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
```

- [ ] **Step 7: Run COFF tests**

Run:

```bash
python -m pytest tests/test_vc6_coff_archive.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/unit_test_runner/vc6/coff_archive.py tests/coff_fixture.py tests/test_vc6_coff_archive.py
git commit -m "Index Microsoft COFF library symbols"
```

---

### Task 3: Add linked-library provider metadata to call analysis

**Files:**
- Modify: `src/unit_test_runner/c_analyzer/call_models.py:14-106`
- Modify: `src/unit_test_runner/c_analyzer/call_analyzer.py:48-117,211-220,269-302`
- Modify: `src/unit_test_runner/c_analyzer/call_report_writer.py:22-53`
- Create: `tests/test_linked_library_call_analysis.py`

**Interfaces:**
- Produces: `LinkProvider`, optional `link_providers_by_name` input to `analyze_calls`, `linked_library_function` classification.
- Preserves: Existing four-argument `analyze_calls(...)` calls.

- [ ] **Step 1: Write call-analysis tests using an injected provider map**

Create `tests/test_linked_library_call_analysis.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.c_analyzer.call_analyzer import analyze_calls
from unit_test_runner.c_analyzer.call_models import LinkProvider
from unit_test_runner.c_analyzer.function_locator import locate_function
from unit_test_runner.c_analyzer.global_access_analyzer import analyze_global_access
from unit_test_runner.c_analyzer.signature_extractor import extract_signature
from unit_test_runner.c_analyzer.source_digest import build_source_digest


class LinkedLibraryCallAnalysisTests(unittest.TestCase):
    def _analysis_inputs(self, root: Path):
        source = root / "consumer.c"
        source.write_text("int Consumer(int value) { return ProductCalc(value); }\n", encoding="ascii")
        digest = build_source_digest(source)
        location = locate_function(digest, "Consumer")
        signature = extract_signature(digest, location)
        globals_report = analyze_global_access(digest, location, signature)
        return digest, location, signature, globals_report

    def test_linked_library_function_is_not_a_stub_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            inputs = self._analysis_inputs(Path(temp_dir))
            provider = LinkProvider(
                library=Path("C:/product/lib/Product.lib"),
                symbol="_ProductCalc@4",
                provider_kind="static_library",
                source="explicit_link32",
                link_order=0,
                project_name="Product",
            )

            report = analyze_calls(*inputs, link_providers_by_name={"ProductCalc": [provider]})
            payload = report.to_dict()
            call = next(item for item in payload["calls"] if item["name"] == "ProductCalc")

            self.assertEqual("linked_library_function", call["target_kind"])
            self.assertEqual("_ProductCalc@4", call["link_provider"]["symbol"])
            self.assertEqual(["_ProductCalc@4"], [item["symbol"] for item in call["link_providers"]])
            self.assertNotIn("ProductCalc", {item["name"] for item in payload["stub_candidates"]})

    def test_multiple_providers_keep_link_order_and_emit_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            inputs = self._analysis_inputs(Path(temp_dir))
            providers = [
                LinkProvider(Path("C:/lib/First.lib"), "_ProductCalc@4", "static_library", "explicit_link32", 0, None),
                LinkProvider(Path("C:/lib/Second.lib"), "__imp__ProductCalc@4", "import_library", "direct_dependency_project", 1, "Second"),
            ]

            payload = analyze_calls(*inputs, link_providers_by_name={"ProductCalc": providers}).to_dict()
            call = next(item for item in payload["calls"] if item["name"] == "ProductCalc")

            self.assertEqual("C:/lib/First.lib", call["link_provider"]["library"])
            self.assertEqual(2, len(call["link_providers"]))
            self.assertTrue(any(item["code"] == "multiple_library_symbol_providers" for item in payload["warnings"]))

    def test_omitted_provider_map_preserves_existing_external_classification(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            inputs = self._analysis_inputs(Path(temp_dir))

            payload = analyze_calls(*inputs).to_dict()

            call = next(item for item in payload["calls"] if item["name"] == "ProductCalc")
            self.assertEqual("external_function", call["target_kind"])
            self.assertIn("ProductCalc", {item["name"] for item in payload["stub_candidates"]})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the call-analysis tests and verify they fail**

```bash
python -m pytest tests/test_linked_library_call_analysis.py -q
```

Expected: import/signature failures because `LinkProvider` and `link_providers_by_name` do not exist.

- [ ] **Step 3: Add provider models and JSON serialization**

Add to `call_models.py`:

```python
@dataclass(frozen=True)
class LinkProvider:
    library: Path
    symbol: str
    provider_kind: str
    source: str
    link_order: int
    project_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "library": path_text(self.library),
            "symbol": self.symbol,
            "provider_kind": self.provider_kind,
            "source": self.source,
            "link_order": self.link_order,
            "project_name": self.project_name,
        }
```

Append these defaulted fields to `FunctionCall`:

```python
link_provider: LinkProvider | None = None
link_providers: list[LinkProvider] = field(default_factory=list)
```

Add both fields to `FunctionCall.to_dict()`.

- [ ] **Step 4: Make provider input optional and classify linked calls**

Change the public signature to:

```python
def analyze_calls(
    digest: SourceDigest,
    function_location: object,
    function_signature: FunctionSignature,
    global_access: GlobalAccessReport,
    link_providers_by_name: dict[str, list[LinkProvider]] | None = None,
    link_warnings: list[CallAnalyzerWarning] | None = None,
) -> CallReport:
```

At each call site inside the analyzer:

```python
providers = sorted((link_providers_by_name or {}).get(name, []), key=lambda item: item.link_order)
target_kind = _target_kind(name, defined, macro_names, pointer_parameters, bool(providers))
```

Update `_target_kind` so the final decisions are:

```python
if name in STANDARD_LIBRARY:
    return "standard_library"
if has_link_provider:
    return "linked_library_function"
return "external_function"
```

Pass `link_provider=providers[0] if providers else None` and `link_providers=providers` into `FunctionCall`. Add one `CallAnalyzerWarning("multiple_library_symbol_providers", ...)` per function with more than one provider. Start the report warning list with `list(link_warnings or [])`.

Keep `_stub_candidates` restricted to `external_function`, `unknown`, and `macro_like`; do not add `linked_library_function`.

- [ ] **Step 5: Render provider details in call-report Markdown**

Change the call table to include a provider column:

```python
"| ID | 名前 | 対象種別 | リンク提供元 | 戻り値の使われ方 | 根拠 | 信頼度 |",
"|---|---|---|---|---|---|---|",
```

For each call, render the primary provider as `library [symbol] (provider_kind)` or an empty string.

- [ ] **Step 6: Run call-analysis and existing analysis tests**

```bash
python -m pytest tests/test_linked_library_call_analysis.py tests/test_function_analysis_reports.py tests/test_link_only_library_calls.py -q
```

Expected: all tests pass; CRT functions remain `standard_library`.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/unit_test_runner/c_analyzer/call_models.py src/unit_test_runner/c_analyzer/call_analyzer.py src/unit_test_runner/c_analyzer/call_report_writer.py tests/test_linked_library_call_analysis.py
git commit -m "Classify linked library function calls"
```

---

### Task 4: Resolve explicit and direct-dependency libraries

**Files:**
- Create: `src/unit_test_runner/vc6/link_context.py`
- Create: `src/unit_test_runner/vc6/link_library_resolver.py`
- Create: `tests/test_vc6_link_library_resolver.py`

**Interfaces:**
- Consumes: workspace root, DSW path, selected project name, selected configuration name, environment mapping, `LibrarySymbolCache`.
- Produces: `resolve_link_context(...) -> LinkContext` with ordered libraries, existing library directories, provider map, and warnings.

- [ ] **Step 1: Write resolver tests for explicit libraries, dependency outputs, configuration matching, non-transitive behavior, and scan failure**

Create `tests/test_vc6_link_library_resolver.py`. Use `tests.coff_fixture.write_import_library` to write real synthetic `.lib` files. The primary test fixture must contain:

```text
App.dsw
App/App.dsp                 selected project, depends on ProductLib
ProductLib/ProductLib.dsp   direct dependency, depends on TransitiveLib
TransitiveLib/TransitiveLib.dsp
libs/Explicit.lib
ProductLib/Debug/ProductLib.lib
TransitiveLib/Debug/TransitiveLib.lib
```

The assertions must cover:

```python
context = resolve_link_context(root, root / "App.dsw", "App", "Win32 Debug", environ={"LIB": str(root / "envlib")})

self.assertEqual(
    ["Explicit.lib", "ProductLib.lib"],
    [item.path.name for item in context.libraries],
)
self.assertEqual(
    ["explicit_link32", "direct_dependency_project"],
    [item.source for item in context.libraries],
)
self.assertNotIn("TransitiveLib.lib", {item.path.name for item in context.libraries})
self.assertIn("ExplicitCall", context.providers_by_name)
self.assertIn("DependencyCall", context.providers_by_name)
self.assertNotIn("TransitiveCall", context.providers_by_name)
```

Add separate tests that assert:

- A dependency with only `Win32 Release` emits `dependency_configuration_not_found` for a `Win32 Debug` target.
- `/implib:` wins over `.lib` `/out:` and `Output_Dir/ProjectName.lib`.
- A broken but existing `.lib` remains in `context.libraries`, yields no providers, and emits `library_symbol_scan_failed`.
- Duplicate absolute paths are deduplicated while preserving the first link order.
- `%ENV%`, `${ENV}`, `$(OUTDIR)`, `$(INTDIR)`, `$(CFG)`, `$(NAME)`, and `($ENV)` expand deterministically.

- [ ] **Step 2: Run resolver tests and verify they fail**

```bash
python -m pytest tests/test_vc6_link_library_resolver.py -q
```

Expected: import failure because the resolver modules do not exist.

- [ ] **Step 3: Add link-context data models**

Create `src/unit_test_runner/vc6/link_context.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from unit_test_runner.c_analyzer.call_models import LinkProvider


@dataclass(frozen=True)
class LinkContextWarning:
    code: str
    message: str
    project_name: str | None = None
    configuration: str | None = None
    library_candidate: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "project_name": self.project_name,
            "configuration": self.configuration,
            "library_candidate": self.library_candidate,
        }


@dataclass(frozen=True)
class ResolvedLinkLibrary:
    path: Path
    source: str
    link_order: int
    project_name: str | None = None
    configuration: str | None = None
    exists: bool = True
    scan_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path.as_posix(),
            "source": self.source,
            "link_order": self.link_order,
            "project_name": self.project_name,
            "configuration": self.configuration,
            "exists": self.exists,
            "scan_status": self.scan_status,
        }


@dataclass
class LinkContext:
    libraries: list[ResolvedLinkLibrary] = field(default_factory=list)
    library_dirs: list[Path] = field(default_factory=list)
    providers_by_name: dict[str, list[LinkProvider]] = field(default_factory=dict)
    warnings: list[LinkContextWarning] = field(default_factory=list)
```

- [ ] **Step 4: Implement deterministic configuration and macro resolution**

Create `link_library_resolver.py` with these public signatures:

```python
def resolve_link_context(
    workspace_root: Path | str,
    dsw_path: Path | str,
    project_name: str,
    configuration: str,
    *,
    environ: Mapping[str, str] | None = None,
    cache: LibrarySymbolCache | None = None,
) -> LinkContext:
    ...


def expand_link_path(
    value: str,
    *,
    output_dir: str | None,
    intermediate_dir: str | None,
    configuration: str,
    project_name: str,
    environ: Mapping[str, str],
) -> tuple[str | None, list[str]]:
    ...
```

Use `parse_dsw()` from `unit_test_runner.dsw_parser` to retain dependency order and `parse_dsp()` from `unit_test_runner.vc6.dsp_parser` for each project. Select the target configuration by matching either full name or short `platform + name`, case-insensitively.

For direct dependencies, select a configuration only when both `platform` and short `name` equal the target values case-insensitively.

Macro expansion must repeatedly replace supported forms until a pass makes no change, with a hard maximum of 10 passes. Return unresolved macro names rather than leaving a partially trusted path.

- [ ] **Step 5: Resolve explicit libraries and library directories**

For each selected-project `link_settings.libraries` item, search in this exact order:

1. Absolute path.
2. Selected DSP directory.
3. Each expanded and existing `/libpath:` directory in DSP order.
4. Each semicolon-delimited directory in `environ.get("LIB", "")`.

Append only one existing file. If no candidate exists, emit `link_library_not_found`. If path macros remain unresolved, emit `link_library_macro_unresolved` and do not append the library.

- [ ] **Step 6: Resolve direct dependency outputs with staged fallback**

For each direct dependency in DSW order:

1. Resolve expanded `import_library`; if exactly one existing file results, use it and stop.
2. Resolve expanded `output_file` only if it ends with `.lib`; if exactly one existing file results, use it and stop.
3. Resolve `output_dir / f"{project.name}.lib"`; if exactly one existing file results, use it.

At any stage, more than one existing candidate emits `dependency_library_output_ambiguous` and rejects the dependency. No candidate after all stages emits `link_library_not_found`.

- [ ] **Step 7: Scan libraries and build provider maps**

Use one `LibrarySymbolCache` instance for the entire call. For each resolved library in link order:

```python
index = cache.scan(library.path)
if index.scan_status != "ok":
    warnings.append(LinkContextWarning(
        "library_symbol_scan_failed",
        f"Library symbol scan failed: {library.path}",
        library_candidate=str(library.path),
    ))
    continue
for normalized_name, symbols in index.symbols_by_normalized_name.items():
    for symbol in symbols:
        providers_by_name.setdefault(normalized_name, []).append(
            LinkProvider(
                library=library.path,
                symbol=symbol.raw_name,
                provider_kind=symbol.provider_kind,
                source=library.source,
                link_order=library.link_order,
                project_name=library.project_name,
            )
        )
```

Sort each provider list by `link_order` and retain all providers.

- [ ] **Step 8: Run resolver and parser tests**

```bash
python -m pytest tests/test_vc6_link_library_resolver.py tests/test_vc6_dsp_link_settings.py tests/test_vc6_coff_archive.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit Task 4**

```bash
git add src/unit_test_runner/vc6/link_context.py src/unit_test_runner/vc6/link_library_resolver.py tests/test_vc6_link_library_resolver.py
git commit -m "Resolve VC6 link library providers"
```

---

### Task 5: Integrate link context into dossier analysis before test design

**Files:**
- Modify: `src/unit_test_runner/dossier/workflow.py:198-409`
- Create: `tests/test_dossier_link_context_integration.py`

**Interfaces:**
- Consumes: `resolve_link_context(...)`.
- Produces: enriched `build_context`, link-aware `call_report`, and link warnings in dossier diagnostics.

- [ ] **Step 1: Write a workflow integration test**

Create a temporary DSW with an `App` project, an explicit synthetic library exporting `_ProductCalc@4`, and a source function that calls `ProductCalc`. Invoke `analyze_function_workflow(..., phase="harness")` and assert:

```python
call_report = json.loads((out_dir / "reports" / "call_report.json").read_text(encoding="utf-8"))
harness = json.loads((out_dir / "reports" / "harness_skeleton_report.json").read_text(encoding="utf-8"))
build_context = json.loads((out_dir / "reports" / "build_context.json").read_text(encoding="utf-8"))

call = next(item for item in call_report["calls"] if item["name"] == "ProductCalc")
self.assertEqual("linked_library_function", call["target_kind"])
self.assertNotIn("ProductCalc", {item["name"] for item in call_report["stub_candidates"]})
self.assertNotIn("ProductCalc", {item["original_function_name"] for item in harness["stub_skeletons"]})
self.assertEqual("Product.lib", Path(build_context["link_libraries"][0]["path"]).name)
self.assertEqual([], build_context["link_context_warnings"])
```

Add a broken-library case that asserts `library_symbol_scan_failed` is present, the call remains `external_function`, and the stub remains generated.

- [ ] **Step 2: Run the workflow integration test and verify it fails**

```bash
python -m pytest tests/test_dossier_link_context_integration.py -q
```

Expected: the call remains `external_function` because workflow does not create or pass link context.

- [ ] **Step 3: Build the link context immediately after project selection**

In `analyze_function_workflow`, directly after `select_project_context(...)`, call:

```python
link_context = resolve_link_context(
    workspace_root,
    dsw_path,
    project["project_name"],
    config["full_name"],
)
```

Import `CallAnalyzerWarning` and convert every `LinkContextWarning` to a call warning:

```python
call_link_warnings = [
    CallAnalyzerWarning(item.code, item.message)
    for item in link_context.warnings
]
```

- [ ] **Step 4: Persist link inputs in the build context**

Add these keys when creating `dossier["build_context"]`:

```python
"link_libraries": [item.to_dict() for item in link_context.libraries],
"library_dirs": [item.as_posix() for item in link_context.library_dirs],
"link_context_warnings": [item.to_dict() for item in link_context.warnings],
```

Extend `dossier["diagnostics"]` with warning dictionaries using severity `warning` and the warning code/message.

- [ ] **Step 5: Pass providers into call analysis before coverage and test design**

Replace the current call with:

```python
call_report = analyze_calls(
    digest,
    location,
    signature,
    global_access,
    link_providers_by_name=link_context.providers_by_name,
    link_warnings=call_link_warnings,
)
```

This placement is mandatory: coverage candidates, test-case stub setup, and harness stub generation must consume the already-correct call report.

- [ ] **Step 6: Run workflow and harness regressions**

```bash
python -m pytest tests/test_dossier_link_context_integration.py tests/test_harness_skeleton_generation.py tests/test_test_case_design_generation.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 5**

```bash
git add src/unit_test_runner/dossier/workflow.py tests/test_dossier_link_context_integration.py
git commit -m "Use DSP library providers during analysis"
```

---

### Task 6: Carry resolved libraries through generated Makefiles and verification linking

**Files:**
- Modify: `src/unit_test_runner/build/build_models.py:109-253`
- Modify: `src/unit_test_runner/build/build_workspace_generator.py:35-68,480-674`
- Modify: `src/unit_test_runner/build/verification_toolchain.py:44-131,208-211`
- Modify: `src/unit_test_runner/build/build_report_writer.py:38-62`
- Create: `tests/test_build_workspace_link_libraries.py`

**Interfaces:**
- Produces: `LinkLibraryEntry`, `BuildWorkspaceReport.link_libraries`, `BuildWorkspaceReport.library_dirs`, `LINK_LIBS`, and `LIBPATHS` in generated Makefiles.

- [ ] **Step 1: Write build-workspace tests for link order and absolute paths**

Create `tests/test_build_workspace_link_libraries.py` with a minimal source/harness fixture and this build context:

```python
build_context = {
    "workspace_root": str(project),
    "include_dirs": [],
    "defines": [],
    "compiler_options": [],
    "link_libraries": [
        {"path": str(first_lib), "source": "explicit_link32", "link_order": 0, "project_name": None, "configuration": "Win32 Debug", "exists": True, "scan_status": "ok"},
        {"path": str(second_lib), "source": "direct_dependency_project", "link_order": 1, "project_name": "Second", "configuration": "Win32 Debug", "exists": True, "scan_status": "ok"},
    ],
    "library_dirs": [str(first_lib.parent), str(second_lib.parent)],
}
```

Assert:

```python
report, _probe = generate_build_workspace(build_context, source_digest, harness_report, out_dir, run_probe=False, dry_run=True)
makefile = (out_dir / "build" / "Makefile").read_text(encoding="cp932")

self.assertEqual([first_lib.resolve(), second_lib.resolve()], [item.path for item in report.link_libraries])
self.assertLess(makefile.index(str(first_lib).replace("/", "\\")), makefile.index(str(second_lib).replace("/", "\\")))
self.assertIn("LINK_LIBS=", makefile)
self.assertIn("LIBPATHS=", makefile)
self.assertIn("$(LINK) /nologo /OPT:REF /OUT:$@ $(OBJS) $(LIBPATHS) $(LINK_LIBS)", makefile)
```

Also test that a `link_libraries` item with `exists=False` is omitted and produces a warning diagnostic.

- [ ] **Step 2: Run the build-workspace test and verify it fails**

```bash
python -m pytest tests/test_build_workspace_link_libraries.py -q
```

Expected: report has no `link_libraries` field and Makefile has no link variables.

- [ ] **Step 3: Add build link models**

Add to `build_models.py`:

```python
@dataclass(frozen=True)
class LinkLibraryEntry:
    path: Path
    source: str
    link_order: int
    project_name: str | None = None
    configuration: str | None = None
    exists: bool = True
    scan_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": _path_text(self.path),
            "source": self.source,
            "link_order": self.link_order,
            "project_name": self.project_name,
            "configuration": self.configuration,
            "exists": self.exists,
            "scan_status": self.scan_status,
        }
```

Add defaulted fields to the end of `BuildWorkspaceReport` before `schema_version`:

```python
link_libraries: list[LinkLibraryEntry] = field(default_factory=list)
library_dirs: list[Path] = field(default_factory=list)
```

Serialize both. Convert the construction in `generate_build_workspace` from positional to keyword arguments.

- [ ] **Step 4: Parse build-context link inputs and render the VC6 Makefile**

Add helpers:

```python
def _link_libraries(build_context: dict[str, Any], diagnostics: list[BuildDiagnostic]) -> list[LinkLibraryEntry]:
    result = []
    for item in sorted(build_context.get("link_libraries", []), key=lambda value: int(value.get("link_order", 0))):
        path = Path(str(item.get("path") or "")).resolve()
        if not item.get("exists", path.exists()) or not path.is_file():
            diagnostics.append(BuildDiagnostic("link_library_not_found", "warning", f"Link library is unavailable: {path}"))
            continue
        result.append(LinkLibraryEntry(path, str(item.get("source") or "unknown"), int(item.get("link_order", len(result))), item.get("project_name"), item.get("configuration"), True, item.get("scan_status")))
    return result


def _library_dirs(build_context: dict[str, Any]) -> list[Path]:
    result = []
    for raw in build_context.get("library_dirs", []):
        path = Path(str(raw)).resolve()
        if path.is_dir() and path not in result:
            result.append(path)
    return result
```

Change `_render_makefile` to accept both lists and emit:

```python
f"LIBPATHS={' '.join('/LIBPATH:\"' + _windows_path(path) + '\"' for path in library_dirs)}",
f"LINK_LIBS={' '.join('\"' + _windows_path(item.path) + '\"' for item in link_libraries)}",
```

Use:

```text
	$(LINK) /nologo /OPT:REF /OUT:$@ $(OBJS) $(LIBPATHS) $(LINK_LIBS)
```

- [ ] **Step 5: Pass libraries to MSVC verification linking**

Extend `run_verification_build` and `_link_command` with `link_libraries: list[Path]` and `library_dirs: list[Path]`.

For MSVC flavor, return:

```python
return [
    compiler,
    "/nologo",
    *[str(path) for path in object_paths],
    *[str(path) for path in link_libraries],
    f"/Fe{exe_path}",
    "/link",
    *[f"/LIBPATH:{path}" for path in library_dirs],
]
```

For Unix flavor, append only libraries whose suffix is `.a`, `.so`, or `.dylib`; do not pass `.lib` files to GCC/Clang.

- [ ] **Step 6: Report effective link inputs**

Add a `## リンクライブラリ` table and `## library path` list to `render_workspace_markdown`.

- [ ] **Step 7: Run build and verification tests**

```bash
python -m pytest tests/test_build_workspace_link_libraries.py tests/test_build_workspace_generation.py tests/test_verification_build_probe.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit Task 6**

```bash
git add src/unit_test_runner/build/build_models.py src/unit_test_runner/build/build_workspace_generator.py src/unit_test_runner/build/verification_toolchain.py src/unit_test_runner/build/build_report_writer.py tests/test_build_workspace_link_libraries.py
git commit -m "Link resolved VC6 libraries in build workspaces"
```

---

### Task 7: Emit resolved libraries in generated VC6 DSPs and summaries

**Files:**
- Modify: `src/unit_test_runner/vc6/debug_workspace_writer.py:102-170,209-229`
- Modify: `src/unit_test_runner/reports/quick_summary.py:22-85`
- Modify: `tests/test_vc6_debug_workspace_writer.py`
- Modify: `tests/test_quick_summary_generation.py`

**Interfaces:**
- Consumes: `BuildWorkspaceReport.to_dict()` link fields and dossier build/call context.
- Produces: ordered LINK32 library arguments, `/libpath:` arguments, and summary counts.

- [ ] **Step 1: Add a VC6 debug DSP regression test**

Extend `tests/test_vc6_debug_workspace_writer.py` with a report containing two link libraries and two library directories. Assert:

```python
dsp_text = write_vc6_debug_project(workspace, report).read_text(encoding="cp932")
first = str(first_lib.resolve()).replace("/", "\\")
second = str(second_lib.resolve()).replace("/", "\\")

self.assertIn(f'/libpath:"{first_lib.parent.resolve()}"'.replace("/", "\\"), dsp_text)
self.assertIn(f'"{first}"', dsp_text)
self.assertIn(f'"{second}"', dsp_text)
self.assertLess(dsp_text.index(first), dsp_text.index(second))
```

- [ ] **Step 2: Add quick-summary count tests**

Extend `tests/test_quick_summary_generation.py` with a dossier containing:

```python
"build_context": {
    "link_libraries": [{"path": "C:/lib/Product.lib"}],
    "link_context_warnings": [{"code": "library_symbol_scan_failed", "message": "broken"}],
},
"call_report_summary": {
    "linked_library_function_count": 2,
},
```

Or, preferably, derive the linked-call count from an embedded `call_report_payload` passed into the summary helper. Assert JSON fields:

```python
self.assertEqual(1, summary["link_resolution"]["library_count"])
self.assertEqual(2, summary["link_resolution"]["linked_function_count"])
self.assertEqual(1, summary["link_resolution"]["warning_count"])
```

- [ ] **Step 3: Run the DSP and summary tests and verify they fail**

```bash
python -m pytest tests/test_vc6_debug_workspace_writer.py tests/test_quick_summary_generation.py -q
```

Expected: generated LINK32 line lacks libraries and summary lacks `link_resolution`.

- [ ] **Step 4: Render library and library-path arguments in debug DSPs**

Add helpers:

```python
def _dsp_link_library_args(report: dict[str, Any]) -> list[str]:
    values = []
    for item in sorted(report.get("link_libraries", []), key=lambda value: int(value.get("link_order", 0))):
        path = str(item.get("path") or "").replace("/", "\\")
        if path:
            values.append(f'"{_escape_option(path)}"')
    return values


def _dsp_library_path_args(report: dict[str, Any]) -> list[str]:
    return [
        f'/libpath:"{_escape_option(str(path).replace("/", "\\"))}"'
        for path in report.get("library_dirs", [])
        if str(path).strip()
    ]
```

Build the effective `# ADD LINK32` line with `/libpath:` arguments before ordered library files.

- [ ] **Step 5: Add link-resolution fields to quick summaries**

In `quick_summary_payload`, derive:

```python
build_context = dossier.get("build_context", {}) if isinstance(dossier.get("build_context"), dict) else {}
call_payload = dossier.get("call_report_payload", {}) if isinstance(dossier.get("call_report_payload"), dict) else {}
linked_count = sum(1 for call in call_payload.get("calls", []) if call.get("target_kind") == "linked_library_function")
link_warnings = build_context.get("link_context_warnings", []) if isinstance(build_context.get("link_context_warnings"), list) else []
```

Add:

```python
"link_resolution": {
    "library_count": len(build_context.get("link_libraries", [])),
    "linked_function_count": linked_count,
    "warning_count": len(link_warnings),
    "warnings": link_warnings[:20],
},
```

Update workflow to store `dossier["call_report_payload"] = call_report.to_dict()` only until summary generation completes; remove this transient key before writing final `function_dossier.json`, or update `quick_summary_compat.py` to read `reports/call_report.json` when generating the summary. Prefer reading the existing report file to avoid duplicating the full call report in the dossier.

Render a `## リンク解決` section in Markdown with the three counts and warning codes.

- [ ] **Step 6: Run report tests**

```bash
python -m pytest tests/test_vc6_debug_workspace_writer.py tests/test_quick_summary_generation.py tests/test_build_workspace_link_libraries.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 7**

```bash
git add src/unit_test_runner/vc6/debug_workspace_writer.py src/unit_test_runner/reports/quick_summary.py src/unit_test_runner/dossier/quick_summary_compat.py tests/test_vc6_debug_workspace_writer.py tests/test_quick_summary_generation.py
git commit -m "Report and emit resolved link libraries"
```

---

### Task 8: Add end-to-end coverage and run the complete regression suite

**Files:**
- Create: `tests/test_linked_library_end_to_end.py`
- Modify only if failures expose a real contract mismatch in earlier tasks.

**Interfaces:**
- Validates the complete data flow: DSP/DSW → library resolution → COFF symbols → call classification → harness omission → Makefile/DSP link input → quick summary.

- [ ] **Step 1: Write the end-to-end fixture**

Create a temporary workspace with:

- `App.dsw` containing `App` and direct dependency `ProductLib`.
- `App/App.dsp` selecting `Win32 Debug`, linking `../libs/Explicit.lib`, and compiling `src/app.c`.
- `ProductLib/ProductLib.dsp` selecting `Win32 Debug`, setting `Output_Dir "Debug"`, and producing `ProductLib.lib`.
- `Explicit.lib` exporting `_ExplicitCall@4`.
- `ProductLib.lib` exporting `__imp__DependencyCall@4`.
- `app.c` calling both functions.

Invoke the CLI through `python -m unit_test_runner --json quick-check ... --profile build` so the test covers the same entry point used by the VS Code quick flow.

- [ ] **Step 2: Assert all generated artifacts agree**

The test must assert:

```python
self.assertEqual(0, completed.returncode, completed.stderr)
call_report = json.loads((out_dir / "reports" / "call_report.json").read_text(encoding="utf-8"))
harness = json.loads((out_dir / "reports" / "harness_skeleton_report.json").read_text(encoding="utf-8"))
build_context = json.loads((out_dir / "reports" / "build_context.json").read_text(encoding="utf-8"))
build_workspace = json.loads((out_dir / "reports" / "build_workspace_report.json").read_text(encoding="utf-8"))
quick_summary = json.loads((out_dir / "reports" / "quick_summary.json").read_text(encoding="utf-8"))
makefile = (out_dir / "build" / "Makefile").read_text(encoding="cp932")
debug_dsp = next((out_dir / "build").glob("UTR_*.dsp")).read_text(encoding="cp932")

linked = {item["name"] for item in call_report["calls"] if item["target_kind"] == "linked_library_function"}
self.assertEqual({"ExplicitCall", "DependencyCall"}, linked)
self.assertFalse(harness["stub_skeletons"])
self.assertEqual(["Explicit.lib", "ProductLib.lib"], [Path(item["path"]).name for item in build_context["link_libraries"]])
self.assertEqual(["Explicit.lib", "ProductLib.lib"], [Path(item["path"]).name for item in build_workspace["link_libraries"]])
self.assertIn("Explicit.lib", makefile)
self.assertIn("ProductLib.lib", makefile)
self.assertIn("Explicit.lib", debug_dsp)
self.assertIn("ProductLib.lib", debug_dsp)
self.assertEqual(2, quick_summary["link_resolution"]["linked_function_count"])
```

Add a second end-to-end test with a broken explicit library. It must assert that the library is still linked, `library_symbol_scan_failed` appears, and the external call still has a generated stub.

- [ ] **Step 3: Run the end-to-end tests**

```bash
python -m pytest tests/test_linked_library_end_to_end.py -q
```

Expected: both end-to-end cases pass.

- [ ] **Step 4: Run focused regression groups**

```bash
python -m pytest \
  tests/test_vc6_dsp_link_settings.py \
  tests/test_vc6_coff_archive.py \
  tests/test_vc6_link_library_resolver.py \
  tests/test_linked_library_call_analysis.py \
  tests/test_dossier_link_context_integration.py \
  tests/test_build_workspace_link_libraries.py \
  tests/test_vc6_debug_workspace_writer.py \
  tests/test_quick_summary_generation.py \
  tests/test_linked_library_end_to_end.py \
  -q
```

Expected: all focused tests pass.

- [ ] **Step 5: Run the full Python suite**

```bash
python -m pytest -q
```

Expected: full suite passes with no new failures.

- [ ] **Step 6: Verify the VS Code extension still compiles**

```bash
cd vscode/extension
npm run compile
npm test
```

Expected: TypeScript compile and Node test suite pass. This feature changes Python-produced report payloads but must not break the adapter.

- [ ] **Step 7: Commit Task 8**

```bash
git add tests/test_linked_library_end_to_end.py
git commit -m "Cover linked library resolution end to end"
```

---

## Final Verification Checklist

- [ ] `DspConfiguration.to_dict()` includes effective linker settings without removing compiler settings.
- [ ] Explicit LINK32 order is preserved.
- [ ] Only direct dependencies are traversed.
- [ ] Dependency configuration comparison is case-insensitive and requires both platform and short configuration name.
- [ ] `/implib:` wins over `.lib` `/out:`, which wins over `Output_Dir/ProjectName.lib`.
- [ ] Every linked library in build context exists at resolution time.
- [ ] COFF parser rejects malformed offsets and sizes without raising out of the public scanner.
- [ ] C++ mangled names never become C provider names.
- [ ] Import libraries produce `provider_kind="import_library"`.
- [ ] Missing or corrupt linker members trigger object-symbol fallback.
- [ ] One CLI workflow shares one `LibrarySymbolCache`.
- [ ] `standard_library` classification precedes library-provider classification.
- [ ] `linked_library_function` never appears in `stub_candidates`.
- [ ] Scan failures preserve stub candidacy and real-library link input.
- [ ] Multiple providers preserve link order and emit one warning per function.
- [ ] Makefile and generated VC6 DSP carry libraries in the same order as build context.
- [ ] No `.lib` is copied into the generated workspace.
- [ ] Quick Summary exposes library, linked-function, and warning counts.
- [ ] Focused tests, full Python suite, TypeScript compile, and Node tests pass.
