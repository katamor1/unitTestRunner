import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.harness import generate_harness_skeleton


class DependencyDispatcherGenerationTests(unittest.TestCase):
    def test_generated_stub_uses_unique_symbol_and_case_override_sets_dispatch_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "target.c"
            header = root / "deps.h"
            source.write_text('#include "deps.h"\nint Target(int value) { return Helper(value); }\n', encoding="utf-8")
            header.write_text("int Helper(int value);\n", encoding="utf-8")
            signature = {
                "source": {"path": str(source), "sha256": "abc"},
                "function": {
                    "name": "Target",
                    "status": "parsed",
                    "style": "ansi",
                    "storage_class": None,
                    "return_type": {"raw": "int", "normalized": "int"},
                    "parameters": [
                        {
                            "index": 0,
                            "name": "value",
                            "is_void": False,
                            "is_variadic": False,
                            "type": {"raw": "int", "base_type": "int", "pointer_level": 0, "is_array": False},
                        }
                    ],
                },
            }
            call_report = {
                "calls": [
                    {
                        "call_id": "CALL_001",
                        "name": "Helper",
                        "target_kind": "external_function",
                        "arguments": [{"index": 0, "raw": "value", "argument_kind": "parameter", "passing_mode_hint": "by_value"}],
                        "return_usage": {"usage_kind": "returned"},
                    }
                ],
                "stub_candidates": [
                    {
                        "name": "Helper",
                        "target_kind": "external_function",
                        "return_value_control_needed": True,
                        "argument_capture_needed": True,
                        "side_effect_control_needed": False,
                        "related_calls": ["CALL_001"],
                        "tags": ["external_dependency"],
                    }
                ],
            }
            test_design = {
                "source": {"path": str(source), "sha256": "abc"},
                "function": {"name": "Target", "status": "generated"},
                "test_cases": [
                    {
                        "test_case_id": "TC_Target_001",
                        "title": "stub override",
                        "target_function": "Target",
                        "purpose": "override dependency",
                        "priority": "high",
                        "case_kind": "return_path",
                        "preconditions": [],
                        "input_assignments": [
                            {
                                "target_name": "value",
                                "target_kind": "parameter",
                                "value_expression": "1",
                                "value_kind": "literal",
                                "source_candidate_id": None,
                                "rationale": "fixture",
                                "review_required": False,
                                "confidence": "high",
                            }
                        ],
                        "state_setups": [],
                        "stub_setups": [
                            {
                                "stub_name": "Helper",
                                "setup_kind": "return_value",
                                "value_expression": "7",
                                "call_behavior": None,
                                "source_candidate_id": None,
                                "related_call_id": "CALL_001",
                                "review_required": False,
                                "confidence": "high",
                            }
                        ],
                        "dependency_overrides": [
                            {"callee": "Helper", "mode": "stub", "rationale": "error path", "review_required": False}
                        ],
                        "execution_steps": [],
                        "expected_observations": [],
                        "coverage_links": [],
                        "candidate_links": [],
                        "review_status": "reviewed",
                        "confidence": "high",
                        "warnings": [],
                    }
                ],
                "additional_case_candidates": [],
                "coverage_summary": {"total_coverage_items": 0, "covered_by_design_count": 0, "uncovered_coverage_ids": [], "coverage_to_test_cases": {}},
                "unresolved_items": [],
                "warnings": [],
            }
            dependency_policy = {
                "source": {"path": str(source)},
                "function": {"name": "Target", "status": "resolved"},
                "dependencies": [
                    {
                        "callee": "Helper",
                        "target_kind": "external_function",
                        "configured_mode": "auto",
                        "resolved_mode": "real",
                        "review_status": "resolved",
                        "implementation_source": "src/helper.c",
                        "related_call_ids": ["CALL_001"],
                        "rewrite_sites": [{"call_id": "CALL_001", "start": {"line": 2, "column": 32}, "end": {"line": 2, "column": 38}}],
                        "signature": {
                            "resolution": "exact",
                            "return_type_raw": "int",
                            "calling_convention": None,
                            "parameters": [{"index": 0, "name": "value", "type_raw": "int", "pointer_level": 0, "qualifiers": [], "is_variadic": False}],
                            "prototype": "int Helper(int value)",
                            "declaration_source": "deps.h",
                            "definition_source": "src/helper.c",
                            "conflicts": [],
                            "confidence": "high",
                        },
                    }
                ],
                "external_objects": [],
                "warnings": [],
            }

            report = generate_harness_skeleton(
                signature,
                {"global_accesses": [], "file_scope_declarations": []},
                call_report,
                test_design,
                root,
                overwrite=True,
                dependency_policy=dependency_policy,
            )

            stub_source = (root / "generated" / "stubs" / "stub_Helper.c").read_bytes().decode("cp932")
            stub_header = (root / "generated" / "stubs" / "stub_Helper.h").read_bytes().decode("cp932")
            dispatcher = (root / "generated" / "dependencies" / "utr_dependency_dispatch.c").read_bytes().decode("cp932")
            control = (root / "generated" / "include" / "utr_dependency_control.h").read_bytes().decode("cp932")
            test_source = (root / "generated" / "tests" / "test_Target.c").read_bytes().decode("cp932")
            payload = json.loads((root / "reports" / "harness_skeleton_report.json").read_text(encoding="utf-8"))

        self.assertNotIn("int Helper(", stub_source)
        self.assertNotIn("int Helper(", stub_header)
        self.assertIn("int Utr_Stub_Helper_Invoke(int value)", stub_source)
        self.assertIn("int Utr_Dep_Helper(int value)", dispatcher)
        self.assertIn("return Helper(value);", dispatcher)
        self.assertIn("#define Stub_Helper_SetReturn(value)", control)
        self.assertIn("Utr_Dep_ResetAllModes();", test_source)
        self.assertIn("Utr_Dep_Helper_SetMode(UTR_DEP_MODE_STUB);", test_source)
        self.assertEqual("Utr_Dep_Helper", payload["dependency_dispatches"][0]["dispatcher_name"])
        self.assertEqual("Utr_Stub_Helper_Invoke", payload["dependency_dispatches"][0]["stub_invoke_name"])
        self.assertEqual("Utr_Stub_Helper", report.stub_skeletons[0].stub_name)

    def test_definition_only_real_dependency_emits_original_prototype_in_dispatcher(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "target.c"
            source.write_text("int Target(int value) { return Helper(value); }\n", encoding="utf-8")
            signature = {
                "source": {"path": str(source), "sha256": "abc"},
                "function": {
                    "name": "Target",
                    "status": "parsed",
                    "style": "ansi",
                    "storage_class": None,
                    "return_type": {"raw": "int", "normalized": "int"},
                    "parameters": [{"index": 0, "name": "value", "is_void": False, "is_variadic": False, "type": {"raw": "int", "base_type": "int", "pointer_level": 0, "is_array": False}}],
                },
            }
            call_report = {
                "calls": [{"call_id": "CALL_001", "name": "Helper", "target_kind": "external_function", "arguments": [{"index": 0, "raw": "value", "argument_kind": "parameter", "passing_mode_hint": "by_value"}], "return_usage": {"usage_kind": "returned"}}],
                "stub_candidates": [],
            }
            design = {
                "source": {"path": str(source)},
                "function": {"name": "Target", "status": "generated"},
                "test_cases": [],
                "additional_case_candidates": [],
                "coverage_summary": {"total_coverage_items": 0, "covered_by_design_count": 0, "uncovered_coverage_ids": [], "coverage_to_test_cases": {}},
                "unresolved_items": [],
                "warnings": [],
            }
            policy = {
                "dependencies": [{
                    "callee": "Helper",
                    "target_kind": "external_function",
                    "resolved_mode": "real",
                    "implementation_source": "helper.c",
                    "related_call_ids": ["CALL_001"],
                    "rewrite_sites": [{"call_id": "CALL_001", "start": {"line": 1, "column": 32}, "end": {"line": 1, "column": 38}}],
                    "signature": {
                        "resolution": "exact",
                        "return_type_raw": "int",
                        "calling_convention": None,
                        "parameters": [{"index": 0, "name": "value", "type_raw": "int", "pointer_level": 0, "qualifiers": [], "is_variadic": False}],
                        "prototype": "int Helper(int value)",
                        "declaration_source": None,
                        "definition_source": "helper.c",
                    },
                }],
                "external_objects": [],
            }

            generate_harness_skeleton(signature, {"global_accesses": [], "file_scope_declarations": []}, call_report, design, root, overwrite=True, dependency_policy=policy)
            dispatcher = (root / "generated" / "dependencies" / "utr_dependency_dispatch.c").read_text(encoding="cp932")

        self.assertIn("int Helper(int value);", dispatcher)
        self.assertLess(dispatcher.index("int Helper(int value);"), dispatcher.index("int Utr_Dep_Helper(int value)"))


    def test_review_required_dependency_does_not_leave_original_symbol_stub(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "target.c"
            source.write_text("int Target(int value) { return Conflicted(value); }\n", encoding="utf-8")
            signature = {
                "source": {"path": str(source), "sha256": "abc"},
                "function": {
                    "name": "Target",
                    "status": "parsed",
                    "style": "ansi",
                    "storage_class": None,
                    "return_type": {"raw": "int", "normalized": "int"},
                    "parameters": [{"index": 0, "name": "value", "is_void": False, "is_variadic": False, "type": {"raw": "int", "base_type": "int", "pointer_level": 0, "is_array": False}}],
                },
            }
            call_report = {
                "calls": [{"call_id": "CALL_001", "name": "Conflicted", "target_kind": "external_function", "arguments": [{"index": 0, "raw": "value", "argument_kind": "parameter", "passing_mode_hint": "by_value"}], "return_usage": {"usage_kind": "returned"}}],
                "stub_candidates": [{
                    "name": "Conflicted",
                    "target_kind": "external_function",
                    "return_value_control_needed": True,
                    "argument_capture_needed": True,
                    "side_effect_control_needed": False,
                    "related_calls": ["CALL_001"],
                    "tags": ["external_dependency"],
                }],
            }
            design = {
                "source": {"path": str(source)},
                "function": {"name": "Target", "status": "generated"},
                "test_cases": [],
                "additional_case_candidates": [],
                "coverage_summary": {"total_coverage_items": 0, "covered_by_design_count": 0, "uncovered_coverage_ids": [], "coverage_to_test_cases": {}},
                "unresolved_items": [],
                "warnings": [],
            }
            policy = {
                "dependencies": [{
                    "callee": "Conflicted",
                    "target_kind": "external_function",
                    "configured_mode": "auto",
                    "resolved_mode": "review_required",
                    "review_status": "review_required",
                    "related_call_ids": ["CALL_001"],
                    "rewrite_sites": [],
                    "signature": {"resolution": "review_required", "conflicts": ["conflicting prototypes"]},
                    "warnings": ["Dependency signature requires review before dispatcher generation."],
                }],
                "external_objects": [],
            }

            report = generate_harness_skeleton(
                signature,
                {"global_accesses": [], "file_scope_declarations": []},
                call_report,
                design,
                root,
                overwrite=True,
                dependency_policy=policy,
            )

        self.assertFalse((root / "generated" / "stubs" / "stub_Conflicted.c").exists())
        self.assertFalse(any(item.original_function_name == "Conflicted" for item in report.stub_skeletons))
        self.assertTrue(any(item.code == "dependency_policy_review_required" for item in report.warnings))


    def test_stub_only_policy_does_not_link_real_implementation_until_case_requests_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "target.c"
            header = root / "deps.h"
            source.write_text('#include "deps.h"\nint Target(int value) { return Helper(value); }\n', encoding="utf-8")
            header.write_text("int Helper(int value);\n", encoding="utf-8")
            signature = {
                "source": {"path": str(source), "sha256": "abc"},
                "function": {
                    "name": "Target",
                    "status": "parsed",
                    "style": "ansi",
                    "storage_class": None,
                    "return_type": {"raw": "int", "normalized": "int"},
                    "parameters": [{"index": 0, "name": "value", "is_void": False, "is_variadic": False, "type": {"raw": "int", "base_type": "int", "pointer_level": 0, "is_array": False}}],
                },
            }
            call_report = {
                "calls": [{"call_id": "CALL_001", "name": "Helper", "target_kind": "external_function", "arguments": [{"index": 0, "raw": "value", "argument_kind": "parameter", "passing_mode_hint": "by_value"}], "return_usage": {"usage_kind": "returned"}}],
                "stub_candidates": [],
            }
            design = {
                "source": {"path": str(source)},
                "function": {"name": "Target", "status": "generated"},
                "test_cases": [{
                    "test_case_id": "TC_001",
                    "title": "stub only",
                    "target_function": "Target",
                    "purpose": "stub only",
                    "priority": "high",
                    "case_kind": "return_path",
                    "preconditions": [],
                    "input_assignments": [],
                    "state_setups": [],
                    "stub_setups": [],
                    "dependency_overrides": [],
                    "execution_steps": [],
                    "expected_observations": [],
                    "coverage_links": [],
                    "candidate_links": [],
                    "review_status": "reviewed",
                    "confidence": "high",
                    "warnings": [],
                }],
                "additional_case_candidates": [],
                "coverage_summary": {"total_coverage_items": 0, "covered_by_design_count": 0, "uncovered_coverage_ids": [], "coverage_to_test_cases": {}},
                "unresolved_items": [],
                "warnings": [],
            }
            policy = {
                "dependencies": [{
                    "callee": "Helper",
                    "target_kind": "external_function",
                    "configured_mode": "stub",
                    "resolved_mode": "stub",
                    "review_status": "resolved",
                    "implementation_source": "src/helper.c",
                    "related_call_ids": ["CALL_001"],
                    "rewrite_sites": [{"call_id": "CALL_001", "start": {"line": 2, "column": 32}, "end": {"line": 2, "column": 38}}],
                    "signature": {
                        "resolution": "exact",
                        "return_type_raw": "int",
                        "calling_convention": None,
                        "parameters": [{"index": 0, "name": "value", "type_raw": "int", "pointer_level": 0, "qualifiers": [], "is_variadic": False}],
                        "prototype": "int Helper(int value)",
                        "declaration_source": "deps.h",
                        "definition_source": "src/helper.c",
                    },
                }],
                "external_objects": [],
            }

            report = generate_harness_skeleton(signature, {"global_accesses": [], "file_scope_declarations": []}, call_report, design, root, overwrite=True, dependency_policy=policy)
            dispatcher = (root / "generated" / "dependencies" / "utr_dependency_dispatch.c").read_text(encoding="cp932")

        self.assertNotIn("return Helper(value);", dispatcher)
        self.assertFalse(report.dependency_dispatches[0].real_available)

    def test_real_case_override_enables_real_branch_for_stub_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "target.c"
            header = root / "deps.h"
            source.write_text('#include "deps.h"\nint Target(int value) { return Helper(value); }\n', encoding="utf-8")
            header.write_text("int Helper(int value);\n", encoding="utf-8")
            signature = {
                "source": {"path": str(source), "sha256": "abc"},
                "function": {"name": "Target", "status": "parsed", "style": "ansi", "storage_class": None, "return_type": {"raw": "int", "normalized": "int"}, "parameters": [{"index": 0, "name": "value", "is_void": False, "is_variadic": False, "type": {"raw": "int", "base_type": "int", "pointer_level": 0, "is_array": False}}]},
            }
            call_report = {"calls": [{"call_id": "CALL_001", "name": "Helper", "target_kind": "external_function", "arguments": [{"index": 0, "raw": "value", "argument_kind": "parameter", "passing_mode_hint": "by_value"}], "return_usage": {"usage_kind": "returned"}}], "stub_candidates": []}
            design = {
                "source": {"path": str(source)}, "function": {"name": "Target", "status": "generated"},
                "test_cases": [{"test_case_id": "TC_001", "title": "real override", "target_function": "Target", "purpose": "real override", "priority": "high", "case_kind": "return_path", "preconditions": [], "input_assignments": [], "state_setups": [], "stub_setups": [], "dependency_overrides": [{"callee": "Helper", "mode": "real", "rationale": "integration path", "review_required": False}], "execution_steps": [], "expected_observations": [], "coverage_links": [], "candidate_links": [], "review_status": "reviewed", "confidence": "high", "warnings": []}],
                "additional_case_candidates": [], "coverage_summary": {"total_coverage_items": 0, "covered_by_design_count": 0, "uncovered_coverage_ids": [], "coverage_to_test_cases": {}}, "unresolved_items": [], "warnings": [],
            }
            policy = {"dependencies": [{"callee": "Helper", "target_kind": "external_function", "configured_mode": "stub", "resolved_mode": "stub", "review_status": "resolved", "implementation_source": "src/helper.c", "related_call_ids": ["CALL_001"], "rewrite_sites": [{"call_id": "CALL_001", "start": {"line": 2, "column": 32}, "end": {"line": 2, "column": 38}}], "signature": {"resolution": "exact", "return_type_raw": "int", "calling_convention": None, "parameters": [{"index": 0, "name": "value", "type_raw": "int", "pointer_level": 0, "qualifiers": [], "is_variadic": False}], "prototype": "int Helper(int value)", "declaration_source": "deps.h", "definition_source": "src/helper.c"}}], "external_objects": []}

            report = generate_harness_skeleton(signature, {"global_accesses": [], "file_scope_declarations": []}, call_report, design, root, overwrite=True, dependency_policy=policy)
            dispatcher = (root / "generated" / "dependencies" / "utr_dependency_dispatch.c").read_text(encoding="cp932")
            test_source = (root / "generated" / "tests" / "test_Target.c").read_text(encoding="cp932")

        self.assertIn("return Helper(value);", dispatcher)
        self.assertTrue(report.dependency_dispatches[0].real_available)
        self.assertIn("Utr_Dep_Helper_SetMode(UTR_DEP_MODE_REAL);", test_source)

    def test_pointer_typedef_uses_pointer_control_api(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "target.c"
            header = root / "deps.h"
            source.write_text('#include "deps.h"\nContextPtr Target(ContextPtr value) { return Helper(value); }\n', encoding="utf-8")
            header.write_text("typedef struct ContextTag Context;\ntypedef Context * ContextPtr;\nContextPtr Helper(ContextPtr value);\n", encoding="utf-8")
            signature = {
                "source": {"path": str(source), "sha256": "abc"},
                "function": {
                    "name": "Target",
                    "status": "parsed",
                    "style": "ansi",
                    "storage_class": None,
                    "return_type": {"raw": "ContextPtr", "normalized": "ContextPtr"},
                    "parameters": [{"index": 0, "name": "value", "is_void": False, "is_variadic": False, "type": {"raw": "ContextPtr", "base_type": "ContextPtr", "pointer_level": 0, "is_array": False}}],
                },
            }
            call_report = {
                "calls": [{"call_id": "CALL_001", "name": "Helper", "target_kind": "external_function", "arguments": [{"index": 0, "raw": "value", "argument_kind": "parameter", "passing_mode_hint": "by_value"}], "return_usage": {"usage_kind": "returned"}}],
                "stub_candidates": [],
            }
            design = {
                "source": {"path": str(source)},
                "function": {"name": "Target", "status": "generated"},
                "test_cases": [],
                "additional_case_candidates": [],
                "coverage_summary": {"total_coverage_items": 0, "covered_by_design_count": 0, "uncovered_coverage_ids": [], "coverage_to_test_cases": {}},
                "unresolved_items": [],
                "warnings": [],
            }
            policy = {
                "dependencies": [{
                    "callee": "Helper",
                    "target_kind": "external_function",
                    "resolved_mode": "stub",
                    "implementation_source": None,
                    "related_call_ids": ["CALL_001"],
                    "rewrite_sites": [{"call_id": "CALL_001", "start": {"line": 2, "column": 47}, "end": {"line": 2, "column": 53}}],
                    "signature": {
                        "resolution": "exact",
                        "return_type_raw": "ContextPtr",
                        "return_type_canonical": "struct ContextTag *",
                        "return_type_category": "pointer",
                        "calling_convention": None,
                        "parameters": [{"index": 0, "name": "value", "type_raw": "ContextPtr", "pointer_level": 0, "qualifiers": [], "is_variadic": False, "canonical_type": "struct ContextTag *", "type_category": "pointer"}],
                        "prototype": "ContextPtr Helper(ContextPtr value)",
                        "declaration_source": str(header),
                        "definition_source": None,
                    },
                }],
                "external_objects": [],
            }

            generate_harness_skeleton(signature, {"global_accesses": [], "file_scope_declarations": []}, call_report, design, root, overwrite=True, dependency_policy=policy)
            stub_header = (root / "generated" / "stubs" / "stub_Helper.h").read_text(encoding="cp932")
            control_header = (root / "generated" / "include" / "utr_dependency_control.h").read_text(encoding="cp932")

        self.assertIn("void Utr_Stub_Helper_SetReturnPointer(void *value);", stub_header)
        self.assertNotIn("SetReturnInt", stub_header)
        self.assertIn("Utr_Stub_Helper_SetReturnPointer", control_header)
        self.assertNotIn("Utr_Stub_Helper_SetReturnInt", control_header)


if __name__ == "__main__":
    unittest.main()
