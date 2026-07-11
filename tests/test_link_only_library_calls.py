import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.c_analyzer.call_analyzer import analyze_calls
from unit_test_runner.c_analyzer.function_locator import locate_function
from unit_test_runner.c_analyzer.global_access_analyzer import analyze_global_access
from unit_test_runner.c_analyzer.signature_extractor import extract_signature
from unit_test_runner.c_analyzer.source_digest import build_source_digest
from unit_test_runner.harness.harness_skeleton_generator import generate_harness_skeleton


class LinkOnlyLibraryCallTests(unittest.TestCase):
    def test_crt_math_functions_are_link_only_and_not_stub_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "math_user.c"
            source.write_text(
                "#include <math.h>\n"
                "double Normalize(double value)\n"
                "{\n"
                "    return sqrt(value);\n"
                "}\n",
                encoding="ascii",
            )
            digest = build_source_digest(source)
            location = locate_function(digest, "Normalize")
            signature = extract_signature(digest, location)
            global_access = analyze_global_access(digest, location, signature)

            call_report = analyze_calls(digest, location, signature, global_access).to_dict()

            calls = {item["name"]: item for item in call_report["calls"]}
            self.assertEqual("standard_library", calls["sqrt"]["target_kind"])
            self.assertNotIn("sqrt", {item["name"] for item in call_report["stub_candidates"]})

    def test_link_only_library_calls_do_not_generate_stub_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "math_user.c"
            source.write_text(
                "#include <math.h>\n"
                "double Normalize(double value)\n"
                "{\n"
                "    return sqrt(value);\n"
                "}\n",
                encoding="ascii",
            )
            digest = build_source_digest(source)
            location = locate_function(digest, "Normalize")
            signature = extract_signature(digest, location)
            global_access = analyze_global_access(digest, location, signature)
            call_report = analyze_calls(digest, location, signature, global_access)
            design = {
                "function": {"name": "Normalize"},
                "test_cases": [
                    {
                        "test_case_id": "TC_Normalize_001",
                        "input_assignments": [{"target_name": "value", "value_expression": "1"}],
                        "stub_setups": [],
                        "expected_observations": [],
                    }
                ],
            }

            report = generate_harness_skeleton(signature, global_access, call_report, design, Path(temp_dir) / "out")

            generated_paths = {item.path.as_posix() for item in report.generated_files}
            self.assertNotIn("generated/stubs/stub_sqrt.c", generated_paths)
            self.assertFalse((Path(temp_dir) / "out" / "generated" / "stubs" / "stub_sqrt.c").exists())


if __name__ == "__main__":
    unittest.main()
