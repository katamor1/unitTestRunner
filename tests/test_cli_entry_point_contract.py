import json
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"
SRC_ROOT = REPO_ROOT / "src"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.build_models import BuildProbeReport, BuildWorkspaceReport
from unit_test_runner.cli import exit_codes
from unit_test_runner.cli.commands import _build_probe_result, handle_build_probe
from unit_test_runner.cli.result import CLIResult


def run_module(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class CliEntryPointContractTests(unittest.TestCase):
    def test_global_help_version_and_subcommand_help_exit_zero(self):
        commands = [
            ("--help",),
            ("--version",),
            ("discover-projects", "--help"),
            ("map-source", "--help"),
            ("analyze-function", "--help"),
            ("generate-harness-skeleton", "--help"),
            ("build-probe", "--help"),
            ("analyze-build-errors", "--help"),
            ("complete-build", "--help"),
            ("run-tests", "--help"),
            ("prepare-evidence", "--help"),
            ("generate-test-design", "--help"),
        ]

        for command in commands:
            with self.subTest(command=command):
                completed = run_module(*command)
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertTrue(completed.stdout)

    def test_doctor_supports_human_and_json_modes(self):
        human = run_module("doctor")
        self.assertEqual(0, human.returncode, human.stderr)
        self.assertIn("Command: doctor", human.stdout)
        self.assertIn("Status: ok", human.stdout)

        machine = run_module("--json", "doctor")
        self.assertEqual(0, machine.returncode, machine.stderr)
        self.assertEqual("", machine.stderr)
        payload = json.loads(machine.stdout)
        self.assertEqual("ok", payload["status"])
        self.assertEqual("doctor", payload["command"])
        self.assertEqual(0, payload["exit_code"])
        self.assertTrue(payload["data"]["python"]["supported"])

    def test_missing_required_argument_exits_one(self):
        completed = run_module("analyze-function")

        self.assertEqual(1, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertIn("required", completed.stderr)

    def test_missing_required_argument_in_json_mode_writes_json_stdout_only(self):
        completed = run_module("--json", "analyze-function")

        self.assertEqual(1, completed.returncode)
        self.assertEqual("", completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("error", payload["status"])
        self.assertEqual(1, payload["exit_code"])
        self.assertEqual("analyze-function", payload["command"])
        self.assertIn("required", payload["errors"][0])

    def test_missing_file_exits_two_and_json_stdout_is_machine_parseable(self):
        completed = run_module(
            "--json",
            "analyze-function",
            "--workspace",
            str(FIXTURE_ROOT),
            "--dsw",
            str(FIXTURE_ROOT / "missing.dsw"),
            "--source",
            "src/control.c",
            "--function",
            "Control_Update",
            "--configuration",
            "Win32 Debug",
            "--out",
            str(Path(tempfile.gettempdir()) / "unitTestRunner-missing"),
        )

        self.assertEqual(2, completed.returncode)
        self.assertEqual("", completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("error", payload["status"])
        self.assertEqual(2, payload["exit_code"])
        self.assertIn("missing.dsw", payload["errors"][0])

    def test_analyze_function_expected_lookup_failures_are_not_internal_errors(self):
        completed = run_module(
            "--json",
            "analyze-function",
            "--workspace",
            str(FIXTURE_ROOT),
            "--dsw",
            str(FIXTURE_ROOT / "Product.dsw"),
            "--source",
            "src/control.c",
            "--function",
            "MissingFunction",
            "--configuration",
            "Win32 Debug",
            "--project",
            "Control",
            "--out",
            str(Path(tempfile.gettempdir()) / "unitTestRunner-missing-function"),
        )

        self.assertEqual(2, completed.returncode)
        self.assertEqual("", completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("error", payload["status"])
        self.assertEqual(2, payload["exit_code"])
        self.assertIn("Function not found", payload["errors"][0])
        self.assertNotEqual("internal_error", payload["status"])

    def test_analyze_function_accepts_absolute_source_inside_workspace(self):
        source = FIXTURE_ROOT / "src" / "control.c"
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "absolute-source"

            completed = run_module(
                "--json",
                "analyze-function",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
                "--source",
                str(source),
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--out",
                str(out_dir),
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("", completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual("analysis_completed", payload["status"])
            self.assertEqual("src/control.c", payload["data"]["target"]["source"])
            request = json.loads((out_dir / "input" / "request.json").read_text(encoding="utf-8"))
            self.assertEqual("src/control.c", request["source"])
            self.assertTrue((out_dir / "extracted" / "src" / "control.c").exists())
            self.assertFalse((out_dir / "extracted" / str(source).replace(":", "")).exists())

        self.assertEqual(before, source.read_bytes())

    def test_analyze_function_default_phase_stops_before_harness_build_and_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "default-phase"

            completed = run_module(
                "--json",
                "analyze-function",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
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

            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual("analysis_completed", payload["status"])
            self.assertEqual("design", payload["data"]["phase"])
            self.assertIn("test_case_design", payload["data"])
            self.assertNotIn("harness_skeleton", payload["data"])
            self.assertFalse((out_dir / "reports" / "harness_skeleton_report.json").exists())
            self.assertFalse((out_dir / "reports" / "build_workspace_report.json").exists())
            self.assertFalse((out_dir / "reports" / "test_execution_report.json").exists())

    def test_analyze_function_execution_phase_runs_downstream_steps(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "execution-phase"

            completed = run_module(
                "--json",
                "analyze-function",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
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
                "--phase",
                "execution",
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual("evidence_prepared", payload["status"])
            self.assertEqual("execution", payload["data"]["phase"])
            self.assertIn("harness_skeleton", payload["data"])
            self.assertIn("build_workspace", payload["data"])
            self.assertIn("test_execution", payload["data"])
            self.assertTrue((out_dir / "reports" / "test_execution_report.json").exists())

    def test_analyze_function_rejects_absolute_source_outside_workspace_as_input_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            outside_source = Path(temp_dir) / "outside.c"
            outside_source.write_text("int Control_Update(void) { return 0; }\n", encoding="utf-8")

            completed = run_module(
                "--json",
                "analyze-function",
                "--workspace",
                str(FIXTURE_ROOT),
                "--dsw",
                str(FIXTURE_ROOT / "Product.dsw"),
                "--source",
                str(outside_source),
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--out",
                str(Path(temp_dir) / "outside-output"),
            )

            self.assertEqual(1, completed.returncode)
            self.assertEqual("", completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual("error", payload["status"])
            self.assertEqual(1, payload["exit_code"])
            self.assertIn("outside workspace", payload["errors"][0])
            self.assertNotEqual("internal_error", payload["status"])

    def test_log_file_is_created_without_polluting_json_stdout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "runner.log"

            completed = run_module("--json", "--log-file", str(log_file), "doctor")

            self.assertEqual(0, completed.returncode, completed.stderr)
            json.loads(completed.stdout)
            self.assertEqual("", completed.stderr)
            self.assertTrue(log_file.exists())
            self.assertIn("doctor", log_file.read_text(encoding="utf-8"))

    def test_not_implemented_result_contract_is_fixed(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        script = (
            "from unit_test_runner.cli.result import not_implemented; "
            "r = not_implemented('future-command', 'future_cli_contract'); "
            "print(r.to_json())"
        )

        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("not_implemented", payload["status"])
        self.assertEqual(20, payload["exit_code"])
        self.assertEqual("future-command", payload["command"])
        self.assertEqual("future_cli_contract", payload["data"]["planned_item"])

    def test_build_probe_failure_result_uses_nonzero_exit_code(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            workspace_report = BuildWorkspaceReport(
                source_path=workspace / "source.c",
                function_name="Target",
                status="generated",
                output_root=workspace,
                copied_files=[],
                referenced_files=[],
                generated_build_files=[],
                compile_units=[],
                link_units=[],
                include_dirs=[],
                defines=[],
                compiler_options=[],
                build_commands=[],
                diagnostics=[],
            )
            probe_report = BuildProbeReport(
                source_path=workspace / "source.c",
                function_name="Target",
                status="failed",
                executed=True,
                exit_code=2,
                commands=[],
                diagnostics=[],
                missing_includes=[],
                unresolved_symbols=[],
                pch_issues=[],
                vc6_compatibility_issues=[],
                log_files=[],
            )

            result = _build_probe_result("build-probe", workspace, workspace_report, probe_report)

        self.assertTrue(hasattr(exit_codes, "EXIT_BUILD_PROBE_FAILED"))
        self.assertEqual(exit_codes.EXIT_BUILD_PROBE_FAILED, result.exit_code)
        self.assertEqual("build_probe_failed", result.status)
        self.assertIn("build_probe", result.data)

    def test_legacy_dossier_build_probe_failure_uses_nonzero_exit_code(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dossier = Path(temp_dir) / "function_dossier.json"
            dossier.write_text("{}", encoding="utf-8")
            args = Namespace(
                command="build-probe",
                workspace=None,
                build_context=None,
                source_digest=None,
                harness_report=None,
                out=None,
                dossier=str(dossier),
                vc6_bin=None,
                vcvars=None,
                dry_run=False,
                run=True,
                timeout=120,
                overwrite=False,
            )

            with mock.patch("unit_test_runner.cli.commands.build_probe", return_value={"dry_run": False, "returncode": 2}):
                result = handle_build_probe(args)

        self.assertEqual("build_probe_failed", result.status)
        self.assertEqual(exit_codes.EXIT_BUILD_PROBE_FAILED, result.exit_code)

    def test_cli_result_projects_report_paths_to_top_level_contract(self):
        result = CLIResult(
            status="ok",
            exit_code=0,
            command="prepare-review",
            message="ok",
            data={"review": {"reports": {"function_dossier_md": "reports/function_dossier.md"}}},
        )

        payload = result.to_dict()

        self.assertEqual(
            {"function_dossier_md": "reports/function_dossier.md"},
            payload["reports"],
        )


if __name__ == "__main__":
    unittest.main()
