import importlib
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
from unit_test_runner.harness import harness_skeleton_generator as harness_generator_module
from unit_test_runner.harness.harness_skeleton_generator import generate_harness_skeleton
from unit_test_runner.test_design.test_case_design_generator import generate_test_case_design
from unit_test_runner.test_input_form import (
    apply_test_input_form,
    build_test_input_form,
    parse_test_input_change_request,
)


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

            test_bytes = (Path(temp_dir) / "generated" / "tests" / "test_Control_Update.c").read_bytes()
            self.assertNotIn(b"\n", test_bytes.replace(b"\r\n", b""))
            test_source = test_bytes.decode("cp932")
            self.assertIn('#error "UTR_REVIEW_REQUIRED:', test_source)
            self.assertNotIn("Target_Invoke_Control_Update(", test_source)
            self.assertNotIn("GetCallCount() >= 0", test_source)
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
        case = design["test_cases"][0]
        design["test_cases"] = [case]
        design["unresolved_items"] = []
        for item in case["input_assignments"]:
            item["review_required"] = False
            if item.get("target_name") in {"out_value", "buffer"}:
                item["value_expression"] = "VALID_STORAGE"
        for item in case["stub_setups"]:
            item["review_required"] = False
            if item.get("setup_kind") == "call_count_observation":
                item["value_expression"] = (
                    "1" if item.get("stub_name") == "CheckLimit" else None
                )
        case["expected_observations"] = [
                {
                    "observation_kind": "return_value",
                    "target_name": "return",
                    "expected_expression": "0",
                    "source": "review",
                    "review_required": False,
                    "confidence": "high",
                    "note": None,
                },
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

        with tempfile.TemporaryDirectory() as temp_dir:
            generate_harness_skeleton(
                self.signature.to_dict(),
                self.global_access.to_dict(),
                self.call_report.to_dict(),
                design,
                Path(temp_dir),
            )

            test_source = (Path(temp_dir) / "generated" / "tests" / "test_Control_Update.c").read_bytes().decode("cp932")
            self.assertNotIn("UTR_REVIEW_REQUIRED", test_source)
            self.assertNotIn("TBD_", test_source)
            self.assertIn("UTR_ASSERT_EQ_INT(0, (int)actual_return);", test_source)
            self.assertIn("#include <string.h>", test_source)
            self.assertIn("extern int g_error;", test_source)
            self.assertIn("UTR_ASSERT_EQ_INT(SENSOR_FAIL, g_error);", test_source)
            self.assertIn('UTR_ASSERT_TRUE(strcmp(buffer, "NG") == 0);', test_source)
            self.assertIn("UTR_ASSERT_EQ_INT(1, Stub_CheckLimit_GetCallCount());", test_source)
            self.assertNotIn("GetCallCount() >= 0", test_source)
            self.assertEqual([], c90_forbidden_tokens(test_source))

    def test_optional_candidate_unresolved_item_does_not_block_reviewed_case(self):
        design = self.test_case_design.to_dict()
        case = design["test_cases"][0]
        design["test_cases"] = [case]
        design["additional_case_candidates"] = [
            {"test_case_id": "TC_Control_Update_OPTIONAL"}
        ]
        design["unresolved_items"] = [
            {
                "item_id": "UNRES_OPTIONAL",
                "related_test_case_ids": ["TC_Control_Update_OPTIONAL"],
            }
        ]
        for item in case["input_assignments"]:
            item["review_required"] = False
            if item.get("target_name") in {"out_value", "buffer"}:
                item["value_expression"] = "VALID_STORAGE"
        for item in case["stub_setups"]:
            item["review_required"] = False
            if item.get("setup_kind") == "call_count_observation":
                item["value_expression"] = None
        case["expected_observations"] = [
            {
                "observation_kind": "return_value",
                "target_name": "return",
                "expected_expression": "0",
                "review_required": False,
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            report = generate_harness_skeleton(
                self.signature.to_dict(),
                self.global_access.to_dict(),
                self.call_report.to_dict(),
                design,
                Path(temp_dir),
            )

            test_source = (
                Path(temp_dir) / "generated" / "tests" / "test_Control_Update.c"
            ).read_text(encoding="cp932")
            self.assertEqual([], report.unresolved_placeholders)
            self.assertFalse(report.test_skeletons[0].review_required)
            self.assertNotIn("UTR_REVIEW_REQUIRED", test_source)

    def test_core_generator_retains_type_bridge_and_target_include_behavior_after_reload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            source = temp_root / "shared.c"
            header = temp_root / "shared0.h"
            header.write_text(
                "typedef short DWORD;\n"
                "typedef struct gbl_input_tag { int value; } gbl_input;\n",
                encoding="ascii",
            )
            source.write_text(
                '#include "shared0.h"\n'
                "DWORD Control_Update(gbl_input prm) { return (DWORD)prm.value; }\n",
                encoding="ascii",
            )
            signature = {
                "source": {"path": str(source)},
                "function": {
                    "name": "Control_Update",
                    "return_type": {"raw": "DWORD"},
                    "parameters": [
                        {
                            "index": 0,
                            "name": "prm",
                            "type": {
                                "raw": "gbl_input",
                                "base_type": "gbl_input",
                                "pointer_level": 0,
                                "is_array": False,
                            },
                        }
                    ],
                },
            }
            design = {
                "function": {"name": "Control_Update"},
                "unresolved_items": [],
                "test_cases": [
                    {
                        "test_case_id": "TC_Control_Update_001",
                        "review_status": "reviewed",
                        "input_assignments": [
                            {
                                "target_name": "prm",
                                "value_expression": "0",
                                "review_required": False,
                            }
                        ],
                        "state_setups": [],
                        "stub_setups": [],
                        "dependency_overrides": [],
                        "expected_observations": [
                            {
                                "observation_kind": "return_value",
                                "target_name": "return",
                                "expected_expression": "0",
                                "review_required": False,
                            }
                        ],
                    }
                ],
            }

            generator = importlib.reload(harness_generator_module)
            generator.generate_harness_skeleton(
                signature,
                {"global_accesses": [], "file_scope_declarations": []},
                {"calls": [], "stub_candidates": []},
                design,
                temp_root / "out",
            )

            test_source = (temp_root / "out" / "generated" / "tests" / "test_Control_Update.c").read_text(encoding="cp932")
            target_header = (temp_root / "out" / "generated" / "harness" / "target_invocation.h").read_text(encoding="cp932")
            target_source = (temp_root / "out" / "generated" / "harness" / "target_invocation.c").read_text(encoding="cp932")
            self.assertIn('#include "shared0.h"', test_source)
            self.assertIn("gbl_input prm = {0};", test_source)
            self.assertIn('#include "shared0.h"', target_header)
            self.assertIn("DWORD Control_Update(gbl_input prm);", target_source)
            self.assertNotIn('#include "shared.h"', target_source)

    def test_analyze_harness_phase_connects_harness_generation(self):
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
                "harness",
                "--out",
                str(out_dir),
            )

            self.assertEqual(0, analyze.returncode, analyze.stderr)
            analyze_payload = json.loads(analyze.stdout)
            self.assertEqual("passed", analyze_payload["outcome"])
            self.assertEqual(
                {"function_dossier", "test_spec"},
                {item["kind"] for item in analyze_payload["artifacts"]},
            )
            self.assertTrue((out_dir / "reports" / "harness_skeleton_report.json").exists())
            self.assertTrue((out_dir / "generated" / "tests" / "test_Control_Update.c").exists())

            test_spec_path = out_dir / "reports" / "test_spec.json"
            form = build_test_input_form(out_dir)
            case = next(item for item in form.cases if item.promotion_eligible)
            changes = []
            for item in case.items:
                if not item.editable:
                    continue
                values = {}
                for control in item.controls:
                    if not control.required_for_confirmation:
                        continue
                    value = control.value
                    if item.kind == "expected_observation":
                        if "return_value" in item.label:
                            value = "OK"
                        elif "global_value" in item.label:
                            value = "0"
                    values[control.name] = value
                changes.append(
                    {
                        "item_id": item.item_id,
                        "subject_fingerprint": item.subject_fingerprint,
                        "values": values,
                        "confirmed": True,
                    }
                )
            apply_test_input_form(
                out_dir,
                parse_test_input_change_request(
                    {"schema_version": "1.0", "changes": changes}
                ),
                expected_revision=form.revision,
            )
            reviewed_test_spec = test_spec_path.read_bytes()
            repeated = run_module(
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
                "harness",
                "--out",
                str(out_dir),
            )

            self.assertEqual(0, repeated.returncode, repeated.stderr)
            self.assertEqual(
                reviewed_test_spec,
                test_spec_path.read_bytes(),
                "harness preparation must consume, not regenerate, the reviewed TestSpec",
            )
            self.assertNotIn(
                b"UTR_REVIEW_REQUIRED",
                (out_dir / "generated" / "tests" / "test_Control_Update.c").read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
