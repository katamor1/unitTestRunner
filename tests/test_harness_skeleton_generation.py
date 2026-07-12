import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
PIPELINE = REPO_ROOT / "tests" / "fixtures" / "c_sources" / "analysis_pipeline" / "pipeline.c"
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.c_analyzer.boundary_candidate_analyzer import generate_boundary_equivalence_candidates
from unit_test_runner.c_analyzer.call_analyzer import analyze_calls
from unit_test_runner.c_analyzer.coverage_design_analyzer import analyze_coverage_design
from unit_test_runner.c_analyzer.function_locator import locate_function
from unit_test_runner.c_analyzer.global_access_analyzer import analyze_global_access
from unit_test_runner.c_analyzer.signature_extractor import extract_signature
from unit_test_runner.c_analyzer.source_digest import build_source_digest
from unit_test_runner.harness.c90_writer import is_c90_compatible_text
from unit_test_runner.harness.harness_skeleton_generator import generate_harness_skeleton
from unit_test_runner.test_design.test_case_design_generator import generate_test_case_design


def run_module(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def c90_forbidden_tokens(text):
    return [token for token in ["//", "for (int ", "stdint.h", "stdbool.h", "inline "] if token in text]


class HarnessSkeletonGenerationTests(unittest.TestCase):
    def setUp(self):
        digest = build_source_digest(PIPELINE)
        location = locate_function(digest, "Control_Update")
        self.signature = extract_signature(digest, location)
        self.global_access = analyze_global_access(digest, location, self.signature)
        self.call_report = analyze_calls(digest, location, self.signature, self.global_access)
        coverage = analyze_coverage_design(digest, location, self.signature, self.global_access, self.call_report)
        boundary = generate_boundary_equivalence_candidates(self.signature, self.global_access, self.call_report, coverage)
        self.test_case_design = generate_test_case_design(self.signature, self.global_access, self.call_report, coverage, boundary)

    def test_generator_outputs_cp932_c90_harness_stubs_tests_and_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = generate_harness_skeleton(
                self.signature.to_dict(),
                self.global_access.to_dict(),
                self.call_report.to_dict(),
                self.test_case_design.to_dict(),
                Path(temp_dir),
            )
            payload = report.to_dict()

            self.assertIn(payload["function"]["status"], {"generated", "partial"})
            files = {Path(item["path"]).as_posix(): item for item in payload["generated_files"]}
            for expected in [
                "generated/include/utr_assert.h",
                "generated/harness/utr_assert.c",
                "generated/harness/utr_runner.c",
                "generated/harness/target_invocation.c",
                "generated/stubs/stub_CheckLimit.c",
                "generated/tests/test_Control_Update.c",
                "generated/tests/test_Control_Update_cases.h",
            ]:
                self.assertIn(expected, files)
                self.assertTrue((Path(temp_dir) / expected).exists(), expected)

            stub_source = (Path(temp_dir) / "generated" / "stubs" / "stub_CheckLimit.c").read_bytes().decode("cp932")
            self.assertIn("Stub_CheckLimit_SetReturn", stub_source)
            self.assertIn("Stub_CheckLimit_GetCallCount", stub_source)
            self.assertEqual([], c90_forbidden_tokens(stub_source))

            test_source = (Path(temp_dir) / "generated" / "tests" / "test_Control_Update.c").read_bytes().decode("cp932")
            self.assertIn("TBD_EXPECTED_RETURN_INT", test_source)
            self.assertIn("Target_Invoke_Control_Update", test_source)
            self.assertEqual([], c90_forbidden_tokens(test_source))

            target_header = (Path(temp_dir) / "generated" / "harness" / "target_invocation.h").read_bytes().decode("cp932")
            self.assertIn("void * buffer", target_header)
            self.assertNotIn("char buffer[16]", target_header)

            self.assertTrue(payload["unresolved_placeholders"])
            self.assertTrue(payload["build_hints"])
            self.assertTrue((Path(temp_dir) / "reports" / "harness_skeleton_report.json").exists())
            self.assertIn("# ハーネスひな形レポート", (Path(temp_dir) / "reports" / "harness_skeleton_report.md").read_text(encoding="utf-8"))

    def test_c90_compatibility_check_ignores_strings_and_matches_tokens(self):
        self.assertTrue(is_c90_compatible_text('const char *url = "http://example";\n'))
        self.assertTrue(is_c90_compatible_text("int inline_value;\n"))
        self.assertFalse(is_c90_compatible_text("for(int i = 0; i < 3; i++) { }\n"))
        self.assertFalse(is_c90_compatible_text("for ( int i = 0; i < 3; i++) { }\n"))
        self.assertFalse(is_c90_compatible_text("#include <stdint.h>\n"))
        self.assertFalse(is_c90_compatible_text("static inline int helper(void) { return 0; }\n"))

    def test_harness_asserts_reviewed_global_and_char_array_string_expectations(self):
        design = self.test_case_design.to_dict()
        design["test_cases"][0]["expected_observations"].extend(
            [
                {
                    "observation_kind": "global_value",
                    "target_name": "g_error",
                    "expected_expression": "SENSOR_FAIL",
                    "source": "global_access",
                    "review_required": False,
                    "confidence": "medium",
                    "note": None,
                },
                {
                    "observation_kind": "char_array_string",
                    "target_name": "buffer",
                    "expected_expression": '"NG"',
                    "source": "parameter_access",
                    "review_required": False,
                    "confidence": "medium",
                    "note": None,
                },
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            generate_harness_skeleton(
                self.signature.to_dict(),
                self.global_access.to_dict(),
                self.call_report.to_dict(),
                design,
                Path(temp_dir),
            )

            test_source = (Path(temp_dir) / "generated" / "tests" / "test_Control_Update.c").read_bytes().decode("cp932")
            self.assertIn("#include <string.h>", test_source)
            self.assertIn("extern int g_error;", test_source)
            self.assertIn("UTR_ASSERT_EQ_INT(SENSOR_FAIL, g_error);", test_source)
            self.assertIn('UTR_ASSERT_TRUE(strcmp(buffer, "NG") == 0);', test_source)
            self.assertEqual([], c90_forbidden_tokens(test_source))

    def test_generate_harness_cli_and_analyze_function_connect_harness_generation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "Control_Update"
            analyze = run_module(
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

            self.assertEqual(0, analyze.returncode, analyze.stderr)
            analyze_payload = json.loads(analyze.stdout)
            self.assertEqual("passed", analyze_payload["data"]["outcome"])
            self.assertIn("dossier review", analyze_payload["data"]["message"])
            self.assertIn("harness_skeleton", analyze_payload["data"]["details"])
            self.assertTrue((out_dir / "reports" / "harness_skeleton_report.json").exists())

            reports = out_dir / "reports"
            explicit_out = Path(temp_dir) / "explicit_harness"
            generated = run_module(
                "--json",
                "generate-harness-skeleton",
                "--function-signature",
                str(reports / "function_signature.json"),
                "--global-access",
                str(reports / "global_access.json"),
                "--call-report",
                str(reports / "call_report.json"),
                "--test-case-design",
                str(reports / "test_case_design.json"),
                "--out",
                str(explicit_out),
            )

            self.assertEqual(0, generated.returncode, generated.stderr)
            payload = json.loads(generated.stdout)
            self.assertEqual("passed", payload["data"]["outcome"])
            self.assertTrue(Path(payload["data"]["details"]["harness_skeleton"]["json"]).exists())
            self.assertTrue((explicit_out / "generated" / "tests" / "test_Control_Update.c").exists())


if __name__ == "__main__":
    unittest.main()
