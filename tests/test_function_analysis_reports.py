import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "c_sources" / "analysis_pipeline" / "pipeline.c"
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.c_analyzer.boundary_candidate_analyzer import generate_boundary_equivalence_candidates
from unit_test_runner.c_analyzer.call_analyzer import analyze_calls
from unit_test_runner.c_analyzer.coverage_design_analyzer import analyze_coverage_design
from unit_test_runner.c_analyzer.function_locator import locate_function
from unit_test_runner.c_analyzer.global_access_analyzer import analyze_global_access
from unit_test_runner.c_analyzer.signature_extractor import extract_signature
from unit_test_runner.c_analyzer.source_digest import build_source_digest


def run_module(*args, check=False):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


class FunctionAnalysisReportTests(unittest.TestCase):
    def setUp(self):
        self.digest = build_source_digest(FIXTURE)
        self.location = locate_function(self.digest, "Control_Update")
        self.signature = extract_signature(self.digest, self.location)
        self.global_access = analyze_global_access(self.digest, self.location, self.signature)
        self.call_report = analyze_calls(self.digest, self.location, self.signature, self.global_access)
        self.coverage = analyze_coverage_design(self.digest, self.location, self.signature, self.global_access, self.call_report)
        self.boundary = generate_boundary_equivalence_candidates(self.signature, self.global_access, self.call_report, self.coverage)

    def test_signature_report_extracts_types_directions_and_complex_parameters(self):
        payload = self.signature.to_dict()

        self.assertEqual("parsed", payload["function"]["status"])
        self.assertEqual("int", payload["function"]["return_type"]["base_type"])
        parameters = {item["name"]: item for item in payload["function"]["parameters"]}
        self.assertEqual("input", parameters["sensor"]["direction_hint"])
        self.assertEqual("output_candidate", parameters["out_value"]["direction_hint"])
        self.assertTrue(parameters["out_value"]["type"]["pointer_level"] >= 1)
        self.assertTrue(parameters["buffer"]["type"]["is_array"])
        self.assertEqual(["16"], parameters["buffer"]["type"]["array_dimensions"])

        callback_location = locate_function(self.digest, "RegisterCallback")
        callback_signature = extract_signature(self.digest, callback_location).to_dict()
        self.assertEqual("__stdcall", callback_signature["function"]["calling_convention"])
        callback = callback_signature["function"]["parameters"][0]
        self.assertTrue(callback["type"]["is_function_pointer"])
        self.assertEqual("callback", callback["name"])

        old_style_location = locate_function(self.digest, "OldStyle")
        old_style_signature = extract_signature(self.digest, old_style_location).to_dict()
        self.assertEqual("knr", old_style_signature["function"]["style"])
        self.assertEqual(["value", "out_value"], [item["name"] for item in old_style_signature["function"]["parameters"]])

        no_args_signature = extract_signature(self.digest, locate_function(self.digest, "NoArgs")).to_dict()
        self.assertEqual([], no_args_signature["function"]["parameters"])
        complex_signature = extract_signature(self.digest, locate_function(self.digest, "ComplexSignature")).to_dict()
        complex_parameters = {item["name"]: item for item in complex_signature["function"]["parameters"] if item["name"]}
        self.assertIn("const", complex_parameters["name"]["type"]["qualifiers"])
        self.assertTrue(complex_parameters["ctx"]["type"]["is_struct"])
        self.assertTrue(any(item["is_variadic"] for item in complex_signature["function"]["parameters"]))

    def test_global_access_report_classifies_state_and_parameter_side_effects(self):
        payload = self.global_access.to_dict()

        declarations = {item["name"]: item for item in payload["file_scope_declarations"]}
        self.assertEqual("file_static", declarations["g_state"]["scope"])
        self.assertEqual("extern", declarations["g_error"]["scope"])
        global_accesses = {(item["name"], item["access_kind"]) for item in payload["global_accesses"]}
        self.assertIn(("g_error", "write"), global_accesses)
        self.assertIn(("g_state", "read_write"), global_accesses)
        parameter_effects = {(item["name"], item["kind"]) for item in payload["side_effect_candidates"]}
        self.assertIn(("out_value", "parameter_write"), parameter_effects)
        self.assertIn(("buffer", "parameter_write"), parameter_effects)

    def test_call_report_classifies_calls_and_stub_candidates(self):
        payload = self.call_report.to_dict()

        calls = {item["name"]: item for item in payload["calls"]}
        self.assertEqual("same_file_static_function", calls["Helper"]["target_kind"])
        self.assertEqual("external_function", calls["CheckLimit"]["target_kind"])
        self.assertEqual("external_function", calls["WritePort"]["target_kind"])
        self.assertEqual("comparison", calls["CheckLimit"]["return_usage"]["usage_kind"])
        self.assertIn("address_of_global", [arg["argument_kind"] for arg in calls["WritePort"]["arguments"]])
        stubs = {item["name"]: item for item in payload["stub_candidates"]}
        self.assertTrue(stubs["CheckLimit"]["return_value_control_needed"])
        self.assertTrue(stubs["WritePort"]["side_effect_control_needed"])

    def test_coverage_design_links_branches_loops_switches_and_returns(self):
        payload = self.coverage.to_dict()

        self.assertGreaterEqual(len(payload["branches"]), 3)
        condition_kinds = {item["condition_kind"] for item in payload["condition_expressions"]}
        self.assertIn("null_check", condition_kinds)
        self.assertIn("range_check", condition_kinds)
        self.assertEqual(["MODE_AUTO", "MODE_MANUAL"], [case["label_value"] for case in payload["switches"][0]["cases"] if case["label_kind"] != "default"])
        coverage_types = {item["coverage_type"] for item in payload["coverage_items"]}
        self.assertIn("branch_true", coverage_types)
        self.assertIn("branch_false", coverage_types)
        self.assertIn("loop_zero", coverage_types)
        self.assertIn("switch_default", coverage_types)
        self.assertIn("return_path", coverage_types)

        shapes_location = locate_function(self.digest, "CoverageShapes")
        shapes_signature = extract_signature(self.digest, shapes_location)
        shapes_global = analyze_global_access(self.digest, shapes_location, shapes_signature)
        shapes_calls = analyze_calls(self.digest, shapes_location, shapes_signature, shapes_global)
        shapes_coverage = analyze_coverage_design(self.digest, shapes_location, shapes_signature, shapes_global, shapes_calls).to_dict()
        self.assertEqual(["do_while"], [item["kind"] for item in shapes_coverage["loops"]])
        self.assertTrue(shapes_coverage["ternaries"])
        shapes_coverage_types = {item["coverage_type"] for item in shapes_coverage["coverage_items"]}
        self.assertIn("ternary_true", shapes_coverage_types)
        self.assertIn("ternary_false", shapes_coverage_types)
        self.assertNotIn("loop_zero", shapes_coverage_types)

    def test_boundary_equivalence_candidates_use_conditions_types_and_calls(self):
        payload = self.boundary.to_dict()

        values = {(item["target_name"], item["value_expression"], item["value_kind"]) for item in payload["input_candidates"]}
        self.assertIn(("sensor", "SENSOR_MIN - 1", "boundary_below"), values)
        self.assertIn(("sensor", "SENSOR_MAX + 1", "boundary_above"), values)
        self.assertIn(("out_value", "NULL", "null"), values)
        self.assertIn(("out_value", "valid_writable_object", "non_null"), values)
        self.assertIn(("mode", "MODE_AUTO", "enum_value"), values)
        stub_values = {(item["call_name"], item["value_expression"]) for item in payload["stub_return_candidates"]}
        self.assertIn(("CheckLimit", "0"), stub_values)
        self.assertTrue(payload["coverage_links"])

        shapes_location = locate_function(self.digest, "CoverageShapes")
        shapes_signature = extract_signature(self.digest, shapes_location)
        shapes_global = analyze_global_access(self.digest, shapes_location, shapes_signature)
        shapes_calls = analyze_calls(self.digest, shapes_location, shapes_signature, shapes_global)
        shapes_coverage = analyze_coverage_design(self.digest, shapes_location, shapes_signature, shapes_global, shapes_calls)
        shapes_boundary = generate_boundary_equivalence_candidates(shapes_signature, shapes_global, shapes_calls, shapes_coverage).to_dict()
        shape_values = {(item["target_name"], item["value_expression"], item["value_kind"]) for item in shapes_boundary["input_candidates"]}
        self.assertIn(("count", "0", "zero"), shape_values)
        self.assertIn(("count", "1", "one"), shape_values)
        self.assertIn(("count", "2", "many"), shape_values)

    def test_analyze_function_generates_analysis_and_design_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "Control_Update"
            completed = run_module(
                "--json",
                "analyze-function",
                "--workspace",
                str(VC6_FIXTURE_ROOT),
                "--dsw",
                str(VC6_FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--phase",
                "execution",
                "--out",
                str(out_dir),
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual("evidence_prepared", result["status"])
            self.assertIn("dossier review", result["message"])
            reports = out_dir / "reports"
            for filename in [
                "function_signature.json",
                "function_signature.md",
                "global_access.json",
                "global_access.md",
                "call_report.json",
                "call_report.md",
                "coverage_design.json",
                "coverage_design.md",
                "boundary_equivalence_candidates.json",
                "boundary_equivalence_candidates.md",
                "test_case_design.json",
                "test_case_design.md",
                "test_case_design.csv",
                "harness_skeleton_report.json",
                "harness_skeleton_report.md",
                "build_workspace_report.json",
                "build_workspace_report.md",
                "build_probe_report.json",
                "build_probe_report.md",
                "build_completion_plan.json",
                "build_completion_plan.md",
                "build_completion_iteration_report.json",
                "build_completion_iteration_report.md",
                "test_execution_report.json",
                "test_execution_report.md",
                "test_result.json",
                "test_result.csv",
                "evidence_manifest.json",
                "evidence_package.md",
            ]:
                self.assertTrue((reports / filename).exists(), filename)
                if filename.endswith(".json"):
                    json.loads((reports / filename).read_text(encoding="utf-8"))

            japanese_headings = {
                "function_signature.md": "# 関数シグネチャレポート",
                "global_access.md": "# グローバルアクセスレポート",
                "call_report.md": "# 呼び出し解析レポート",
                "coverage_design.md": "# カバレッジ設計レポート",
                "boundary_equivalence_candidates.md": "# 境界値・同値クラス候補レポート",
                "test_case_design.md": "# テストケース設計レポート",
                "harness_skeleton_report.md": "# ハーネスひな形レポート",
                "build_workspace_report.md": "# ビルドワークスペースレポート",
                "build_probe_report.md": "# ビルドプローブレポート",
                "build_completion_plan.md": "# ビルド補完計画",
                "build_completion_iteration_report.md": "# ビルド補完イテレーションレポート",
                "test_execution_report.md": "# テスト実行レポート",
                "evidence_package.md": "# 関数単体テストエビデンスパッケージ",
            }
            for filename, heading in japanese_headings.items():
                markdown = (reports / filename).read_text(encoding="utf-8")
                self.assertIn(heading, markdown, filename)
                self.assertFalse(markdown.startswith("# Function "), filename)
                self.assertFalse(markdown.startswith("# Test "), filename)
                self.assertFalse(markdown.startswith("# Build "), filename)

            dossier = json.loads((reports / "function_dossier.json").read_text(encoding="utf-8"))
            self.assertIn("function_signature", dossier)
            self.assertIn("global_access", dossier)
            self.assertIn("call_report", dossier)
            self.assertIn("coverage_design", dossier)
            self.assertIn("boundary_equivalence_candidates", dossier)
            self.assertIn("test_case_design", dossier)
            self.assertIn("harness_skeleton", dossier)
            self.assertIn("build_workspace", dossier)
            self.assertIn("build_probe", dossier)
            self.assertIn("build_completion", dossier)
            self.assertIn("test_execution", dossier)
            self.assertIn("evidence", dossier)


if __name__ == "__main__":
    unittest.main()
