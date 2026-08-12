import copy
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

from tests.spec_support import generate_public_build_workspace as generate_build_workspace
from unit_test_runner.build import verification_toolchain as verification_module
from unit_test_runner.build.verification_toolchain import VerificationBuildResult
from unit_test_runner.cli.main import _apply_build_probe_environment
from unit_test_runner.cli.parser import build_parser
from unit_test_runner.dossier import analyze_function_workflow


class VerificationBuildToolchainTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows batch setup behavior")
    def test_environment_setup_batch_with_spaces_applies_to_verification_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            setup_dir = root / "Visual Studio Tools"
            setup_dir.mkdir()
            setup = setup_dir / "vcvars.bat"
            setup.write_text(
                "@echo off\nset UTR_VERIFICATION_ENV=ready\n",
                encoding="ascii",
            )

            exit_code, output = verification_module._run_command(
                [
                    sys.executable,
                    "-c",
                    (
                        "import os,sys; "
                        "sys.exit(0 if os.environ.get('UTR_VERIFICATION_ENV') "
                        "== 'ready' else 9)"
                    ),
                ],
                cwd=root,
                timeout_seconds=30,
                env_setup=setup,
            )

        self.assertEqual(0, exit_code, output)

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
            phase="harness",
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
            reviewed_harness = copy.deepcopy(reports["harness_report"])
            reviewed_harness["unresolved_placeholders"] = []
            for test in reviewed_harness.get("test_skeletons", []):
                test["review_required"] = False

            with mock.patch("unit_test_runner.build.build_workspace_generator.run_verification_build", return_value=verification_result) as run_verification:
                workspace_report, probe = generate_build_workspace(
                    reports["build_context"],
                    reports["source_digest"],
                    reviewed_harness,
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
