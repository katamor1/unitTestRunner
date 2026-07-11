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


class LinkedLibraryProviderWarningTests(unittest.TestCase):
    def test_multiple_symbol_spellings_from_one_library_do_not_emit_multiple_library_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "consumer.c"
            source.write_text("int Consumer(int value) { return ProductCalc(value); }\n", encoding="ascii")
            digest = build_source_digest(source)
            location = locate_function(digest, "Consumer")
            signature = extract_signature(digest, location)
            globals_report = analyze_global_access(digest, location, signature)
            library = Path("C:/product/lib/Product.lib")
            providers = [
                LinkProvider(library, "_ProductCalc@4", "static_library", "explicit_link32", 0, "Product"),
                LinkProvider(library, "__imp__ProductCalc@4", "import_library", "explicit_link32", 0, "Product"),
            ]

            payload = analyze_calls(
                digest,
                location,
                signature,
                globals_report,
                link_providers_by_name={"ProductCalc": providers},
            ).to_dict()

            call = next(item for item in payload["calls"] if item["name"] == "ProductCalc")
            self.assertEqual("linked_library_function", call["target_kind"])
            self.assertEqual(2, len(call["link_providers"]))
            self.assertFalse(any(item["code"] == "multiple_library_symbol_providers" for item in payload["warnings"]))


if __name__ == "__main__":
    unittest.main()
