import tempfile
import unittest
from pathlib import Path

from tests.coff_fixture import write_import_library, write_library_with_second_linker, write_object_library_without_linker
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

    def test_second_linker_member_is_supported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            library = Path(temp_dir) / "Second.lib"
            write_library_with_second_linker(library, "_SecondCalc@4")

            index = LibrarySymbolCache().scan(library)

            self.assertEqual("ok", index.scan_status)
            self.assertEqual("static_library", index.symbols_by_normalized_name["SecondCalc"][0].provider_kind)

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
