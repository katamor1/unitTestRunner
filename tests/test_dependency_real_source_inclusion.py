import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build import generate_build_workspace
from unit_test_runner.harness import generate_harness_skeleton


class DependencyRealSourceInclusionTests(unittest.TestCase):
    def test_build_workspace_rewrites_target_and_includes_real_dependency_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            output = root / "out"
            target = project / "target.c"
            helper = project / "helper.c"
            header = project / "deps.h"
            project.mkdir()
            target.write_text('#include "deps.h"\nint Target(int value) { return Helper(value); }\n', encoding="ascii")
            helper.write_text('#include "deps.h"\nint Helper(int value) { return value + 1; }\n', encoding="ascii")
            header.write_text("int Helper(int value);\n", encoding="ascii")

            signature = {
                "source": {"path": str(target), "sha256": "abc"},
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
                "stub_candidates": [],
            }
            test_design = {
                "source": {"path": str(target), "sha256": "abc"},
                "function": {"name": "Target", "status": "generated"},
                "test_cases": [],
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
                        "rewrite_sites": [{"call_id": "CALL_001", "start": {"line": 2, "column": 32}, "end": {"line": 2, "column": 38}}],
                        "signature": {
                            "resolution": "exact",
                            "return_type_raw": "int",
                            "calling_convention": None,
                            "parameters": [{"index": 0, "name": "value", "type_raw": "int", "pointer_level": 0, "qualifiers": [], "is_variadic": False}],
                            "prototype": "int Helper(int value)",
                            "declaration_source": "deps.h",
                            "definition_source": "helper.c",
                            "conflicts": [],
                            "confidence": "high",
                        },
                    }
                ],
                "external_objects": [],
                "warnings": [],
            }
            harness = generate_harness_skeleton(
                signature,
                {"global_accesses": [], "file_scope_declarations": []},
                call_report,
                test_design,
                output,
                overwrite=True,
                dependency_policy=policy,
            )
            (output / "reports").mkdir(exist_ok=True)
            (output / "reports" / "dependency_policy.json").write_text(json.dumps(policy), encoding="utf-8")
            source_digest = {
                "source": {"path": str(target)},
                "preprocessor": {"includes": [{"name": "deps.h", "resolved_candidates": [str(header)]}]},
            }
            build_context = {"workspace_root": str(project), "include_dirs": [str(project)], "defines": [], "compiler_options": []}

            report, _probe = generate_build_workspace(
                build_context,
                source_digest,
                harness.to_dict(),
                output,
                run_probe=False,
                dry_run=True,
            )

            extracted_target = output / "extracted" / "target.c"
            self.assertIn("Utr_Dep_Helper(value)", extracted_target.read_text(encoding="cp932"))
            self.assertIn("Helper(value)", target.read_text(encoding="ascii"))
            dependency_files = [item for item in report.copied_files if item.file_kind == "dependency_source"]
            self.assertEqual(1, len(dependency_files))
            self.assertEqual(helper.resolve(), dependency_files[0].source_path)
            self.assertTrue((output / dependency_files[0].workspace_path).exists())
            compile_sources = {unit.source_file.as_posix() for unit in report.compile_units}
            self.assertIn(dependency_files[0].workspace_path.as_posix(), compile_sources)
            self.assertIn("generated/dependencies/utr_dependency_dispatch.c", compile_sources)
            self.assertFalse((output / "extracted" / "deps.h").exists())
            self.assertFalse(any(item.code == "dependency_call_rewrite_skipped" for item in report.diagnostics))

    def test_mismatched_rewrite_site_blocks_build_without_modifying_product_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            output = root / "out"
            project.mkdir()
            target = project / "target.c"
            helper = project / "helper.c"
            header = project / "deps.h"
            target.write_text(
                '#include "deps.h"\nint Target(int value) { return Helper(value); }\n',
                encoding="ascii",
            )
            helper.write_text(
                '#include "deps.h"\nint Helper(int value) { return value + 1; }\n',
                encoding="ascii",
            )
            header.write_text("int Helper(int value);\n", encoding="ascii")
            original_bytes = {path: path.read_bytes() for path in (target, helper, header)}
            signature = {
                "source": {"path": str(target), "sha256": "abc"},
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
                            "type": {
                                "raw": "int",
                                "base_type": "int",
                                "pointer_level": 0,
                                "is_array": False,
                            },
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
                        "arguments": [],
                        "return_usage": {"usage_kind": "returned"},
                    }
                ],
                "stub_candidates": [],
            }
            test_design = {
                "source": {"path": str(target), "sha256": "abc"},
                "function": {"name": "Target", "status": "generated"},
                "test_cases": [],
                "additional_case_candidates": [],
                "coverage_summary": {
                    "total_coverage_items": 0,
                    "covered_by_design_count": 0,
                    "uncovered_coverage_ids": [],
                    "coverage_to_test_cases": {},
                },
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
                        "configured_mode": "stub",
                        "resolved_mode": "stub",
                        "review_status": "resolved",
                        "implementation_source": "helper.c",
                        "related_call_ids": ["CALL_001"],
                        "rewrite_sites": [
                            {
                                "call_id": "CALL_001",
                                "start": {"line": 2, "column": 31},
                                "end": {"line": 2, "column": 37},
                            }
                        ],
                        "signature": {
                            "resolution": "exact",
                            "return_type_raw": "int",
                            "calling_convention": None,
                            "parameters": [
                                {
                                    "index": 0,
                                    "name": "value",
                                    "type_raw": "int",
                                    "pointer_level": 0,
                                    "qualifiers": [],
                                    "is_variadic": False,
                                }
                            ],
                            "prototype": "int Helper(int value)",
                            "declaration_source": "deps.h",
                            "definition_source": "helper.c",
                            "conflicts": [],
                            "confidence": "high",
                        },
                    }
                ],
                "external_objects": [],
                "warnings": [],
            }
            harness = generate_harness_skeleton(
                signature,
                {"global_accesses": [], "file_scope_declarations": []},
                call_report,
                test_design,
                output,
                overwrite=True,
                dependency_policy=policy,
            )
            source_digest = {
                "source": {"path": str(target)},
                "preprocessor": {
                    "includes": [{"name": "deps.h", "resolved_candidates": [str(header)]}]
                },
            }
            build_context = {
                "workspace_root": str(project),
                "include_dirs": [str(project)],
                "defines": [],
                "compiler_options": [],
            }

            report, probe = generate_build_workspace(
                build_context,
                source_digest,
                harness.to_dict(),
                output,
                run_probe=True,
                dry_run=False,
                toolchain="verification",
            )

            self.assertEqual("blocked", report.status)
            self.assertEqual("blocked", probe.status)
            self.assertFalse(probe.executed)
            self.assertIsNone(probe.exit_code)
            self.assertTrue(
                any(
                    item.code == "dependency_call_rewrite_failed"
                    and item.severity == "error"
                    and "CALL_001" in item.message
                    for item in report.diagnostics
                )
            )
            self.assertNotIn(
                "Utr_Dep_Helper",
                (output / "extracted" / "target.c").read_text(encoding="cp932"),
            )
            self.assertFalse((output / "bin" / "utr_probe.exe").exists())
            self.assertEqual(original_bytes, {path: path.read_bytes() for path in original_bytes})


if __name__ == "__main__":
    unittest.main()
