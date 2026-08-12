import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unit_test_runner.c_analyzer import analyze_function, list_functions
from unit_test_runner.c_analyzer.function_locator import locate_function
from unit_test_runner.c_analyzer.global_access_analyzer import analyze_global_access
from unit_test_runner.c_analyzer.signature_extractor import extract_signature
from unit_test_runner.c_analyzer.source_digest import build_source_digest


SOURCE = Path(__file__).parent / "fixtures" / "vc6_project" / "src" / "control.c"


class CAnalyzerTests(unittest.TestCase):
    def test_target_and_global_analysis_keep_ambiguous_types_unresolved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "ambiguous.c"
            source.write_text(
                "MysteryValue g_value;\n"
                "MysteryValue Target(MysteryValue value) { return g_value; }\n",
                encoding="ascii",
            )
            digest = build_source_digest(source)
            location = locate_function(digest, "Target")
            signature = extract_signature(digest, location)
            globals_report = analyze_global_access(digest, location, signature)

        self.assertEqual("MysteryValue", signature.return_type.raw)
        self.assertEqual("MysteryValue", signature.parameters[0].type_info.raw)
        self.assertIn("type_unresolved", [item.code for item in signature.warnings])
        self.assertEqual("MysteryValue", globals_report.file_scope_declarations[0].type_raw)
        self.assertIn("type_unresolved", [item.code for item in globals_report.warnings])

    def test_list_functions_masks_comments_and_strings(self):
        functions = list_functions(SOURCE)
        names = [function["name"] for function in functions]

        self.assertEqual(["Helper", "Control_Update", "Control_Reset"], names)
        self.assertTrue(all(function["start_line"] < function["end_line"] for function in functions))

    def test_analyze_function_extracts_signature_access_calls_and_branches(self):
        result = analyze_function(SOURCE, "Control_Update")

        self.assertEqual("Control_Update", result["name"])
        self.assertEqual("int", result["return_type"])
        self.assertEqual(
            [
                {"name": "mode", "type": "int", "is_pointer": False, "is_array": False, "is_const": False},
                {
                    "name": "sensor_value",
                    "type": "int",
                    "is_pointer": False,
                    "is_array": False,
                    "is_const": False,
                },
            ],
            result["parameters"],
        )
        self.assertIn("g_control_state", result["globals_read"])
        self.assertIn("g_control_state", result["globals_written"])
        self.assertIn("g_error_code", result["globals_written"])
        self.assertIn("ReadSensor", [call["name"] for call in result["external_calls"]])
        self.assertIn("WriteOutput", [call["name"] for call in result["external_calls"]])
        self.assertIn("Helper", [call["name"] for call in result["static_calls"]])

        branch_conditions = [branch["condition"] for branch in result["branches"]]
        self.assertIn("sensor_value < SENSOR_MIN", branch_conditions)
        self.assertIn("sensor_value > SENSOR_MAX || ReadSensor() == SENSOR_FAIL", branch_conditions)
        self.assertIn("mode", [branch["expression"] for branch in result["switches"]])
        self.assertIn("MODE_AUTO", [case["value"] for case in result["cases"]])
        self.assertIn("i = 0; i < 3; i++", [loop["condition"] for loop in result["loops"]])
        self.assertEqual(4, len(result["returns"]))


if __name__ == "__main__":
    unittest.main()
