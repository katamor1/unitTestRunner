import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build import generate_build_workspace
from unit_test_runner.execution.execution_runner import run_test_executable_cases
from unit_test_runner.harness import generate_harness_skeleton


@unittest.skipUnless(any(shutil.which(name) for name in ("gcc", "clang", "cc")), "host C compiler is required")
class DependencyPolicyEndToEndTests(unittest.TestCase):
    def test_real_default_and_case_stub_override_build_and_run_without_symbol_collisions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            output = root / "workspace"
            project.mkdir()
            target = project / "target.c"
            helper = project / "helper.c"
            header = project / "product.h"
            header.write_text("extern int g_state;\nint Helper(int value);\n", encoding="ascii")
            target.write_text(
                '#include "product.h"\n'
                "int Target(int value)\n"
                "{\n"
                "    return Helper(value);\n"
                "}\n",
                encoding="ascii",
            )
            helper.write_text(
                '#include "product.h"\n'
                "int g_state;\n"
                "int Helper(int value)\n"
                "{\n"
                "    g_state = value;\n"
                "    return 0;\n"
                "}\n",
                encoding="ascii",
            )
            signature = {
                "source": {"path": str(target), "sha256": "target"},
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
            global_access = {
                "global_accesses": [
                    {
                        "name": "g_state",
                        "scope": "extern",
                        "related_declaration": {"name": "g_state", "type_raw": "int", "storage_class": "extern", "scope": "extern"},
                    }
                ],
                "file_scope_declarations": [
                    {"name": "g_state", "type_raw": "int", "storage_class": "extern", "scope": "extern"}
                ],
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
                        "tags": [],
                    }
                ],
            }
            cases = []
            for case_id, value, override, expected_state in (
                ("TC_Target_Real", "11", "inherit", "11"),
                ("TC_Target_Stub", "22", "stub", "0"),
            ):
                cases.append(
                    {
                        "test_case_id": case_id,
                        "title": case_id,
                        "target_function": "Target",
                        "purpose": "dependency selection",
                        "priority": "high",
                        "case_kind": "dependency_mode",
                        "preconditions": [],
                        "input_assignments": [
                            {
                                "target_name": "value",
                                "target_kind": "parameter",
                                "value_expression": value,
                                "value_kind": "literal",
                                "source_candidate_id": None,
                                "rationale": "fixture",
                                "review_required": False,
                                "confidence": "high",
                            }
                        ],
                        "state_setups": [
                            {
                                "variable_name": "g_state",
                                "scope": "extern",
                                "value_expression": "0",
                                "setup_method_hint": "direct_assignment",
                                "review_required": False,
                                "confidence": "high",
                            }
                        ],
                        "stub_setups": [
                            {
                                "stub_name": "Helper",
                                "setup_kind": "return_value",
                                "value_expression": "0",
                                "call_behavior": None,
                                "source_candidate_id": None,
                                "related_call_id": "CALL_001",
                                "review_required": False,
                                "confidence": "high",
                            }
                        ],
                        "dependency_overrides": [
                            {"callee": "Helper", "mode": override, "rationale": "case selection", "review_required": False}
                        ],
                        "execution_steps": [],
                        "expected_observations": [
                            {
                                "observation_kind": "global_value",
                                "target_name": "g_state",
                                "expected_expression": expected_state,
                                "source": "dependency_policy",
                                "review_required": False,
                                "confidence": "high",
                                "note": None,
                            }
                        ],
                        "coverage_links": [],
                        "candidate_links": [],
                        "review_status": "reviewed",
                        "confidence": "high",
                        "warnings": [],
                    }
                )
            design = {
                "source": {"path": str(target), "sha256": "target"},
                "function": {"name": "Target", "status": "generated"},
                "test_cases": cases,
                "additional_case_candidates": [],
                "coverage_summary": {"total_coverage_items": 0, "covered_by_design_count": 0, "uncovered_coverage_ids": [], "coverage_to_test_cases": {}},
                "unresolved_items": [],
                "warnings": [],
            }
            policy = {
                "source": {"path": "target.c"},
                "function": {"name": "Target", "status": "resolved"},
                "dependencies": [
                    {
                        "callee": "Helper",
                        "target_kind": "external_function",
                        "configured_mode": "auto",
                        "resolved_mode": "real",
                        "review_status": "resolved",
                        "implementation_source": "helper.c",
                        "related_call_ids": ["CALL_001"],
                        "rewrite_sites": [{"call_id": "CALL_001", "start": {"line": 4, "column": 12}, "end": {"line": 4, "column": 18}}],
                        "signature": {
                            "resolution": "exact",
                            "return_type_raw": "int",
                            "calling_convention": None,
                            "parameters": [{"index": 0, "name": "value", "type_raw": "int", "pointer_level": 0, "qualifiers": [], "is_variadic": False}],
                            "prototype": "int Helper(int value)",
                            "declaration_source": "product.h",
                            "definition_source": "helper.c",
                            "conflicts": [],
                            "confidence": "high",
                        },
                    }
                ],
                "external_objects": [
                    {
                        "symbol": "g_state",
                        "type_raw": "int",
                        "configured_mode": "auto",
                        "resolved_mode": "real",
                        "review_status": "resolved",
                        "declaration_header": "product.h",
                        "definition_source": "helper.c",
                        "definition_candidates": ["helper.c"],
                        "evidence": [],
                        "warnings": [],
                    }
                ],
                "warnings": [],
            }
            harness = generate_harness_skeleton(
                signature,
                global_access,
                call_report,
                design,
                output,
                overwrite=True,
                dependency_policy=policy,
            )
            (output / "reports" / "dependency_policy.json").write_text(__import__("json").dumps(policy), encoding="utf-8")
            source_digest = {
                "source": {"path": str(target)},
                "preprocessor": {"includes": [{"name": "product.h", "resolved_candidates": [str(header)]}]},
            }
            build_context = {"workspace_root": str(project), "include_dirs": [str(project)], "defines": [], "compiler_options": []}

            workspace_report, probe_report = generate_build_workspace(
                build_context,
                source_digest,
                harness.to_dict(),
                output,
                run_probe=True,
                dry_run=False,
                toolchain="verification",
            )

            self.assertEqual("succeeded", probe_report.status, (output / "logs" / "build.log").read_text(encoding="utf-8"))
            self.assertFalse((output / "generated" / "stubs" / "utr_extern_globals.c").exists())
            target_copy = (output / "extracted" / "target.c").read_text(encoding="cp932")
            self.assertIn("Utr_Dep_Helper(value)", target_copy)
            self.assertNotIn("int Helper(int value)\n{", (output / "generated" / "stubs" / "stub_Helper.c").read_text(encoding="cp932"))
            compile_sources = {unit.source_file.as_posix() for unit in workspace_report.compile_units}
            self.assertIn("generated/dependencies/utr_dependency_dispatch.c", compile_sources)
            self.assertTrue(any(source.endswith("helper.c") for source in compile_sources))

            command_result, summary, case_results, status = run_test_executable_cases(
                output,
                Path("bin/utr_probe.exe"),
                ["TC_Target_Real", "TC_Target_Stub"],
                timeout_seconds=10,
            )

            self.assertEqual(0, command_result.exit_code)
            self.assertEqual("passed", status)
            self.assertEqual(2, summary.passed)
            self.assertEqual({"TC_Target_Real": "passed", "TC_Target_Stub": "passed"}, {item.test_case_id: item.status for item in case_results})


if __name__ == "__main__":
    unittest.main()
