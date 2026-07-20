import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dependency_policy.analyzer import analyze_dependency_policy


class DependencyPolicyAnalyzerTests(unittest.TestCase):
    def _project(self, root: Path):
        include = root / "include"
        src = root / "src"
        include.mkdir(parents=True)
        src.mkdir(parents=True)
        (include / "deps.h").write_text(
            "extern int g_state;\n"
            "extern int g_missing;\n"
            "int Internal_Update(int *value);\n"
            "int External_Read(int value);\n",
            encoding="utf-8",
        )
        target = src / "target.c"
        target.write_text(
            '#include "deps.h"\n'
            "int Target(int value)\n{\n"
            "    int first;\n"
            "    first = Internal_Update(&g_state);\n"
            "    return first + External_Read(value);\n"
            "}\n",
            encoding="utf-8",
        )
        internal = src / "internal.c"
        internal.write_text(
            '#include "deps.h"\n'
            "int g_state;\n"
            "int Internal_Update(int *value)\n{\n"
            "    g_state += *value;\n"
            "    return g_state;\n"
            "}\n",
            encoding="utf-8",
        )
        return target, internal, include / "deps.h"

    def test_auto_resolves_state_coupled_internal_real_and_boundary_stub(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target, internal, header = self._project(root)
            call_report = {
                "calls": [
                    {
                        "call_id": "CALL_001",
                        "name": "Internal_Update",
                        "target_kind": "external_function",
                        "name_position": {"line": 5, "column": 13, "offset": 0},
                        "call_range": {"start": {"line": 5, "column": 13}, "end": {"line": 5, "column": 42}},
                        "arguments": [{"raw": "&g_state", "argument_kind": "address_of_global", "passing_mode_hint": "by_address"}],
                        "return_usage": {"usage_kind": "assigned"},
                    },
                    {
                        "call_id": "CALL_002",
                        "name": "External_Read",
                        "target_kind": "external_function",
                        "name_position": {"line": 6, "column": 20, "offset": 0},
                        "call_range": {"start": {"line": 6, "column": 20}, "end": {"line": 6, "column": 40}},
                        "arguments": [{"raw": "value", "argument_kind": "parameter", "passing_mode_hint": "by_value"}],
                        "return_usage": {"usage_kind": "returned"},
                    },
                ],
                "stub_candidates": [
                    {"name": "External_Read", "tags": ["external_dependency", "return_value_used"]}
                ],
            }
            global_access = {
                "file_scope_declarations": [
                    {"name": "g_state", "type_raw": "int", "storage_class": "extern", "raw": "extern int g_state;"},
                    {"name": "g_missing", "type_raw": "int", "storage_class": "extern", "raw": "extern int g_missing;"},
                ],
                "global_accesses": [{"name": "g_state", "access_kind": "read_write"}],
            }
            source_digest = {"preprocessor": {"includes": [{"resolved_candidates": [str(header)]}]}}

            report = analyze_dependency_policy(
                workspace_root=root,
                target_source=target,
                source_digest=source_digest,
                function_signature={"function": {"name": "Target"}},
                global_access=global_access,
                call_report=call_report,
                project_sources=[target, internal],
            )

        modes = {item.callee: item.resolved_mode for item in report.dependencies}
        self.assertEqual("real", modes["Internal_Update"])
        self.assertEqual("stub", modes["External_Read"])
        internal_policy = next(item for item in report.dependencies if item.callee == "Internal_Update")
        self.assertIn("g_state", internal_policy.shared_globals)
        self.assertEqual(Path("src/internal.c"), internal_policy.implementation_source)
        objects = {item.symbol: item for item in report.external_objects}
        self.assertEqual("real", objects["g_state"].resolved_mode)
        self.assertEqual(Path("src/internal.c"), objects["g_state"].definition_source)
        self.assertEqual("fixture", objects["g_missing"].resolved_mode)

    def test_auto_uses_reviewed_stub_when_real_source_has_external_link_dependencies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            include = root / "include"
            src = root / "src"
            include.mkdir(parents=True)
            src.mkdir(parents=True)
            header = include / "deps.h"
            header.write_text(
                "extern int g_state;\n"
                "int Helper(int value);\n"
                "int Next(int value);\n",
                encoding="utf-8",
            )
            target = src / "target.c"
            target.write_text(
                '#include "deps.h"\n'
                "int g_state;\n"
                "int Target(int value)\n"
                "{\n"
                "    g_state += value;\n"
                "    return Helper(value);\n"
                "}\n",
                encoding="utf-8",
            )
            helper = src / "helper.c"
            helper.write_text(
                '#include "deps.h"\n'
                "int Helper(int value)\n"
                "{\n"
                "    g_state += value;\n"
                "    return Next(value);\n"
                "}\n",
                encoding="utf-8",
            )
            next_source = src / "next.c"
            next_source.write_text(
                '#include "deps.h"\n'
                "int Next(int value) { return value + 1; }\n",
                encoding="utf-8",
            )

            analysis_args = {
                "workspace_root": root,
                "target_source": target,
                "source_digest": {
                    "preprocessor": {"includes": [{"resolved_candidates": [str(header)]}]}
                },
                "function_signature": {"function": {"name": "Target"}},
                "global_access": {
                    "file_scope_declarations": [],
                    "global_accesses": [{"name": "g_state", "access_kind": "read_write"}],
                },
                "call_report": {
                    "calls": [
                        {
                            "call_id": "CALL_001",
                            "name": "Helper",
                            "target_kind": "external_function",
                            "name_position": {"line": 6, "column": 12},
                            "call_range": {
                                "start": {"line": 6, "column": 12},
                                "end": {"line": 6, "column": 25},
                            },
                            "arguments": [
                                {
                                    "raw": "value",
                                    "argument_kind": "parameter",
                                    "passing_mode_hint": "by_value",
                                }
                            ],
                            "return_usage": {"usage_kind": "returned"},
                        }
                    ],
                    "stub_candidates": [],
                },
                "project_sources": [target, helper, next_source],
                "project_headers": [header],
            }
            report = analyze_dependency_policy(**analysis_args)
            explicit_real = analyze_dependency_policy(
                **analysis_args,
                existing_policy={
                    "dependencies": [{"callee": "Helper", "configured_mode": "real"}]
                },
            )

        dependency = report.dependencies[0]
        self.assertEqual("stub", dependency.resolved_mode)
        self.assertEqual("review_required", dependency.review_status)
        self.assertEqual("review_required", report.status)
        self.assertTrue(
            any(item.kind == "implementation_transitive_dependency" for item in dependency.evidence)
        )
        self.assertTrue(any("Next" in warning for warning in dependency.warnings))
        explicit_dependency = explicit_real.dependencies[0]
        self.assertEqual("real", explicit_dependency.resolved_mode)
        self.assertEqual("review_required", explicit_dependency.review_status)
        self.assertTrue(any("Next" in warning for warning in explicit_dependency.warnings))

    def test_unsupported_indirect_and_conflicting_external_definition_require_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target, internal, header = self._project(root)
            duplicate = root / "src" / "duplicate.c"
            duplicate.write_text("int g_state;\n", encoding="utf-8")
            report = analyze_dependency_policy(
                workspace_root=root,
                target_source=target,
                source_digest={"preprocessor": {"includes": [{"resolved_candidates": [str(header)]}]}},
                function_signature={"function": {"name": "Target"}},
                global_access={
                    "file_scope_declarations": [{"name": "g_state", "type_raw": "int", "storage_class": "extern", "raw": "extern int g_state;"}],
                    "global_accesses": [{"name": "g_state"}],
                },
                call_report={
                    "calls": [
                        {
                            "call_id": "CALL_001",
                            "name": "callback",
                            "target_kind": "function_pointer",
                            "name_position": {"line": 5, "column": 5, "offset": 0},
                            "call_range": {"start": {"line": 5, "column": 5}, "end": {"line": 5, "column": 20}},
                            "arguments": [],
                            "return_usage": {"usage_kind": "ignored"},
                        }
                    ],
                    "stub_candidates": [],
                },
                project_sources=[target, internal, duplicate],
            )

        self.assertEqual("review_required", report.dependencies[0].resolved_mode)
        self.assertEqual([], report.dependencies[0].rewrite_sites)
        self.assertEqual("review_required", report.external_objects[0].resolved_mode)
        self.assertEqual("review_required", report.status)

    def test_existing_explicit_stub_mode_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target, internal, header = self._project(root)
            report = analyze_dependency_policy(
                workspace_root=root,
                target_source=target,
                source_digest={"preprocessor": {"includes": [{"resolved_candidates": [str(header)]}]}},
                function_signature={"function": {"name": "Target"}},
                global_access={"file_scope_declarations": [], "global_accesses": []},
                call_report={
                    "calls": [
                        {
                            "call_id": "CALL_001",
                            "name": "Internal_Update",
                            "target_kind": "external_function",
                            "name_position": {"line": 5, "column": 13, "offset": 0},
                            "call_range": {"start": {"line": 5, "column": 13}, "end": {"line": 5, "column": 42}},
                            "arguments": [{"raw": "&g_state", "argument_kind": "address_of_global", "passing_mode_hint": "by_address"}],
                            "return_usage": {"usage_kind": "assigned"},
                        }
                    ],
                    "stub_candidates": [],
                },
                project_sources=[target, internal],
                existing_policy={"dependencies": [{"callee": "Internal_Update", "configured_mode": "stub"}]},
            )

        self.assertEqual("stub", report.dependencies[0].configured_mode)
        self.assertEqual("stub", report.dependencies[0].resolved_mode)

    def test_mixed_direct_and_indirect_uses_for_same_symbol_require_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target, internal, header = self._project(root)
            report = analyze_dependency_policy(
                workspace_root=root,
                target_source=target,
                source_digest={"preprocessor": {"includes": [{"resolved_candidates": [str(header)]}]}},
                function_signature={"function": {"name": "Target"}},
                global_access={"file_scope_declarations": [], "global_accesses": []},
                call_report={
                    "calls": [
                        {
                            "call_id": "CALL_DIRECT",
                            "name": "Internal_Update",
                            "target_kind": "external_function",
                            "name_position": {"line": 5, "column": 13},
                            "arguments": [{"raw": "&g_state", "argument_kind": "address_of_global", "passing_mode_hint": "by_address"}],
                            "return_usage": {"usage_kind": "assigned"},
                        },
                        {
                            "call_id": "CALL_INDIRECT",
                            "name": "Internal_Update",
                            "target_kind": "function_pointer",
                            "name_position": {"line": 6, "column": 5},
                            "arguments": [],
                            "return_usage": {"usage_kind": "ignored"},
                        },
                    ],
                    "stub_candidates": [],
                },
                project_sources=[target, internal],
            )

        self.assertEqual("review_required", report.dependencies[0].resolved_mode)
        self.assertEqual([], report.dependencies[0].rewrite_sites)
        self.assertTrue(any("mixed" in warning.lower() for warning in report.dependencies[0].warnings))

    def test_member_call_is_review_required_and_not_rewritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            include = root / "include"
            src = root / "src"
            include.mkdir(parents=True)
            src.mkdir(parents=True)
            header = include / "ops.h"
            header.write_text(
                "typedef struct OpsTag { int (*handler)(int); } Ops;\n",
                encoding="utf-8",
            )
            target = src / "target.c"
            target.write_text(
                '#include "ops.h"\n'
                "int Target(Ops *ops, int value)\n"
                "{\n"
                "    return ops->handler(value);\n"
                "}\n",
                encoding="utf-8",
            )
            report = analyze_dependency_policy(
                workspace_root=root,
                target_source=target,
                source_digest={"preprocessor": {"includes": [{"resolved_candidates": [str(header)]}]}},
                function_signature={"function": {"name": "Target"}},
                global_access={"file_scope_declarations": [], "global_accesses": []},
                call_report={
                    "calls": [
                        {
                            "call_id": "CALL_MEMBER",
                            "name": "handler",
                            "target_kind": "external_function",
                            "name_position": {"line": 4, "column": 17},
                            "arguments": [{"raw": "value", "argument_kind": "parameter", "passing_mode_hint": "by_value"}],
                            "return_usage": {"usage_kind": "returned"},
                        }
                    ],
                    "stub_candidates": [],
                },
                project_sources=[target],
            )

        self.assertEqual("member_call", report.dependencies[0].target_kind)
        self.assertEqual("review_required", report.dependencies[0].resolved_mode)
        self.assertEqual([], report.dependencies[0].rewrite_sites)

    def test_function_address_use_makes_direct_dependency_review_required(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            include = root / "include"
            src = root / "src"
            include.mkdir(parents=True)
            src.mkdir(parents=True)
            header = include / "helper.h"
            header.write_text("int Helper(int value);\n", encoding="utf-8")
            target = src / "target.c"
            target.write_text(
                '#include "helper.h"\n'
                "int Target(int value)\n"
                "{\n"
                "    int (*selected)(int);\n"
                "    selected = Helper;\n"
                "    return Helper(value);\n"
                "}\n",
                encoding="utf-8",
            )
            helper = src / "helper.c"
            helper.write_text('#include "helper.h"\nint Helper(int value) { return value + 1; }\n', encoding="utf-8")
            report = analyze_dependency_policy(
                workspace_root=root,
                target_source=target,
                source_digest={"preprocessor": {"includes": [{"resolved_candidates": [str(header)]}]}},
                function_signature={"function": {"name": "Target"}},
                global_access={"file_scope_declarations": [], "global_accesses": []},
                call_report={
                    "calls": [
                        {
                            "call_id": "CALL_DIRECT",
                            "name": "Helper",
                            "target_kind": "external_function",
                            "name_position": {"line": 6, "column": 12},
                            "arguments": [{"raw": "value", "argument_kind": "parameter", "passing_mode_hint": "by_value"}],
                            "return_usage": {"usage_kind": "returned"},
                        }
                    ],
                    "stub_candidates": [],
                },
                project_sources=[target, helper],
            )

        self.assertEqual("function_address_use", report.dependencies[0].target_kind)
        self.assertEqual("review_required", report.dependencies[0].resolved_mode)
        self.assertEqual([], report.dependencies[0].rewrite_sites)
        self.assertTrue(any("address" in warning.lower() for warning in report.dependencies[0].warnings))


if __name__ == "__main__":
    unittest.main()
