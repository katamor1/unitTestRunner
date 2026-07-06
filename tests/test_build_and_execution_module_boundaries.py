import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build_completion.compatibility_feedback import plan_compatibility_feedback
from unit_test_runner.build_completion.completion_applier import apply_safe_completions
from unit_test_runner.build_completion.completion_loop import build_iteration_report
from unit_test_runner.build_completion.completion_models import BuildCompletionPlan, BuildCompletionPolicy
from unit_test_runner.build_completion.diagnostic_classifier import summarize_diagnostics
from unit_test_runner.build_completion.include_completion import plan_include_completions
from unit_test_runner.build_completion.pch_completion import plan_pch_completions
from unit_test_runner.build_completion.stub_completion import plan_stub_completions
from unit_test_runner.execution.evidence_manifest import build_evidence_manifest
from unit_test_runner.execution.executable_resolver import resolve_executable
from unit_test_runner.execution.execution_models import TestExecutionPolicy, TestExecutionReport
from unit_test_runner.execution.execution_runner import build_execution_command
from unit_test_runner.execution.precondition_validator import validate_execution_preconditions
from unit_test_runner.execution.result_mapper import map_results_to_test_design
from unit_test_runner.execution import test_execution as test_execution_module
from unit_test_runner.execution.test_result_writer import write_test_execution_reports
from unit_test_runner.reports.build_completion_iteration_markdown import render_build_completion_iteration_markdown
from unit_test_runner.reports.build_completion_markdown import render_build_completion_markdown
from unit_test_runner.reports.evidence_package_markdown import render_evidence_package_markdown
from unit_test_runner.reports.test_execution_markdown import render_test_execution_markdown


class BuildCompletionModuleBoundaryTests(unittest.TestCase):
    def sample_build_probe_report(self):
        return {
            "schema_version": "0.1",
            "source": {"path": "src/control.c"},
            "function": {"name": "Control_Update", "status": "failed"},
            "diagnostics": [
                {"severity": "error", "code": "C1083", "message": "missing include"},
                {"severity": "warning", "code": "C4996", "message": "warning"},
            ],
            "missing_includes": [
                {
                    "include_name": "control.h",
                    "included_from": "src/control.c",
                    "diagnostic_raw": "fatal error C1083: Cannot open include file: 'control.h'",
                }
            ],
            "unresolved_symbols": [
                {
                    "symbol_name": "_ReadSensor",
                    "diagnostic_code": "LNK2001",
                    "diagnostic_raw": "unresolved external symbol _ReadSensor",
                }
            ],
            "pch_issues": [{"issue_kind": "unexpected_eof", "diagnostic_raw": "fatal error C1010"}],
            "vc6_compatibility_issues": [
                {
                    "issue_kind": "mixed_declaration",
                    "file": "generated/tests/test_Control_Update.c",
                    "line_number": 7,
                    "diagnostic_raw": "error C2143",
                }
            ],
        }

    def test_build_completion_planners_are_exposed_as_separate_modules(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            (source_root / "include").mkdir()
            (source_root / "include" / "control.h").write_text("/* fixture */\n", encoding="ascii")
            build_probe = self.sample_build_probe_report()
            call_report = {
                "calls": [
                    {
                        "call_id": "CALL_001",
                        "name": "ReadSensor",
                        "signature": {"return_type": "int"},
                    }
                ]
            }

            summary = summarize_diagnostics(build_probe)
            include_candidates, include_actions, include_warnings, include_manual = plan_include_completions(build_probe, source_root)
            stub_candidates, stub_actions, stub_warnings = plan_stub_completions(build_probe, call_report)
            pch_candidates, pch_actions, pch_manual = plan_pch_completions(build_probe)
            feedback, feedback_manual = plan_compatibility_feedback(build_probe)

            self.assertEqual(1, summary.missing_include_count)
            self.assertEqual(1, summary.unresolved_symbol_count)
            self.assertEqual(["control.h"], [candidate.include_name for candidate in include_candidates])
            self.assertEqual("ACT_INCLUDE_001", include_candidates[0].selected_action_id)
            self.assertFalse(include_warnings)
            self.assertFalse(include_manual)
            self.assertEqual(["add_include_dir"], [action.action_kind for action in include_actions])
            self.assertEqual("ReadSensor", stub_candidates[0].function_name_candidate)
            self.assertEqual("from_call_report", stub_candidates[0].return_type_strategy)
            self.assertEqual(["generate_stub"], [action.action_kind for action in stub_actions])
            self.assertFalse(stub_warnings)
            self.assertEqual("adjust_pch_option", pch_actions[0].action_kind)
            self.assertTrue(pch_manual)
            self.assertEqual("harness_skeleton_generation", feedback[0].feedback_target_item)
            self.assertTrue(feedback_manual)

    def test_stub_completion_applier_uses_call_argument_count_for_generated_signature(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "build").mkdir()
            (workspace / "build" / "Makefile").write_text("OBJS=\n", encoding="cp932")
            build_probe = self.sample_build_probe_report()
            call_report = {
                "calls": [
                    {
                        "call_id": "CALL_001",
                        "name": "ReadSensor",
                        "arguments": [
                            {"index": 0, "raw": "channel"},
                            {"index": 1, "raw": "gain"},
                        ],
                    }
                ]
            }

            candidates, actions, warnings = plan_stub_completions(build_probe, call_report)
            plan = BuildCompletionPlan(
                source_path=Path("src/control.c"),
                function_name="Control_Update",
                status="planned",
                policy=BuildCompletionPolicy(),
                completion_actions=actions,
                stub_completion_candidates=candidates,
            )
            result = apply_safe_completions(workspace, plan)

            self.assertFalse(warnings)
            self.assertEqual(["ACT_STUB_001"], result.applied_actions)
            header = (workspace / "generated" / "stubs" / "stub_ReadSensor.h").read_text(encoding="cp932")
            source = (workspace / "generated" / "stubs" / "stub_ReadSensor.c").read_text(encoding="cp932")
            self.assertIn("int ReadSensor(int arg0, int arg1);", header)
            self.assertIn("int ReadSensor(int arg0, int arg1)", source)
            self.assertNotIn("int ReadSensor(void)", source)

    def test_completion_loop_builds_iteration_report_from_plan(self):
        build_probe = self.sample_build_probe_report()
        plan = BuildCompletionPlan(
            source_path=Path("src/control.c"),
            function_name="Control_Update",
            status="planned",
            policy=BuildCompletionPolicy(),
        )

        report = build_iteration_report(plan, build_probe)

        self.assertEqual("planned", report.status)
        self.assertEqual("not_run", report.iterations[0].progress)
        self.assertEqual(1, report.final_diagnostics_summary.missing_include_count)
        self.assertIn("# ビルド補完計画", render_build_completion_markdown(plan))
        self.assertIn("# ビルド補完イテレーションレポート", render_build_completion_iteration_markdown(report))


class ExecutionEvidenceModuleBoundaryTests(unittest.TestCase):
    def sample_test_case_design(self):
        return {
            "test_cases": [
                {
                    "test_case_id": "TC_Control_Update_001",
                    "review_status": "review_required",
                    "coverage_links": [{"coverage_id": "BR_001"}],
                    "expected_observations": [{"expected_expression": "TBD_EXPECTED_RETURN_INT"}],
                }
            ]
        }

    def test_execution_evidence_modules_are_exposed_and_composable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "bin").mkdir()
            (workspace / "reports").mkdir()
            (workspace / "logs").mkdir()
            exe = workspace / "bin" / "utr_probe.exe"
            exe.write_bytes(b"fake exe")
            build_probe = {"function": {"status": "succeeded"}}
            executable = resolve_executable(workspace, None, build_probe)

            command = build_execution_command(workspace, executable, timeout_seconds=5, dry_run=True)
            status, warnings, review_items = validate_execution_preconditions(build_probe, executable, TestExecutionPolicy(run_tests=True, dry_run=False))
            case_results, mapped_review_items = map_results_to_test_design(None, self.sample_test_case_design())

            self.assertTrue(executable.exists)
            self.assertEqual("bin/utr_probe.exe", executable.path.as_posix())
            self.assertTrue(command.dry_run)
            self.assertEqual("ready", status)
            self.assertFalse(warnings)
            self.assertFalse(review_items)
            self.assertEqual("inconclusive", case_results[0].status)
            self.assertTrue(case_results[0].review_required)
            self.assertTrue(mapped_review_items)

    def test_test_execution_entrypoint_does_not_keep_legacy_private_helpers(self):
        for name in [
            "_resolve_executable",
            "_run_executable",
            "_write_test_reports",
            "_build_manifest",
            "_write_manifest_and_package",
            "_environment_summary",
        ]:
            with self.subTest(name=name):
                self.assertFalse(hasattr(test_execution_module, name))

    def test_execution_evidence_writers_and_manifest_are_exposed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "reports").mkdir()
            (workspace / "logs").mkdir()
            (workspace / "logs" / "test_execution.log").write_text("DRY RUN\n", encoding="utf-8")
            (workspace / "reports" / "harness_skeleton_report.json").write_text(
                json.dumps({"generated_files": []}), encoding="utf-8"
            )
            report = TestExecutionReport(
                source_path=Path("src/control.c"),
                function_name="Control_Update",
                status="not_run",
                executed=False,
                executable=None,
                command=None,
                command_result=None,
                parsed_result=None,
                case_results=[],
                unresolved_review_items=[],
                evidence_files=[],
                warnings=[],
                policy=TestExecutionPolicy(),
            )

            write_test_execution_reports(workspace, report)
            manifest = build_evidence_manifest(
                workspace,
                report,
                {"function": {"status": "succeeded"}},
                {"copied_files": []},
                None,
            )

            self.assertTrue((workspace / "reports" / "test_execution_report.json").exists())
            self.assertEqual("Control_Update", manifest.function_name)
            self.assertEqual("succeeded", manifest.summary.build_probe_status)
            self.assertIn("# テスト実行レポート", render_test_execution_markdown(report))
            self.assertIn("# 関数単体テストエビデンスパッケージ", render_evidence_package_markdown(manifest, report))


if __name__ == "__main__":
    unittest.main()
