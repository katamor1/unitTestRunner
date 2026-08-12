import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.build_models import BuildProbeReport, BuildWorkspaceReport
from unit_test_runner.cli import exit_codes
from unit_test_runner.cli.commands import _build_probe_result
from unit_test_runner.cli.errors import CLIError
from unit_test_runner.cli.main import main
from unit_test_runner.cli.outcomes import DomainOutcome
from unit_test_runner.cli.result import CLIResult
from unit_test_runner.contracts import RunOutcome
from unit_test_runner.vc6 import ProjectContextSelectionError


PUBLIC_COMMANDS = (
    "doctor",
    "discover-projects",
    "map-source",
    "list-functions",
    "analyze-function",
    "finalize-dossier",
    "review-set",
    "get-test-input-form",
    "apply-test-input-form",
    "build-probe",
    "run-tests",
    "reanalyze-function",
    "apply-reanalysis",
    "suite-register",
    "suite-update",
    "suite-remove",
    "suite-list",
    "suite-run",
)
ENVELOPE_KEYS = {"command", "outcome", "message", "artifacts", "diagnostics"}


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


class CliEntryPointContractTests(unittest.TestCase):
    def assert_envelope(self, payload, *, command, outcome):
        self.assertEqual(ENVELOPE_KEYS, set(payload))
        self.assertEqual(command, payload["command"])
        self.assertEqual(outcome, payload["outcome"])

    def test_contract_serialization_failure_returns_a_valid_internal_error_envelope(self):
        invalid_result = CLIResult(
            status="failed",
            exit_code=0,
            command="run-tests",
            message="Inconsistent result.",
            outcome=DomainOutcome("test_run", RunOutcome.FAILED, False),
        )
        stdout = io.StringIO()

        with mock.patch("unit_test_runner.cli.main.dispatch", return_value=invalid_result), redirect_stdout(stdout):
            exit_code = main(["--json", "doctor"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_codes.EXIT_INTERNAL_ERROR, exit_code)
        self.assert_envelope(payload, command="run-tests", outcome="error")
        self.assertEqual("contract_error", payload["diagnostics"][0]["code"])

    def test_global_help_version_and_all_public_subcommand_help_exit_zero(self):
        for command in (("--help",), ("--version",), *((name, "--help") for name in PUBLIC_COMMANDS)):
            with self.subTest(command=command):
                completed = run_module(*command)
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertTrue(completed.stdout)

    def test_build_probe_rejects_obsolete_host_toolchain_alias(self):
        completed = run_module(
            "--json",
            "build-probe",
            "--workspace",
            str(FIXTURE_ROOT),
            "--toolchain",
            "host",
        )

        self.assertEqual(exit_codes.EXIT_INPUT_ERROR, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assert_envelope(payload, command="build-probe", outcome="error")
        self.assertIn("invalid choice", payload["diagnostics"][0]["message"])

    def test_doctor_supports_human_and_exact_json_envelope_modes(self):
        human = run_module("doctor")
        self.assertEqual(0, human.returncode, human.stderr)
        self.assertIn("Command: doctor", human.stdout)
        self.assertIn("Outcome: passed", human.stdout)

        machine = run_module("--json", "doctor")
        self.assertEqual(0, machine.returncode, machine.stderr)
        self.assertEqual("", machine.stderr)
        self.assert_envelope(json.loads(machine.stdout), command="doctor", outcome="passed")

    def test_missing_required_argument_in_json_mode_writes_error_envelope_only(self):
        completed = run_module("--json", "analyze-function")

        self.assertEqual(exit_codes.EXIT_INPUT_ERROR, completed.returncode)
        self.assertEqual("", completed.stderr)
        payload = json.loads(completed.stdout)
        self.assert_envelope(payload, command="analyze-function", outcome="error")
        self.assertIn("required", payload["diagnostics"][0]["message"])

    def test_missing_dsw_is_a_nonzero_machine_parseable_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = run_module(
                "--json", "analyze-function",
                "--workspace", str(FIXTURE_ROOT),
                "--dsw", str(FIXTURE_ROOT / "missing.dsw"),
                "--source", "src/control.c",
                "--function", "Control_Update",
                "--configuration", "Win32 Debug",
                "--out", str(Path(temp_dir) / "missing"),
            )

        self.assertNotEqual(0, completed.returncode)
        self.assert_envelope(json.loads(completed.stdout), command="analyze-function", outcome="error")

    def test_analyze_function_accepts_in_workspace_absolute_source_and_writes_canonical_artifacts(self):
        source = FIXTURE_ROOT / "src" / "control.c"
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "absolute-source"
            completed = run_module(
                "--json", "analyze-function",
                "--workspace", str(FIXTURE_ROOT),
                "--dsw", str(FIXTURE_ROOT / "Product.dsw"),
                "--source", str(source),
                "--function", "Control_Update",
                "--configuration", "Win32 Debug",
                "--project", "Control",
                "--out", str(out_dir),
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assert_envelope(payload, command="analyze-function", outcome="passed")
            self.assertEqual(
                {"function_dossier", "test_spec"},
                {item["kind"] for item in payload["artifacts"]},
            )
            dossier = json.loads((out_dir / "reports" / "function_dossier.json").read_text(encoding="utf-8"))
            self.assertEqual("src/control.c", dossier["subject"]["source_path"])
            self.assertTrue((out_dir / "extracted" / "src" / "control.c").is_file())
        self.assertEqual(before, source.read_bytes())

    def test_analyze_default_stops_before_harness_and_harness_phase_generates_scaffold(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            design_dir = Path(temp_dir) / "design"
            harness_dir = Path(temp_dir) / "harness"
            common = (
                "--workspace", str(FIXTURE_ROOT),
                "--dsw", str(FIXTURE_ROOT / "Product.dsw"),
                "--source", "src/control.c",
                "--function", "Control_Update",
                "--configuration", "Win32 Debug",
                "--project", "Control",
            )
            design = run_module("--json", "analyze-function", *common, "--out", str(design_dir))
            harness = run_module(
                "--json", "analyze-function", *common,
                "--phase", "harness", "--out", str(harness_dir),
            )

            self.assertEqual(0, design.returncode, design.stderr)
            self.assertEqual(0, harness.returncode, harness.stderr)
            self.assertFalse((design_dir / "reports" / "harness_skeleton_report.json").exists())
            self.assertTrue((harness_dir / "reports" / "harness_skeleton_report.json").is_file())
            self.assertFalse((harness_dir / "reports" / "build_probe_report.json").exists())
            self.assertFalse((harness_dir / "runs").exists())

    def test_analyze_rejects_absolute_source_outside_workspace_without_writing_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            outside_source = Path(temp_dir) / "outside.c"
            outside_source.write_text("int Control_Update(void) { return 0; }\n", encoding="utf-8")
            output = Path(temp_dir) / "outside-output"
            completed = run_module(
                "--json", "analyze-function",
                "--workspace", str(FIXTURE_ROOT),
                "--dsw", str(FIXTURE_ROOT / "Product.dsw"),
                "--source", str(outside_source),
                "--function", "Control_Update",
                "--configuration", "Win32 Debug",
                "--project", "Control",
                "--out", str(output),
            )

            self.assertNotEqual(0, completed.returncode)
            self.assert_envelope(json.loads(completed.stdout), command="analyze-function", outcome="error")
            self.assertFalse(output.exists())

    def test_analyze_rejects_source_contained_output_as_input_error_without_writing_output(self):
        output = FIXTURE_ROOT / "unit-test-runner-output-boundary-test"
        self.addCleanup(lambda: output.exists() and shutil.rmtree(output))
        completed = run_module(
            "--json", "analyze-function",
            "--workspace", str(FIXTURE_ROOT),
            "--dsw", str(FIXTURE_ROOT / "Product.dsw"),
            "--source", "src/control.c",
            "--function", "Control_Update",
            "--configuration", "Win32 Debug",
            "--project", "Control",
            "--out", str(output),
        )

        self.assertEqual(exit_codes.EXIT_INPUT_ERROR, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assert_envelope(payload, command="analyze-function", outcome="error")
        self.assertIn("outside the source root", payload["diagnostics"][0]["message"])
        self.assertFalse(output.exists())

    def test_build_probe_failure_result_uses_failed_outcome_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            workspace_report = BuildWorkspaceReport(
                source_path=workspace / "source.c", function_name="Target",
                status="generated", output_root=workspace, copied_files=[],
                referenced_files=[], generated_build_files=[], compile_units=[],
                link_units=[], include_dirs=[], defines=[], compiler_options=[],
                build_commands=[], diagnostics=[],
            )
            probe_report = BuildProbeReport(
                source_path=workspace / "source.c", function_name="Target",
                status="failed", executed=True, exit_code=2, commands=[],
                diagnostics=[], missing_includes=[], unresolved_symbols=[],
                pch_issues=[], vc6_compatibility_issues=[], log_files=[],
            )
            result = _build_probe_result("build-probe", workspace, workspace_report, probe_report)

        self.assertEqual(exit_codes.EXIT_BUILD_PROBE_FAILED, result.exit_code)
        self.assertEqual(RunOutcome.FAILED, result.outcome.state)

    def test_build_probe_blocked_result_uses_blocked_outcome_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            workspace_report = BuildWorkspaceReport(
                source_path=workspace / "source.c", function_name="Target",
                status="generated", output_root=workspace, copied_files=[],
                referenced_files=[], generated_build_files=[], compile_units=[],
                link_units=[], include_dirs=[], defines=[], compiler_options=[],
                build_commands=[], diagnostics=[],
            )
            probe_report = BuildProbeReport(
                source_path=workspace / "source.c", function_name="Target",
                status="blocked", executed=False, exit_code=None, commands=[],
                diagnostics=[], missing_includes=[], unresolved_symbols=[],
                pch_issues=[], vc6_compatibility_issues=[], log_files=[],
            )
            result = _build_probe_result("build-probe", workspace, workspace_report, probe_report)

        self.assertEqual(exit_codes.EXIT_TESTS_BLOCKED, result.exit_code)
        self.assertEqual(RunOutcome.BLOCKED, result.outcome.state)

    def test_map_source_blocks_without_writing_output_for_missing_or_ambiguous_membership(self):
        cases = (
            (REPO_ROOT / "tests" / "fixtures" / "vc6_dsw" / "dependencies" / "Product.dsw", "src/control.c", ("Control", "Common")),
            (FIXTURE_ROOT / "Product.dsw", "src/control.c", ("Control", "FactoryTest")),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            for index, (dsw, source, candidates) in enumerate(cases):
                with self.subTest(dsw=dsw):
                    output = Path(temp_dir) / f"mapping-{index}.json"
                    completed = run_module(
                        "--json", "map-source", "--dsw", str(dsw),
                        "--source", source, "--out", str(output),
                    )

                    self.assertEqual(exit_codes.EXIT_TESTS_BLOCKED, completed.returncode)
                    payload = json.loads(completed.stdout)
                    self.assert_envelope(payload, command="map-source", outcome="blocked")
                    messages = "\n".join(item["message"] for item in payload["diagnostics"])
                    for candidate in candidates:
                        self.assertIn(candidate, messages)
                    self.assertFalse(output.exists())

    def test_analyze_function_selection_error_is_blocked_with_candidates(self):
        selection_error = ProjectContextSelectionError(
            "Multiple unique project/configuration/source selections.",
            [{"project_name": "Control"}, {"project_name": "Common"}],
        )
        stdout = io.StringIO()
        with (
            mock.patch(
                "unit_test_runner.cli.commands.analyze_function_workflow",
                side_effect=selection_error,
            ),
            redirect_stdout(stdout),
        ):
            exit_code = main([
                "--json", "analyze-function",
                "--workspace", str(FIXTURE_ROOT),
                "--dsw", str(FIXTURE_ROOT / "Product.dsw"),
                "--source", "src/control.c",
                "--function", "Control_Update",
                "--configuration", "Win32 Debug",
                "--out", str(FIXTURE_ROOT / "candidate-output"),
            ])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_codes.EXIT_TESTS_BLOCKED, exit_code)
        self.assert_envelope(payload, command="analyze-function", outcome="blocked")
        self.assertIn("Control", payload["diagnostics"][0]["message"])
        self.assertIn("Common", payload["diagnostics"][0]["message"])

    def test_blocked_cli_error_serializes_a_blocked_envelope(self):
        stdout = io.StringIO()
        error = CLIError(
            "Formal review approval is required.",
            exit_codes.EXIT_TESTS_BLOCKED,
            "analyze-function",
            "review_required",
        )

        with mock.patch("unit_test_runner.cli.main.dispatch", side_effect=error), redirect_stdout(stdout):
            exit_code = main(["--json", "doctor"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_codes.EXIT_TESTS_BLOCKED, exit_code)
        self.assert_envelope(payload, command="analyze-function", outcome="blocked")
        self.assertEqual("review_required", payload["diagnostics"][0]["code"])

    def test_internal_data_is_not_promoted_into_the_public_envelope(self):
        result = CLIResult(
            status="ok", exit_code=0, command="doctor", message="ok",
            outcome=DomainOutcome("command", RunOutcome.PASSED, None),
        )

        payload = result.to_dict()

        self.assertEqual(ENVELOPE_KEYS, set(payload))
        self.assertNotIn("data", payload)


if __name__ == "__main__":
    unittest.main()
