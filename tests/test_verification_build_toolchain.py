import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.build.build_workspace_generator import generate_build_workspace
from unit_test_runner.build.verification_toolchain import VerificationBuildResult
from unit_test_runner.cli.main import _apply_build_probe_environment
from unit_test_runner.cli.parser import build_parser
from unit_test_runner.dossier import analyze_function_workflow


class VerificationBuildToolchainTests(unittest.TestCase):
    def prepare_analysis(self, temp_dir):
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
        reports = out_dir / "reports"
        return out_dir, {
            "build_context": json.loads((reports / "build_context.json").read_text(encoding="utf-8")),
            "source_digest": json.loads((reports / "source_digest.json").read_text(encoding="utf-8")),
            "harness_report": json.loads((reports / "harness_skeleton_report.json").read_text(encoding="utf-8")),
        }

    def test_cli_build_probe_toolchain_sets_verification_environment(self):
        args = build_parser().parse_args(
            [
                "build-probe",
                "--workspace",
                "workspace",
                "--run",
                "--toolchain",
                "verification",
                "--cc",
                "gcc",
            ]
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            _apply_build_probe_environment(args)
            self.assertEqual("verification", os.environ["UNIT_TEST_RUNNER_BUILD_TOOLCHAIN"])
            self.assertEqual("gcc", os.environ["UNIT_TEST_RUNNER_CC"])

    def test_generator_can_report_successful_verification_toolchain_build(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir, reports = self.prepare_analysis(temp_dir)
            verification_result = VerificationBuildResult(
                executed=True,
                exit_code=0,
                command_line="gcc -o bin/utr_probe.exe",
                log_text="VERIFICATION BUILD\nBuild succeeded\n",
                diagnostics=[],
                compiler="gcc",
            )

            with mock.patch("unit_test_runner.build.build_workspace_generator.run_verification_build", return_value=verification_result) as run_verification:
                workspace_report, probe = generate_build_workspace(
                    reports["build_context"],
                    reports["source_digest"],
                    reports["harness_report"],
                    out_dir,
                    run_probe=True,
                    dry_run=False,
                    toolchain="verification",
                    cc="gcc",
                )

            self.assertEqual("verification_toolchain", workspace_report.build_commands[0].command_kind)
            self.assertEqual("succeeded", probe.status)
            self.assertTrue(probe.executed)
            self.assertEqual("verification_toolchain", probe.commands[0].command_kind)
            self.assertEqual("gcc -o bin/utr_probe.exe", probe.commands[0].command_line)
            self.assertTrue((out_dir / "build" / "verification_build.txt").exists())
            run_verification.assert_called_once()


if __name__ == "__main__":
    unittest.main()
