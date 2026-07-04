import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.log_parser import parse_build_log
from unit_test_runner.build_completion.build_completion_analyzer import analyze_build_errors, analyze_build_errors_from_workspace
from unit_test_runner.build_completion.completion_applier import apply_safe_completions
from unit_test_runner.build_completion.symbol_normalizer import normalize_link_symbol
from unit_test_runner.dossier import analyze_function_workflow


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


class BuildCompletionStep15Tests(unittest.TestCase):
    def prepare_workspace(self, temp_dir):
        out_dir = Path(temp_dir) / "Control_Update"
        analyze_function_workflow(
            VC6_FIXTURE_ROOT,
            VC6_FIXTURE_ROOT / "Product.dsw",
            "src/control.c",
            "Control_Update",
            "Win32 Debug",
            out_dir,
            "Control",
        )
        return out_dir

    def write_probe_report_with_errors(self, workspace):
        parsed = parse_build_log(
            """
control.c(4) : fatal error C1083: Cannot open include file: 'control.h': No such file or directory
LINK : fatal error LNK2001: unresolved external symbol _ReadSensor
error LNK2019: unresolved external symbol _LateDependency@8 referenced in function _Control_Update
fatal error C1010: unexpected end of file while looking for precompiled header directive
generated\\tests\\test_Control_Update.c(7) : error C2143: syntax error : missing ';' before 'type'
"""
        )
        payload = {
            "schema_version": "0.1",
            "source": {"path": "src/control.c"},
            "function": {"name": "Control_Update", "status": "failed"},
            "executed": True,
            "exit_code": 2,
            "diagnostics": [item.to_dict() for item in parsed.diagnostics],
            "missing_includes": [item.to_dict() for item in parsed.missing_includes],
            "unresolved_symbols": [item.to_dict() for item in parsed.unresolved_symbols],
            "pch_issues": [item.to_dict() for item in parsed.pch_issues],
            "vc6_compatibility_issues": [item.to_dict() for item in parsed.vc6_compatibility_issues],
            "log_files": ["logs/build.log"],
        }
        path = workspace / "reports" / "build_probe_report.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def test_analyzer_plans_include_stub_pch_and_compatibility_actions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(temp_dir)
            self.write_probe_report_with_errors(workspace)

            plan, iteration = analyze_build_errors_from_workspace(workspace, source_root=VC6_FIXTURE_ROOT)
            payload = plan.to_dict()

            self.assertEqual("planned", payload["function"]["status"])
            self.assertTrue(payload["include_completion_candidates"])
            self.assertTrue(any(item["include_name"] == "control.h" for item in payload["include_completion_candidates"]))
            stubs = {item["function_name_candidate"]: item for item in payload["stub_completion_candidates"]}
            self.assertIn("ReadSensor", stubs)
            self.assertIn("LateDependency", stubs)
            self.assertEqual("from_call_report", stubs["ReadSensor"]["return_type_strategy"])
            self.assertEqual("default_int", stubs["LateDependency"]["return_type_strategy"])
            self.assertTrue(payload["pch_completion_candidates"])
            self.assertTrue(payload["compatibility_feedback_items"])
            self.assertTrue(any(action["action_kind"] == "generate_stub" for action in payload["completion_actions"]))
            self.assertEqual("not_run", iteration.to_dict()["iterations"][0]["progress"])
            self.assertTrue((workspace / "reports" / "build_completion_plan.json").exists())
            self.assertIn("# Build Completion Plan", (workspace / "reports" / "build_completion_plan.md").read_text(encoding="utf-8"))

    def test_symbol_normalizer_strips_leading_underscore_and_stdcall_suffix(self):
        self.assertEqual("ReadSensor", normalize_link_symbol("_ReadSensor").function_name_candidate)
        normalized = normalize_link_symbol("_LateDependency@8")
        self.assertEqual("LateDependency", normalized.function_name_candidate)
        self.assertEqual("stdcall_decorated", normalized.decoration_kind)

    def test_safe_completion_applier_generates_cp932_stub_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(temp_dir)
            self.write_probe_report_with_errors(workspace)
            plan, _ = analyze_build_errors_from_workspace(workspace, source_root=VC6_FIXTURE_ROOT)

            applied = apply_safe_completions(workspace, plan)
            self.assertTrue(applied.generated_files)
            stub = workspace / "generated" / "stubs" / "stub_LateDependency.c"
            self.assertTrue(stub.exists())
            text = stub.read_bytes().decode("cp932")
            self.assertIn("int LateDependency(void)", text)
            self.assertNotIn("//", text)
            makefile = (workspace / "build" / "Makefile").read_text(encoding="cp932")
            self.assertIn("stub_LateDependency.obj", makefile)

            second = apply_safe_completions(workspace, plan)
            self.assertTrue(any(warning.code == "existing_file_not_overwritten" for warning in second.warnings))

    def test_cli_analyze_build_errors_complete_build_and_analyze_function_step15(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self.prepare_workspace(temp_dir)
            self.write_probe_report_with_errors(workspace)

            analyze = run_module("--json", "analyze-build-errors", "--workspace", str(workspace), "--source-root", str(VC6_FIXTURE_ROOT))
            self.assertEqual(0, analyze.returncode, analyze.stderr)
            analyze_payload = json.loads(analyze.stdout)
            self.assertEqual("completion_plan_generated", analyze_payload["status"])
            self.assertTrue(Path(analyze_payload["data"]["build_completion_plan"]["json"]).exists())

            complete = run_module("--json", "complete-build", "--workspace", str(workspace), "--apply-safe-completions", "--max-iterations", "1")
            self.assertEqual(0, complete.returncode, complete.stderr)
            complete_payload = json.loads(complete.stdout)
            self.assertEqual("completion_applied", complete_payload["status"])
            self.assertTrue((workspace / "reports" / "build_completion_iteration_report.json").exists())

            out_dir = Path(temp_dir) / "AnalyzeFunctionStep15"
            full = run_module(
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
                "--out",
                str(out_dir),
            )
            self.assertEqual(0, full.returncode, full.stderr)
            full_payload = json.loads(full.stdout)
            self.assertEqual("evidence_prepared", full_payload["status"])
            self.assertIn("Step 17", full_payload["message"])
            self.assertIn("build_completion", full_payload["data"])
            self.assertTrue((out_dir / "reports" / "build_completion_plan.json").exists())


if __name__ == "__main__":
    unittest.main()
