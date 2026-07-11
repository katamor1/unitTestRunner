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

            payload = analyze_calls(*inputs, link_providers_by_name={"ProductCalc": list(reversed(providers))}).to_dict()
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

    def test_standard_library_classification_precedes_link_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "math_user.c"
            source.write_text("double Normalize(double value) { return sqrt(value); }\n", encoding="ascii")
            digest = build_source_digest(source)
            location = locate_function(digest, "Normalize")
            signature = extract_signature(digest, location)
            globals_report = analyze_global_access(digest, location, signature)
            provider = LinkProvider(Path("C:/lib/crt.lib"), "_sqrt", "static_library", "explicit_link32", 0)

            payload = analyze_calls(digest, location, signature, globals_report, {"sqrt": [provider]}).to_dict()

            call = next(item for item in payload["calls"] if item["name"] == "sqrt")
            self.assertEqual("standard_library", call["target_kind"])
            self.assertNotIn("sqrt", {item["name"] for item in payload["stub_candidates"]})


if __name__ == "__main__":
    unittest.main()
